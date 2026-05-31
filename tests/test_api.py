"""API tests: drive the Litestar app over HTTP and confirm it is a thin shell over the engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from litestar.testing import TestClient

from mundane.api.app import create_app
from mundane.api.schemas import parse_action
from mundane.engine.actions import ACTION_TYPES, CastInstant, PassPriority, PlayCard
from mundane.engine.serialize import action_to_dict

if TYPE_CHECKING:
    from collections.abc import Iterator

    from litestar import Litestar

    from mundane.engine.actions import Action

COUNTERED_PARTY_SEQUENCE: list[dict[str, object]] = [
    {"type": "play_card", "player": 0, "hand_index": 0},
    {"type": "pass_priority", "player": 0},
    {"type": "cast_instant", "player": 1, "hand_index": 0},
    {"type": "pass_priority", "player": 0},
    {"type": "pass_priority", "player": 1},
    {"type": "pass_priority", "player": 0},
    {"type": "pass_priority", "player": 1},
]

ROUND_TRIP_ACTIONS: list[Action] = [
    PlayCard(player=0, hand_index=1),
    CastInstant(player=1, hand_index=2, target_id=3),
    CastInstant(player=0, hand_index=0),
    PassPriority(player=1),
]


@pytest.fixture
def client() -> Iterator[TestClient[Litestar]]:
    """Yield a TestClient backed by a freshly created app (and its own in-memory store)."""
    with TestClient(app=create_app()) as test_client:
        yield test_client


def test_play_through_scenario_leaves_alex_at_20(client: TestClient[Litestar]) -> None:
    """Creating a game and posting the countered-party sequence leaves Alex at 20 in DO_STUFF."""
    game_id = client.post("/games").json()["game_id"]
    for action in COUNTERED_PARTY_SEQUENCE:
        response = client.post(f"/games/{game_id}/actions", json=action)
        assert response.status_code == 201
    state = client.get(f"/games/{game_id}").json()
    assert state["players"][1]["composure"] == 20
    assert state["phase"] == "DO_STUFF"
    assert state["stack"] == []


def test_illegal_move_returns_422_and_leaves_state_untouched(client: TestClient[Litestar]) -> None:
    """An illegal move is rejected with 422 and the stored game is not changed at all."""
    game_id = client.post("/games").json()["game_id"]
    before = client.get(f"/games/{game_id}").json()

    response = client.post(
        f"/games/{game_id}/actions",
        json={"type": "cast_instant", "player": 0, "hand_index": 0},  # the party is not an instant
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "that card isn't an instant"

    assert client.get(f"/games/{game_id}").json() == before


def test_unknown_game_returns_404(client: TestClient[Litestar]) -> None:
    """Reading a game that was never created returns 404."""
    assert client.get("/games/does-not-exist").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"type": "teleport", "player": 0},                    # unknown discriminator
        {"player": 0, "hand_index": 0},                       # missing discriminator
        {"type": "play_card", "player": 0},                   # missing required field
        {"type": "play_card", "player": "zero", "hand_index": 0},  # wrong field type
    ],
)
def test_malformed_action_body_returns_422(client: TestClient[Litestar], body: dict[str, object]) -> None:
    """A body that does not describe a valid action is rejected with 422, not a 500."""
    game_id = client.post("/games").json()["game_id"]
    assert client.post(f"/games/{game_id}/actions", json=body).status_code == 422


def test_export_returns_log_and_final_state(client: TestClient[Litestar]) -> None:
    """The export endpoint returns the serialised action log alongside the final state."""
    game_id = client.post("/games").json()["game_id"]
    for action in COUNTERED_PARTY_SEQUENCE:
        client.post(f"/games/{game_id}/actions", json=action)

    exported = client.get(f"/games/{game_id}/export").json()
    assert sorted(exported) == ["final_state", "log"]
    log = exported["log"]
    assert len(log) == 7
    assert log[0] == {"type": "play_card", "player": 0, "hand_index": 0}
    assert log[2] == {"type": "cast_instant", "player": 1, "hand_index": 0, "target_id": None}
    assert exported["final_state"]["players"][1]["composure"] == 20


def test_export_is_a_downloadable_attachment(client: TestClient[Litestar]) -> None:
    """The export response is a JSON attachment, named per game, so it saves as a file."""
    game_id = client.post("/games").json()["game_id"]
    response = client.get(f"/games/{game_id}/export")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == f'attachment; filename="mundane-game-{game_id}.json"'
    assert response.headers["content-type"].startswith("application/json")
    assert sorted(response.json()) == ["final_state", "log"]


def test_action_json_round_trips_through_the_parser() -> None:
    """For every action type, action_to_dict then parse_action is the identity (parser <-> registry)."""
    assert {type(action) for action in ROUND_TRIP_ACTIONS} == set(ACTION_TYPES.values())
    for action in ROUND_TRIP_ACTIONS:
        assert parse_action(action_to_dict(action)) == action
