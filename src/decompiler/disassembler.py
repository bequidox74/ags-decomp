from __future__ import annotations

import enum
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import NamedTuple, Self
from warnings import warn

from binary_reader import BinaryReader
from string_writer import StringWriter
from utils import format_bindata, quote, verify

type Parameter = Fixup | Label | Register
type Offset = int


# see https://github.com/adventuregamestudio/ags/blob/master/Engine/script/cc_instance.cpp
@enum.unique
class Opcode(enum.Enum):
    NOP = (0, "NULL", "")
    ADD = (1, "addi", "ra")
    SUB = (2, "subi", "ra")
    REGTOREG = (3, "mov", "rr")
    WRITELIT = (4, "memwritelit", "aa")
    RET = (5, "ret", "")
    LITTOREG = (6, "movl", "ra")
    MEMREAD = (7, "memread4", "r")
    MEMWRITE = (8, "memwrite4", "r")
    MULREG = (9, "mul", "rr")
    DIVREG = (10, "div", "rr")
    ADDREG = (11, "add", "rr")
    SUBREG = (12, "sub", "rr")
    BITAND = (13, "and", "rr")
    BITOR = (14, "or", "rr")
    ISEQUAL = (15, "cmpeq", "rr")
    NOTEQUAL = (16, "cmpne", "rr")
    GREATER = (17, "gt", "rr")
    LESSTHAN = (18, "lt", "rr")
    GTE = (19, "gte", "rr")
    LTE = (20, "lte", "rr")
    AND = (21, "land", "rr")
    OR = (22, "lor", "rr")
    CALL = (23, "call", "r")
    MEMREADB = (24, "memread1", "r")
    MEMREADW = (25, "memread2", "r")
    MEMWRITEB = (26, "memwrite1", "r")
    MEMWRITEW = (27, "memwrite2", "r")
    JZ = (28, "jzi", "a")
    PUSHREG = (29, "push", "r")
    POPREG = (30, "pop", "r")
    JMP = (31, "jmpi", "a")
    MUL = (32, "muli", "ra")
    CALLEXT = (33, "farcall", "r")
    PUSHREAL = (34, "farpush", "r")
    SUBREALSTACK = (35, "farsubsp", "a")
    LINENUM = (36, "sourceline", "a")
    CALLAS = (37, "callscr", "r")
    THISBASE = (38, "thisaddr", "a")
    NUMFUNCARGS = (39, "setfuncargs", "a")
    MODREG = (40, "mod", "rr")
    XORREG = (41, "xor", "rr")
    NOTREG = (42, "not", "r")
    SHIFTLEFT = (43, "shl", "rr")
    SHIFTRIGHT = (44, "shr", "rr")
    CALLOBJ = (45, "callobj", "r")
    CHECKBOUNDS = (46, "checkbounds", "ra")
    MEMWRITEPTR = (47, "memwrite.ptr", "r")
    MEMREADPTR = (48, "memread.ptr", "r")
    MEMZEROPTR = (49, "memwrite.ptr.0", "")
    MEMINITPTR = (50, "meminit.ptr", "r")
    LOADSPOFFS = (51, "load.sp.offs", "a")
    CHECKNULL = (52, "checknull.ptr", "")
    FADD = (53, "faddi", "rr")
    FSUB = (54, "fsubi", "rr")
    FMULREG = (55, "fmul", "rr")
    FDIVREG = (56, "fdiv", "rr")
    FADDREG = (57, "fadd", "rr")
    FSUBREG = (58, "fsub", "rr")
    FGREATER = (59, "fgt", "rr")
    FLESSTHAN = (60, "flt", "rr")
    FGTE = (61, "fgte", "rr")
    FLTE = (62, "flte", "rr")
    ZEROMEMORY = (63, "zeromem", "a")
    CREATESTRING = (64, "newstring", "r")
    STRINGSEQUAL = (65, "streq", "rr")
    STRINGSNOTEQ = (66, "strne", "rr")
    CHECKNULLREG = (67, "checknull", "r")
    LOOPCHECKOFF = (68, "loopcheckoff", "")
    MEMZEROPTRND = (69, "memwrite.ptr.0.nd", "")
    JNZ = (70, "jnzi", "a")
    DYNAMICBOUNDS = (71, "dynamicbounds", "r")
    NEWARRAY = (72, "newarray", "raa")
    NEWUSEROBJECT = (73, "newuserobject", "ra")

    def __init__(self, _, mnemonic: str, argfmt: str) -> None:
        self.mnemonic = mnemonic
        self.args_format = argfmt
        self.nargs = len(argfmt)

    def __new__(cls, value: int, *_):
        obj = object.__new__(cls)
        obj._value_ = value
        return obj


