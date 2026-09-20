from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from warnings import warn

from string_writer import StringWriter


@dataclass
class AST(ABC):
    @abstractmethod
    def emit(self, sw: StringWriter) -> None:
        pass


@dataclass
class StItem(AST):
    pass


@dataclass
class StStatement(AST):
    pass


@dataclass
class StExpression(AST):
    pass


@dataclass
class StPlaceholder(StExpression):
    def emit(self, sw: StringWriter) -> None:
        warn("Placeholder leaked into output")
        sw.print("PLACEHOLDER")


PLACEHOLDER = StPlaceholder()


@dataclass
class StReturn(StStatement):
    value: StExpression

    def emit(self, sw: StringWriter) -> None:
        sw.print("return ")
        self.value.emit(sw)
        sw.print(";")


@dataclass
class StBreak(StStatement):
    def emit(self, sw: StringWriter) -> None:
        sw.print("break;")


@dataclass
class StIf(StStatement):
    cond: StExpression
    then: list[StStatement]

    def emit(self, sw: StringWriter) -> None:
        sw.print("if (")
        self.cond.emit(sw)
        sw.println(") {")
        sw.indent()
        for s in self.then:
            s.emit(sw)
            sw.println()
        sw.dedent()
        sw.print("}")


@dataclass
class StWhile(StStatement):
    cond: StExpression
    body: list[StStatement]

    def emit(self, sw: StringWriter) -> None:
        sw.print("while (")
        self.cond.emit(sw)
        sw.println(") {")
        sw.indent()
        for s in self.body:
            s.emit(sw)
            sw.println()
        sw.dedent()
        sw.print("}")


@dataclass
class StFunction(StItem):
    name: str
    stmts: list[StStatement]

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
class StScript(AST):
    items: Sequence[StItem]

    def emit(self, sw: StringWriter) -> None:
        for i in self.items:
            i.emit(sw)
            sw.println()
            sw.println()
