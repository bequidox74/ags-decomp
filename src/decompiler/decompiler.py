import logging

from decompiler._internal import control_flow, recovery
from decompiler.disassembler import Disassembly, Function
from decompiler.syntax_tree import StFunction, StScript

logger = logging.getLogger(__name__)


def decompile(disassembly: Disassembly) -> StScript:
    funcs: list[StFunction] = []
    for f in disassembly.functions.values():
        result = decompile_func(f)
        if result is not None:
            funcs.append(result)
    return StScript(funcs)


def decompile_func(func: Function) -> StFunction | None:
    logger.info("decompiling %s", func.mangled_name)
    try:
        cf = control_flow.analyze(func)
        return recovery.recover(func, cf)
    except Exception:  # pylint: disable=broad-exception-caught
        # logger.error("error while decompiling %s", func.mangled_name)
        logger.exception("error while decompiling %s", func.mangled_name)
        return StFunction(f"INVALID_{func.mangled_name}", [])