JUMPS = {
    Opcode.JMP,
    Opcode.JZ,
    Opcode.JNZ,
}


class ExportType(IntEnum):
    FUNCTION = (1, "function")
    DATA = (2, "data")

    repr: str

    def __new__(cls, value: int, repr_: str) -> Self:
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.repr = repr_
        return obj


class Export(NamedTuple):
    name: str
    address: Offset
    type: ExportType


class Register(Enum):
    SP = 1
    MAR = 2
    AX = 3
    BX = 4
    CX = 5
    OP = 6
    DX = 7

    def __str__(self) -> str:
        return self.name.lower()


class FixupType(IntEnum):
    NO_FIXUP = 0
    GLOBAL_DATA = 1
    FUNCTION = 2
    STRING = 3
    IMPORT = 4
    DATA_DATA = 5
    STACK = 6


@dataclass
class Fixup:
    original: int
    fixed: int | str
    type: FixupType

    def __str__(self) -> str:
        match self.type:
            case FixupType.STRING:
                return quote(str(self.fixed))
            case FixupType.IMPORT:
                return str(self.fixed)
            case FixupType.GLOBAL_DATA:
                return f"gdata@0x{self.original:X}"
            case _:
                return str(self.original)


@dataclass(unsafe_hash=True)
class Label:
    from_: int
    to: int
    func_name: str
    count: int = 0

    def __str__(self) -> str:
        return f"L{self.to}_{self.func_name}"


@dataclass
class Instruction:
    opcode: Opcode
    params: list[Parameter]
    code_offset: Offset
    func_offset: Offset

    def get_reg(self, idx: int = 0) -> Register:
        reg = self.params[idx]
        assert isinstance(reg, Register)
        return reg

    def get_int(self, idx: int = 0) -> int:
        val = self.params[idx]
        assert isinstance(val, Fixup)
        assert val.type == FixupType.NO_FIXUP
        return val.original

    def get_fixup(self, idx: int = 0, type_: FixupType | None = None) -> Fixup:
        fup = self.params[idx]
        assert isinstance(fup, Fixup)
        if type_ is not None:
            assert fup.type == type_
        return fup

    def get_label(self, idx: int = 0) -> Label:
        label = self.params[idx]
        assert isinstance(label, Label)
        return label

    def __post_init__(self) -> None:
        assert len(self.params) <= 3

    def __hash__(self) -> int:
        return hash(self.code_offset)

    def __str__(self) -> str:
        mnemonic = self.opcode.mnemonic
        fmt_params = ", ".join(map(str, self.params))
        result = [mnemonic]
        if fmt_params:
            result.append(fmt_params)
        return " ".join(result)

    def __repr__(self) -> str:
        return f"<Instruction '{self}'>"


@dataclass
class Function:
    mangled_name: str
    name: str
    nargs: int
    code_offset: int
    script_offset: int
    size: int

    instructions: dict[Offset, Instruction]
    """Dict of `code offset` -> `Instruction`"""

    instr_list: list[Instruction] = field(init=False)

    def __post_init__(self) -> None:
        self.instr_list = list(self.instructions.values())
        self.instr_list.sort(key=lambda i: i.func_offset)


