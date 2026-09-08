from __future__ import annotations

from dataclasses import field
from typing import ClassVar, Self

from disassembler import *
from syntax_tree import *

type _MemOffset = int
type _InstructionList = list[Instruction]
type _Leaders = set[Instruction]
type _Address = int
type _CodeBlocks = dict[_Address, _CfgBlock]


@dataclass
class _LocalVar:
    size: int
    id_: int
    is_newly_created: bool = True
    declaration: STVarDeclaration | None = None

    @property
    def name(self) -> str:
        return f"local{self.id_}"


@dataclass
class _ScriptVar:
    size: int
    id_: int
    type_: STType | None = None

    @property
    def name(self) -> str:
        return f"var{self.id_}"


@dataclass
class _CfgBlock:
    instructions: list[Instruction]
    preds: list[_CfgBlock] = field(default_factory=list)
    succs: list[_CfgBlock] = field(default_factory=list)

    def link_to(self, target: Self) -> None:
        self.succs.append(target)
        target.preds.append(self)


class Decompiler:
    _BINOPS: ClassVar = {
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
        Opcode.FADDREG: BinOp.ADD,
        Opcode.FSUBREG: BinOp.SUB,
        Opcode.FMULREG: BinOp.MUL,
        Opcode.FDIVREG: BinOp.DIV,
        Opcode.FGTE: BinOp.GTE,
        Opcode.FGREATER: BinOp.GT,
        Opcode.FLTE: BinOp.LTE,
        Opcode.FLESSTHAN: BinOp.LT,
    }

    _BINOPS_LITERAL: ClassVar = {
        Opcode.ADD: BinOp.ADD,
        Opcode.SUB: BinOp.SUB,
        Opcode.MUL: BinOp.MUL,
        Opcode.FADD: BinOp.ADD,
        Opcode.FSUB: BinOp.SUB,
    }

    _BRANCH: ClassVar = {
        Opcode.JMP,
        Opcode.JZ,
        Opcode.JNZ,
    }

    _TERMINATORS: ClassVar = {
        Opcode.RET,
    } | _BRANCH

    _COUNTER_LOCAL: ClassVar = "local"
    _COUNTER_SCRVAR: ClassVar = "script"
    _COUNTER_GLOBAL: ClassVar = "global"

    _GLOBAL_LABEL: ClassVar = "global"

    def __init__(self, dis: Disassembly) -> None:
        self.dis = dis
        self._stfuncs: list[STFunction] = []
        self._gdata = bytearray(self.dis.gdata)
        self._linenum = 0
        self._thisbase = 0
        self._write_target: Literal["global", "local", "script", "array"] = "global"  # noqa: UP037
        self._array_item_count = 0
        self._counters: dict[str, int] = {}

        self._stack: list
        self._statements: list[STStatement]
        self._labels: list[Label]
        self._locals: dict[_MemOffset, _LocalVar]
        self._svars: dict[_MemOffset, _ScriptVar] = {}

        self._sp: int = 0
        self._mar: int | FixedUpValue | STBinaryExpression = 0
        self._op = 0
        self._ax = 0
        self._bx = 0
        self._cx = 0
        self._dx = 0

        self._build_cfg()
        self._decompile()
        self._build_script()

    def _build_cfg(self) -> None:
        # all our entry points are given as function names in the exports table.
        for func in self.dis.functions:
            leaders = self._find_leaders(func)
            blocks = self._build_blocks(func.instructions, leaders)
            self._link_blocks(blocks)

    def _find_leaders(self, func: Function) -> _Leaders:
        leaders: _Leaders = set()
        if not func.instructions:
            return leaders
        leaders.add(func.instructions[0])  # the first instruction is a leader
        for i, inst in enumerate(func.instructions):
            if inst.opcode in self._BRANCH:
                target = inst.params[0]
                assert isinstance(target, Label)
                leaders.add(func.lookup[target.to])
            if inst.opcode in self._TERMINATORS and i + 1 < len(func.instructions):
                leaders.add(func.instructions[i + 1])
        return leaders

    def _build_blocks(
        self,
        instructions: _InstructionList,
        leaders: _Leaders,
    ) -> _CodeBlocks:
        blocks: list[_InstructionList] = []
        current: _InstructionList = []
        for inst in instructions:
            if inst in leaders and current:
                blocks.append(current)
                current = []
            current.append(inst)
        if current:
            blocks.append(current)
        return {b[0].offset: _CfgBlock(b) for b in blocks}

    def _link_blocks(self, blocks: _CodeBlocks) -> None:
        addresses = sorted(blocks)
        for i, address in enumerate(addresses):
            block = blocks[address]
            last = block.instructions[-1]
            if last.opcode == Opcode.JMP:
                label = last.params[0]
                assert isinstance(label, Label)
                block.link_to(blocks[label.to])
            elif last.opcode in self._BRANCH:
                label = last.params[0]
                assert isinstance(label, Label)
                block.link_to(blocks[label.to])
                if i + 1 < len(addresses):
                    block.link_to(blocks[addresses[i + 1]])
            elif last.opcode == Opcode.RET:
                # return is the exit node, no linking here.
                pass
            else:
                # fallthrough
                if i + 1 < len(addresses):
                    block.link_to(blocks[addresses[i + 1]])

    def _decompile(self) -> None:
        for func in self.dis.functions:
            self._stack = []
            self._labels = []
            self._locals = {}
            self._statements = []

            for item in func.instructions:
                if isinstance(item, Label):
                    self._labels.append(item)
                    continue

                opc = item.opcode
                if opc in self._BINOPS:
                    ra = item.as_reg(0)
                    rb = item.as_reg(1)
                    a = self._make_expr(ra)
                    b = self._make_expr(rb)
                    expr = STBinaryExpression(a, b, self._BINOPS[opc])
                    self._setr(ra, expr)

                    if ra == Register.MAR and rb == Register.CX:
                        # array index, CX will hold an expression at this point
                        self._write_target = "array"
                elif opc in self._BINOPS_LITERAL:
                    r = item.as_reg(0)
                    v = item.as_int(1)
                    if r == Register.SP:  # offsets only
                        if opc == Opcode.ADD:
                            self._sp += v
                        elif opc == Opcode.SUB:
                            self._sp -= v
                        else:
                            raise AssertionError
                    else:
                        left = self._make_expr(r)
                        right = STLiteral(v)
                        expr = STBinaryExpression(
                            left, right, self._BINOPS_LITERAL[opc]
                        )
                        self._setr(r, expr)
                elif opc == Opcode.LINENUM:
                    self._linenum = item.as_int(0)
                elif opc == Opcode.THISBASE:
                    self._thisbase = item.as_int(0)
                elif opc == Opcode.PUSHREG:
                    rv = self._getr(item.as_reg(0))
                    self._stack.append(rv)
                elif opc == Opcode.POPREG:
                    rv = item.as_reg(0)
                    v = self._stack.pop()
                    self._setr(rv, v)
                elif opc == Opcode.REGTOREG:  # R1 -> R2
                    rs = item.as_reg(0)
                    rd = item.as_reg(1)
                    self._setr(rd, self._getr(rs))

                    if rs == Register.SP and rd == Register.MAR:
                        # local vars are written using SP
                        self._write_target = "local"
                elif opc == Opcode.LITTOREG:  # R <- A
                    reg = item.as_reg(0)
                    v = item.as_fup(1)
                    self._setr(reg, v)

                    if reg == Register.MAR:
                        if v.type_ == FixupType.GLOBAL_DATA:
                            # top-level script var
                            self._write_target = "script"
                        elif v.type_ == FixupType.IMPORT:
                            # true global var
                            self._write_target = "global"
                elif opc == Opcode.LOADSPOFFS:
                    offset = item.as_int(0)
                    self._mar = self._sp - offset
                    assert self._mar >= 0
                    self._write_target = "local"  # writing to stack, so must be a local
                elif opc == Opcode.ZEROMEMORY:
                    size = item.as_int(0)
                    self._emit_vardecl(size)
                elif opc == Opcode.MEMWRITEB:
                    self._emit_assign(item, 1)
                elif opc == Opcode.MEMWRITEW:
                    self._emit_assign(item, 2)
                elif opc == Opcode.MEMWRITE:
                    self._emit_assign(item, 4)
                elif opc == Opcode.CHECKBOUNDS:
                    r = item.as_reg(0)
                    assert r == Register.AX  # i'm not sure if this is always the case
                    v = item.as_int(1)
                    self._array_item_count = v
                elif opc == Opcode.MEMREADB:
                    r = item.as_reg(0)
                    self._emit_varexpr(1, r)
                elif opc == Opcode.MEMREADW:
                    r = item.as_reg(0)
                    self._emit_varexpr(2, r)
                elif opc == Opcode.MEMREAD:
                    r = item.as_reg(0)
                    self._emit_varexpr(4, r)
                elif opc == Opcode.RET:
                    pass  # TODO: return values
                else:
                    raise NotImplementedError(opc)

            stfunc = STFunction("function", func.name, [], self._statements)
            self._stfuncs.append(stfunc)

    def _emit_vardecl(self, size: int) -> None:
        # globals are initialized by the compiler, and local variables are the
        # only other place where declaration without definition is legal.
        assert self._write_target == "local", "Illegal target for local"

        # again, we can only declare locals here, so MAR should have the value
        # of SP, which is guaranteed to be in int.
        assert isinstance(self._mar, int), "MAR has non-int before declaring local"

        lvar = self._get_local(self._mar, size)
        assert lvar.is_newly_created, "Declaring an existing local"
        type_ = self._guess_type_from_size(size)
        stmt = STVarDeclaration(type_, lvar.name)
        lvar.declaration = stmt
        self._statements.append(stmt)

    def _emit_assign(self, inst: Instruction, size: int) -> None:
        # MAR + write target determine the LHS
        target: STAssignmentTarget
        match self._write_target:
            case "local":
                assert isinstance(self._mar, int)
                lvar = self._get_local(self._mar, size)
                type_ = None
                if lvar.is_newly_created:
                    type_ = self._guess_type_from_size(lvar.size)
                else:
                    # the variable must already be declared
                    assert lvar.declaration is not None
                target = STVarAssignTarget(lvar.name, None, type_)
            case "global":
                assert isinstance(self._mar, FixedUpValue)
                assert self._mar.type_ == FixupType.IMPORT, "MAR is not an import"
                name = self._mar.fixed
                assert isinstance(name, str)
                target = STVarAssignTarget(name, None, None)
            case "array":
                # arrays will have MAR = (variable + CX(AX(index) * size))
                var, index, item_size = self._array_from_mar()

                if isinstance(var, int):
                    lvar = self._get_local(var, size)
                    assert lvar.declaration is not None
                    type_ = self._guess_type_from_size(item_size)
                    type_.array_size = self._array_item_count
                    lvar.declaration.type_ = type_
                    target = STVarAssignTarget(lvar.name, index)
                elif var.type_ == FixupType.GLOBAL_DATA:
                    svar = self._get_svar(var.original, size)
                    target = STVarAssignTarget(svar.name, index, svar.type_)
                elif var.type_ == FixupType.IMPORT:
                    assert isinstance(var.fixed, str)
                    type_ = self._guess_type_from_size(size)
                    target = STVarAssignTarget(var.fixed, index, type_)
            case "script":
                assert isinstance(self._mar, FixedUpValue)
                assert self._mar.type_ == FixupType.GLOBAL_DATA
                svar = self._get_svar(self._mar.original, size)
                assert svar.type_ is not None
                target = STVarAssignTarget(svar.name, None, svar.type_)

        # R determines the value
        r = inst.as_reg(0)
        v = self._make_expr(r)

        stmt = STAssignment(target, v)  # pyright: ignore[reportPossiblyUnboundVariable]
        self._statements.append(stmt)

    def _emit_varexpr(self, size: int, r: Register) -> None:
        if isinstance(self._mar, int):
            lvar = self._get_local(self._mar, size)
            self._setr(r, STVarExpression(lvar.name, None))
        elif isinstance(self._mar, FixedUpValue):
            t = self._mar.type_
            if t == FixupType.GLOBAL_DATA:
                svar = self._get_svar(self._mar.original, size)
                self._setr(r, STVarExpression(svar.name, None))
            elif t == FixupType.IMPORT:
                assert isinstance(self._mar.fixed, str)
                self._setr(r, STVarExpression(self._mar.fixed, None))
        elif isinstance(self._mar, STBinaryExpression):
            # array access
            var, index, item_size = self._array_from_mar()
            if isinstance(var, int):
                lvar = self._get_local(var, item_size)
                # must not access non-existent locals
                assert not lvar.is_newly_created
                self._setr(r, STVarExpression(lvar.name, index))
            elif var.type_ == FixupType.GLOBAL_DATA:
                svar = self._get_svar(var.original, item_size)
                self._setr(r, STVarExpression(svar.name, index))
            elif var.type_ == FixupType.IMPORT:
                assert isinstance(var.fixed, str)
                self._setr(r, STVarExpression(var.fixed, index))
            else:
                raise NotImplementedError(var.type_)

    def _build_script(self) -> None:
        items: list[STItem] = []

        # TODO: svars with initial values
        for svar in self._svars.values():
            assert svar.type_ is not None, "Typeless script variable"
            decl = STVarDeclaration(svar.type_, svar.name)
            items.append(decl)

        items.extend(self._stfuncs)  # add decompiled functions
        self.script = STScript(items)

    def _getr(self, register: Register):
        match register:
            case Register.SP:
                return self._sp
            case Register.MAR:
                return self._mar
            case Register.OP:
                return self._op
            case Register.AX:
                return self._ax
            case Register.BX:
                return self._bx
            case Register.CX:
                return self._cx
            case Register.DX:
                return self._dx

    def _setr(self, register: Register, value) -> None:
        match register:
            case Register.SP:
                assert isinstance(value, int), "SP has a non-int value"
                self._sp = value
            case Register.MAR:
                assert isinstance(value, int | FixedUpValue | STBinaryExpression)
                self._mar = value
            case Register.OP:
                self._op = value
            case Register.AX:
                self._ax = value
            case Register.BX:
                self._bx = value
            case Register.CX:
                self._cx = value
            case Register.DX:
                self._dx = value

    def _make_expr(self, reg: Register) -> STExpression:
        rv = self._getr(reg)
        if isinstance(rv, STExpression):
            return rv
        elif isinstance(rv, int | float | str):
            return STLiteral(rv)
        elif isinstance(rv, FixedUpValue) and rv.type_ == FixupType.NO_FIXUP:
            return STLiteral(rv.original)
        else:
            raise NotImplementedError

    def _guess_type_from_size(self, size: int) -> STType:
        assert size > 0, "Size is not positive"
        if size == 1:
            return STType("char")
        elif size == 2:
            return STType("short")
        elif size == 4:
            return STType("int")
        else:
            return STType("char", array_size=size)

    def _next_id(self, counter: str) -> int:
        if counter not in self._counters:
            self._counters[counter] = 0
        result = self._counters[counter]
        self._counters[counter] += 1
        return result

    def _get_local(self, offset: int, size: int) -> _LocalVar:
        if offset in self._locals:
            lvar = self._locals[offset]
            # if we're accessing the same local again, it is no longer
            # "newly created", for obvious reasons.
            lvar.is_newly_created = False
            return lvar
        else:
            lvar = _LocalVar(size, self._next_id(self._COUNTER_LOCAL))
            self._locals[offset] = lvar
            return lvar

    def _get_svar(self, offset: int, size: int) -> _ScriptVar:
        if offset in self._svars:
            svar = self._svars[offset]
            assert svar.size == size
            return svar
        else:
            type_ = self._guess_type_from_size(size)
            svar = _ScriptVar(size, self._next_id(self._COUNTER_SCRVAR), type_)
            self._svars[offset] = svar
            return svar

    def _array_from_mar(self) -> tuple[int | FixedUpValue, STExpression, int]:
        expr = self._mar
        assert isinstance(expr, STBinaryExpression)
        assert expr.operation == BinOp.ADD

        var = expr.left
        assert isinstance(var, STLiteral)
        var = var.value
        assert isinstance(var, int | FixedUpValue)

        mul = expr.right
        assert isinstance(mul, STBinaryExpression)
        assert mul.operation == BinOp.MUL

        index = mul.left  # index should be an arbitrary expression
        assert isinstance(index, STExpression)
        item_size = mul.right  # item_size should be a literal int
        assert isinstance(item_size, STLiteral)
        item_size = item_size.value
        assert isinstance(item_size, int)

        return var, index, item_size
