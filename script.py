from __future__ import annotations

import enum

from binary_reader import BinaryReader
from dataclasses import dataclass
from typing import NamedTuple


# see https://github.com/adventuregamestudio/ags/blob/master/Engine/script/cc_instance.cpp
class Opcode(enum.IntEnum):
    ADD = 1
    SUB = 2
    REGTOREG = 3
    WRITELIT = 4
    RET = 5
    LITTOREG = 6
    MEMREAD = 7
    MEMWRITE = 8
    MULREG = 9
    DIVREG = 10
    ADDREG = 11
    SUBREG = 12
    BITAND = 13
    BITOR = 14
    ISEQUAL = 15
    NOTEQUAL = 16
    GREATER = 17
    LESSTHAN = 18
    GTE = 19
    LTE = 20
    AND = 21
    OR = 22
    CALL = 23
    MEMREADB = 24
    MEMREADW = 25
    MEMWRITEB = 26
    MEMWRITEW = 27
    JZ = 28
    PUSHREG = 29
    POPREG = 30
    JMP = 31
    MUL = 32
    CALLEXT = 33
    PUSHREAL = 34
    SUBREALSTACK = 35
    LINENUM = 36
    CALLAS = 37
    THISBASE = 38
    NUMFUNCARGS = 39
    MODREG = 40
    XORREG = 41
    NOTREG = 42
    SHIFTLEFT = 43
    SHIFTRIGHT = 44
    CALLOBJ = 45
    CHECKBOUNDS = 46
    MEMWRITEPTR = 47
    MEMREADPTR = 48
    MEMZEROPTR = 49
    MEMINITPTR = 50
    LOADSPOFFS = 51
    CHECKNULL = 52
    FADD = 53
    FSUB = 54
    FMULREG = 55
    FDIVREG = 56
    FADDREG = 57
    FSUBREG = 58
    FGREATER = 59
    FLESSTHAN = 60
    FGTE = 61
    FLTE = 62
    ZEROMEMORY = 63
    CREATESTRING = 64
    STRINGSEQUAL = 65
    STRINGSNOTEQ = 66
    CHECKNULLREG = 67
    LOOPCHECKOFF = 68
    MEMZEROPTRND = 69
    JNZ = 70
    DYNAMICBOUNDS = 71
    NEWARRAY = 72
    NEWUSEROBJECT = 73


OPCODE_TO_NAME = {
    Opcode.ADD: "addi",
    Opcode.SUB: "subi",
    Opcode.REGTOREG: "mov",
    Opcode.WRITELIT: "memwritelit",
    Opcode.RET: "ret",
    Opcode.LITTOREG: "movl",
    Opcode.MEMREAD: "memread4",
    Opcode.MEMWRITE: "memwrite4",
    Opcode.MULREG: "mul",
    Opcode.DIVREG: "div",
    Opcode.ADDREG: "add",
    Opcode.SUBREG: "sub",
    Opcode.BITAND: "and",
    Opcode.BITOR: "or",
    Opcode.ISEQUAL: "cmpeq",
    Opcode.NOTEQUAL: "cmpne",
    Opcode.GREATER: "gt",
    Opcode.LESSTHAN: "lt",
    Opcode.GTE: "gte",
    Opcode.LTE: "lte",
    Opcode.AND: "land",
    Opcode.OR: "lor",
    Opcode.CALL: "call",
    Opcode.MEMREADB: "memread1",
    Opcode.MEMREADW: "memread2",
    Opcode.MEMWRITEB: "memwrite1",
    Opcode.MEMWRITEW: "memwrite2",
    Opcode.JZ: "jzi",
    Opcode.PUSHREG: "push",
    Opcode.POPREG: "pop",
    Opcode.JMP: "jmpi",
    Opcode.MUL: "muli",
    Opcode.CALLEXT: "farcall",
    Opcode.PUSHREAL: "farpush",
    Opcode.SUBREALSTACK: "farsubsp",
    Opcode.LINENUM: "sourceline",
    Opcode.CALLAS: "callscr",
    Opcode.THISBASE: "thisaddr",
    Opcode.NUMFUNCARGS: "setfuncargs",
    Opcode.MODREG: "mod",
    Opcode.XORREG: "xor",
    Opcode.NOTREG: "not",
    Opcode.SHIFTLEFT: "shl",
    Opcode.SHIFTRIGHT: "shr",
    Opcode.CALLOBJ: "callobj",
    Opcode.CHECKBOUNDS: "checkbounds",
    Opcode.MEMWRITEPTR: "memwrite.ptr",
    Opcode.MEMREADPTR: "memread.ptr",
    Opcode.MEMZEROPTR: "memwrite.ptr.0",
    Opcode.MEMINITPTR: "meminit.ptr",
    Opcode.LOADSPOFFS: "load.sp.offs",
    Opcode.CHECKNULL: "checknull.ptr",
    Opcode.FADD: "faddi",
    Opcode.FSUB: "fsubi",
    Opcode.FMULREG: "fmul",
    Opcode.FDIVREG: "fdiv",
    Opcode.FADDREG: "fadd",
    Opcode.FSUBREG: "fsub",
    Opcode.FGREATER: "fgt",
    Opcode.FLESSTHAN: "flt",
    Opcode.FGTE: "fgte",
    Opcode.FLTE: "flte",
    Opcode.ZEROMEMORY: "zeromem",
    Opcode.CREATESTRING: "newstring",
    Opcode.STRINGSEQUAL: "streq",
    Opcode.STRINGSNOTEQ: "strne",
    Opcode.CHECKNULLREG: "checknull",
    Opcode.LOOPCHECKOFF: "loopcheckoff",
    Opcode.MEMZEROPTRND: "memwrite.ptr.0.nd",
    Opcode.JNZ: "jnzi",
    Opcode.DYNAMICBOUNDS: "dynamicbounds",
    Opcode.NEWARRAY: "newarray",
    Opcode.NEWUSEROBJECT: "newuserobject",
}
NAME_TO_OPCODE = dict((v, k) for (k, v) in OPCODE_TO_NAME.items())

class FixupType(enum.IntEnum):
    NO_FIXUP = 0
    GLOBAL_DATA = 1
    FUNCTION = 2
    STRING = 3
    IMPORT = 4
    DATA_DATA = 5
    STACK = 6


class Export(NamedTuple):
    export: str
    address: int


class Section(NamedTuple):
    name: str
    offset: int


@dataclass
class Script:
    version: int
    global_data: bytes
    code: bytes
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

        code = b""
        if code_size > 0:
            code = br.read_bytes(code_size * 4)

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
