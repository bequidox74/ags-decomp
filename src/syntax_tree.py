from abc import ABC
from dataclasses import dataclass
from typing import Sequence

from string_writer import StringWriter


class AST(ABC):
    def emit(self, sw: StringWriter) -> None:
        pass


class STItem(AST):
    pass


@dataclass
class STFunction(STItem):
    name: str

    def emit(self, sw: StringWriter) -> None:
        sw.print("function ")
        sw.print(self.name)
        sw.print(" {}")


@dataclass
class STScript(AST):
    items: Sequence[STItem]

    def emit(self, sw: StringWriter) -> None:
        for i in self.items:
            i.emit(sw)
            sw.println()
            sw.println()
