import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from decompiler.disassembler import Function, Instruction, Opcode, Register
from decompiler.syntax_tree import (
    StDoWhile,
    StIfElse,
    StStatement,
    StSwitch,
    StWhile,
)

if TYPE_CHECKING:
    from decompiler._internal.recovery import Structurer

logger = logging.getLogger(__name__)

type Offset = int
type Dominators = dict[Block, set[Block]]
type ImDominators = dict[Block, Block]
type DomTree = dict[Block, list[Block]]

_JUMPS = {
    Opcode.JMP,
    Opcode.JZ,
    Opcode.JNZ,
}

_COND_JUMPS = {
    Opcode.JZ,
    Opcode.JNZ,
}

_SWITCH_CMP = {
    Opcode.NOTEQUAL,
    Opcode.STRINGSNOTEQ,
}


@dataclass
class Block:
    ins: list[Instruction] = field(default_factory=list)
    term: Instruction = field(init=False)

    def __post_init__(self) -> None:
        if self.ins:
            self.term = self.ins[-1]

    def __repr__(self) -> str:
        ins: str
        if len(self.ins) == 0:
            ins = ""
        elif len(self.ins) == 1:
            ins = " " + str(self.ins[0])
        elif len(self.ins) == 2:
            ins = f" {self.ins[0]}; {self.ins[1]}"
        else:
            ins = f" {self.ins[0]}..{self.ins[-1]}"

        return f"<Block{ins}>"

    def __hash__(self) -> int:
        return id(self.ins)

    def __len__(self) -> int:
        return len(self.ins)


@dataclass
class Match(ABC):
    header: Block
    join: Block

    @abstractmethod
    def structure(self, structurer: Structurer) -> StStatement:
        raise NotImplementedError


@dataclass
class IfMatch(Match):
    then: Block

    def structure(self, structurer: Structurer) -> StIfElse:
        stmts = structurer.build_region(self.then, self.join)
        return StIfElse(stmts)


@dataclass
class IfElseMatch(Match):
    then: Block
    else_: Block

    def structure(self, structurer: Structurer) -> StIfElse:
        then_stmts = structurer.build_region(self.then, self.join)
        else_stmts = structurer.build_region(self.else_, self.join)
        return StIfElse(then_stmts, else_stmts)


@dataclass
class SwitchMatch(Match):
    cases: dict[Block, Block]
    default: Block | None

    def structure(self, structurer: Structurer) -> StSwitch:
        cases: list[list[StStatement]] = []
        for c in self.cases.values():
            cases.append(structurer.build_region(c, self.join))

        default = None
        if self.default is not None:
            default = structurer.build_region(self.default, self.join)

        return StSwitch(cases, default)


@dataclass
class WhileMatch(Match):
    body: Block
    jump: Block

    def structure(self, structurer: Structurer) -> StWhile:
        stmts = structurer.build_region(self.body, self.join)
        return StWhile(stmts)


@dataclass
class DoWhileMatch(Match):
    cond: Block

    def structure(self, structurer: Structurer) -> StDoWhile:
        stmts = structurer.build_region(self.header, self.join)
        return StDoWhile(stmts)


@dataclass
class CFG:
    entry: Block
    exit: Block
    pred: dict[Block, list[Block]] = field(default_factory=lambda: defaultdict(list))
    succ: dict[Block, list[Block]] = field(default_factory=lambda: defaultdict(list))

    def __post_init__(self) -> None:
        assert len(self.pred) == len(self.succ)
        assert self.entry not in self.pred
        assert self.exit not in self.succ

    def link(self, a: Block, b: Block) -> None:
        self.succ[a].append(b)
        self.pred[b].append(a)

    def fallthrough(self, b: Block) -> Block:
        return self.succ[b][0]

    def followed(self, b: Block) -> Block:
        return self.succ[b][1]

    def is_dead(self, b: Block) -> bool:
        return b != self.entry and not self.pred[b]

    def reversed(self) -> CFG:
        result = CFG(self.exit, self.entry)
        blocks = set(self.pred) | set(self.succ)
        for bl in blocks:
            result.succ[bl].extend(self.pred[bl])
            result.pred[bl].extend(self.succ[bl])
        return result


@dataclass(init=False)
class ControlFlow:
    func: Function
    leaders: set[Instruction]
    blocks: dict[Offset, Block]
    blocks_list: list[Block]
    cfg: CFG
    reverse_cfg: CFG

    dom: Dominators  # dominators
    idom: dict[Block, Block]  # immediate dominators
    pdom: Dominators  # postdominators
    ipdom: dict[Block, Block]  # immediate postdominators

    loops: set[Block]
    headers: dict[Block, Match]
    trampolines: dict[Block, Block]

    def blocks_between(self, start: Block, stop: Block) -> list[Block]:
        result = []
        for bl in self.blocks_list:
            if start in self.dom[bl] and stop in self.pdom[bl]:
                result.append(bl)
        return result


