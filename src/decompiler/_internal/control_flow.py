import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from decompiler.disassembler import Function, Instruction, Opcode

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

_MATCHERS: tuple[Callable[[Block, ControlFlow], Match | None], ...]


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


@dataclass
class Match:
    header: Block
    join: Block


@dataclass
class IfMatch(Match):
    then: Block


@dataclass
class IfElseMatch(Match):
    then: Block
    else_: Block


@dataclass
class SwitchMatch(Match):
    cases: dict[Block, Block]


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

    def reversed(self) -> CFG:
        result = CFG(self.exit, self.entry)
        blocks = set(self.pred) | set(self.succ)
        for bl in blocks:
            result.succ[bl].extend(self.pred[bl])
            result.pred[bl].extend(self.succ[bl])
        return result


@dataclass(init=False)
class ControlFlow:
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

    def blocks_between(self, start: Block, stop: Block) -> list[Block]:
        result = []
        for bl in self.blocks_list:
            if start in self.dom[bl] and stop in self.pdom[bl]:
                result.append(bl)
        return result


class Matcher:
    def __init__(self) -> None:
        self._matched: set[Block] = set()
        self._matchers = (
            self._match_switch,
            self._match_if_else,
            self._match_if,
        )

    def find_headers(self, cf: ControlFlow) -> dict[Block, Match]:
        matches: dict[Block, Match] = {}
        # process innermost blocks first.
        sorted_ = sorted(cf.blocks_list, key=lambda b: len(cf.dom[b]), reverse=True)
        for bl in sorted_:
            if bl in self._matched:
                continue
            if not self._is_potential_header(bl):
                continue
            for matcher in self._matchers:
                result = matcher(bl, cf)
                if result is not None:
                    matches[bl] = result
                    break
        return matches

    def _is_potential_header(self, bl: Block) -> bool:
        return bl.term.opcode in _COND_JUMPS

    def _match_switch(self, bl: Block, cf: ControlFlow) -> Match | None:
        if len(bl.ins) < 2:
            return None
        join = cf.ipdom[bl]

        # case conditions are nested inside one another in the dominator tree,
        # so given our order of iteration (innermost-first), we should assume
        # the current block is the last in the chain.
        cases: list[Block] = []
        bodies: list[Block] = []
        s = bl
        while s is not None:
            if len(s.ins) < 2:
                break
            cmp = s.ins[-2]
            if cmp.opcode not in _SWITCH_CMP:
                break
            cases.append(s)
            bodies.append(cf.cfg.followed(s))
            self._matched.add(s)
            s = cf.cfg.pred[s][0]
        cases = cases[::-1]
        bodies = bodies[::-1]

        return SwitchMatch(bl, join, {c[0]: c[1] for c in zip(cases, bodies)})

    def _match_if_else(self, bl: Block, cf: ControlFlow) -> Match | None:
        then = cf.cfg.fallthrough(bl)
        else_ = cf.cfg.followed(bl)
        join = cf.ipdom[bl]
        if then == join or else_ == join:
            return None
        self._matched.add(bl)
        if join == cf.cfg.exit:
            return IfMatch(bl, join, then)
        return IfElseMatch(bl, join, then, else_)

    def _match_if(self, bl: Block, cf: ControlFlow) -> Match | None:
        body = cf.cfg.fallthrough(bl)
        skip = cf.cfg.followed(bl)
        join = cf.ipdom[bl]
        if skip != join:
            return None
        self._matched.add(bl)
        return IfMatch(bl, join, body)


def analyze(func: Function) -> ControlFlow:
    cf = ControlFlow()
    cf.leaders = _find_leaders(func)
    cf.blocks = _make_blocks(func, cf.leaders)
    cf.blocks_list = list(cf.blocks.values())
    cf.cfg = _build_cfg(cf.blocks)
    cf.reverse_cfg = cf.cfg.reversed()
    cf.dom = _find_dominators(cf.cfg, cf.blocks_list, cf.cfg.entry)
    cf.idom = _compute_idom(cf.dom)
    cf.pdom = _find_dominators(cf.reverse_cfg, cf.blocks_list, cf.cfg.exit)
    cf.ipdom = _compute_idom(cf.pdom)
    cf.loops = _find_loops(cf.cfg, cf.blocks_list, cf.dom)
    cf.headers = Matcher().find_headers(cf)
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
        blocks[current[0].func_offset] = Block(current)
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


def _find_loops(cfg: CFG, blocks: list[Block], dom: Dominators) -> set[Block]:
    result = set()
    for bl in blocks:
        for suc in cfg.succ[bl]:
            if suc in dom[bl]:
                result.add(suc)
    return result
