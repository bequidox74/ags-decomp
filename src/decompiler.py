from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from disassembler import Disassembly, Function, Instruction, Label, Opcode
from syntax_tree import STFunction, STScript


@dataclass
class _Block:
    ins: list[Instruction]

    def __hash__(self) -> int:
        return id(self.ins)

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
    @dataclass(init=False)
    class _FuncState:
        func: Function
        leaders: set[Instruction]
        blocks: dict[int, _Block]

        cfg: _CFGraph
        alpha: _Block
        omega: _Block

        def __init__(self, func: Function) -> None:
            self.func = func

    _BRANCH: ClassVar[set[Opcode]] = {
        Opcode.JMP,
        Opcode.JZ,
        Opcode.JNZ,
    }
    _TERMINATORS: ClassVar[set[Opcode]] = _BRANCH | {Opcode.RET}

    def __init__(self, disassembly: Disassembly) -> None:
        self.disassembly = disassembly
        self.script: STScript

        self._decompile()

    def _decompile(self) -> None:
        funcs: list[STFunction] = []
        for f in self.disassembly.functions:
            funcs.append(self._do_func(f))

        self.script = self._make_script(funcs)

    def _do_func(self, func: Function) -> STFunction:
        fs = self._FuncState(func)
        self._find_leaders(fs)
        self._build_blocks(fs)
        self._link_blocks(fs)
        return STFunction(func.name)

    def _find_leaders(self, fstate: Decompiler._FuncState) -> None:
        func = fstate.func
        leaders: set[Instruction] = set()
        fstate.leaders = leaders
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

    def _build_blocks(self, fstate: Decompiler._FuncState) -> None:
        blocks: list[list[Instruction]] = []

        current: list[Instruction] = []
        for inst in fstate.func.instructions:
            if inst in fstate.leaders and current:
                blocks.append(current)
                current = []
            current.append(inst)
        if current:
            blocks.append(current)

        assert len(blocks) > 0, "function must have at least one block"
        fstate.blocks = {b[0].offset.script: _Block(b) for b in blocks}

    def _link_blocks(self, fstate: Decompiler._FuncState) -> None:
        cfg = _CFGraph()

        blocks = fstate.blocks
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

        fstate.cfg = cfg
        fstate.alpha = blocks[addresses[0]]
        fstate.omega = omega

    def _make_script(self, funcs: list[STFunction]) -> STScript:
        return STScript(funcs)