class _Matcher:
    def __init__(self, loops: set[Block]) -> None:
        self.loops = loops
        self._matched: set[Block] = set()
        self._matchers = (
            self._match_while,
            self._match_do_while,
            self._try_match_switch,
            self._match_if_else,
            self._match_if,
        )

    def find_headers(self, cf: ControlFlow) -> dict[Block, Match]:
        matches: dict[Block, Match] = {}
        # process innermost blocks first.
        sorted_ = sorted(cf.blocks_list, key=lambda b: len(cf.dom[b]), reverse=True)
        for bl in sorted_:
            if bl != cf.cfg.entry and not cf.cfg.pred[bl]:
                continue
            if bl in self._matched:
                continue
            if not self._is_potential_header(bl):
                continue
            for matcher in self._matchers:
                result = matcher(bl, cf)
                if result is not None:
                    matches[result.header] = result
                    break
        for l in self.loops:
            assert isinstance(matches[l], WhileMatch | DoWhileMatch)
        return matches

    def _is_potential_header(self, bl: Block) -> bool:
        return bl in self.loops or bl.term.opcode in _JUMPS

    def _match_while(self, bl: Block, cf: ControlFlow) -> Match | None:
        if bl not in self.loops:
            return None

        jump: Block = bl
        # depending on whether there's a break in the body, it may or
        # may not end with a JZ, so we need to check the fallthrough too.
        if bl.term.opcode is not Opcode.JZ:
            s = cf.cfg.fallthrough(bl)
            if not s.ins:
                return None
            if s.term.opcode is not Opcode.JZ:
                return None
            jump = s

        join = cf.ipdom[bl]
        body = cf.cfg.fallthrough(jump)

        if body.term.opcode is not Opcode.JMP:
            return None
        if body.term.get_label().to != bl.ins[0].code_offset:
            return None

        return WhileMatch(bl, join, body, jump)

    def _match_do_while(self, bl: Block, cf: ControlFlow) -> DoWhileMatch | None:
        if bl.term.opcode is not Opcode.JNZ:
            return None
        body = cf.cfg.followed(bl)
        if body not in self.loops:
            return None
        join = cf.ipdom[bl]
        assert cf.cfg.fallthrough(bl) is join
        cond = bl
        return DoWhileMatch(body, join, cond)

    def _try_match_switch(self, bl: Block, cf: ControlFlow) -> SwitchMatch | None:
        result = self._match_switch(bl, cf)
        if result is None:
            try:
                pred = cf.cfg.pred[bl][0]
                pred = cf.cfg.pred[pred][0]
            except IndexError:
                return None
            return self._match_switch(pred, cf)
        return result

    def _match_switch(self, bl: Block, cf: ControlFlow) -> SwitchMatch | None:
        # all switches start with two consecutive JMPs (dispatch + break trampoline).
        # do-while also starts with two jumps, but at this point all do-whiles have
        # alrady been matched.
        if len(bl) < 2:
            return None
        i1 = bl.term
        if i1.opcode is not Opcode.JMP:
            return None
        try:
            i2 = cf.func.instr_list[i1.index + 1]
            if i2.opcode is not Opcode.JMP:
                return None

            # also ensure there's a move into BX.
            mov = cf.func.instr_list[i1.index - 1]
            if mov.opcode is not Opcode.REGTOREG:
                return None
            if mov.get_reg(0) is not Register.AX:
                return None
            if mov.get_reg(1) is not Register.BX:
                return None
        except IndexError:
            return None

        self._matched.add(bl)
        # the second is the join of the switch.
        join = cf.blocks[i2.get_label().to]
        # the first jump is the beginning of the dispatch block.
        dispatch = cf.blocks[i1.get_label().to]
        if dispatch.term.opcode not in (Opcode.JZ, Opcode.JMP):
            return SwitchMatch(bl, join, {}, None)  # empty switch

        # walk the dispatch chain and discover all the labels.
        labels = []
        b = dispatch
        while self._is_dispatch_block(b):
            labels.append(b)
            b = cf.cfg.succ[b][0]

        # check if we stopped at the jump to the default case.
        default: Block | None = None
        if b.term.opcode is Opcode.JMP:
            default = cf.cfg.succ[b][0]

        self._matched.add(dispatch)
        if default is not None:
            self._matched.add(default)
        cases = {l: cf.cfg.followed(l) for l in labels}
        for case, body in cases.items():
            self._matched.add(case)
            self._matched.add(body)
        return SwitchMatch(bl, join, cases, default)

    def _is_dispatch_block(self, bl: Block) -> bool:
        return (
            len(bl.ins) >= 2
            and bl.ins[-2].opcode in _SWITCH_CMP
            and bl.term.opcode is Opcode.JZ
        )

    def _match_if_else(
        self, bl: Block, cf: ControlFlow
    ) -> IfElseMatch | IfMatch | None:
        if bl.term.opcode is not Opcode.JZ:
            return None
        then = cf.cfg.fallthrough(bl)
        else_ = cf.cfg.followed(bl)
        join = cf.ipdom[bl]
        if then == join or else_ == join:
            return None
        if join == cf.cfg.exit:
            return IfMatch(bl, join, then)
        return IfElseMatch(bl, join, then, else_)

    def _match_if(self, bl: Block, cf: ControlFlow) -> IfMatch | None:
        if bl.term.opcode is not Opcode.JZ:
            return None
        body = cf.cfg.fallthrough(bl)
        skip = cf.cfg.followed(bl)
        join = cf.ipdom[bl]
        if skip != join:
            return None
        return IfMatch(bl, join, body)


