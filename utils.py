from typing import Iterable


def sjoin(joiner: str, it: Iterable):
    return joiner.join((str(x) for x in it))


def quote(s: str) -> str:
    return f'"{s}"'
