import enum
import warnings

from dataclasses import dataclass, field
from typing import NamedTuple

from binary_reader import BinaryReader
from string_writer import StringWriter
from utils import sjoin, quote, format_bindata


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


@dataclass
class FixedUpValue(Parameter):
    original: int
    type_: FixupType = FixupType.NO_FIXUP


class Instruction(NamedTuple):
    opcode: Opcode
    params: list[Parameter]

    def format(self) -> str:
        p: list = self.params.copy()
        opc = self.opcode
        assert opc.nargs == len(p), "Instruction parameter count mismatch"
        for i in range(len(p)):
            match opc.args_format[i]:
                case "r":
                    p[i] = Register(p[i]).name
                case "a":
                    pass  # leave as is (TODO: float heuristic?)
                case _:
                    raise RuntimeError(f"Illegal args format: {opc.args_format}")
        return f"{self.opcode.mnemonic} {sjoin(", ", p)}"

    def __str__(self) -> str:
        return self.format()


class Function(NamedTuple):
    name: str
    nargs: int
    offset: int
    instructions: list[Instruction]


@dataclass
class Disassembly:
    functions: list[Function]
    strings: list[str]
    gdata: bytes

    def format(self, sw: StringWriter | None = None, **kwargs) -> str:
        if sw is None:
            sw = StringWriter()

        if self.gdata:
            sw.cr()
            sw.println(".data")
            sw.indent()
            for line in format_bindata(self.gdata):
                sw.println(line)
            sw.dedent()
            sw.println()

        if self.functions:
            sw.cr()
            sw.println(".code")
            for func in self.functions:
                sw.println(f"{func.name}${func.nargs}: ; @0x{func.offset:X}")
                sw.indent()
                for ins in func.instructions:
                    out = ins.opcode.mnemonic
                    if ins.params:
                        out += f" {sjoin(", ", ins.params)}"
                    sw.println(out)
                sw.dedent()
                sw.println()

        if self.strings:
            sw.cr()
            sw.println(".strings")
            width = len(str(len(self.strings)))
            for i, s in enumerate(self.strings):
                idx = format(i, f"{width}")
                sw.println(f"{idx}:{quote(s)}")

        return str(sw)

    def __str__(self) -> str:
        return self.format()


class Disassembler:
    def disassemble(self, source) -> Disassembly:
        self.source = source
        self.ds = Disassembly([], [], b"")
        self._read_scom()
        self._disassemble()
        return self.ds

    def _read_scom(self) -> None:
        br = BinaryReader(self.source)

        assert br.read_fixed_string(4) == "SCOM", "Source is not a compiled AGS script"
        assert br.u32() == 90, "Unsupported SCOM version"

        self.gdata_size = br.u32()
        self.code_size = br.u32()
        self.strings_size = br.u32()

        if self.gdata_size > 0:
            self.ds.gdata = br.read_bytes(self.gdata_size)

        self.code: list[int] = []
        for _ in range(self.code_size):
            self.code.append(br.u32())

        self.strings: dict[int, str] = {}
        strings_start = br.tell()
        while br.tell() < strings_start + self.strings_size:
            # remember string offsets for later fixups
            offset = br.tell() - strings_start
            self.strings[offset] = br.cstr()
        self.ds.strings = list(self.strings.values())

        self.fixups_size = br.u32()
        self.fixups: dict[int, FixupType] = {}
        types = []
        offsets = []
        for _ in range(self.fixups_size):
            types.append(br.u8())
        for _ in range(self.fixups_size):
            offsets.append(br.u32())
        for i in range(self.fixups_size):
            self.fixups[offsets[i]] = FixupType(types[i])

        self.imports_size = br.u32()
        self.imports: dict[int, str] = {}
        for _ in range(self.imports_size):
            import_ = br.cstr()
            if import_:  # skip empty imports
                self.imports[br.tell()] = br.cstr()

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
        ranges: list[tuple[int, int]] = list(zip(entries, entries[1:]))  # make pairs

        for s, e in ranges:
            func = self._dis_function(s, e)
            self.ds.functions.append(func)

    def _dis_function(self, start: int, end: int) -> Function:
        mangled_name = self.func_names[start]
        parts = mangled_name.split("$")
        name = parts[0]
        nargs = int(parts[1])
        instructions: list[Instruction] = []

        i = start
        while i < end:
            opcode = Opcode(self.code[i])
            instr = self._process_opcode(i, opcode)
            instructions.append(instr)
            i += 1 + opcode.nargs

        return Function(name, nargs, start, instructions)

    def _process_opcode(self, offset: int, opcode: Opcode) -> Instruction:
        params: list = []
        for i, f in enumerate(opcode.args_format):
            idx = offset + i + 1
            arg = self.code[idx]
            match f:
                case "r":  # register
                    params.append(Register(arg).name.lower())
                case "a":  # argument, possible fixup
                    # is there a fixup for this index?
                    if idx in self.fixups:
                        match self.fixups[idx]:
                            case FixupType.STRING:
                                params.append(quote(self.strings[arg]))
                            case FixupType.GLOBAL_DATA:
                                params.append(f"@{arg}")
                            case _:
                                warnings.warn(f"Unsupported fixup: {self.fixups[idx]}")
                    else:
                        params.append(arg)  # append literal integer

        return Instruction(opcode, params)
