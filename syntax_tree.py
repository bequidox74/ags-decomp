from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from string_writer import StringWriter


class BinOp(Enum):
    MUL = ("*", 10)
    DIV = ("/", 10)
    MOD = ("%", 10)

    ADD = ("+", 9)
    SUB = ("-", 9)

    GTE = (">=", 8)
    GT = (">", 8)
    LTE = ("<=", 8)
    LT = ("<", 8)

    EQ = ("==", 7)
    NEQ = ("!=", 7)

    BITAND = ("&", 6)
    BITOR = ("|", 4)

    AND = ("&&", 3)
    OR = ("||", 2)

    def __init__(self, symbol: str, precedence: int):
        self.symbol = symbol
        self.precedence = precedence


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

    def emit(self, sw: StringWriter) -> None:
        self._emit_child(sw, self.left, side="left")
        sw.append(f" {self.operation.value[0]} ")
        self._emit_child(sw, self.right, side="right")

    def _emit_child(
        self,
        sw: StringWriter,
        child: STExpression,
        side: Literal["left", "right"],
    ) -> None:
        if not isinstance(child, STBinaryExpression):
            child.emit(sw)
            return

        parent_op = self.operation
        child_op = child.operation
        needs_parens = self._needs_parens(
            parent_op,
            child_op,
            side,
        )
        if needs_parens:
            sw.append("(")
        child.emit(sw)
        if needs_parens:
            sw.append(")")

    @staticmethod
    def _needs_parens(
        parent: BinOp,
        child: BinOp,
        side: Literal["left", "right"],
    ) -> bool:
        if child.precedence < parent.precedence:
            return True
        if child.precedence > parent.precedence:
            return False
        return side == "right"


@dataclass
class STVarExpression(STExpression):
    name: str
    array_index: STExpression | None

    def emit(self, sw: StringWriter) -> None:
        sw.append(self.name)
        if self.array_index is not None:
            sw.append("[")
            self.array_index.emit(sw)
            sw.append("]")


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
