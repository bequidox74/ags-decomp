from dataclasses import dataclass

from disassembler import Function, Instruction, Register
from syntax_tree import STStatement

from ._cfg import _Block, _CFGraph

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

    trampolines: dict[_Block, _Block]
    breaks: dict[_Block, _Block]
    loop_headers: set[_Block]
    headers: set[_Block]
    stmts: list[STStatement]
    vm: _VM

    def __init__(self, func: Function) -> None:
        self.func = func
        self.stmts = []
