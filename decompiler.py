from __future__ import annotations

import gc
import logging
from dataclasses import field
from typing import ClassVar, Final

from disassembler import *
from syntax_tree import *
from utils import sjoin

type _MemOffset = int
type _Address = int
type _CodeBlocks = dict[_Address, _Block]
type _WriteTarget = Literal["local", "script", "global", "array"]
type _Dominators = dict[_Block, set[_Block]]
type _IDomTree = dict[_Block, _Block]

logger = logging.getLogger(__name__)

_DIAGNOSTICS: Final[bool] = True


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
class _Block:
    instructions: list[Instruction]

    def __str__(self) -> str:
        if not self.instructions:
            return ""
        return sjoin("; ", self.instructions[0], "...", self.instructions[-1])

    def __repr__(self) -> str:
        return f"<CfgBlock '{self}'>"

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, value: object) -> bool:
        return self is value


@dataclass
class _CFGraph:
    _preds: dict[_Block, list[_Block]] = field(default_factory=dict)
    _succs: dict[_Block, list[_Block]] = field(default_factory=dict)

    def link(self, from_: _Block, to: _Block) -> None:
        self._succs.setdefault(from_, []).append(to)
        self._preds.setdefault(to, []).append(from_)

    def unlink(self, from_: _Block, to: _Block) -> None:
        self._succs.get(from_, []).remove(to)
        self._preds.get(to, []).remove(from_)

    def reverse(self) -> _CFGraph:
        result = _CFGraph()
        for b, p in self._preds.items():
            result._succs[b] = p  # pylint: disable=W0212
        for b, s in self._succs.items():
            result._preds[b] = s  # pylint: disable=W0212
        return result

    def preds(self, b: _Block) -> list[_Block]:
        return self._preds.setdefault(b, [])

    def succs(self, b: _Block) -> list[_Block]:
        return self._succs.setdefault(b, [])

    def __delitem__(self, key: _Block) -> None:
        del self._preds[key]
        del self._succs[key]


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
    _TERMINATORS: ClassVar = _BRANCH | {Opcode.RET}

    _COUNTER_LOCAL: ClassVar[_WriteTarget] = "local"
    _COUNTER_SCRVAR: ClassVar[_WriteTarget] = "script"
    _COUNTER_GLOBAL: ClassVar[_WriteTarget] = "global"

    _GLOBAL_LABEL: ClassVar = "global"

    def __init__(self, dis: Disassembly) -> None:
        self.dis = dis
        self.script: STScript

        self._stfuncs: list[STFunction] = []
        self._gdata = bytearray(self.dis.gdata)
        self._linenum = 0
        self._thisbase = 0
        self._write_target: _WriteTarget = "global"
        self._array_item_count = 0
        self._counters: dict[str, int] = {}

        self._max_doms_iters = 0
        self._emitted = []

        self._idom: _IDomTree = {}
        self._ipostdom: _IDomTree = {}

        self._stack: list = []
        self._labels: list[Label] = []
        self._locals: dict[_MemOffset, _LocalVar] = {}
        self._svars: dict[_MemOffset, _ScriptVar] = {}
        self._loops: set[_Block] = set()
        self._loop_jumps: list[int] = []

        self._sp: int = 0
        self._mar: int | FixedUpValue | STBinaryExpression = 0
        self._op = 0
        self._ax = 0
        self._bx = 0
        self._cx = 0
        self._dx = 0

        self._build_cfg()
        self._build_script()

    def _build_cfg(self) -> None:
        self._max_doms_iters = 0
        self._cfg_node_count = []

        # all our entry points are given as function names in the exports table.
        for func in self.dis.functions:
            logger.debug("building CFG for func %s$%d", func.name, func.nargs)
            leaders = self._find_leaders(func)
            blocks = self._build_blocks(func.instructions, leaders)
            cfg, omega = self._link_blocks(blocks)
            self._cfg_node_count.append((func.name, len(blocks)))

            stmts: list[STStatement] = []
            if not blocks:
                logger.debug("skipping empty function")
            else:
                blocks_list = list(blocks.values())
                blocks_list.append(omega)
                reverse_cfg = cfg.reverse()
                self._dom = self._find_dominators(blocks_list, cfg, blocks_list[0])
                self._postdom = self._find_dominators(blocks_list, reverse_cfg, omega)
                self._idom = self._idom_tree(self._dom)
                self._ipostdom = self._idom_tree(self._postdom)
                stmts = self._decompile(blocks_list, cfg)

            stblock = STBlock(stmts)
            stfunc = STFunction("function", func.name, [], stblock)
            if stfunc.type_ == "function" and isinstance(stmts[-1], STReturn):
                expr = stmts[-1].expr
                if isinstance(expr, STLiteral) and expr.value == 0:
                    stmts.pop()
            self._stfuncs.append(stfunc)

        if _DIAGNOSTICS:
            logger.info("max domtree iterations: %d", self._max_doms_iters)
            logger.info(
                "most CFG nodes: %s",
                sorted(self._cfg_node_count, key=lambda x: x[1], reverse=True)[:3],
            )
        gc.collect()  # force a GC to release unused memory

    def _find_leaders(self, func: Function) -> set[Instruction]:
        leaders: set[Instruction] = set()
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
        instructions: list[Instruction],
        leaders: set[Instruction],
    ) -> _CodeBlocks:
        blocks: list[list[Instruction]] = []
        current: list[Instruction] = []
        for inst in instructions:
            if inst in leaders and current:
                blocks.append(current)
                current = []
            current.append(inst)
        if current:
            blocks.append(current)
        return {b[0].offset: _Block(b) for b in blocks}

    def _link_blocks(self, blocks: _CodeBlocks) -> tuple[_CFGraph, _Block]:
        cfg = _CFGraph()
        addresses = sorted(blocks)
        for i, address in enumerate(addresses):
            block = blocks[address]
            last = block.instructions[-1]
            if last.opcode is Opcode.JMP or last.opcode in self._BRANCH:
                label = last.params[0]
                assert isinstance(label, Label)
                cfg.link(block, blocks[label.to])
                if last.opcode in self._BRANCH and i + 1 < len(addresses):
                    cfg.link(block, blocks[addresses[i + 1]])
            elif last.opcode == Opcode.RET:
                pass  # return is the exit node, no linking here.
            else:  # fallthrough
                if i + 1 < len(addresses):
                    cfg.link(block, blocks[addresses[i + 1]])

        # prune dead code
        for bl in blocks.values():
            if not cfg.preds(bl) and not cfg.succs(bl):
                del cfg[bl]

        # find leaves and insert a synthetic exit node
        leaves = {b for b in blocks.values() if not cfg.succs(b)}
        omega = _Block([])
        for l in leaves:
            cfg.link(l, omega)

        return cfg, omega

    def _find_dominators(
        self, blocks: list[_Block], graph: _CFGraph, alpha: _Block
    ) -> _Dominators:
        # worst case is quadratic; usually converges faster.
        # assume everything is dominated by everything
        doms = {b: set(blocks) for b in blocks}
        doms[alpha] = {alpha}  # except entry, which is only dominated by itself
        changed = True
        iters = 0
        while changed:  # loop until there are no updates to the tree
            iters += 1
            changed = False
            for k, v in doms.items():
                if k == alpha:
                    # entry only dominates itself by definition; no need to update.
                    continue
                preds = graph.preds(k)
                if not preds:
                    continue
                # find common dominators of this node's predecessors
                new_doms = {k} | set.intersection(*(doms[p] for p in preds))
                if new_doms != v:
                    doms[k] = new_doms
                    changed = True
        self._max_doms_iters = max(self._max_doms_iters, iters)
        return doms

    def _idom_tree(self, dom: _Dominators) -> _IDomTree:
        idom = {}
        for bl, dset in dom.items():
            strict = dset - {bl}
            if strict:
                idom[bl] = max(strict, key=lambda x: len(dom[x]))
        return idom

    def _decompile(self, blocks: list[_Block], cfg: _CFGraph) -> list[STStatement]:
        self._stack = []
        self._labels = []
        self._locals = {}
        self._loops = self._find_loops(blocks, cfg)

        alpha = blocks[0]
        return self._decomp_region(cfg, alpha)

    def _find_loops(self, blocks: list[_Block], cfg: _CFGraph) -> set[_Block]:
        loops: set[_Block] = set()
        for b in blocks:
            for s in cfg.succs(b):
                if s in self._dom[b]:
                    loops.add(s)
        return loops

    def _decomp_region(
        self, cfg: _CFGraph, in_block: _Block, stop: _Block | None = None
    ) -> list[STStatement]:
        stmts: list[STStatement] = []
        block: _Block | None = in_block
        while block is not None and block != stop:
            if not block.instructions:
                return stmts
            stmts.extend(self._emulate_block(block))

            if block in self._loops:
                block = self._decomp_loop(cfg, block, stmts)
                continue

            term = block.instructions[-1]
            if term.opcode is Opcode.RET:
                block = None
            elif term.opcode is Opcode.JMP:
                assert isinstance(term.params[0], Label)
                label = term.params[0]
                if self._loop_jumps and label.to == self._loop_jumps[-1]:
                    # if jumping to a loop break, emit a break statement.
                    stmts.append(STBreak())
                block = None
            elif term.opcode is Opcode.JZ:
                block = self._decomp_cond(cfg, block, stmts)
            else:
                assert len(cfg.succs(block)) == 1, (
                    "multiple successors for simple block"
                )
                block = cfg.succs(block)[0] if cfg.succs(block) else None
        return stmts

    def _decomp_cond(
        self, cfg: _CFGraph, block: _Block, stmts: list[STStatement]
    ) -> _Block | None:
        assert len(cfg.succs(block)) == 2, "cond node must have exactly 2 successors"
        skipped, taken = cfg.succs(block)
        merge = self._ipostdom[block]
        cond = self._make_expr(Register.AX)

        if taken == merge:
            then = STBlock(self._decomp_region(cfg, skipped, merge))
            stmts.append(STIf(cond, then, None))
            return merge
        if skipped == merge:
            then = STBlock(self._decomp_region(cfg, taken, merge))
            stmts.append(STIf(cond, then, None))
            return merge
        else:
            then = STBlock(self._decomp_region(cfg, taken, merge))

            else_stmts = self._decomp_region(cfg, skipped, merge)
            if len(else_stmts) == 1 and isinstance(else_stmts[0], STIf):
                else_ = else_stmts[0]
            elif else_stmts:
                else_ = STBlock(else_stmts)
            else:
                else_ = None

            stmts.append(STIf(cond, then, else_))
            return merge

    def _decomp_loop(
        self, cfg: _CFGraph, block: _Block, stmts: list[STStatement]
    ) -> _Block | None:
        succs = cfg.succs(block)
        if len(succs) == 1:
            # break
            block = succs[0]
            self._loop_jumps.append(block.instructions[0].offset)
        else:
            # cond + body
            assert len(succs) == 2
        body = cfg.succs(block)[1]
        after = self._ipostdom[block]

        cond = self._make_expr(Register.AX)
        body_stmts = self._decomp_region(cfg, body, after)
        body = STBlock(body_stmts)

        while_ = STWhile(cond, body)
        stmts.append(while_)
        return after

    def _emulate_block(self, block: _Block) -> list[STStatement]:
        stmts: list[STStatement] = []
        for inst in block.instructions:
            if isinstance(inst, Label):
                self._labels.append(inst)
                continue

            opc = inst.opcode
            if opc in self._BINOPS:
                ra = inst.as_reg(0)
                rb = inst.as_reg(1)
                a = self._make_expr(ra)
                b = self._make_expr(rb)
                expr = STBinaryExpression(a, b, self._BINOPS[opc])
                self._setr(ra, expr)

                if ra is Register.MAR and rb is Register.CX:
                    # array index, CX will hold an expression at this point
                    self._write_target = "array"
            elif opc in self._BINOPS_LITERAL:
                r = inst.as_reg(0)
                v = inst.as_int(1)
                if r is Register.SP:  # offsets only
                    if opc is Opcode.ADD:
                        self._sp += v
                    elif opc is Opcode.SUB:
                        self._sp -= v
                    else:
                        raise AssertionError
                else:
                    left = self._make_expr(r)
                    right = STLiteral(v)
                    expr = STBinaryExpression(left, right, self._BINOPS_LITERAL[opc])
                    self._setr(r, expr)
            elif opc is Opcode.LINENUM:
                self._linenum = inst.as_int(0)
            elif opc is Opcode.THISBASE:
                self._thisbase = inst.as_int(0)
            elif opc is Opcode.PUSHREG:
                rv = self._getr(inst.as_reg(0))
                self._stack.append(rv)
            elif opc is Opcode.POPREG:
                rv = inst.as_reg(0)
                v = self._stack.pop()
                self._setr(rv, v)
            elif opc is Opcode.REGTOREG:  # R1 -> R2
                rs = inst.as_reg(0)
                rd = inst.as_reg(1)
                self._setr(rd, self._getr(rs))

                if rs is Register.SP and rd is Register.MAR:
                    # local vars are written using SP
                    self._write_target = "local"
            elif opc is Opcode.LITTOREG:  # R <- A
                reg = inst.as_reg(0)
                v = inst.as_fup(1)
                self._setr(reg, v)

                if reg is Register.MAR:
                    if v.type_ is FixupType.GLOBAL_DATA:
                        # top-level script var
                        self._write_target = "script"
                    elif v.type_ is FixupType.IMPORT:
                        # true global var
                        self._write_target = "global"
            elif opc is Opcode.LOADSPOFFS:
                offset = inst.as_int(0)
                self._mar = self._sp - offset
                assert self._mar >= 0
                self._write_target = "local"  # writing to stack, so must be a local
            elif opc is Opcode.ZEROMEMORY:
                size = inst.as_int(0)
                self._emit_vardecl(size)
            elif opc is Opcode.MEMWRITEB:
                stmts.append(self._emit_assign(inst, 1))
            elif opc is Opcode.MEMWRITEW:
                stmts.append(self._emit_assign(inst, 2))
            elif opc is Opcode.MEMWRITE:
                stmts.append(self._emit_assign(inst, 4))
            elif opc is Opcode.CHECKBOUNDS:
                r = inst.as_reg(0)
                assert r is Register.AX  # i'm not sure if this is always the case
                v = inst.as_int(1)
                self._array_item_count = v
            elif opc is Opcode.MEMREADB:
                r = inst.as_reg(0)
                self._exec_varexpr(1, r)
            elif opc is Opcode.MEMREADW:
                r = inst.as_reg(0)
                self._exec_varexpr(2, r)
            elif opc is Opcode.MEMREAD:
                r = inst.as_reg(0)
                self._exec_varexpr(4, r)
            elif opc is Opcode.CALL:
                pass
            elif opc is Opcode.RET:
                ret = self._make_expr(Register.AX)
                stmts.append(STReturn(ret))
            else:
                pass
                # raise NotImplementedError(opc)
        return stmts

    def _emit_vardecl(self, size: int) -> STVarDeclaration:
        # globals are initialized by the compiler, and local variables are the
        # only other place where declaration without definition is legal.
        assert self._write_target == "local", "illegal target for local"

        # again, we can only declare locals here, so MAR should have the value
        # of SP, which is guaranteed to be in int.
        assert isinstance(self._mar, int), "MAR has non-int before declaring local"

        lvar = self._get_local(self._mar, size)
        assert lvar.is_newly_created, "declaring an existing local"
        type_ = self._guess_type_from_size(size)
        stmt = STVarDeclaration(type_, lvar.name)
        lvar.declaration = stmt
        return stmt

    def _emit_assign(self, inst: Instruction, size: int) -> STAssignment:
        # MAR + write target determine the LHS
        target: STAssignmentTarget
        match self._write_target:
            case "local":
                assert isinstance(self._mar, int), "writing to a local with non-int MAR"
                lvar = self._get_local(self._mar, size)
                type_ = None
                if lvar.is_newly_created:
                    type_ = self._guess_type_from_size(lvar.size)
                else:
                    assert lvar.declaration is not None, (
                        "variable must already be declared"
                    )
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
                else:
                    raise TypeError
            case "script":
                assert isinstance(self._mar, FixedUpValue)
                assert self._mar.type_ == FixupType.GLOBAL_DATA
                svar = self._get_svar(self._mar.original, size)
                assert svar.type_ is not None
                target = STVarAssignTarget(svar.name, None, svar.type_)

        # R determines the value
        r = inst.as_reg(0)
        v = self._make_expr(r)
        return STAssignment(target, v)

    def _exec_varexpr(self, size: int, r: Register) -> None:
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
        elif isinstance(rv, FixedUpValue):
            if rv.type_ == FixupType.NO_FIXUP:
                return STLiteral(rv.original)
            elif rv.type_ == FixupType.IMPORT:
                return STLiteral(str(rv.fixed))
            raise NotImplementedError
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
