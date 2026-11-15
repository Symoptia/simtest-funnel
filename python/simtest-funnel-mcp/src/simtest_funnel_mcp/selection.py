"""Column selection by exact names and glob patterns (shared by both tools)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from fnmatch import fnmatchcase

_GLOB_CHARS = frozenset("*?[")


def is_pattern(entry: str) -> bool:
    """True if ``entry`` contains a glob metacharacter (``*``, ``?``, ``[``)."""
    return any(c in _GLOB_CHARS for c in entry)


def expand(entries: Iterable[str], available: Sequence[str]) -> tuple[list[str], list[str]]:
    """Expand ``entries`` against ``available`` column names.

    Returns ``(selected, unmatched)``. Entries are processed in order; an
    entry equal to an available name selects that name (even if it contains
    glob characters); otherwise an entry with glob characters selects every
    available name it matches (case-sensitive, in ``available`` order), and a
    plain name is kept as given (the caller decides what a name that is not
    available means). Duplicates are dropped. ``unmatched`` lists the entries
    that matched no available name.
    """
    names = set(available)
    selected: dict[str, None] = {}
    unmatched: list[str] = []
    for entry in entries:
        if entry in names:
            selected[entry] = None
        elif is_pattern(entry):
            hits = [c for c in available if fnmatchcase(c, entry)]
            if not hits:
                unmatched.append(entry)
            for c in hits:
                selected[c] = None
        else:
            unmatched.append(entry)
            selected[entry] = None
    return list(selected), unmatched
