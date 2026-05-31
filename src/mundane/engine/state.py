"""Game-state dataclasses: the single source of truth for a Mundane game.

Nothing in this module mutates state; :func:`mundane.engine.rules.apply_action` is the only
thing that does. Cards are referenced **by id** throughout the state (see
:data:`mundane.engine.cards.CARD_LIBRARY`); card *objects* — and the effect functions they carry —
live only in the library, never in serialisable state. That separation is what lets a whole
:class:`GameState` round-trip through JSON.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class CardType(Enum):
    """The five kinds of card. The first three are permanents (they stay on the board)."""

    PERSON = "person"        # creature-like; stays on the board once it resolves
    APPLIANCE = "appliance"  # artifact-like permanent
    HABIT = "habit"          # enchantment-like permanent
    TASK = "task"            # sorcery-speed one-shot; uses the stack
    INSTANT = "instant"      # can be cast any time you hold priority


type Effect = Callable[[GameState, StackItem], None]
"""An effect mutates the state when its card resolves, given the resolving :class:`StackItem`."""


def _no_effect(_state: GameState, _item: StackItem) -> None:
    """Do nothing. Permanents resolve onto the board, so they carry this placeholder effect."""


@dataclass
class Card:
    """A card *definition*. Lives only in CARD_LIBRARY; state refers to it by ``id``."""

    id: str
    name: str
    cost: int                      # Time required to play it
    type: CardType
    effect: Effect = _no_effect
    text: str = ""


PERMANENTS = (CardType.PERSON, CardType.APPLIANCE, CardType.HABIT)


@dataclass
class Player:
    """One household. Card collections hold library ids (``str``), never Card objects."""

    name: str
    composure: int = 20            # the "life total" - hit 0 and your household falls apart
    time: int = 0                  # resource available this turn
    hand: list[str] = field(default_factory=list)
    board: list[str] = field(default_factory=list)
    deck: list[str] = field(default_factory=list)
    discard: list[str] = field(default_factory=list)


@dataclass
class StackItem:
    """A card waiting to resolve. ``id`` is unique within a game (see ``GameState.next_stack_id``)."""

    card_id: str
    controller: int                # index into state.players
    target_id: int | None = None
    id: int = 0                    # assigned by the engine from GameState.next_stack_id


PHASES = ["RESET", "WAKE_UP", "PLAN", "DO_STUFF", "WIND_DOWN"]


@dataclass
class GameState:
    """The entire game. Fully JSON-serialisable: every field is data, never code."""

    players: list[Player]
    active_player: int = 0         # whose TURN it is (slow: changes once per turn)
    priority_player: int = 0       # who may act RIGHT NOW (fast: changes constantly)
    phase: str = "PLAN"
    stack: list[StackItem] = field(default_factory=list)
    passes_in_a_row: int = 0       # consecutive priority passes with nobody acting
    turn: int = 1
    winner: int | None = None
    next_stack_id: int = 1         # stable id source for stack items; keeps state self-contained

    def next_player(self, i: int) -> int:
        """Return the index of the player after ``i`` (wraps around the table)."""
        return (i + 1) % len(self.players)

    def opponent(self, i: int) -> int:
        """Return the opponent of player ``i`` (2-player convenience)."""
        return (i + 1) % len(self.players)
