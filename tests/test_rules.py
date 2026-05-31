"""Engine rules tests: the legality preconditions mirrored one-for-one, plus the countered party."""

from __future__ import annotations

import dataclasses
import json
from copy import deepcopy
from functools import reduce

import pytest

from mundane.engine.actions import Action, CastInstant, IllegalAction, PassPriority, PlayCard
from mundane.engine.rules import apply_action
from mundane.engine.serialize import dumps, state_to_dict
from mundane.engine.state import GameState, Player


def party_scenario() -> GameState:
    """Build the opening position: Steve holds the party, Alex holds the complaint, 5 Time each."""
    steve = Player(name="Steve", time=5, hand=["throw_a_house_party"])
    alex = Player(name="Alex", time=5, hand=["noise_complaint"])
    return GameState(players=[steve, alex], active_player=0, priority_player=0, phase="PLAN")


COUNTERED_PARTY_LOG: list[Action] = [
    PlayCard(player=0, hand_index=0),  # Steve casts Throw a House Party -> stack
    PassPriority(player=0),  # Steve passes; priority -> Alex
    CastInstant(player=1, hand_index=0),  # Alex responds with Noise Complaint -> top of stack
    PassPriority(player=0),  # priority back to active Steve; he passes
    PassPriority(player=1),  # both passed -> resolve top: complaint counters party
    PassPriority(player=0),  # stack empty now; pass again...
    PassPriority(player=1),  # ...both pass -> phase advances
]


def _assert_rejected(state: GameState, action: Action, needle: str) -> None:
    """Assert ``action`` is rejected with a message matching ``needle`` and state is unchanged."""
    before = deepcopy(state)
    with pytest.raises(IllegalAction, match=needle):
        apply_action(state, action)
    assert state == before


def test_noise_complaint_counters_the_party() -> None:
    """Alex's Noise Complaint counters Steve's party; Alex stays at 20 and both cards hit discard."""
    final = reduce(apply_action, COUNTERED_PARTY_LOG, party_scenario())
    assert final.players[1].composure == 20
    assert final.players[0].discard == ["throw_a_house_party"]
    assert final.players[1].discard == ["noise_complaint"]
    assert final.phase == "DO_STUFF"
    assert final.stack == []


def test_state_is_json_serialisable_by_id() -> None:
    """A mid-game state serialises to JSON containing card ids, never effect-function reprs."""
    state = party_scenario()
    apply_action(state, PlayCard(player=0, hand_index=0))  # party now on the stack
    blob = json.dumps(dataclasses.asdict(state))
    assert "throw_a_house_party" in blob
    assert "<function" not in blob


def test_state_to_dict_round_trips_through_json() -> None:
    """A mid-game state serialises to a JSON string that parses back to the same dict."""
    state = party_scenario()
    apply_action(state, PlayCard(player=0, hand_index=0))  # party on the stack
    blob = dumps(state_to_dict(state))
    parsed = json.loads(blob)
    assert parsed == state_to_dict(state)
    assert parsed["stack"][0]["card_id"] == "throw_a_house_party"
    assert parsed["players"][0]["hand"] == []


def test_rejected_action_mutates_nothing() -> None:
    """A rejected move raises IllegalAction and leaves the state byte-for-byte unchanged."""
    _assert_rejected(party_scenario(), CastInstant(player=0, hand_index=0), "isn't an instant")


def test_play_card_requires_priority() -> None:
    """Only the player who holds priority may play a card."""
    _assert_rejected(party_scenario(), PlayCard(player=1, hand_index=0), "don't have priority")


def test_play_card_requires_active_player() -> None:
    """A non-active player who somehow holds priority still cannot play sorcery-speed cards."""
    state = party_scenario()
    state.priority_player = 1
    _assert_rejected(state, PlayCard(player=1, hand_index=0), "only the active player")


def test_play_card_only_during_plan() -> None:
    """Sorcery-speed cards are legal only in the Plan phase."""
    state = party_scenario()
    state.phase = "DO_STUFF"
    _assert_rejected(state, PlayCard(player=0, hand_index=0), "only during Plan")


def test_play_card_requires_empty_stack() -> None:
    """Sorcery-speed cards require an empty stack."""
    state = party_scenario()
    state.players[0].hand = ["throw_a_house_party", "espresso_machine"]
    apply_action(state, PlayCard(player=0, hand_index=0))  # party -> stack, priority stays with Steve
    _assert_rejected(state, PlayCard(player=0, hand_index=0), "stack must be empty")


def test_play_card_rejects_an_instant() -> None:
    """An instant must be cast with CastInstant, not played at sorcery speed."""
    state = party_scenario()
    state.players[0].hand = ["noise_complaint"]
    _assert_rejected(state, PlayCard(player=0, hand_index=0), "use CastInstant for instants")


def test_play_card_requires_enough_time() -> None:
    """Playing a card costs Time; you cannot overspend."""
    state = party_scenario()
    state.players[0].time = 2  # the party costs 3
    _assert_rejected(state, PlayCard(player=0, hand_index=0), "not enough Time")


def test_cast_instant_requires_priority() -> None:
    """Only the player who holds priority may cast an instant."""
    state = party_scenario()
    state.players[1].hand = ["noise_complaint"]
    _assert_rejected(state, CastInstant(player=1, hand_index=0), "don't have priority")


def test_pass_priority_requires_priority() -> None:
    """Only the player who holds priority may pass it."""
    _assert_rejected(party_scenario(), PassPriority(player=1), "don't have priority to pass")


def test_no_actions_after_game_over() -> None:
    """Once a winner is decided, every action is rejected."""
    state = party_scenario()
    state.winner = 0
    _assert_rejected(state, PassPriority(player=0), "the game is over")


def test_permanent_resolves_onto_the_board() -> None:
    """A PERSON / APPLIANCE / HABIT resolves onto its controller's board, not the discard."""
    state = party_scenario()
    state.players[0].hand = ["helpful_roommate"]
    log: list[Action] = [PlayCard(player=0, hand_index=0), PassPriority(player=0), PassPriority(player=1)]
    final = reduce(apply_action, log, state)
    assert final.players[0].board == ["helpful_roommate"]
    assert final.players[0].discard == []


def test_winner_is_set_when_composure_hits_zero() -> None:
    """When a party drops a player's Composure to 0 or below, the opponent wins."""
    state = party_scenario()
    state.players[1].composure = 2  # the party deals 3
    log: list[Action] = [PlayCard(player=0, hand_index=0), PassPriority(player=0), PassPriority(player=1)]
    final = reduce(apply_action, log, state)
    assert final.players[1].composure == -1
    assert final.winner == 0
