from dataclasses import dataclass
from typing import NamedTuple

from script import Opcode, Script
from string_writer import StringWriter
from utils import sjoin


class Instruction(NamedTuple):
    opcode: Opcode
    params: list

    def format(self) -> str:
        return f"{self.opcode.mnemonic} {sjoin(", ", self.params)}"

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
        sw.println(f"; {len(self.script.imports)} imports, {len(self.script.exports)} exports")
        sw.println()

        # .data
        if self.script.global_data:
            sw.println(f".data ; {len(self.script.global_data)} bytes")
            sw.indent()

            gd = self.script.global_data
            for i in range(0, len(gd), 16):
                sw.println(" ".join(f"{b:02X}" for b in gd[i : i + 16]))

            sw.cr()
            sw.println()

        # .code
        if self.functions:
            sw.println(".code")
            sw.indent()

            for func in self.functions:
                sw.println(
                    f"{func.name}${func.nargs}: ; @0x{func.offset:X}, {func.nargs} args"
                )
                sw.indent()
                for ins in func.instructions:
                    sw.println(str(ins))
                sw.dedent()
                sw.println()

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
            for n in range(opc.nargs):
                params.append(code[i + 1 + n])
                i += 1
            assert len(params) <= 3, "Too many parameters for instruction"
            i += 1
            func.instructions.append(Instruction(opc, params))
