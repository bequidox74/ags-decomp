from collections.abc import Callable
from dataclasses import dataclass

from disassembler import Opcode

from .._cfg import _Block
from .._func_state import _FuncState


@dataclass
class _Match:
    header: _Block
    join: _Block


type _Matcher = Callable[[_FuncState, _Block], _Match | None]  # noqa: PYI047


def match_if(fs: _FuncState, bl: _Block) -> _Match | None:
    return _Match(bl, bl)


@dataclass
class _WhileMatch(_Match):
    pass


def match_while(fs: _FuncState, bl: _Block) -> _Match | None:
    term = bl.ins[-1]
    if term.opcode is not Opcode.JZ:
        return None
    if bl not in fs.loop_headers:
        return None
    exit_ = fs.cfg.getsuccs(bl)[0]
    if fs.ipdom[bl] != exit_:
        return None
    return _WhileMatch(bl, exit_)
