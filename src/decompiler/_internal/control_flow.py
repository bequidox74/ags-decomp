from dataclasses import dataclass

from decompiler.disassembler import Function, Instruction, Opcode

type Offset = int
type Block = list[Instruction]

_JUMPS = {
    Opcode.JMP,
    Opcode.JZ,
    Opcode.JNZ,
}


@dataclass(init=False)
class ControlFlow:
    leaders: set[Instruction]
    blocks: dict[Offset, Block]


def analyze(func: Function) -> ControlFlow:
    cf = ControlFlow()
    cf.leaders = _find_leaders(func)
    cf.blocks = _make_blocks(func, cf.leaders)
    return cf


def _find_leaders(func: Function) -> set[Instruction]:
    leaders: set[Instruction] = set()
    leaders.add(func.instr_list[0])
    for idx, ins in enumerate(func.instr_list):
        is_jump = ins.opcode in _JUMPS
        is_ret = ins.opcode is Opcode.RET
        if is_jump:
            l = ins.get_label()
            leaders.add(func.instructions[l.to])
        if (is_jump or is_ret) and idx + 1 < len(func.instr_list):  # fallthrough
            leaders.add(func.instr_list[idx + 1])
    return leaders


def _make_blocks(func: Function, leaders: set[Instruction]) -> dict[Offset, Block]:
    blocks = {}
    current: Block = []

    def flush() -> None:
        nonlocal current
        blocks[current[0].func_offset] = current
        current = []

    for ins in func.instr_list:
        if ins in leaders and current:
            flush()
        current.append(ins)
    if current:
        flush()
    return blocks
