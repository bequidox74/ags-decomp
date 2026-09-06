from utils import strip_lines


class StringWriter:
    def __init__(self, indent: str | int = "  ") -> None:
        if isinstance(indent, int):
            indent = " " * indent
        self.buffer = []
        self.indent_string = indent
        self._current_indent = ""
        self._level = 0

    @property
    def level(self) -> int:
        return self._level

    @level.setter
    def level(self, value: int) -> None:
        self._level = max(0, value)
        self._current_indent = self.indent_string * self._level

    def append(self, s: str) -> None:
        self.buffer.append(s)

    def indent(self, levels: int = 1) -> None:
        self.level += levels

    def dedent(self, levels: int = 1) -> None:
        self.level -= levels

    # carriage return
    def cr(self) -> None:
        self.level = 0

    def print(self, s: str = "") -> None:
        if self._current_indent:
            self.buffer.append(self._current_indent)
        if s:
            self.buffer.append(s)

    def println(self, s: str = "") -> None:
        self.print(s)
        self.buffer.append("\n")

    def __str__(self) -> str:
        return strip_lines("".join(self.buffer))
