"""The Game wrapper: a :class:`GameState`, the card pool it runs on, and the action log.

A game is event-sourced. The state is a fold of ``apply_action`` over the log, so the log alone (plus
the card snapshot) can rebuild the state — exactly the "download game log" / replay payload. ``submit``
appends to the log **only when the action is accepted**; a rejected move (``IllegalAction``) never
happened and is never logged.

The resolved card **pool** lives here (not on :class:`GameState`): it carries bound effect closures,
which are code and must never reach serialisable state. The **snapshot** is the pool's plain-data,
JSON-ready mirror (set by the API at creation time) so an exported game replays self-contained.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .rules import apply_action
from .serialize import action_to_dict, state_to_dict
from .state import Card, GameState, Player

if TYPE_CHECKING:
    from .actions import Action


@dataclass
class Game:
    """A live game: its state, the card pool it runs on, the action log, and the export snapshot."""

    state: GameState
    cards: dict[str, Card]
    log: list[Action] = field(default_factory=list)
    card_snapshot: dict[str, object] = field(default_factory=dict)

    def submit(self, action: Action) -> GameState:
        """Apply ``action`` (raising ``IllegalAction`` if illegal) and, only on success, log it."""
        apply_action(self.state, action, self.cards)
        self.log.append(action)
        return self.state

    def export(self) -> dict[str, object]:
        """Return the serialised log, final state, and card snapshot — the download/replay payload."""
        return {
            "log": [action_to_dict(action) for action in self.log],
            "final_state": state_to_dict(self.state),
            "card_snapshot": self.card_snapshot,
        }


def new_game(cards: dict[str, Card]) -> Game:
    """Create the opening position: Steve (the party) vs Alex (the complaint), 5 Time each, in Plan.

    ``cards`` is the resolved pool the game runs on. The opening hands name cards from the core set
    (the demo deal); turning the pool into real per-player decks is a separate concern.
    """
    steve = Player(name="Steve", time=5, hand=["core:throw_a_house_party"])
    alex = Player(name="Alex", time=5, hand=["core:noise_complaint"])
    state = GameState(players=[steve, alex], active_player=0, priority_player=0, phase="PLAN")
    return Game(state=state, cards=cards)
