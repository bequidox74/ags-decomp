import enum
import itertools
from dataclasses import dataclass
from typing import NamedTuple, TypeAlias

from binary_reader import BinaryReader
from string_writer import StringWriter
from utils import format_bindata, quote, sjoin

Primitive: TypeAlias = int | str | float


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


class FixupType(enum.IntEnum):
    NO_FIXUP = 0
    GLOBAL_DATA = 1
    FUNCTION = 2
    STRING = 3
    IMPORT = 4
    DATA_DATA = 5
    STACK = 6


class Export(NamedTuple):
    name: str
    address: int


class Section(NamedTuple):
    name: str
    offset: int


class Parameter:
    pass


class Register(Parameter, enum.Enum):
    SP = 1
    MAR = 2
    AX = 3
    BX = 4
    CX = 5
    OP = 6
    DX = 7

    def __str__(self) -> str:
        return self.name.lower()


@dataclass
class FixedUpValue(Parameter):
    original: int
    fixed: Primitive | None = None
    type_: FixupType = FixupType.NO_FIXUP

    def __str__(self) -> str:
        match self.type_:
            case FixupType.STRING:
                return quote(str(self.fixed))
            case FixupType.IMPORT:
                return str(self.fixed)
            case FixupType.GLOBAL_DATA:
                return f"local@{self.original}"
            case _:
                return str(self.original)


@dataclass
class Label(Parameter):
    from_: int
    to: int
    func_name: str
    count: int = 0

    def as_param(self) -> str:
        return f"L{self.to}_{self.func_name}"

    def as_label(self) -> str:
        return f"L{self.to}_{self.func_name}: ; {self.count} references"

    def __str__(self) -> str:
        return self.as_param()


class Instruction(NamedTuple):
    opcode: Opcode
    params: list[Parameter]

    def get_reg(self, idx: int) -> Register:
        reg = self.params[idx]
        assert isinstance(reg, Register)
        return reg

    def get_int(self, idx: int) -> int:
        val = self.params[idx]
        assert isinstance(val, FixedUpValue)
        assert val.type_ == FixupType.NO_FIXUP
        return val.original

    def get_fup(self, idx: int, type_: FixupType | None = None) -> FixedUpValue:
        fup = self.params[idx]
        assert isinstance(fup, FixedUpValue)
        if type_ is not None:
            assert fup.type_ == type_
        return fup


class Function(NamedTuple):
    name: str
    nargs: int
    offset: int
    items: list[Instruction | Label]


