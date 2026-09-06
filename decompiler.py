import struct

from enum import Enum, auto
from disassembler import *
from syntax_tree import *


class Decompiler:
    class WriteTarget(Enum):
        LOCAL = auto()

    class LocalVar:
        size: int

    def __init__(self, dis: Disassembly) -> None:
        self.dis = dis
        self.funcs: list[STFunction] = []
        self.ast: AST

        self.gdata = bytearray(self.dis.gdata)
        self.registers: dict[Register, Any] = {
            Register.SP: 0,
            Register.OP: 0,
            Register.AX: 0,
            Register.BX: 0,
            Register.CX: 0,
            Register.DX: 0,
            Register.MAR: 0,
        }

        self.linenum = 0
        self.thisbase = 0

        self._decompile()

    @property
    def sp(self) -> int:
        v = self.registers[Register.SP]
        assert isinstance(v, int)
        return v

    @property
    def op(self) -> Any:
        return self.registers[Register.OP]

    @property
    def ax(self) -> Any:
        return self.registers[Register.AX]

    @property
    def bx(self) -> Any:
        return self.registers[Register.BX]

    @property
    def cx(self) -> Any:
        return self.registers[Register.CX]

    @property
    def dx(self) -> Any:
        return self.registers[Register.DX]

    @property
    def mar(self) -> Any:
        return self.registers[Register.MAR]

    def _decompile(self) -> None:
        funcs: list[STFunction] = []
        self.ast = STScript(funcs)
        for func in self.dis.functions:
            self.locals: dict[int, Decompiler.LocalVar] = {}
            self.func = STFunction(func.name, [])
            for ins in func.instructions:
                match ins.opcode:
                    case Opcode.LINENUM:
                        self.linenum = ins.params[0]
                    case Opcode.THISBASE:
                        self.thisbase = ins.params[0]
                    case Opcode.REGTOREG:
                        assert isinstance(ins.params[0], Register)
                        assert isinstance(ins.params[1], Register)
                        src = ins.params[0]
                        dst = ins.params[1]
                        self.registers[dst] = self.registers[src]

                        if src == Register.SP and dst == Register.MAR:
                            # prepare write to local
                            self.write_target = Decompiler.WriteTarget.LOCAL
                    case Opcode.LITTOREG:
                        assert isinstance(ins.params[0], Register)
                        assert isinstance(ins.params[1], FixedUpValue)
                        reg = ins.params[0]
                        self.registers[reg] = self._fixup(ins.params[1])
                    case Opcode.ZEROMEMORY | Opcode.MEMWRITE:
                        self._handle_memwrite(ins)
            funcs.append(self.func)

    def _fixup(self, v: FixedUpValue) -> Primitive:
        match v.type_:
            case FixupType.NO_FIXUP:
                return v.original
            case _:
                if v.fixed is None:
                    return v.original
                else:
                    return v.fixed

    def _handle_memwrite(self, ins: Instruction) -> None:
        # any write to memory emits an assignment
        match ins.opcode:
            case Opcode.ZEROMEMORY:  # zeromem
                # variable is simply declared
                pass
            case Opcode.MEMWRITE:  # memwrite4
                # writing int/float/pointer, assume int initially
                # current SP tells us what variable is being written
                reg = ins.params[0]
                assert isinstance(reg, Register)
                stmt = STAssignment(f"int local{0}", self.registers[reg])
                self.func.statements.append(stmt)

    def _prepare_local(self, sp: int) -> None:
        if sp in self.locals:
            return
        else:
            self.locals[sp] = Decompiler.LocalVar()
