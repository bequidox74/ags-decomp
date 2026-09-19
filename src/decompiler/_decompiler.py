import logging
from typing import ClassVar

from disassembler import Disassembly, Function, Instruction, Label, Opcode, Register

from ._cfg import _Block, _CFGraph
from ._func_state import _VM, _Dominators, _FuncState, _IDomTree, _Region
from ._match import MATCHERS
from ._syntax_tree import *

debug: bool = True  # pylint: disable=invalid-name
logger = logging.getLogger(__name__)
logger.disabled = not debug


class Decompiler:
    _BRANCH: ClassVar[set[Opcode]] = {
        Opcode.JZ,
        Opcode.JNZ,
    }

    _JUMPS: ClassVar[set[Opcode]] = {
        Opcode.JMP,
        Opcode.JZ,
        Opcode.JNZ,
    }

    _TERMINATORS: ClassVar[set[Opcode]] = _JUMPS | {Opcode.RET}

    _SUCC_TAKEN: ClassVar = 0
    _SUCC_FALLTHROUGH: ClassVar = 1

    def __init__(self, disassembly: Disassembly) -> None:
        self.disassembly = disassembly
        self.script: StScript

        self._max_doms_iters: int = 0
        self._has_unknown: bool = False

        self._decompile()

    def _decompile(self) -> None:
        funcs: list[StFunction] = []
        for f in self.disassembly.functions:
            funcs.append(self._do_func(f))

        self.script = self._make_script(funcs)

    def _do_func(self, func: Function) -> StFunction:
        logger.info("decompiling %s", func.mangled_name)
        fs = _FuncState(func)

        self._find_leaders(fs)
        self._build_blocks(fs)
        self._link_blocks(fs)

        logger.debug("finding dominators")
        fs.dom = self._dominators(fs.blocks_list, fs.cfg, fs.alpha)
        fs.idom = self._idom_tree(fs.dom)

        logger.debug("finding postdominators")
        fs.pdom = self._dominators(fs.blocks_list, fs.revcfg, fs.omega)
        fs.ipdom = self._idom_tree(fs.pdom)

        fs.vm = _VM()
        self._normalize_edges(fs)
        self._find_loop_headers(fs)
        self._recover(fs)

        if self._has_unknown:
            logger.warning(
                "unknown bytecode patterns encountered in func %s", fs.func.mangled_name
            )

        return StFunction(func.name, fs.stmts)

    def _find_leaders(self, fs: _FuncState) -> None:
        logger.debug("finding leaders")
        func = fs.func
        leaders: set[Instruction] = set()
        fs.leaders = leaders
        if not func.instructions:
            return

        leaders.add(func.instructions[0])  # the first instruction is a leader
        for i, inst in enumerate(func.instructions):
            if inst.opcode is Opcode.JMP or inst.opcode in self._BRANCH:
                target = inst.params[0]
                assert isinstance(target, Label)
                leaders.add(func.lookup[target.to])
            if inst.opcode in self._TERMINATORS and i + 1 < len(func.instructions):
                leaders.add(func.instructions[i + 1])

        assert len(leaders) > 0, "function must have at least one leader"

    def _build_blocks(self, fs: _FuncState) -> None:
        logger.debug("building bytecode blocks")
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
        logger.debug("linking blocks into a CFG")
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
        prune_count = 0
        for bl in blocks.values():
            if not cfg.getpreds(bl) and not cfg.getsuccs(bl):
                prune_count += 1
                del cfg[bl]
        logger.debug("pruned %d dead code blocks", prune_count)

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
        logger.debug("normalizing edges")
        cfg = fs.cfg
        trampolines: dict[_Block, _Block] = {}
        fs.trampolines = trampolines

        # first, collapse trampoline chains.
        for block in cfg.succs:
            succs = cfg.getsuccs(block)
            for succ in succs:
                while len(succ.ins) == 1 and succ.ins[0].opcode is Opcode.JMP:
                    ss = cfg.getsuccs(succ)
                    assert len(ss) == 1, "trampoline must have exactly 1 successor"
                    succ = ss[0]
                    trampolines[block] = succ

        # then, collapse loop breaks.
        breaks: dict[_Block, _Block] = {}
        fs.breaks = breaks
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
            if jump.ins[-1].opcode is not Opcode.JZ:
                # we're only concerned with JMPs to JZs, i.e. loop conditions.
                continue
            ss = cfg.getsuccs(jump)
            assert len(ss) == 2, "loop exit must have exactly 2 successors"

            breaks[block] = ss[self._SUCC_TAKEN]

    def _find_loop_headers(self, fs: _FuncState) -> None:
        loops: set[_Block] = set()
        fs.loop_headers = loops
        for b in fs.blocks_list:
            for s in fs.cfg.getsuccs(b):
                if s in fs.dom[b]:
                    loops.add(s)

    def _recover(self, fs: _FuncState) -> None:
        logger.debug("recovering source code")
        self._find_headers(fs)
        # sort blocks by depth so innermost blocks are processed first.
        logger.debug("sorting blocks by depth")
        blocks = sorted(fs.headers, key=lambda b: len(fs.dom[b]), reverse=True)

        logger.debug("matching patterns for headers")
        for b in blocks:
            self._structure(fs, b)

    def _find_headers(self, fs: _FuncState) -> None:
        logger.debug("finding headers")
        headers: set[_Block] = set()
        fs.headers = headers

        for b in fs.blocks_list:
            assert len(b.ins) > 0, "block must not be empty"
            if b in fs.trampolines:
                continue  # trampolines cannot be headers
            if b in fs.breaks:
                continue  # breaks also cannot be headers

            last = b.ins[-1]
            if last.opcode is Opcode.JZ:
                headers.add(b)  # JZ may be a switch or an ordinary if-else.
            elif last.opcode is Opcode.JNZ:
                succs = fs.cfg.getsuccs(b)
                succ = succs[self._SUCC_TAKEN]
                if succ in fs.loop_headers:
                    # JNZ with a jump to a loop header is a do-while terminator.
                    headers.add(succs[self._SUCC_TAKEN])

    def _structure(self, fs: _FuncState, bl: _Block) -> None:
        regions: dict[_Block, _Region] = {}
        fs.regions = regions
        for matcher in MATCHERS:
            match = matcher(fs, bl)
            if match is None:
                continue
            regions[bl] = _Region(match, fs.blocks_between(match.header, match.join))

        fs.stmts.extend(self._build_block(fs, fs.alpha))

    def _build_block(
        self, fs: _FuncState, start: _Block, stop: _Block | None = None
    ) -> list[StStatement]:
        stmts = []
        visited = set()
        bl = start
        while bl is not None and bl not in visited:
            visited.add(bl)

            if bl in fs.regions:
                m = fs.regions[bl].match
                stmts.append(m.build(fs, bl))
                bl = m.join

            stmt = self._make_leaf(fs, bl)
            if stmt is not None:
                stmts.append(stmt)
            bl = self._follow(fs, bl, stop)

        return stmts

    def _follow(self, fs: _FuncState, bl: _Block, stop: _Block | None) -> _Block | None:
        if bl is fs.omega:
            return None
        if bl in fs.trampolines:
            return fs.trampolines[bl]

        succs = fs.cfg.getsuccs(bl)
        if len(succs) == 1:
            return succs[0]

        ft = fs.cfg.fallthrough(bl)
        if ft is not None:
            return ft

        term = bl.ins[-1]
        if term.opcode is Opcode.JMP:
            if term is stop:
                return None
            return fs.cfg.taken(bl)

        return None

    def _make_leaf(self, fs: _FuncState, bl: _Block) -> StStatement | None:
        if bl is fs.omega:
            return None
        if bl in fs.trampolines:
            return None
        if bl in fs.breaks:
            return StBreak()

        assert len(bl.ins) > 0
        term = bl.ins[-1]
        if term.opcode is Opcode.RET:
            return StReturn(PLACEHOLDER)
        return None

    def _emulate(self, fs: _FuncState, bl: _Block) -> None:
        vm = fs.vm
        for ins in bl.ins:
            if ins.opcode is Opcode.LITTOREG:
                reg = ins.as_reg(0)
                lit = ins.as_int(1)
                vm.setreg(reg, lit)

    def _make_script(self, funcs: list[StFunction]) -> StScript:
        return StScript(funcs)
