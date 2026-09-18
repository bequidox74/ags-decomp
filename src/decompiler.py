from disassembler import Disassembly, Function
from syntax_tree import STBlock, STFunction, STScript


class Decompiler:
    def __init__(self, disassembly: Disassembly) -> None:
        self.disassembly = disassembly

        funcs: list[STFunction] = []
        for f in self.disassembly.functions:
            funcs.append(self._decompile(f))

        self.script = self._make_script(funcs)

    def _decompile(self, func: Function) -> STFunction:
        return STFunction("function", func.name, [], STBlock([]))

    def _make_script(self, funcs: list[STFunction]) -> STScript:
        return STScript(funcs)
