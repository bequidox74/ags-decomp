from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import ClassVar

from disassembler import Disassembly, Function, Instruction, Label, Opcode
from syntax_tree import STFunction, STScript

debug: bool = True  # pylint: disable=invalid-name
logger = logging.getLogger(__name__)
logger.disabled = not debug

type _Dominators = dict[_Block, set[_Block]]
type _IDomTree = dict[_Block, _Block]


@dataclass(init=False)
class _FuncState:
    func: Function
    leaders: set[Instruction]
    blocks: dict[int, _Block]
    blocks_list: list[_Block]

    cfg: _CFGraph
    revcfg: _CFGraph
    alpha: _Block
    omega: _Block

    dom: _Dominators
    pdom: _Dominators
    idom: _IDomTree
    ipdom: _IDomTree

    loop_headers: set[_Block]

    def __init__(self, func: Function) -> None:
        self.func = func


@dataclass
class _Block:
    ins: list[Instruction]

    def __hash__(self) -> int:
        return id(self.ins)

    def __eq__(self, value: object) -> bool:
        return self is value

    def __repr__(self) -> str:
        if self.ins:
            first = str(self.ins[0])
            last = str(self.ins[-1])
            return f"<Block {first}..{last}>"
        else:
            return "<Block>"


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
            result._succs[b] = p  # pylint: disable=protected-access
        for b, s in self._succs.items():
            result._preds[b] = s  # pylint: disable=protected-access
        return result

    def preds(self, b: _Block) -> list[_Block]:
        return self._preds.setdefault(b, [])

    def succs(self, b: _Block) -> list[_Block]:
        return self._succs.setdefault(b, [])

    def __delitem__(self, key: _Block) -> None:
        del self._preds[key]
        del self._succs[key]


class Decompiler:
    _BRANCH: ClassVar[set[Opcode]] = {
        Opcode.JMP,
        Opcode.JZ,
        Opcode.JNZ,
    }
    _TERMINATORS: ClassVar[set[Opcode]] = _BRANCH | {Opcode.RET}

    def __init__(self, disassembly: Disassembly) -> None:
        self.disassembly = disassembly
        self.script: STScript

        self._max_doms_iters: int = 0

        self._decompile()

    def _decompile(self) -> None:
        funcs: list[STFunction] = []
        for f in self.disassembly.functions:
            funcs.append(self._do_func(f))

        self.script = self._make_script(funcs)

    def _do_func(self, func: Function) -> STFunction:
        logger.info("decompiling %s", func.mangled_name)
        fs = _FuncState(func)

        logger.debug("building CFG")
        self._find_leaders(fs)
        self._build_blocks(fs)
        self._link_blocks(fs)

        logger.debug("building domtrees")
        fs.dom = self._dominators(fs.blocks_list, fs.cfg, fs.alpha)
        fs.pdom = self._dominators(fs.blocks_list, fs.revcfg, fs.omega)
        fs.idom = self._idom_tree(fs.dom)
        fs.ipdom = self._idom_tree(fs.pdom)

        logger.debug("building AST")
        self._find_loop_headers(fs)

        return STFunction(func.name)

    def _find_leaders(self, fs: _FuncState) -> None:
        func = fs.func
        leaders: set[Instruction] = set()
        fs.leaders = leaders
        if not func.instructions:
            return

        leaders.add(func.instructions[0])  # the first instruction is a leader
        for i, inst in enumerate(func.instructions):
            if inst.opcode in self._BRANCH:
                target = inst.params[0]
                assert isinstance(target, Label)
                leaders.add(func.lookup[target.to])
            if inst.opcode in self._TERMINATORS and i + 1 < len(func.instructions):
                leaders.add(func.instructions[i + 1])

        assert len(leaders) > 0, "function must have at least one leader"

    def _build_blocks(self, fs: _FuncState) -> None:
        blocks: list[list[Instruction]] = []

        current: list[Instruction] = []
        for inst in fs.func.instructions:
            if inst in fs.leaders and current:
                blocks.append(current)
                current = []
            current.append(inst)
        if current:
            blocks.append(current)

        assert len(blocks) > 0, "function must have at least one block"
        fs.blocks = {b[0].offset.script: _Block(b) for b in blocks}
        fs.blocks_list = list(fs.blocks.values())

    def _link_blocks(self, fs: _FuncState) -> None:
        cfg = _CFGraph()

        blocks = fs.blocks
        addresses = sorted(blocks)
        for i, address in enumerate(addresses):
            block = blocks[address]
            last = block.ins[-1]
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

        fs.cfg = cfg
        fs.revcfg = fs.cfg.reverse()
        fs.alpha = blocks[addresses[0]]
        fs.omega = omega

    def _dominators(
        self, blocks: list[_Block], graph: _CFGraph, entry: _Block
    ) -> _Dominators:
        # worst case is quadratic; usually converges faster.
        # initially, assume everything is dominated by everything.
        doms = {b: set(blocks) for b in blocks}
        doms[entry] = {entry}  # except entry, which is only dominated by itself
        changed = True
        iters = 0

        while changed:  # loop until there are no updates to the tree
            iters += 1
            changed = False
            for k, v in doms.items():
                if k == entry:
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

    def _idom_tree(self, doms: _Dominators) -> _IDomTree:
        idom = {}
        for bl, dset in doms.items():
            strict = dset - {bl}
            if strict:
                idom[bl] = max(strict, key=lambda x: len(doms[x]))
        return idom

    def _find_loop_headers(self, fs: _FuncState) -> None:
        loops: set[_Block] = set()
        fs.loop_headers = loops
        for b in fs.blocks_list:
            for s in fs.cfg.succs(b):
                if s in fs.dom[b]:
                    loops.add(s)

    def _make_script(self, funcs: list[STFunction]) -> STScript:
        return STScript(funcs)
