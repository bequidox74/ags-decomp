from dataclasses import dataclass, field

from disassembler import Instruction


@dataclass
class _Block:
    ins: list[Instruction]

    def __hash__(self) -> int:
        return id(self.ins)

    def __eq__(self, value: object) -> bool:
        return self is value

    def __repr__(self) -> str:
        if self.ins:
            first = str(self.ins[0])
            last = str(self.ins[-1])
            return f"<Block {first}..{last}>"
        else:
            return "<Block>"


@dataclass
class _CFGraph:
    preds: dict[_Block, list[_Block]] = field(default_factory=dict)
    succs: dict[_Block, list[_Block]] = field(default_factory=dict)

    def link(self, from_: _Block, to: _Block) -> None:
        self.succs.setdefault(from_, []).append(to)
        self.preds.setdefault(to, []).append(from_)

    def unlink(self, from_: _Block, to: _Block) -> None:
        self.succs.get(from_, []).remove(to)
        self.preds.get(to, []).remove(from_)

    def reverse(self) -> _CFGraph:
        result = _CFGraph()
        for b, p in self.preds.items():
            result.succs[b] = p  # pylint: disable=protected-access
        for b, s in self.succs.items():
            result.preds[b] = s  # pylint: disable=protected-access
        return result

    def getpreds(self, b: _Block) -> list[_Block]:
        return self.preds.setdefault(b, [])

    def getsuccs(self, b: _Block) -> list[_Block]:
        return self.succs.setdefault(b, [])

    def __delitem__(self, key: _Block) -> None:
        del self.preds[key]
        del self.succs[key]
