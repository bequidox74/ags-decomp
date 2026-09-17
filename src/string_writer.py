from utils import strip_lines


class StringWriter:
    def __init__(self, indent: str | int = "  ") -> None:
        if isinstance(indent, int):
            indent = " " * indent
        self.buffer = []
        self.indent_string = indent
        self._current_indent = ""
        self._level = 0
        self._print_indent = False

    @property
    def level(self) -> int:
        return self._level

    @level.setter
    def level(self, value: int) -> None:
        self._level = max(0, value)
        self._current_indent = self.indent_string * self._level

    def indent(self, levels: int = 1) -> None:
        self.level += levels

    def dedent(self, levels: int = 1) -> None:
        self.level -= levels

    # carriage return
    def cr(self) -> None:
        self.level = 0

    def print(self, s: str) -> None:
        if self._print_indent:
            self.buffer.append(self._current_indent)
            self._print_indent = False
        self.buffer.append(s)
    append = print

    def println(self, s: str = "") -> None:
        self.print(s)
        self.buffer.append("\n")
        self._print_indent = True

    def __str__(self) -> str:
        return strip_lines("".join(self.buffer))
