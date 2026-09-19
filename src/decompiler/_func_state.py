from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

from disassembler import Function, Instruction, Register

from ._cfg import _Block, _CFGraph
from ._syntax_tree import StStatement

if TYPE_CHECKING:
    from ._match import _Match

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


class _Region(NamedTuple):
    match: _Match
    blocks: set[_Block]


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

    trampolines: dict[_Block, _Block]
    breaks: dict[_Block, _Block]
    loop_headers: set[_Block]
    headers: set[_Block]
    stmts: list[StStatement]
    regions: dict[_Block, _Region]
    vm: _VM

    def __init__(self, func: Function) -> None:
        self.func = func
        self.stmts = []

    def blocks_between(self, from_: _Block, to: _Block) -> set[_Block]:
        dominated = set()
        postdominated = set()
        for b in self.dom:
            if from_ in self.dom[b]:
                dominated.add(b)
        for b in self.pdom:
            if to in self.pdom[b]:
                postdominated.add(b)
        return dominated.intersection(postdominated)
