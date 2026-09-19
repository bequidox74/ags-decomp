from abc import ABC
from collections.abc import Sequence
from dataclasses import dataclass

from string_writer import StringWriter


class AST(ABC):
    def emit(self, sw: StringWriter) -> None:
        pass


class STItem(AST):
    pass


class STStatement(AST):
    pass


@dataclass
class STReturn(STStatement):
    value: int

    def emit(self, sw: StringWriter) -> None:
        sw.print(f"return {self.value};")


@dataclass
class STFunction(STItem):
    name: str
    stmts: list[STStatement]

    def emit(self, sw: StringWriter) -> None:
        sw.print("function ")
        sw.print(self.name)
        sw.println("() {")
        sw.indent()
        for s in self.stmts:
            s.emit(sw)
            sw.println()
        sw.dedent()
        sw.print("}")


@dataclass
class STScript(AST):
    items: Sequence[STItem]

    def emit(self, sw: StringWriter) -> None:
        for i in self.items:
            i.emit(sw)
            sw.println()
            sw.println()
