from dataclasses import dataclass
from typing import NamedTuple

from script import Opcode, Script
from string_writer import StringWriter
from utils import sjoin, quote

REGISTERS = {
    1: "sp",  # stack pointer
    2: "mar",  # memory address
    3: "ax",  # general purpose A
    4: "bx",  # g.p. B
    5: "cx",  # g.p. C, (array index)
    6: "op",  # object pointer
    7: "dx",  # g.p. D
}


class Instruction(NamedTuple):
    opcode: Opcode
    params: list

    def format(self) -> str:
        p = self.params.copy()
        opc = self.opcode
        assert opc.nargs == len(p), "Instruction parameter count mismatch"
        for i in range(len(p)):
            match opc.args_format[i]:
                case "r":
                    p[i] = REGISTERS[p[i]]
                case "a":
                    pass  # leave as is (TODO: float heuristic?)
                case _:
                    raise RuntimeError(f"Illegal args format: {opc.args_format}")
        return f"{self.opcode.mnemonic} {sjoin(", ", p)}"

    def __str__(self) -> str:
        return self.format()


class Function(NamedTuple):
    name: str
    nargs: int
    type_: int
    offset: int
    instructions: list[Instruction]


@dataclass
class Disassembly:
    script: Script
    functions: list[Function]

    def format(
        self,
        sw: StringWriter | None = None,
    ) -> str:
        if sw is None:
            sw = StringWriter()

        sw.println(f"; AGS SCOM version {self.script.version}")
        sw.println()

        # .data
        if self.script.global_data:
            sw.println(f".data ; {len(self.script.global_data)} bytes")

            gd = self.script.global_data
            for i in range(0, len(gd), 16):
                sw.println(" ".join(f"{b:02X}" for b in gd[i : i + 16]))

            sw.cr()
            sw.println()

        # .code
        if self.functions:
            sw.println(".code")

            for i, func in enumerate(self.functions):
                sw.println(
                    f"{func.name}${func.nargs}: ; @0x{func.offset:X}, {func.nargs} args"
                )
                sw.indent()
                for ins in func.instructions:
                    sw.println(str(ins))
                sw.dedent()

                # remove ugly double newline
                if i != len(self.functions) - 1:
                    sw.println()

            sw.cr()
            sw.println()

        # .strings
        if self.script.strings:
            sw.println(".strings")
            width = len(str(len(self.script.strings)))
            for i, s in enumerate(self.script.strings):
                sw.println(f"{format(i, f"0{width}")}: {quote(s)}")
            sw.cr()
            sw.println()

        return str(sw)

    def __str__(self) -> str:
        return self.format()


class Disassembler:
    def disassemble(self, script: Script) -> Disassembly:
        self._functions: list[Function] = []
        self.script: Script = script

        # find function entry points
        # see https://github.com/adventuregamestudio/ags/blob/6802bad8dc3189462003d4a169fc591f64cfb9b6/Engine/script/cc_instance.cpp#L371
        for export in script.exports:
            name, nargs = export.name.split("$")
            nargs = int(nargs)
            # high byte is type, should always be 1
            type_ = (export.address >> 8 * 3) & 0xFF
            # lowest 3 bytes are the offset into code data
            offset = export.address & 0x00FFFFFF
            func = Function(name, nargs, type_, offset, [])
            self._functions.append(func)

        # sort entry points, determine function spans, and disassemble
        entries: dict[int, Function] = {}
        for f in self._functions:
            entries[f.offset] = f
        sorted_entries = sorted(list(entries.keys()))
        for i in range(len(sorted_entries)):
            from_ = sorted_entries[i]
            to = sorted_entries[i + 1] if i < len(sorted_entries) - 1 else None
            self._do_func(entries[from_], from_, to)

        return Disassembly(script, self._functions)

    def _do_func(self, func: Function, from_: int, to: int | None) -> None:
        code = self.script.code
        i = from_
        if to is None:
            to = len(code)

        while i < len(code):
            opc = Opcode(code[i] & 0x00FFFFFF)
            params = []
            for _ in range(opc.nargs):
                i += 1
                params.append(code[i])
            assert len(params) <= 3, "Too many parameters for instruction"
            i += 1
            func.instructions.append(Instruction(opc, params))
