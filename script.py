from __future__ import annotations

import enum

from binary_reader import BinaryReader
from dataclasses import dataclass
from typing import NamedTuple


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


@dataclass
class Script:
    version: int
    global_data: bytes
    code: list[int]
    strings: list[str]
    fixup_types: list[FixupType]
    fixups: list[int]
    imports: list[str]
    exports: list[Export]
    sections: list[Section]

    @classmethod
    def read(cls, source) -> Script:
        br = BinaryReader(source)
        signature = br.fstr(4)
        assert signature == "SCOM", "Source is not a compiled AGS script."

        version = br.u32()
        global_data_size = br.u32()
        code_size = br.u32()
        strings_size = br.u32()

        global_data = b""
        if global_data_size > 0:
            global_data = br.read_bytes(global_data_size)

        code = []
        for _ in range(code_size):
            code.append(br.u32())

        strings = []
        start_offset = br.tell()
        if strings_size > 0:
            while br.tell() - start_offset < strings_size:
                strings.append(br.cstr())

        fixups_size = br.u32()
        fixup_types = []
        fixups = []
        if fixups_size > 0:
            for _ in range(fixups_size):
                fixup_types.append(FixupType(br.u8()))
            for _ in range(fixups_size):
                fixups.append(br.u32())

        imports_size = br.u32()
        imports = []
        for _ in range(imports_size):
            imports.append(br.cstr())

        exports_size = br.u32()
        exports = []
        for _ in range(exports_size):
            exports.append(Export(br.cstr(), br.u32()))

        sections_size = br.u32()
        sections = []
        for _ in range(sections_size):
            sections.append(Section(br.cstr(), br.i32()))

        signature = br.read_bytes(4)
        assert signature == b"\xfe\xca\xef\xbe"

        return Script(
            version,
            global_data,
            code,
            strings,
            fixup_types,
            fixups,
            imports,
            exports,
            sections,
        )
