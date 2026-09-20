from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from disassembler import Opcode

from ._cfg import _Block
from ._func_state import _FuncState
from ._syntax_tree import PLACEHOLDER, StIf, StStatement, StWhile

if TYPE_CHECKING:
    from ._decompiler import Decompiler


@dataclass
class _Match(ABC):
    header: _Block
    join: _Block

    @abstractmethod
    def build(self, dc: Decompiler, fs: _FuncState, bl: _Block) -> StStatement:
        pass


type _Matcher = Callable[[_FuncState, _Block], _Match | None]  # noqa: PYI047


@dataclass
class _IfMatch(_Match):
    then: _Block

    def build(self, dc: Decompiler, fs: _FuncState, bl: _Block) -> StStatement:
        body = dc.build_block(fs, self.then, self.join)
        return StIf(PLACEHOLDER, body)


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
    return _IfMatch(bl, join, then)


@dataclass
class _WhileMatch(_Match):
    body: _Block

    def build(self, dc: Decompiler, fs: _FuncState, bl: _Block) -> StStatement:
        body = dc.build_block(fs, self.body, self.join)
        return StWhile(PLACEHOLDER, body)


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
    body = fs.cfg.fallthrough(bl)
    assert body is not None
    return _WhileMatch(bl, exit_, body)


MATCHERS = (match_while, match_if)
