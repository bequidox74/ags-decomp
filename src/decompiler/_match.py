from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from disassembler import Opcode

from ._cfg import _Block
from ._func_state import _FuncState
from ._syntax_tree import StIf, StStatement, StWhile


@dataclass
class _Match(ABC):
    header: _Block
    join: _Block

    @abstractmethod
    def build(self, fs: _FuncState, bl: _Block) -> StStatement:
        pass


type _Matcher = Callable[[_FuncState, _Block], _Match | None]  # noqa: PYI047


@dataclass
class _IfMatch(_Match):
    branches: list[_Block]

    def build(self, fs: _FuncState, bl: _Block) -> StStatement:
        return StIf()


def match_if(fs: _FuncState, bl: _Block) -> _Match | None:
    term = bl.ins[-1]
    if term.opcode is not Opcode.JZ:
        return None

    cfg = fs.cfg
    skip = cfg.taken(bl)
    join = fs.ipdom[bl]
    assert skip is not None
    if skip is not join:
        return None

    then = cfg.fallthrough(bl)
    assert then is not None
    if then == join:
        return None

    return _IfMatch(bl, join, [then])


@dataclass
class _WhileMatch(_Match):
    def build(self, fs: _FuncState, bl: _Block) -> StStatement:
        return StWhile()


def match_while(fs: _FuncState, bl: _Block) -> _Match | None:
    term = bl.ins[-1]
    if term.opcode is not Opcode.JZ:
        return None
    if bl not in fs.loop_headers:
        return None
    exit_ = fs.cfg.taken(bl)
    assert exit_ is not None
    if fs.ipdom[bl] != exit_:
        return None
    return _WhileMatch(bl, exit_)


MATCHERS = (match_while, match_if)
