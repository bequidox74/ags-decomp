from decompiler._internal import control_flow
from decompiler.disassembler import Disassembly, Function
from decompiler.syntax_tree import StFunction, StScript


def decompile(disassembly: Disassembly) -> StScript:
    funcs: list[StFunction] = []
    for f in disassembly.functions.values():
        funcs.append(_decompile_func(f))
    return StScript(funcs)


def _decompile_func(func: Function) -> StFunction:
    control_flow.analyze(func)
    return StFunction(func.name)