class Disassembly:
    def __init__(self, source) -> None:
        self.source = source

        self.version: int
        self.len_gdata: int
        self.num_codes: int
        self.len_strings: int

        self.data_offset: int
        self.code_offset: int
        self.strings_offset: int
        self.fixups_offset: int
        self.imports_offset: int
        self.exports_offset: int
        self.sections_offset: int

        self.data: bytes = b""
        self.code: list[int] = []
        self.strings: dict[Offset, str] = {}
        self.fixups: dict[Offset, FixupType] = {}
        self.imports: list[str] = []
        self.exports: dict[Offset, Export] = {}
        self.sections: dict[Offset, str] = {}

        self.functions: dict[Offset, Function] = {}
        """Dict of `code offset` -> `Function`"""
        self.jumps: defaultdict[Offset, set[Label]] = defaultdict(set)
        self._func_ranges: list[range]

        with BinaryReader(source) as br:
            self._read_scom(br)
        self._disassemble()

    def script_to_code_offset(self, script: Offset) -> Offset:
        return (script - self.code_offset) // 4

    def code_to_script_offset(self, code: Offset) -> Offset:
        return self.code_offset + code * 4

    def code_offset_to_func(self, code: Offset) -> Function | None:
        range_ = next((r for r in self._func_ranges if code in r), None)
        if range_ is None:
            return None
        return self.functions[range_.start]

    def __str__(self) -> str:
        return self.format()

    @property
    def num_fixups(self) -> int:
        return len(self.fixups)

    @property
    def num_imports(self) -> int:
        return len(self.imports)

    @property
    def num_exports(self) -> int:
        return len(self.exports)

    @property
    def num_sections(self) -> int:
        return len(self.sections)

    def _read_scom(self, br: BinaryReader) -> None:
        verify(br.read_fixed_string(4) == "SCOM", "Source is not a compiled AGS script")
        self.version = br.u32()
        if self.version != 90:
            warn(f"Unsupported SCOM version: {self.version}")

        self.len_gdata = br.u32()
        self.num_codes = br.u32()
        self.len_strings = br.u32()

        if self.len_gdata > 0:
            self.data_offset = br.tell()
            self.data = br.read_bytes(self.len_gdata)

        self.code_offset = br.tell()
        for _ in range(self.num_codes):
            self.code.append(br.i32())

        self.strings_offset = br.tell()
        while br.tell() < self.strings_offset + self.len_strings:
            # remember string offsets for later fixups
            offset = br.tell() - self.strings_offset
            self.strings[offset] = br.cstr()

        self.fixups_offset = br.tell()
        num_fixups = br.u32()
        types = []
        offsets = []
        for _ in range(num_fixups):
            types.append(br.u8())
        for _ in range(num_fixups):
            offsets.append(br.u32())
        for i in range(num_fixups):
            self.fixups[offsets[i]] = FixupType(types[i])

        self.imports_offset = br.tell()
        num_imports = br.u32()
        for _ in range(num_imports):
            import_ = br.cstr()
            self.imports.append(import_)

        self.exports_offset = br.tell()
        num_exports = br.u32()
        for _ in range(num_exports):
            export = br.cstr()
            raw = br.u32()
            address = raw & 0x00FFFFFF
            type_ = (raw >> 24) & 0xFF
            self.exports[br.tell()] = Export(export, address, ExportType(type_))  # pylint: disable=no-value-for-parameter

        self.sections_offset = br.tell()
        num_sections = br.u32()
        self.sections = {}
        for _ in range(num_sections):
            name = br.cstr()
            offset = br.u32()
            self.sections[offset] = name

        verify(br.u32() == 0xBEEFCAFE, "Invalid SCOM end signature")

    def _disassemble(self) -> None:
        # exports can contain *both* functions and variables.
        # read exports table to find out where the functions begin and end.
        entries: list[Offset] = []
        self._func_names: dict[Offset, str] = {}
        for e in self.exports.values():
            if e.type is not ExportType.FUNCTION:
                continue
            entries.append(e.address)
            self._func_names[e.address] = e.name

        # build ranges (start, end) in ascending order.
        entries.sort()
        entries.append(len(self.code))
        self._func_ranges: list[range] = [
            range(entries[i], entries[i + 1]) for i in range(len(entries) - 1)
        ]

        for r in self._func_ranges:
            start = r.start
            end = r.stop
            func = self._dis_function(start, end, self._func_names[start])
            self.functions[start] = func

    def _dis_function(self, start: int, end: int, mangled_name: str) -> Function:
        parts = mangled_name.split("$")
        name = parts[0]
        nargs = int(parts[1])
        instructions: dict[Offset, Instruction] = {}
        script_offset = self.code_to_script_offset(start)

        pc = start
        while pc < end:
            opcode = Opcode(self.code[pc])
            instr = self._process_opcode(start, pc, opcode, mangled_name)
            instructions[pc] = instr
            pc += 1 + opcode.nargs

        return Function(
            mangled_name, name, nargs, start, script_offset, end - start, instructions
        )

    def _process_opcode(
        self, start: Offset, pc: Offset, opcode: Opcode, func_name: str
    ) -> Instruction:
        func_offset = pc - start
        match opcode:
            case Opcode.JMP | Opcode.JZ | Opcode.JNZ:
                from_ = pc
                to = pc + 2 + self.code[pc + 1]  # + 2 to skip our args
                labels = self.jumps[to]
                label = Label(from_, to, func_name)
                label.count += 1
                labels.add(label)
                inst = Instruction(opcode, [label], pc, func_offset)
                return inst
            case _:
                pass

        params: list[Parameter] = []
        for i, f in enumerate(opcode.args_format):
            arg_idx = pc + i + 1
            arg = self.code[arg_idx]
            match f:
                case "r":  # register
                    params.append(Register(arg))
                case "a":  # argument, possible fixup
                    # is there a fixup for this index?
                    if arg_idx in self.fixups:
                        type_ = self.fixups[arg_idx]
                        match self.fixups[arg_idx]:
                            case FixupType.STRING:
                                params.append(Fixup(arg, self.strings[arg], type_))
                            case FixupType.IMPORT:
                                params.append(Fixup(arg, self.imports[arg], type_))
                            case _:
                                params.append(Fixup(arg, arg, type_))
                    else:
                        params.append(Fixup(arg, arg, FixupType.NO_FIXUP))

        return Instruction(opcode, params, pc, func_offset)

    def format(self, sw: StringWriter | None = None, fixups: bool = False) -> str:
        if sw is None:
            sw = StringWriter()

        sw.println(f";AGS SCOM version {self.version}")

        # printing bytes isn't very elegant, but it's the only way to be sure
        # it's correct, at least until a proper analyzer is implemented.
        if self.data:
            sw.cr()
            sw.println(f".data[{len(self.data)}]")
            sw.indent()
            for line in format_bindata(self.data):
                sw.println(line)
            sw.dedent()
            sw.println()

        offset = 0
        if self.functions:
            sw.cr()
            sw.println(f".code[{self.num_codes}]")
            for func in self.functions.values():
                sw.print(func.mangled_name)
                sw.print(": ;")
                sw.print(f"code offset=0x{func.code_offset:X}, ")
                sw.print(f"script offset=0x{func.script_offset:X}")
                sw.println()

                sw.indent()
                sw.indent()
                for item in func.instructions.values():
                    if offset in self.jumps:
                        sw.dedent()
                        sw.println(f"L{offset}_{func.name}:")
                        sw.indent()

                    is_linenum = item.opcode == Opcode.LINENUM
                    if is_linenum:
                        sw.dedent()
                    sw.print(str(item))
                    if item.opcode in JUMPS:
                        l = item.get_label()
                        sw.print(f" ;{item.opcode.mnemonic} {l.to - l.from_}")
                    sw.println()
                    if is_linenum:
                        sw.indent()
                    offset += 1 + len(item.params)
                sw.dedent()
                sw.dedent()
                sw.println()

        if self.strings:
            sw.cr()
            sw.println(f".strings[{self.len_strings}] ;{len(self.strings)} strings")
            for i, (o, s) in enumerate(self.strings.items()):
                sw.println(f"{i}@0x{o:X}: {quote(s)}")
            sw.println()

        if self.imports:
            sw.cr()
            referenced = sum(bool(i) for i in self.imports)
            comment = f" ;{self.num_imports} names, {referenced} referenced"
            sw.println(f".imports[{self.num_imports}]{comment}")
            for o, name in enumerate(self.imports):
                if not name:
                    continue
                sw.println(f"{o}: {name}")
            sw.println()

        if self.exports:
            sw.cr()
            sw.println(f".exports[{self.num_exports}]")
            for export in self.exports.values():
                comment = f" ;{export.type.repr} "
                sw.println(f"{export.address}: ({export.type}) {export.name}{comment}")
            sw.println()

        if fixups and self.fixups:
            sw.cr()
            sw.println(f".fixups[{len(self.fixups)}]")
            for idx, type_ in self.fixups.items():
                sw.println(f"{idx}: {type_.name.lower()}")
            sw.println()

        if self.sections:
            sw.cr()
            sw.println(f".sections[{self.num_sections}]")
            for o, name in self.sections.items():
                sw.println(f"{o}: {name}")

        return str(sw)
