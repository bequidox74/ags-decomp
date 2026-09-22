from typing import TYPE_CHECKING

from decompiler.disassembler import Function
from decompiler.syntax_tree import StBreak, StFunction, StStatement

if TYPE_CHECKING:
    from decompiler._internal.control_flow import Block, ControlFlow


class Structurer:
    def __init__(self, func: Function, cf: ControlFlow) -> None:
        self._visited: set[Block] = set()
        self.func = func
        self.cf = cf

    def structure(self) -> StFunction:
        stmts = self.build_region(self.cf.cfg.entry)
        return StFunction(self.func.name, stmts)

    def build_region(
        self, start: Block, stop: Block | None = None
    ) -> list[StStatement]:
        stmts: list[StStatement] = []
        bl: Block | None = start
        while bl is not None and bl is not stop:
            if bl in self._visited:
                break
            self._visited.add(bl)
            if bl in self.cf.trampolines:
                stmts.append(StBreak())
            if bl in self.cf.headers:
                stmts.append(self.cf.headers[bl].structure(self))
                continue
            bl = self._next_block(bl)
        return stmts

    def _next_block(self, bl: Block) -> Block | None:
        if bl in self.cf.trampolines:
            return self.cf.trampolines[bl]
        succs = self.cf.cfg.succ[bl]
        if len(succs) == 1:
            return succs[0]
        return None


def recover(func: Function, cf: ControlFlow) -> StFunction:
    return Structurer(func, cf).structure()
