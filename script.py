from __future__ import annotations

import enum

from binary_reader import BinaryReader
from dataclasses import dataclass
from typing import NamedTuple


# see https://github.com/adventuregamestudio/ags/blob/master/Engine/script/cc_instance.cpp
@enum.unique
class Opcode(enum.Enum):
    NOP = (0, "NULL", 0)
    ADD = (1, "addi", 2)
    SUB = (2, "subi", 2)
    REGTOREG = (3, "mov", 2)
    WRITELIT = (4, "memwritelit", 2)
    RET = (5, "ret", 0)
    LITTOREG = (6, "movl", 2)
    MEMREAD = (7, "memread4", 1)
    MEMWRITE = (8, "memwrite4", 1)
    MULREG = (9, "mul", 2)
    DIVREG = (10, "div", 2)
    ADDREG = (11, "add", 2)
    SUBREG = (12, "sub", 2)
    BITAND = (13, "and", 2)
    BITOR = (14, "or", 2)
    ISEQUAL = (15, "cmpeq", 2)
    NOTEQUAL = (16, "cmpne", 2)
    GREATER = (17, "gt", 2)
    LESSTHAN = (18, "lt", 2)
    GTE = (19, "gte", 2)
    LTE = (20, "lte", 2)
    AND = (21, "land", 2)
    OR = (22, "lor", 2)
    CALL = (23, "call", 1)
    MEMREADB = (24, "memread1", 1)
    MEMREADW = (25, "memread2", 1)
    MEMWRITEB = (26, "memwrite1", 1)
    MEMWRITEW = (27, "memwrite2", 1)
    JZ = (28, "jzi", 1)
    PUSHREG = (29, "push", 1)
    POPREG = (30, "pop", 1)
    JMP = (31, "jmpi", 1)
    MUL = (32, "muli", 2)
    CALLEXT = (33, "farcall", 1)
    PUSHREAL = (34, "farpush", 1)
    SUBREALSTACK = (35, "farsubsp", 1)
    LINENUM = (36, "sourceline", 1)
    CALLAS = (37, "callscr", 1)
    THISBASE = (38, "thisaddr", 1)
    NUMFUNCARGS = (39, "setfuncargs", 1)
    MODREG = (40, "mod", 2)
    XORREG = (41, "xor", 2)
    NOTREG = (42, "not", 1)
    SHIFTLEFT = (43, "shl", 2)
    SHIFTRIGHT = (44, "shr", 2)
    CALLOBJ = (45, "callobj", 1)
    CHECKBOUNDS = (46, "checkbounds", 2)
    MEMWRITEPTR = (47, "memwrite.ptr", 1)
    MEMREADPTR = (48, "memread.ptr", 1)
    MEMZEROPTR = (49, "memwrite.ptr.0", 0)
    MEMINITPTR = (50, "meminit.ptr", 1)
    LOADSPOFFS = (51, "load.sp.offs", 1)
    CHECKNULL = (52, "checknull.ptr", 0)
    FADD = (53, "faddi", 2)
    FSUB = (54, "fsubi", 2)
    FMULREG = (55, "fmul", 2)
    FDIVREG = (56, "fdiv", 2)
    FADDREG = (57, "fadd", 2)
    FSUBREG = (58, "fsub", 2)
    FGREATER = (59, "fgt", 2)
    FLESSTHAN = (60, "flt", 2)
    FGTE = (61, "fgte", 2)
    FLTE = (62, "flte", 2)
    ZEROMEMORY = (63, "zeromem", 1)
    CREATESTRING = (64, "newstring", 1)
    STRINGSEQUAL = (65, "streq", 2)
    STRINGSNOTEQ = (66, "strne", 2)
    CHECKNULLREG = (67, "checknull", 1)
    LOOPCHECKOFF = (68, "loopcheckoff", 0)
    MEMZEROPTRND = (69, "memwrite.ptr.0.nd", 0)
    JNZ = (70, "jnzi", 1)
    DYNAMICBOUNDS = (71, "dynamicbounds", 1)
    NEWARRAY = (72, "newarray", 3)
    NEWUSEROBJECT = (73, "newuserobject", 2)
    
    def __init__(self, _, mnemonic: str, nargs: int) -> None:
        self.mnemonic = mnemonic
        self.nargs = nargs

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
