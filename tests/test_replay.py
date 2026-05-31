"""Replay tests: a game's state is a pure fold of its action log (the event-sourcing property)."""

from __future__ import annotations

from functools import reduce

import pytest

from mundane.engine.actions import CastInstant, IllegalAction, PassPriority, PlayCard
from mundane.engine.game import Game, new_game
from mundane.engine.rules import apply_action
from mundane.engine.serialize import state_to_dict


def _play_countered_party(game: Game) -> None:
    """Submit the canonical countered-party sequence to ``game``."""
    game.submit(PlayCard(player=0, hand_index=0))
    game.submit(PassPriority(player=0))
    game.submit(CastInstant(player=1, hand_index=0))
    game.submit(PassPriority(player=0))
    game.submit(PassPriority(player=1))
    game.submit(PassPriority(player=0))
    game.submit(PassPriority(player=1))


def test_state_is_the_fold_of_its_log() -> None:
    """Folding a game's recorded log over a fresh initial state reproduces the live state."""
    game = new_game()
    _play_countered_party(game)
    replayed = reduce(apply_action, game.log, new_game().state)
    assert replayed == game.state


def test_rejected_moves_are_not_logged() -> None:
    """A rejected action does not appear in the log, and the log stays a faithful replay."""
    game = new_game()
    with pytest.raises(IllegalAction):
        game.submit(CastInstant(player=0, hand_index=0))  # the party is not an instant
    assert game.log == []
    _play_countered_party(game)
    assert len(game.log) == 7
    assert reduce(apply_action, game.log, new_game().state) == game.state


def test_export_contains_log_and_final_state() -> None:
    """export() returns the serialised log plus the final state, ready to download and to replay."""
    game = new_game()
    _play_countered_party(game)
    exported = game.export()

    assert exported["final_state"] == state_to_dict(game.state)

    log = exported["log"]
    assert isinstance(log, list)
    assert log[0] == {"type": "play_card", "player": 0, "hand_index": 0}
    assert log[2] == {"type": "cast_instant", "player": 1, "hand_index": 0, "target_id": None}
    assert log[-1] == {"type": "pass_priority", "player": 1}
