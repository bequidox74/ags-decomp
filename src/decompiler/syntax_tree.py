from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from string_writer import StringWriter


class AST(ABC):
    @abstractmethod
    def emit(self, sw: StringWriter) -> None:
        pass


@dataclass
class StFunction(AST):
    name: str
    stmts: list[StStatement]

    def emit(self, sw: StringWriter) -> None:
        sw.print(f"function {self.name}() ")
        emit_block(sw, self.stmts)


type StItem = StFunction


@dataclass
class StStatement(AST, ABC):
    pass


@dataclass
class StIfElse(StStatement):
    then: list[StStatement]
    else_: list[StStatement] | None = None

    def emit(self, sw: StringWriter) -> None:
        sw.print("if (0) ")
        emit_block(sw, self.then)

        if self.else_ is not None:
            sw.print(" else ")
            if len(self.else_) == 1 and isinstance(self.else_[0], StIfElse):
                self.else_[0].emit(sw)
            else:
                emit_block(sw, self.else_)


@dataclass
class StWhile(StStatement):
    body: list[StStatement]

    def emit(self, sw: StringWriter) -> None:
        sw.print("while (0) ")
        emit_block(sw, self.body)


@dataclass
class StDoWhile(StStatement):
    body: list[StStatement]

    def emit(self, sw: StringWriter) -> None:
        sw.print("do ")
        emit_block(sw, self.body)
        sw.print(" while (0);")


@dataclass
class StBreak(StStatement):
    def emit(self, sw: StringWriter) -> None:
        sw.print("break;")


@dataclass
class StSwitch(StStatement):
    cases: list[list[StStatement]]
    default: list[StStatement] | None

    def emit(self, sw: StringWriter) -> None:
        sw.println("switch (0) {")
        for c in self.cases:
            sw.println("case _:")
            sw.indent()
            for s in c:
                s.emit(sw)
                sw.println()
            sw.dedent()

        if self.default is not None:
            sw.println("default:")
            sw.indent()
            for s in self.default:
                s.emit(sw)
                sw.println()
            sw.dedent()
        sw.print("}")


@dataclass
class StScript(AST):
    items: Sequence[StItem]

    def emit(self, sw: StringWriter) -> None:
        num_funcs = sum(isinstance(i, StFunction) for i in self.items)
        sw.println("// Decompiled AGS script")
        sw.println(f"// {len(self.items)} items, {num_funcs} functions")
        sw.println()

        for i in self.items:
            i.emit(sw)
            sw.println()
            sw.println()


def emit_block(sw: StringWriter, block: list[StStatement]) -> None:
    sw.println("{")
    sw.indent()
    for s in block:
        s.emit(sw)
        sw.println()
    sw.dedent()
    sw.print("}")
