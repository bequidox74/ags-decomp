from collections.abc import Iterable
from itertools import batched
from typing import TypeVar

T = TypeVar("T")


def verify(cond: bool, *args) -> None:
    if not cond:
        raise AssertionError(*args)


def sjoin(joiner: str, it: Iterable):
    return joiner.join(str(x) for x in it)


def quote(s: str) -> str:
    return f'"{s}"'


def format_bindata(b: bytes) -> list[str]:
    result: list[str] = []
    for batch in batched(b, 16):
        as_hex = [f"{b:02X}" for b in batch]
        left = " ".join(as_hex[:8])
        right = " ".join(as_hex[8:])
        result.append(f"{left}  {right}")
    return result


def strip_lines(s: str) -> str:
    lines = []
    for line in s.splitlines():
        lines.append(line.rstrip())
    return "\n".join(lines).strip() + "\n"
