"""Serialisation helpers: turn a :class:`GameState` into plain, JSON-ready data.

This is deliberately one-way (state -> dict -> JSON): the export/download feature never reads the
file back. Round-trip *loading* is out of scope; if it is added later, decode with msgspec
(``msgspec.json.decode(data, type=GameState)``, msgspec ships with Litestar) rather than a
hand-written decoder.
"""

from __future__ import annotations

import dataclasses
import json
from enum import Enum
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .state import GameState


def _jsonify(value: object) -> object:
    """Recursively convert dataclass-derived data to JSON-native values (any Enum -> its value)."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _jsonify(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonify(item) for item in value]
    return value


def state_to_dict(state: GameState) -> dict[str, object]:
    """Return a plain, JSON-ready dict for ``state``. After M1 it holds only ids and scalars."""
    return cast("dict[str, object]", _jsonify(dataclasses.asdict(state)))


def dumps(obj: object) -> str:
    """Serialise ``obj`` to a pretty-printed JSON string."""
    return json.dumps(obj, indent=2)