def analyze(func: Function) -> ControlFlow:
    cf = ControlFlow()
    cf.func = func
    cf.leaders = _find_leaders(func)
    cf.blocks = _make_blocks(func, cf.leaders)
    cf.blocks_list = list(cf.blocks.values())
    cf.cfg = _build_cfg(cf.blocks)
    cf.reverse_cfg = cf.cfg.reversed()
    cf.dom = _find_dominators(cf.cfg, cf.blocks_list, cf.cfg.entry)
    cf.idom = _compute_idom(cf.dom)
    cf.pdom = _find_dominators(cf.reverse_cfg, cf.blocks_list, cf.cfg.exit)
    cf.ipdom = _compute_idom(cf.pdom)
    _resolve_jump_chains(cf)
    cf.loops = _find_loops(cf.cfg, cf.blocks_list, cf.dom)
    cf.headers = _Matcher(cf.loops).find_headers(cf)
    return cf


def _find_leaders(func: Function) -> set[Instruction]:
    leaders: set[Instruction] = set()
    leaders.add(func.instr_list[0])
    for idx, ins in enumerate(func.instr_list):
        is_jump = ins.opcode in _JUMPS
        is_ret = ins.opcode is Opcode.RET
        if is_jump:
            l = ins.get_label()
            leaders.add(func.instructions[l.to])
        if (is_jump or is_ret) and idx + 1 < len(func.instr_list):  # fallthrough
            leaders.add(func.instr_list[idx + 1])
    return leaders


def _make_blocks(func: Function, leaders: set[Instruction]) -> dict[Offset, Block]:
    blocks = {}
    current: list[Instruction] = []

    def flush() -> None:
        nonlocal current
        blocks[current[0].code_offset] = Block(current)
        current = []

    for ins in func.instr_list:
        if ins in leaders and current:
            flush()
        current.append(ins)
    if current:
        flush()

    return blocks


def _build_cfg(blocks: dict[Offset, Block]) -> CFG:
    offsets = sorted(blocks)
    exit_ = Block()
    cfg = CFG(blocks[offsets[0]], exit_)

    for i, off in enumerate(offsets):
        bl = blocks[off]
        if bl.term.opcode in _JUMPS:
            # fallthrough first
            if bl.term.opcode in _COND_JUMPS:
                cfg.link(bl, blocks[offsets[i + 1]])

            # then jump target
            l = bl.term.get_label()
            cfg.link(bl, blocks[l.to])
        elif bl.term.opcode is Opcode.RET:
            cfg.link(bl, exit_)
        else:  # fallthrough
            # we don't check for OOB since the last block
            # is guaranteed to be terminate with a return.
            cfg.link(bl, blocks[offsets[i + 1]])

    return cfg


def _find_dominators(cfg: CFG, blocks: list[Block], entry: Block) -> Dominators:
    """
    Implements a naive algorithm for finding the dominators
    in a CFG. Has quadratic complexity O(V*E) in the worst case.
    In practice, usually converges in just a few runs.
    """
    dom: Dominators = {b: set(blocks) for b in blocks}
    dom[entry] = {entry}

    changed = True
    iters = 0
    while changed:
        iters += 1
        changed = False
        for bl, bl_dom in dom.items():
            if bl is cfg.entry:
                continue  # skip the entry; it trivially dominates everything.
            pred = cfg.pred[bl]
            if not pred:
                continue  # can happen with dead code.
            # compute the dominator equation
            new_dom = {bl} | set.intersection(*(dom[p] for p in pred))
            if new_dom != bl_dom:
                changed = True
                dom[bl] = new_dom

    logger.debug("max dominators iterations: %d", iters)
    return dom


def _compute_idom(dom: Dominators) -> ImDominators:
    idom: ImDominators = {}
    for bl, bl_dom in dom.items():
        strict = bl_dom - {bl}
        if strict:
            idom[bl] = max(strict, key=lambda b: len(dom[b]))
    return idom


def _resolve_jump_chains(cf: ControlFlow) -> None:
    result = {}
    for bl in cf.blocks_list:
        s = bl
        chain = False
        while True:
            if len(s.ins) == 1 and s.term.opcode is Opcode.JMP:
                s = cf.cfg.succ[s][0]
                chain = True
            else:
                break
        if chain:
            result[bl] = s
    cf.trampolines = result


def _find_loops(cfg: CFG, blocks: list[Block], dom: Dominators) -> set[Block]:
    result = set()
    for bl in blocks:
        for suc in cfg.succ[bl]:
            if not cfg.pred[bl]:
                continue  # skip dead jumps from unbroken do-while loops.
            if suc in dom[bl]:
                result.add(suc)
    return result
