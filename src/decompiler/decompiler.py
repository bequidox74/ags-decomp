from decompiler.disassembler import Disassembly
from decompiler.syntax_tree import StFunction, StScript


def decompile(disassembly: Disassembly) -> StScript:
    funcs: list[StFunction] = []
    for f in disassembly.functions.values():
        funcs.append(StFunction(f.name))
    return StScript(funcs)
