"""Strict tool arguments: unknown names refused, errors stated compactly.

Every tool argument model and every nested input object (tolerance sets,
column pairs, x-range, per-column overrides) refuses names it does not
define, so a misspelt argument fails the call instead of being ignored. The
published input schema says the same (``additionalProperties: false``).
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Mapping
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from pydantic_core import PydanticCustomError

#: pydantic error type of an unknown name (see :func:`refuse_unknown`).
UNKNOWN_ARGUMENT = "unknown_argument"
#: Input values quoted in error messages are cut to this many characters.
QUOTE_CHARS = 60


def known_names(model: type[BaseModel]) -> list[str]:
    """The names ``model`` accepts (aliases where set), in definition order."""
    return [f.alias or name for name, f in model.model_fields.items()]


def unknown_message(unknown: Iterable[str], known: Iterable[str]) -> str:
    """``unknown argument 'x'; did you mean 'y'?`` for each unknown name.

    A close match (``difflib``) is suggested when there is one; otherwise
    the accepted names are listed.
    """
    choices = list(known)
    parts: list[str] = []
    for name in unknown:
        close = difflib.get_close_matches(name, choices, n=1)
        if close:
            parts.append(f"unknown argument {name!r}; did you mean {close[0]!r}?")
        else:
            parts.append(
                f"unknown argument {name!r} (accepted: {', '.join(choices)})"
            )
    return " ".join(parts)


def refuse_unknown(model: type[BaseModel], data: object) -> object:
    """Raise a validation error naming every key of ``data`` that ``model``
    does not define; return ``data`` unchanged otherwise."""
    if not isinstance(data, Mapping):
        return data
    known = known_names(model)
    unknown = [str(k) for k in data if k not in known]
    if unknown:
        raise PydanticCustomError(UNKNOWN_ARGUMENT, unknown_message(unknown, known))
    return data


class StrictInput(BaseModel):
    """Base of the nested input objects: unknown keys are refused with a
    suggestion, and the schema says ``additionalProperties: false``."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _refuse_unknown(cls, data: object) -> object:
        return refuse_unknown(cls, data)


_M = TypeVar("_M", bound=BaseModel)


def strict_model(model: type[_M]) -> type[_M]:
    """A subclass of ``model`` (a tool's argument model) that refuses
    unknown names like :class:`StrictInput`."""

    class Strict(model):  # type: ignore[misc, valid-type]
        model_config = ConfigDict(extra="forbid")

        @model_validator(mode="before")
        @classmethod
        def _refuse_unknown(cls, data: object) -> object:
            return refuse_unknown(cls, data)

    Strict.__name__ = Strict.__qualname__ = model.__name__
    return Strict


def _location(loc: tuple[int | str, ...], data: object) -> str:
    """``tolerances[0].atoly`` for a pydantic error location.

    Parts that do not name a key or index of the input are dropped: pydantic
    adds the member type of a union (``x_range.lo.float``). The last part
    is kept when it names a missing key of an object.
    """
    out = ""
    cur: Any = data
    for i, part in enumerate(loc):
        if isinstance(part, int) and isinstance(cur, list) and 0 <= part < len(cur):
            out += f"[{part}]"
            cur = cur[part]
        elif isinstance(part, str) and isinstance(cur, Mapping) and (
            part in cur or i == len(loc) - 1
        ):
            out += f".{part}" if out else part
            cur = cur.get(part)
        # anything else is a union member tag: dropped
    return out


def _quote(value: object) -> str:
    text = repr(value)
    return text if len(text) <= QUOTE_CHARS else text[: QUOTE_CHARS - 3] + "..."


def describe_validation_error(exc: ValidationError, data: object) -> str:
    """One line per argument at fault (a list when several are), e.g. ``unknown argument 'header_lin';
    did you mean 'header_line'?`` or ``tolerances[0].atoly: Input should be
    greater than or equal to 0 (got -1)``."""
    messages: dict[str, list[str]] = {}
    for err in exc.errors(include_url=False):
        where = _location(tuple(err["loc"]), data)
        if err["type"] == UNKNOWN_ARGUMENT:
            text = str(err["msg"])
        elif err["type"] == "missing":
            text = "required argument missing"
        else:
            text = f"{err['msg']} (got {_quote(err.get('input'))})"
        listed = messages.setdefault(where, [])
        if text not in listed:
            listed.append(text)
    lines = [
        (f"{where}: " if where else "") + " or ".join(texts)
        for where, texts in messages.items()
    ]
    if len(lines) == 1:
        return f"invalid arguments: {lines[0]}"
    return "invalid arguments:\n" + "\n".join(f"- {line}" for line in lines)


def strip_titles(schema: object) -> object:
    """``schema`` without the ``title`` keywords pydantic generates from
    field and model names (they repeat the names and cost context)."""
    if isinstance(schema, list):
        return [strip_titles(v) for v in schema]
    if not isinstance(schema, dict):
        return schema
    out: dict[str, object] = {}
    for key, value in schema.items():
        if key == "title" and isinstance(value, str):
            continue
        if key in ("properties", "$defs") and isinstance(value, dict):
            out[key] = {name: strip_titles(sub) for name, sub in value.items()}
        else:
            out[key] = strip_titles(value)
    return out
