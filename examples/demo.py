"""Runnable demo: Steve's house party gets shut down by Alex's noise complaint.

Run with ``python examples/demo.py``. This is the scenario the engine was designed around;
it doubles as a smoke check that ``apply_action`` still behaves as intended. The cards come from a
local set fixture (``examples/core.json``), built through the same loader the API uses.
"""

import json
from functools import partial, reduce
from pathlib import Path

from mundane.engine.actions import Action, CastInstant, IllegalAction, PassPriority, PlayCard
from mundane.engine.cards import build_pool
from mundane.engine.rules import apply_action
from mundane.engine.state import GameState, Player

_CORE_SET = json.loads((Path(__file__).parent / "core.json").read_text(encoding="utf-8"))


def demo() -> None:
    """Play the canonical scenario and print the outcome."""
    pool = build_pool(_CORE_SET)
    step = partial(apply_action, cards=pool)

    steve = Player(name="Steve", time=5, hand=["core:throw_a_house_party"])
    alex = Player(name="Alex", time=5, hand=["core:noise_complaint"])
    state = GameState(players=[steve, alex], active_player=0, priority_player=0, phase="PLAN")

    # The engine is a referee. Illegal actions are rejected and change nothing:
    try:
        apply_action(state, CastInstant(player=0, hand_index=0), pool)  # the party isn't an instant
    except IllegalAction as exc:
        print(f"rejected, state untouched: {exc}")

    # A legal game is just a fold over a stream of actions, interleaved between players:
    # who acts next is whatever the state says holds priority.
    action_log: list[Action] = [
        PlayCard(player=0, hand_index=0),  # Steve casts Throw a House Party -> stack
        PassPriority(player=0),  # Steve passes; priority -> Alex
        CastInstant(player=1, hand_index=0),  # Alex responds; Noise Complaint -> top of stack
        PassPriority(player=0),  # priority went back to active Steve; he passes
        PassPriority(player=1),  # both passed -> resolve top: complaint counters party
        PassPriority(player=0),  # stack empty now; passes again...
        PassPriority(player=1),  # ...both pass -> phase advances
    ]
    final = reduce(step, action_log, state)

    steve_discard = [pool[card_id].name for card_id in final.players[0].discard]
    alex_discard = [pool[card_id].name for card_id in final.players[1].discard]
    print(f"Alex's Composure: {final.players[1].composure}   (20 = the party never landed)")
    print(f"Steve's discard:  {steve_discard}")
    print(f"Alex's discard:   {alex_discard}")
    print(f"Phase now:        {final.phase}, stack size: {len(final.stack)}")


if __name__ == "__main__":  # pragma: no cover
    demo()
