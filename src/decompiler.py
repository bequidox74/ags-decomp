from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from disassembler import Disassembly, Function, Instruction, Label, Opcode
from syntax_tree import STFunction, STScript


class Decompiler:
    type _Block = list[Instruction]

    @dataclass
    class _FuncState:
        func: Function
        leaders: set[Instruction] = field(default_factory=set)
        blocks: dict[int, Decompiler._Block] = field(default_factory=dict)

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

    def _build_blocks(self, fstate: Decompiler._FuncState) -> None:
        blocks: list[Decompiler._Block] = []

        current: list[Instruction] = []
        for inst in fstate.func.instructions:
            if inst in fstate.leaders and current:
                blocks.append(current)
                current = []
            current.append(inst)
        if current:
            blocks.append(current)

        fstate.blocks = {b[0].offset.script: b for b in blocks}

    def _make_script(self, funcs: list[STFunction]) -> STScript:
        return STScript(funcs)