class Disassembly:
    def __init__(self, source) -> None:
        self.source = source
        self.functions: list[Function] = []
        self.gdata: bytes = b""
        self.gdata_offset = 0
        self.scom_version: int = 90
        self.code: list[int] = []
        self.jumps: dict[int, Label] = {}  # dict[dst, label]

        self._pc = 0

        self._read_scom()
        self._disassemble()

    def format(self, sw: StringWriter | None = None) -> str:
        if sw is None:
            sw = StringWriter()

        sw.println(f"; AGS SCOM version {self.scom_version}")

        # printing bytes isn't very elegant, but it's the only way to be sure
        # it's correct, at least until a proper analyzer is implemented.
        if self.gdata:
            sw.cr()
            sw.println(f".data[{len(self.gdata)}]")
            sw.indent()
            for line in format_bindata(self.gdata):
                sw.println(line)
            sw.dedent()
            sw.println()

        if self.functions:
            sw.cr()
            sw.println(f".code[{self.code_size}]")
            for func in self.functions:
                sw.println(f"{func.name}${func.nargs}: ; @{func.offset}")
                sw.indent()
                sw.indent()
                for item in func.items:
                    if isinstance(item, Label):
                        old_level = sw.level
                        sw.cr()
                        sw.println(item.as_label())
                        sw.level = old_level
                    elif isinstance(item, Instruction):
                        is_linenum = item.opcode == Opcode.LINENUM
                        out = item.opcode.mnemonic
                        if is_linenum:
                            sw.dedent()
                        if item.params:
                            out += f" {sjoin(', ', item.params)}"
                        sw.println(out)
                        if is_linenum:
                            sw.indent()
                sw.dedent()
                sw.dedent()
                sw.println()

        if self.strings:
            sw.cr()
            sw.println(f".strings[{self.strings_size}] ; {len(self.strings)} strings")
            for i, s in self._indexed_strings.items():
                sw.println(f"{i}: {quote(s)}")
            sw.println()

        if self.imports:
            sw.cr()
            comment = f" ; {self.imports_size} names, {len(self.imports)} referenced"
            sw.println(f".imports[{self.imports_size}]{comment}")
            for offset, name in self.imports.items():
                sw.println(f"{offset}: {name}")
            sw.println()

        if self.exports:
            sw.cr()
            sw.println(f".exports[{self.exports_size}]")
            for offset, export in self.exports.items():
                comment = " ; function" if "$" in export.name else " ; variable"
                sw.println(f"{offset}: {export.name}{comment}")
            sw.println()

        if self.fixups:
            sw.cr()
            sw.println(f".fixups[{len(self.fixups)}]")
            for idx, type_ in self.fixups.items():
                sw.println(f"{idx}: {type_.name.lower()}")
            sw.println()

        if self.sections:
            sw.cr()
            sw.println(f".sections[{self.sections_size}]")
            for s in self.sections:
                sw.println(f"{s.offset}: {s.name}")

        return str(sw)

    def __str__(self) -> str:
        return self.format()

    def _read_scom(self) -> None:
        br = BinaryReader(self.source)

        assert br.read_fixed_string(4) == "SCOM", "Source is not a compiled AGS script"
        self.scom_version = br.u32()
        assert self.scom_version == 90, "Unsupported SCOM version"

        self.gdata_size = br.u32()
        self.code_size = br.u32()
        self.strings_size = br.u32()

        if self.gdata_size > 0:
            self.gdata_offset = br.tell()
            self.gdata = br.read_bytes(self.gdata_size)

        for _ in range(self.code_size):
            self.code.append(br.i32())

        self._indexed_strings: dict[int, str] = {}
        strings_start = br.tell()
        while br.tell() < strings_start + self.strings_size:
            # remember string offsets for later fixups
            offset = br.tell() - strings_start
            self._indexed_strings[offset] = br.cstr()
        self.strings = list(self._indexed_strings.values())

        fixups_size = br.u32()
        self.fixups: dict[int, FixupType] = {}
        types = []
        offsets = []
        for _ in range(fixups_size):
            types.append(br.u8())
        for _ in range(fixups_size):
            offsets.append(br.u32())
        for i in range(fixups_size):
            self.fixups[offsets[i]] = FixupType(types[i])

        self.imports_size = br.u32()
        self.imports: dict[int, str] = {}
        for i in range(self.imports_size):
            import_ = br.cstr()
            if import_:  # skip empty imports
                self.imports[i] = import_

        self.exports_size = br.u32()
        self.exports: dict[int, Export] = {}
        for _ in range(self.exports_size):
            export = br.cstr()
            address = br.u32() & 0x00FFFFFF
            self.exports[br.tell()] = Export(export, address)

        # read in the sections just in case
        self.sections_size = br.u32()
        self.sections: list[Section] = []
        for _ in range(self.sections_size):
            name = br.cstr()
            offset = br.u32()
            self.sections.append(Section(name, offset))

        assert br.u32() == 0xBEEFCAFE, "Invalid SCOM end signature"

    def _disassemble(self):
        # exports can contain *both* functions and variables.
        # read exports table to find out where the functions begin and end
        self.func_names: dict[int, str] = {}
        entries: list[int] = []
        for e in self.exports.values():
            if "$" not in e.name:
                # functions always have $ in the name, so we skip variables
                continue
            self.func_names[e.address] = e.name
            entries.append(e.address)
        entries.sort()
        entries.append(len(self.code))
        ranges: list[tuple[int, int]] = list(itertools.pairwise(entries))  # make pairs

        for s, e in ranges:
            func = self._dis_function(s, e)
            self.functions.append(func)

    def _dis_function(self, start: int, end: int) -> Function:
        mangled_name = self.func_names[start]
        parts = mangled_name.split("$")
        name = parts[0]
        nargs = int(parts[1])
        instructions: list[Instruction] = []

        self._pc = start
        while self._pc < end:
            opcode = Opcode(self.code[self._pc])
            instr = self._process_opcode(self._pc, opcode, name)
            instructions.append(instr)
            self._pc += 1 + opcode.nargs

        items = self._insert_labels(instructions)
        return Function(name, nargs, start, items)

    def _insert_labels(
        self, instructions: list[Instruction]
    ) -> list[Instruction | Label]:
        items: list[Instruction | Label] = []
        pc = 0
        for ins in instructions:
            if pc in self.jumps:
                items.append(self.jumps[pc])
            items.append(ins)
            pc += 1 + len(ins.params)
        return items

    def _process_opcode(
        self, offset: int, opcode: Opcode, func_name: str
    ) -> Instruction:
        match opcode:
            case Opcode.JMP | Opcode.JZ | Opcode.JNZ:
                from_ = offset
                to = offset + 2 + self.code[offset + 1]  # + 2 to skip our args
                label = Label(from_, to, func_name)
                self.jumps[to] = label
                return Instruction(opcode, [label])
            case _:
                pass

        params: list[Parameter] = []
        for i, f in enumerate(opcode.args_format):
            idx = offset + i + 1
            arg = self.code[idx]
            match f:
                case "r":  # register
                    params.append(Register(arg))
                case "a":  # argument, possible fixup
                    # is there a fixup for this index?
                    if idx in self.fixups:
                        type_ = self.fixups[idx]
                        match self.fixups[idx]:
                            case FixupType.STRING:
                                params.append(
                                    FixedUpValue(
                                        arg,
                                        self._indexed_strings[arg],
                                        type_,
                                    )
                                )
                            case FixupType.IMPORT:
                                params.append(
                                    FixedUpValue(
                                        arg,
                                        self.imports[arg],
                                        type_,
                                    )
                                )
                            case _:
                                params.append(
                                    FixedUpValue(
                                        arg,
                                        None,
                                        type_,
                                    )
                                )
                    else:
                        params.append(
                            FixedUpValue(
                                arg,
                                None,
                                FixupType.NO_FIXUP,
                            )
                        )

        return Instruction(opcode, params)
