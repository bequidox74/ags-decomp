from typing import Iterable


def sjoin(joiner: str, it: Iterable):
    return joiner.join((str(x) for x in it))
