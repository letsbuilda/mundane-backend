"""API tests: drive the Litestar app over HTTP and confirm it is a thin shell over the engine."""

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from litestar.testing import TestClient

from mundane.api.app import GameStore, create_app
from mundane.api.schemas import parse_action
from mundane.api.set_loader import DEFAULT_SET_URLS, Fetcher, SetFetchError
from mundane.engine.actions import ACTION_TYPES, CastInstant, PassPriority, PlayCard
from mundane.engine.serialize import action_to_dict

if TYPE_CHECKING:
    from collections.abc import Iterator

    from litestar import Litestar

    from mundane.engine.actions import Action

_FIXTURE_BYTES = (Path(__file__).parent / "fixtures" / "core.json").read_bytes()
_DEFAULT_URL = DEFAULT_SET_URLS[0]
# A second allowlisted URL the "bad set" fetchers can answer for.
_ALLOWLISTED_URL = "https://raw.githubusercontent.com/letsbuilda/mundane-cards/main/sets/extra.json"


def _fake_fetch(url: str) -> bytes:
    """Serve the core fixture for the default (allowlisted) URL; raise if any other URL is reached."""
    if url == _DEFAULT_URL:
        return _FIXTURE_BYTES
    msg = f"unexpected fetch in test: {url!r}"
    raise SetFetchError(msg)


def _serve(body: bytes) -> Fetcher:
    """Return a fetcher that answers with ``body`` (the URL must still pass the allowlist first)."""

    def fetch(_url: str) -> bytes:
        """Return the captured body regardless of URL."""
        return body

    return fetch


def _boom_fetch(_url: str) -> bytes:
    """Fail as if the upstream were down (a fetcher that always raises)."""
    msg = "upstream is down"
    raise SetFetchError(msg)


def _set_bytes(cards: list[dict[str, object]]) -> bytes:
    """Serialise a minimal, otherwise-valid set wrapping ``cards`` to bytes."""
    return json.dumps({"set_id": "extra", "name": "Extra", "version": "1.0.0", "cards": cards}).encode()


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
    """Yield a TestClient whose store resolves card sets from the local core fixture (offline)."""
    with TestClient(app=create_app(store=GameStore(fetch=_fake_fetch))) as test_client:
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
        {"type": "teleport", "player": 0},  # unknown discriminator
        {"player": 0, "hand_index": 0},  # missing discriminator
        {"type": "play_card", "player": 0},  # missing required field
        {"type": "play_card", "player": "zero", "hand_index": 0},  # wrong field type
    ],
)
def test_malformed_action_body_returns_422(client: TestClient[Litestar], body: dict[str, object]) -> None:
    """A body that does not describe a valid action is rejected with 422, not a 500."""
    game_id = client.post("/games").json()["game_id"]
    assert client.post(f"/games/{game_id}/actions", json=body).status_code == 422


def test_create_game_snapshots_the_pool(client: TestClient[Litestar]) -> None:
    """Creating a game snapshots the resolved pool (composed ids + a content hash) into the export."""
    game_id = client.post("/games").json()["game_id"]
    snapshot = client.get(f"/games/{game_id}/export").json()["card_snapshot"]
    assert snapshot["content_hash"].startswith("sha256:")
    ids = [card["id"] for card in snapshot["cards"]]
    assert "core:throw_a_house_party" in ids
    assert "core:noise_complaint" in ids


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/letsbuilda/mundane-cards/main/sets/core.json",  # wrong host
        "https://raw.githubusercontent.com.evil.com/letsbuilda/mundane-cards/main/sets/core.json",  # host as prefix
        "https://raw.githubusercontent.com/letsbuilda/other-repo/main/sets/core.json",  # wrong path prefix
        "http://raw.githubusercontent.com/letsbuilda/mundane-cards/main/sets/core.json",  # not https
    ],
)
def test_non_allowlisted_url_returns_422(client: TestClient[Litestar], url: str) -> None:
    """A set URL off the allowlist (host parsed, not substring-matched) is rejected with 422."""
    assert client.post("/games", json={"set_urls": [url]}).status_code == 422


