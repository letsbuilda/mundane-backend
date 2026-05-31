"""The Game wrapper: a :class:`GameState` plus the ordered log of actions that produced it.

A game is event-sourced. The state is a fold of ``apply_action`` over the log, so the log alone can
rebuild the state — which is exactly the "download game log" / replay payload. ``submit`` appends to
the log **only when the action is accepted**; a rejected move (``IllegalAction``) never happened and
is never logged.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .rules import apply_action
from .serialize import action_to_dict, state_to_dict
from .state import GameState, Player

if TYPE_CHECKING:
    from .actions import Action


@dataclass
class Game:
    """A live game: its current state and the action log that produced it."""

    state: GameState
    log: list[Action] = field(default_factory=list)

    def submit(self, action: Action) -> GameState:
        """Apply ``action`` (raising ``IllegalAction`` if illegal) and, only on success, log it."""
        apply_action(self.state, action)
        self.log.append(action)
        return self.state

    def export(self) -> dict[str, object]:
        """Return the serialised action log and final state — the download payload and replay seed."""
        return {
            "log": [action_to_dict(action) for action in self.log],
            "final_state": state_to_dict(self.state),
        }


def new_game() -> Game:
    """Create the opening position: Steve (the party) vs Alex (the complaint), 5 Time each, in Plan."""
    steve = Player(name="Steve", time=5, hand=["throw_a_house_party"])
    alex = Player(name="Alex", time=5, hand=["noise_complaint"])
    state = GameState(players=[steve, alex], active_player=0, priority_player=0, phase="PLAN")
    return Game(state=state)
