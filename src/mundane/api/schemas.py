"""Translate action JSON (a tagged union) into engine action dataclasses.

Every action body carries a ``type`` discriminator, e.g.
``{"type": "play_card", "player": 0, "hand_index": 0}``. The tags are exactly the keys of the
engine's canonical ``ACTION_TYPES`` registry, so the HTTP surface mirrors the engine and the
round-trip ``action_to_dict`` -> :func:`parse_action` is the identity (covered by a test).

A body that does not describe a valid action — unknown ``type``, missing field, wrong field type —
is rejected with :class:`IllegalAction`, which the app maps to HTTP 422. No legality lives here; this
is pure translation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mundane.engine.actions import CastInstant, IllegalAction, PassPriority, PlayCard

if TYPE_CHECKING:
    from mundane.engine.actions import Action


def _require_int(body: dict[str, object], key: str) -> int:
    """Return ``body[key]`` as an int, or reject the action if it is missing or not an integer."""
    value = body.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"action field {key!r} must be an integer"
        raise IllegalAction(msg)
    return value


def _optional_int(body: dict[str, object], key: str) -> int | None:
    """Return ``body[key]`` as an int, or None when it is absent or explicitly null."""
    if body.get(key) is None:
        return None
    return _require_int(body, key)


def parse_action(body: dict[str, object]) -> Action:
    """Parse a tagged-union action body into the matching action dataclass."""
    tag = body.get("type")
    match tag:
        case "play_card":
            return PlayCard(player=_require_int(body, "player"), hand_index=_require_int(body, "hand_index"))
        case "cast_instant":
            return CastInstant(
                player=_require_int(body, "player"),
                hand_index=_require_int(body, "hand_index"),
                target_id=_optional_int(body, "target_id"),
            )
        case "pass_priority":
            return PassPriority(player=_require_int(body, "player"))
        case _:
            msg = f"unknown action type: {tag!r}"
            raise IllegalAction(msg)
