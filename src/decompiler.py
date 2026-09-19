from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import ClassVar

from disassembler import Disassembly, Function, Instruction, Label, Opcode, Register
from syntax_tree import STFunction, STReturn, STScript, STStatement

debug: bool = True  # pylint: disable=invalid-name
logger = logging.getLogger(__name__)
logger.disabled = not debug

type _Dominators = dict[_Block, set[_Block]]
type _IDomTree = dict[_Block, _Block]


@dataclass
class _VM:
    ax: int = 0

    def getreg(self, register: Register) -> int:
        if register is Register.AX:
            return self.ax
        else:
            raise NotImplementedError

    def setreg(self, register: Register, value) -> None:
        if register is Register.AX:
            self.ax = value
        else:
            raise NotImplementedError


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
    stmts: list[STStatement]
    vm: _VM

    def __init__(self, func: Function) -> None:
        self.func = func
        self.stmts = []


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
    preds: dict[_Block, list[_Block]] = field(default_factory=dict)
    succs: dict[_Block, list[_Block]] = field(default_factory=dict)

    def link(self, from_: _Block, to: _Block) -> None:
        self.succs.setdefault(from_, []).append(to)
        self.preds.setdefault(to, []).append(from_)

    def unlink(self, from_: _Block, to: _Block) -> None:
        self.succs.get(from_, []).remove(to)
        self.preds.get(to, []).remove(from_)

    def reverse(self) -> _CFGraph:
        result = _CFGraph()
        for b, p in self.preds.items():
            result.succs[b] = p  # pylint: disable=protected-access
        for b, s in self.succs.items():
            result.preds[b] = s  # pylint: disable=protected-access
        return result

    def getpreds(self, b: _Block) -> list[_Block]:
        return self.preds.setdefault(b, [])

    def getsuccs(self, b: _Block) -> list[_Block]:
        return self.succs.setdefault(b, [])

    def __delitem__(self, key: _Block) -> None:
        del self.preds[key]
        del self.succs[key]


class Decompiler:
    _BRANCH: ClassVar[set[Opcode]] = {
        Opcode.JZ,
        Opcode.JNZ,
    }

    _TERMINATORS: ClassVar[set[Opcode]] = {
        Opcode.JMP,
        Opcode.JZ,
        Opcode.JNZ,
        Opcode.RET,
    }

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

        logger.debug("recovering source code")
        fs.vm = _VM()
        self._normalize_edges(fs)
        self._find_loop_headers(fs)
        self._recover(fs)

        return STFunction(func.name, fs.stmts)

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
            if last.opcode in self._BRANCH:
                label = last.params[0]
                assert isinstance(label, Label)
                cfg.link(block, blocks[label.to])
                if i + 1 < len(addresses):
                    cfg.link(block, blocks[addresses[i + 1]])
            elif last.opcode is Opcode.JMP:
                label = last.params[0]
                assert isinstance(label, Label)
                cfg.link(block, blocks[label.to])
            elif last.opcode == Opcode.RET:
                pass  # return is the exit node, no linking here.
            else:  # fallthrough
                if i + 1 < len(addresses):
                    cfg.link(block, blocks[addresses[i + 1]])

        # prune dead code
        for bl in blocks.values():
            if not cfg.getpreds(bl) and not cfg.getsuccs(bl):
                del cfg[bl]

        # find leaves and insert a synthetic exit node
        leaves = {b for b in blocks.values() if not cfg.getsuccs(b)}
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
                preds = graph.getpreds(k)
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

    def _normalize_edges(self, fs: _FuncState) -> None:
        cfg = fs.cfg

        # first, collapse trampoline chains.
        for block in cfg.succs:
            succs = cfg.getsuccs(block)
            for i, succ in enumerate(succs):
                while len(succ.ins) == 1 and succ.ins[0].opcode is Opcode.JMP:
                    ss = cfg.getsuccs(succ)
                    assert len(ss) == 1, "trampoline must have exactly 1 successor"
                    succ = ss[0]
                    succs[i] = succ

        # then, collapse loop breaks.
        for block in fs.blocks_list:
            ins = block.ins[-2:]
            if len(ins) < 2:
                continue

            first, second = ins
            if first.opcode is not Opcode.LITTOREG:
                continue
            if first.as_reg(0) is not Register.AX:
                continue
            if first.as_int(1) != 0:
                continue
            if second.opcode is not Opcode.JMP:
                continue

            succs = cfg.getsuccs(block)
            assert len(succs) == 1, "loop break must have exactly 1 successor"

            jump = succs[0]
            ss = cfg.getsuccs(jump)
            assert len(ss) == 1, "loop break trampoline must have exactly 1 successor"

            succs[0] = ss[0]

    def _find_loop_headers(self, fs: _FuncState) -> None:
        loops: set[_Block] = set()
        fs.loop_headers = loops
        for b in fs.blocks_list:
            for s in fs.cfg.getsuccs(b):
                if s in fs.dom[b]:
                    loops.add(s)

    def _recover(self, fs: _FuncState) -> None:
        # sort blocks by depth so innermost blocks are processed first.
        blocks = sorted(fs.blocks_list, key=lambda b: len(fs.dom[b]), reverse=True)
        for b in blocks:
            self._pattern_match(fs, b)

    def _pattern_match(self, fs: _FuncState, block: _Block) -> None:
        term = block.ins[-1]
        if term.opcode is Opcode.RET:
            self._emulate(fs, block)
            fs.stmts.append(STReturn(fs.vm.ax))
        else:
            raise RuntimeError("Unknown bytecode pattern")

    def _emulate(self, fs: _FuncState, block: _Block) -> None:
        vm = fs.vm
        for ins in block.ins:
            if ins.opcode is Opcode.LITTOREG:
                reg = ins.as_reg(0)
                lit = ins.as_int(1)
                vm.setreg(reg, lit)

    def _make_script(self, funcs: list[STFunction]) -> STScript:
        return STScript(funcs)
