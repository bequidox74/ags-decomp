class StringWriter:
    def __init__(self, indent: str | int = "  ") -> None:
        if isinstance(indent, int):
            indent = " " * indent
        self.buffer = []
        self.indent_string = indent
        self._current_indent = ""
        self.level = 0

    def append(self, s: str) -> None:
        self.buffer.append(s)

    def indent(self) -> None:
        self.level += 1
        self._current_indent = self.indent_string * self.level

    def dedent(self, levels: int = 1) -> None:
        self.level = max(0, self.level - levels)
        self._current_indent = self.indent_string * self.level

    # carriage return
    def cr(self) -> None:
        self.level = 0
        self._current_indent = ""

    def print(self, s: str = "") -> None:
        if self._current_indent:
            self.buffer.append(self._current_indent)
        if s:
            self.buffer.append(s)

    def println(self, s: str = "") -> None:
        self.print(s)
        self.buffer.append("\n")

    def __str__(self) -> str:
        return "".join(self.buffer)
