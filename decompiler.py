from __future__ import annotations

from enum import Enum, auto
from disassembler import *
from syntax_tree import *

MemOffset: TypeAlias = int


@dataclass
class LocalVar:
    size: int
    id_: int
    newly_created: bool = True
    type_: STType | None = None

    @property
    def name(self) -> str:
        return f"local{self.id_}"


@dataclass
class GlobalVar:
    size: int
    id_: int
    type_: STType | None = None

    @property
    def name(self) -> str:
        return f"global{self.id_}"


class Decompiler:
    class WriteTarget(Enum):
        LOCAL = auto()
        GLOBAL = auto()

    WT = WriteTarget
    BINOPS = {
        Opcode.ADDREG: BinOp.ADD,
        Opcode.SUBREG: BinOp.SUB,
        Opcode.MULREG: BinOp.MUL,
        Opcode.DIVREG: BinOp.DIV,
        Opcode.MODREG: BinOp.MOD,
        Opcode.BITAND: BinOp.BITAND,
        Opcode.BITOR: BinOp.BITOR,
        Opcode.ISEQUAL: BinOp.EQ,
        Opcode.NOTEQUAL: BinOp.NEQ,
        Opcode.GTE: BinOp.GTE,
        Opcode.GREATER: BinOp.GT,
        Opcode.LTE: BinOp.LTE,
        Opcode.LESSTHAN: BinOp.LT,
        Opcode.AND: BinOp.AND,
        Opcode.OR: BinOp.OR,
    }

    def __init__(self, dis: Disassembly) -> None:
        self.dis = dis
        self.stfuncs: list[STFunction] = []

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
        self._build_script()

    @property
    def sp(self) -> int:
        v = self.registers[Register.SP]
        assert isinstance(v, int)
        return v

    @sp.setter
    def sp(self, v: int) -> None:
        self.registers[Register.SP] = v

    @property
    def mar(self) -> int:
        v = self.registers[Register.MAR]
        assert isinstance(v, int)
        return v

    @mar.setter
    def mar(self, v: int) -> None:
        self.registers[Register.MAR] = v

    def _next_local_id(self) -> int:
        result = self.local_id
        self.local_id += 1
        return result

    def _next_global_id(self) -> int:
        result = self.global_id
        self.global_id += 1
        return result

    def _decompile(self) -> None:
        self.write_target: Decompiler.WriteTarget | None = None
        self.global_id = 0
        self.globals: dict[MemOffset, GlobalVar] = {}

        for func in self.dis.functions:
            self._dc_func(func)
            self.stfuncs.append(self.stfunc)

    def _build_script(self) -> None:
        items: list[STItem] = []

        for gvar in self.globals.values():
            assert gvar.type_ is not None
            decl = STVarDeclaration(gvar.type_, gvar.name)
            items.append(decl)

        items.extend(self.stfuncs)  # add decompiled functions
        self.script = STScript(items)

    def _dc_func(self, func: Function) -> None:
        self.sp = 0  # new stack frame; reset SP
        self.local_id = 0
        self.stack: list[STExpression] = []
        self.locals: dict[MemOffset, LocalVar] = {}
        self.stfunc = STFunction("function", func.name, [], [])
        for ins in func.instructions:
            self._dc_ins(ins)

    def _dc_ins(self, ins: Instruction) -> None:
        if ins.opcode in self.BINOPS:
            ra = ins.get_reg(0)
            rb = ins.get_reg(1)
            a = self._make_expr(ra)
            b = self._make_expr(rb)
            expr = STBinaryExpression(a, b, self.BINOPS[ins.opcode])
            self.registers[ra] = expr
            return

        match ins.opcode:
            case Opcode.LINENUM:
                self.linenum = ins.get_int(0)

            case Opcode.THISBASE:
                self.thisbase = ins.get_int(0)

            case Opcode.PUSHREG:
                reg = ins.get_reg(0)
                expr = self._make_expr(reg)
                self.stack.append(expr)

            case Opcode.POPREG:
                reg = ins.get_reg(0)
                self.registers[reg] = self.stack.pop()

            case Opcode.REGTOREG:
                src = ins.get_reg(0)
                dst = ins.get_reg(1)
                self.registers[dst] = self.registers[src]

                if src == Register.SP and dst == Register.MAR:
                    # prepare write to local
                    self.write_target = self.WriteTarget.LOCAL

            case Opcode.LITTOREG:
                reg = ins.get_reg(0)
                val = ins.get_fup(1)
                self.registers[reg] = self._fixup(val)

                if reg != Register.MAR:
                    return
                match val.type_:
                    case FixupType.GLOBAL_DATA | FixupType.IMPORT:
                        # prepare write to global
                        self.write_target = self.WriteTarget.GLOBAL

            case (
                Opcode.ZEROMEMORY
                | Opcode.MEMWRITE
                | Opcode.MEMWRITEB
                | Opcode.MEMWRITEW
            ):
                self._handle_memwrite(ins)

            case Opcode.ADD | Opcode.SUB:
                reg = ins.get_reg(0)
                val = self._fixup(ins.get_fup(1))
                if reg == Register.SP:
                    # simply move the SP
                    if ins.opcode == Opcode.ADD:
                        self.registers[reg] += val
                    elif ins.opcode == Opcode.SUB:
                        self.registers[reg] -= val
                    else:
                        raise RuntimeError
                else:
                    # need to construct an expression
                    raise NotImplementedError

            case Opcode.LOADSPOFFS:
                val = self._fixup(ins.get_fup(0))
                assert isinstance(val, int)
                self.mar = self.sp - val
                self.write_target = self.WT.LOCAL

            case Opcode.RET:
                pass  # TODO!

            case _:
                raise NotImplementedError

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
                self._write_zeros(ins)
            case Opcode.MEMWRITEB:  # memwrite1
                self._write_register(ins, 1)
            case Opcode.MEMWRITEW:  # memwrite2
                self._write_register(ins, 2)
            case Opcode.MEMWRITE:  # memwrite4
                self._write_register(ins, 4)

    def _write_zeros(self, ins: Instruction) -> None:
        # global vars are not initialized at runtime
        assert self.write_target != self.WriteTarget.GLOBAL
        # variable is simply declared
        size = ins.params[0]
        assert isinstance(size, FixedUpValue)
        size = self._fixup(size)
        assert isinstance(size, int)

        lvar = self._get_local(self.sp, size)

        # determine appropriate type -- TODO!
        match size:
            case 1:
                lvar.type_ = STType("char")
            case 2:
                lvar.type_ = STType("short")
            case 4:
                lvar.type_ = STType("int")
            case _:
                raise NotImplementedError

        stmt = STVarDeclaration(lvar.type_, f"local{lvar.id_}")
        self.stfunc.statements.append(stmt)

    def _write_register(self, ins: Instruction, size: int) -> None:
        # writing int/float/pointer, assume int initially.
        # current SP tells us what variable is being written.
        reg = ins.get_reg(0)
        expr = self._make_expr(reg)

        match self.write_target:
            case self.WT.LOCAL:
                self._emit_local(expr, size)
            case self.WT.GLOBAL:
                self._emit_global(expr, size)

    def _emit_local(self, expr: STExpression, size: int) -> None:
        lvar = self._get_local(self.mar, size)
        type_ = None
        if lvar.newly_created:
            # newly created, need to define
            type_ = self._default_type_for_size(size)
            lvar.type_ = type_
        lhs = STVarAssignTarget(lvar.name, None, type_)
        stmt = STAssignment(lhs, expr)
        self.stfunc.statements.append(stmt)

    def _emit_global(self, expr: STExpression, size: int) -> None:
        gvar = self._get_global(self.mar, size)
        gvar.type_ = self._default_type_for_size(size)
        lhs = STVarAssignTarget(gvar.name, None)
        stmt = STAssignment(lhs, expr)
        self.stfunc.statements.append(stmt)

    def _default_type_for_size(self, size: int) -> STType:
        match size:
            case 1:
                return STType("char")
            case 2:
                return STType("short")
            case 4:
                return STType("int")
            case _:
                raise RuntimeError

    def _make_expr(self, reg: Register) -> STExpression:
        rv = self.registers[reg]
        if isinstance(rv, STExpression):
            return rv
        elif isinstance(rv, int | float | str):
            return STLiteral(rv)
        else:
            raise NotImplementedError

    def _get_local(self, sp: int, size: int) -> LocalVar:
        lvar: LocalVar
        if sp not in self.locals:
            # new variable, set newly_created
            lvar = LocalVar(size, self._next_local_id(), True)
            self.locals[sp] = lvar
        else:
            # old variable, clear newly_created
            lvar = self.locals[sp]
            lvar.newly_created = False

        assert lvar.size == size
        return lvar

    def _get_global(self, mar: int, size: int) -> GlobalVar:
        gvar: GlobalVar
        if mar not in self.globals:
            gvar = GlobalVar(size, self._next_global_id())
            self.globals[mar] = gvar
        else:
            gvar = self.globals[mar]
            assert gvar.size == size

        return gvar
