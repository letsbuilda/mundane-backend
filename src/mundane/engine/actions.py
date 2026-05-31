"""Player actions: the data players submit, plus the rejection exception.

Actions are *data*, not method calls — a whole game is ``reduce(apply_action, actions, initial)``.
:data:`ACTION_TYPES` is the single canonical registry mapping JSON discriminator tags to action
classes; both the JSON export (``serialize.py``) and the HTTP parser (``api/schemas.py``) derive
from it so the wire format can never drift from the engine.
"""

from dataclasses import dataclass


@dataclass
class PlayCard:
    """Sorcery-speed play of a PERSON / APPLIANCE / HABIT / TASK from hand."""

    player: int
    hand_index: int


@dataclass
class CastInstant:
    """Cast an INSTANT from hand. Legal any time the player holds priority."""

    player: int
    hand_index: int
    target_id: int | None = None


@dataclass
class PassPriority:
    """Pass priority. The phase advances as a *consequence* of passing, not via its own action."""

    player: int


type Action = PlayCard | CastInstant | PassPriority
"""The closed set of moves a player may submit."""


ACTION_TYPES: dict[str, type[Action]] = {
    "play_card": PlayCard,
    "cast_instant": CastInstant,
    "pass_priority": PassPriority,
}
"""Canonical JSON tag -> action-class registry (the ``type`` discriminator values)."""


class IllegalAction(Exception):  # noqa: N818  (public API name fixed by the spec)
    """Raised when an action is rejected. State is never mutated on rejection."""
