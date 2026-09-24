from functools import singledispatchmethod

from decompiler._internal.control_flow import (
    Block,
    ControlFlow,
    DoWhileMatch,
    IfElseMatch,
    IfMatch,
    Match,
    SwitchMatch,
    WhileMatch,
)
from decompiler.disassembler import Function
from decompiler.syntax_tree import (
    StDoWhile,
    StFunction,
    StIfElse,
    StStatement,
    StSwitch,
    StWhile,
)


class _Structurer:
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
            if bl in self.cf.headers:
                header = self.cf.headers[bl]
                stmts.append(self.build_construct(header))
                bl = header.join
                continue
            bl = self._next_block(bl)
        return stmts

    @singledispatchmethod
    def build_construct(self, match: Match) -> StStatement:
        raise NotImplementedError

    @build_construct.register
    def _(self, match: IfMatch) -> StIfElse:
        stmts = self.build_region(match.then, match.join)
        return StIfElse(stmts)

    @build_construct.register
    def _(self, match: IfElseMatch) -> StIfElse:
        then_stmts = self.build_region(match.then, match.join)
        else_stmts = self.build_region(match.else_, match.join)
        return StIfElse(then_stmts, else_stmts)

    @build_construct.register
    def _(self, match: SwitchMatch) -> StSwitch:
        cases: list[list[StStatement]] = []
        for c in match.cases.values():
            cases.append(self.build_region(c, match.join))

        default = None
        if match.default is not None:
            default = self.build_region(match.default, match.join)

        return StSwitch(cases, default)

    @build_construct.register
    def _(self, match: WhileMatch) -> StWhile:
        stmts = self.build_region(match.body, match.join)
        return StWhile(stmts)

    @build_construct.register
    def _(self, match: DoWhileMatch) -> StDoWhile:
        stmts = self.build_region(match.header, match.join)
        return StDoWhile(stmts)

    def _next_block(self, bl: Block) -> Block | None:
        if bl in self.cf.trampolines:
            return self.cf.trampolines[bl]
        succs = self.cf.cfg.succ[bl]
        if len(succs) == 1:
            s = succs[0]
            if s != self.cf.cfg.exit:
                return s
        return None


def structure(func: Function, cf: ControlFlow) -> StFunction:
    return _Structurer(func, cf).structure()
