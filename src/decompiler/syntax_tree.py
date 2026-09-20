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

    def emit(self, sw: StringWriter) -> None:
        sw.println(f"function {self.name}() {{")
        sw.print("}")


type StItem = StFunction


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