def test_set_urls_must_be_a_list_of_strings(client: TestClient[Litestar]) -> None:
    """A ``set_urls`` field that is not a list of strings is rejected with 422."""
    assert client.post("/games", json={"set_urls": "not-a-list"}).status_code == 422


def test_schema_invalid_set_returns_422() -> None:
    """A fetched set that fails schema validation (here: no ``cards``) is rejected with 422."""
    body = json.dumps({"set_id": "extra", "name": "Extra", "version": "1.0.0"}).encode()
    with TestClient(app=create_app(store=GameStore(fetch=_serve(body)))) as client:
        assert client.post("/games", json={"set_urls": [_ALLOWLISTED_URL]}).status_code == 422


def test_unknown_effect_returns_422() -> None:
    """A schema-valid set whose card names an effect outside the engine vocabulary is rejected (422)."""
    body = _set_bytes([{"id": "x", "name": "X", "cost": 1, "type": "task", "effect": "teleport", "text": "t"}])
    with TestClient(app=create_app(store=GameStore(fetch=_serve(body)))) as client:
        assert client.post("/games", json={"set_urls": [_ALLOWLISTED_URL]}).status_code == 422


def test_bad_effect_params_returns_422() -> None:
    """A card whose params are wrong for its effect (damage_composure without amount) is rejected (422)."""
    body = _set_bytes([{"id": "x", "name": "X", "cost": 3, "type": "task", "effect": "damage_composure", "text": "t"}])
    with TestClient(app=create_app(store=GameStore(fetch=_serve(body)))) as client:
        assert client.post("/games", json={"set_urls": [_ALLOWLISTED_URL]}).status_code == 422


def test_duplicate_ids_returns_422() -> None:
    """A set that defines the same composed id twice is rejected with 422."""
    card: dict[str, object] = {"id": "dup", "name": "Dup", "cost": 1, "type": "task", "effect": "none", "text": "t"}
    body = _set_bytes([card, {**card, "name": "Dup 2"}])
    with TestClient(app=create_app(store=GameStore(fetch=_serve(body)))) as client:
        assert client.post("/games", json={"set_urls": [_ALLOWLISTED_URL]}).status_code == 422


def test_fetch_failure_returns_502() -> None:
    """An upstream fetch failure (network/timeout/oversize) maps to 502, not 500."""
    with TestClient(app=create_app(store=GameStore(fetch=_boom_fetch))) as client:
        assert client.post("/games", json={"set_urls": [_ALLOWLISTED_URL]}).status_code == 502


def test_loader_failure_leaves_store_untouched() -> None:
    """When loading fails, nothing is stored — the referee discipline holds at the API layer too."""
    store = GameStore(fetch=_fake_fetch)
    with TestClient(app=create_app(store=store)) as client:
        assert client.post("/games", json={"set_urls": ["https://evil.example/x"]}).status_code == 422
    assert store.games == {}


def test_export_returns_log_final_state_and_snapshot(client: TestClient[Litestar]) -> None:
    """The export endpoint returns the action log, the final state, and the card snapshot."""
    game_id = client.post("/games").json()["game_id"]
    for action in COUNTERED_PARTY_SEQUENCE:
        client.post(f"/games/{game_id}/actions", json=action)

    exported = client.get(f"/games/{game_id}/export").json()
    assert sorted(exported) == ["card_snapshot", "final_state", "log"]
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
    assert sorted(response.json()) == ["card_snapshot", "final_state", "log"]


def test_action_json_round_trips_through_the_parser() -> None:
    """For every action type, action_to_dict then parse_action is the identity (parser <-> registry)."""
    assert {type(action) for action in ROUND_TRIP_ACTIONS} == set(ACTION_TYPES.values())
    for action in ROUND_TRIP_ACTIONS:
        assert parse_action(action_to_dict(action)) == action
