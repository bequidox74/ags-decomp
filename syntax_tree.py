from __future__ import annotations

from dataclasses import dataclass
from abc import ABC, abstractmethod
from enum import Enum
from typing import Literal, Sequence

from string_writer import StringWriter


class BinOp(Enum):
    PLUS = "+"
    MINUS = "-"
    MUL = "*"
    DIV = "/"
    MOD = "%"


class AST(ABC):
    @abstractmethod
    def emit(self, sw: StringWriter) -> None:
        pass


class STExpression(AST):
    pass


@dataclass
class STLiteral(STExpression):
    value: int | float | str

    def emit(self, sw: StringWriter) -> None:
        sw.append(str(self.value))


@dataclass
class STBinaryExpression(STExpression):
    left: STExpression
    right: STExpression
    operation: BinOp


class STItem(AST):
    pass


@dataclass
class STType(AST):  # wrapper for by-reference access
    t: Literal["int", "char", "short", "float", "bool", "String"]
    guess: bool = True

    def emit(self, sw: StringWriter) -> None:
        sw.append(self.t)


@dataclass
class STScript(AST):
    items: Sequence[STItem]

    def emit(self, sw: StringWriter) -> None:
        for item in self.items:
            item.emit(sw)
            sw.println()


class STStatement(AST):
    pass


class STAssignmentTarget(AST):
    pass


@dataclass
class STVarAssignTarget(STAssignmentTarget):
    name: str
    array_index: STExpression | None
    type_: STType | None = None

    def emit(self, sw: StringWriter) -> None:
        if self.type_ is not None:
            sw.append(self.type_.t + " ")
        sw.append(f"{self.name}")
        if self.array_index is not None:
            sw.append("[")
            self.array_index.emit(sw)
            sw.append("]")


@dataclass
class STAssignment(STStatement):
    lhs: STAssignmentTarget
    rhs: STExpression

    def emit(self, sw: StringWriter) -> None:
        sw.print()
        self.lhs.emit(sw)
        sw.append(" = ")
        self.rhs.emit(sw)
        sw.append(";")


@dataclass
class STVarDeclaration(STStatement, STItem):
    type_: STType
    name: str

    def emit(self, sw: StringWriter) -> None:
        sw.print()
        self.type_.emit(sw)
        sw.append(f" {self.name};")


@dataclass
class STFunctionParam(AST):
    type_: STType
    id_: str


@dataclass
class STFunction(STItem):
    type_: STType | Literal["function"]
    name: str
    parameters: list[STFunctionParam]
    statements: list[STStatement]

    def emit(self, sw: StringWriter) -> None:
        sw.println(f"function {self.name}() {{")
        sw.indent()
        for stmt in self.statements:
            stmt.emit(sw)
            sw.println()
        sw.dedent()
        sw.println("}")
        sw.println()
