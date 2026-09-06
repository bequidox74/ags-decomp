from __future__ import annotations

from dataclasses import dataclass
from abc import ABC

from disassembler import Primitive
from string_writer import StringWriter


class AST(ABC):
    def emit(self, sw: StringWriter) -> None:
        raise NotImplementedError


@dataclass
class STScript(AST):
    funcs: list[STFunction]

    def emit(self, sw: StringWriter) -> None:
        for func in self.funcs:
            func.emit(sw)
            sw.println()


@dataclass
class STStatement(AST, ABC):
    pass


@dataclass
class STLiteral(AST):
    value: Primitive


@dataclass
class STAssignment(STStatement):
    lhs: str
    rhs: str

    def emit(self, sw: StringWriter) -> None:
        sw.print(f"{self.lhs} = {self.rhs}")
        # self.rhs.emit(sw)
        sw.append(";")
        sw.println()


@dataclass
class STFunction(AST):
    name: str
    statements: list[STStatement]

    def emit(self, sw: StringWriter) -> None:
        sw.println(f"function {self.name}() {{")
        sw.indent()
        for stmt in self.statements:
            stmt.emit(sw)
        sw.dedent()
        sw.println("}")
        sw.println()
