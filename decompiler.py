from __future__ import annotations

from enum import Enum, auto
from disassembler import *
from syntax_tree import *


class Decompiler:
    class WriteTarget(Enum):
        LOCAL = auto()
        GLOBAL = auto()

    @dataclass
    class LocalVar:
        size: int
        id_: int
        newly_created: bool = True
        type_: STType | None = None

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

    @sp.setter
    def sp(self, sp: int) -> None:
        self.registers[Register.SP] = sp

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

    def _next_local_id(self) -> int:
        result = self.local_id
        self.local_id += 1
        return result

    def _decompile(self) -> None:
        funcs: list[STFunction] = []
        self.ast = STScript(funcs)
        self.write_target: Decompiler.WriteTarget | None = None
        self.local_id = 0

        for func in self.dis.functions:
            self.locals: dict[int, Decompiler.LocalVar] = {}
            self.func = STFunction("function", func.name, [], [])
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
                        reg = ins.params[0]
                        val = ins.params[1]
                        assert isinstance(reg, Register)
                        assert isinstance(val, FixedUpValue)
                        self.registers[reg] = self._fixup(val)

                        if reg == Register.MAR:
                            match val.type_:
                                case FixupType.GLOBAL_DATA | FixupType.IMPORT:
                                    # prepare write to global
                                    self.write_target = Decompiler.WriteTarget.GLOBAL

                    case Opcode.ZEROMEMORY | Opcode.MEMWRITE:
                        self._handle_memwrite(ins)

                    case Opcode.ADD:
                        reg = ins.params[0]
                        val = ins.params[1]
                        assert isinstance(reg, Register)
                        assert isinstance(val, FixedUpValue)

                        val = self._fixup(val)
                        if reg == Register.SP:
                            # simply move the SP
                            self.registers[reg] += val
                        else:
                            # need to construct an expression
                            raise NotImplementedError

                    case Opcode.LOADSPOFFS:
                        val = ins.params[0]
                        assert isinstance(val, FixedUpValue)
                        val = self._fixup(val)
                        assert isinstance(val, int)
                        self.sp -= val

                    case Opcode.RET:
                        pass  # TODO!

                    case _:
                        raise NotImplementedError

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
                assert self.write_target != Decompiler.WriteTarget.GLOBAL
                # variable is simply declared
                size = ins.params[0]
                assert isinstance(size, FixedUpValue)
                size = self._fixup(size)
                assert isinstance(size, int)

                lvar = self._lookup_local(self.sp, size)

                # determine appropriate type -- TODO!
                if size == 4:
                    lvar.type_ = STType("int")
                else:
                    raise NotImplementedError

                stmt = STVarDeclaration(lvar.type_, f"local{lvar.id_}")
                self.func.statements.append(stmt)
            case Opcode.MEMWRITE:  # memwrite4
                # writing int/float/pointer, assume int initially.
                # current SP tells us what variable is being written.
                reg = ins.params[0]
                assert isinstance(reg, Register)
                lvar = self._lookup_local(self.sp, 4)

                expr = self._make_expr(reg)

                if lvar.newly_created:
                    # if we have not written into this variable before,
                    # it must be a variable definition.
                    lvar.type_ = STType("int")
                    name = f"local{lvar.id_}"
                    lhs = STVarDeclaration(lvar.type_, name)
                else:
                    # if we have written into it before, then it's a
                    # simple assignment.
                    name = f"local{lvar.id_}"
                    lhs = STVarAssignTarget(name, None)
                stmt = STAssignment(lhs, expr)
                self.func.statements.append(stmt)

    def _make_expr(self, reg: Register) -> STExpression:
        rv = self.registers[reg]
        if isinstance(rv, STExpression):
            return rv
        elif isinstance(rv, int | float | str):
            return STLiteral(rv)
        else:
            raise NotImplementedError

    def _lookup_local(self, sp: int, size: int) -> Decompiler.LocalVar:
        if sp not in self.locals:
            # new variable, set newly_created
            lvar = Decompiler.LocalVar(size, self._next_local_id(), True)
            self.locals[sp] = lvar
        else:
            # old variable, clear newly_created
            lvar = self.locals[sp]
            lvar.newly_created = False

        assert self.locals[sp].size == size
        return self.locals[sp]
