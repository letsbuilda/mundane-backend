"""D1 store tests: games persist as snapshot + action rows and replay to the same state.

``FakeD1`` mimics the slice of the D1 binding the store uses (prepare / bind / run / first / all) over an
in-memory ``sqlite3`` database built from the real ``migrations/``, so these run anywhere.
"""

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from litestar.exceptions import NotFoundException
from litestar.testing import TestClient

from mundane.api.app import create_app
from mundane.api.d1_store import D1GameStore
from mundane.api.set_loader import DEFAULT_SET_URLS, SetFetchError, load_sets, pool_from_snapshot
from mundane.api.store import GameConflictError
from mundane.engine.actions import PassPriority, PlayCard
from mundane.engine.serialize import state_to_dict

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from mundane.engine.game import Game

_ROOT = Path(__file__).parent.parent
_FIXTURE_BYTES = (Path(__file__).parent / "fixtures" / "core.json").read_bytes()


def _fake_fetch(url: str) -> bytes:
    """Serve the core fixture for the default set URL."""
    if url == DEFAULT_SET_URLS[0]:
        return _FIXTURE_BYTES
    msg = f"unexpected fetch in test: {url!r}"
    raise SetFetchError(msg)


class FakeStatement:
    """A prepared statement over sqlite3, shaped like D1's (results as plain dicts)."""

    def __init__(self, conn: sqlite3.Connection, query: str, values: tuple[object, ...] = ()) -> None:
        """Hold the query and its bound values."""
        self._conn = conn
        self._query = query
        self._values = values

    def bind(self, *values: object) -> FakeStatement:
        """Return the statement with ``values`` bound."""
        return FakeStatement(self._conn, self._query, values)

    async def run(self) -> object:
        """Execute; report affected rows under ``meta.changes`` like D1."""
        cursor = self._conn.execute(self._query, self._values)
        return {"success": True, "meta": {"changes": cursor.rowcount}}

    async def first(self) -> object:
        """Return the first row as a dict, or None."""
        row = self._conn.execute(self._query, self._values).fetchone()
        return dict(row) if row is not None else None

    async def all(self) -> object:
        """Return every row as dicts under ``results``."""
        return {"results": [dict(row) for row in self._conn.execute(self._query, self._values)]}


class FakeD1:
    """An in-memory D1 stand-in with the project's migrations applied."""

    def __init__(self) -> None:
        """Create the database and apply every migration in order."""
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        for migration in sorted((_ROOT / "migrations").glob("*.sql")):
            self.conn.executescript(migration.read_text(encoding="utf-8"))

    def prepare(self, query: str) -> FakeStatement:
        """Prepare ``query``."""
        return FakeStatement(self.conn, query)


def _run[T](coroutine: Coroutine[object, object, T]) -> T:
    """Run one store call to completion."""
    return asyncio.run(coroutine)


def test_a_game_survives_a_fresh_store() -> None:
    """A game played through one store instance reloads, move for move, from another (a new Worker)."""
    db = FakeD1()
    first = D1GameStore(db, fetch=_fake_fetch)
    game_id, game = _run(first.create("auth0|steve"))
    for action in (PlayCard(player=0, hand_index=0), PassPriority(player=0)):
        game.submit(action)
        _run(first.save(game_id, game))

    reloaded = _run(D1GameStore(db, fetch=_fake_fetch).get(game_id, "auth0|steve"))
    assert state_to_dict(reloaded.state) == state_to_dict(game.state)
    assert reloaded.log == game.log
    assert reloaded.card_snapshot == game.card_snapshot


def test_games_are_only_visible_to_their_owner() -> None:
    """Another player's game, and a game that doesn't exist, are the same 404."""
    store = D1GameStore(FakeD1(), fetch=_fake_fetch)
    game_id, _ = _run(store.create("auth0|steve"))
    with pytest.raises(NotFoundException):
        _run(store.get(game_id, "auth0|alex"))
    with pytest.raises(NotFoundException):
        _run(store.get("missing", "auth0|steve"))


def test_racing_moves_conflict_instead_of_overwriting() -> None:
    """Two requests that load the same game and both move: the second is refused, not silently lost."""
    store = D1GameStore(FakeD1(), fetch=_fake_fetch)
    game_id, _ = _run(store.create("auth0|steve"))
    one = _run(store.get(game_id, "auth0|steve"))
    two = _run(store.get(game_id, "auth0|steve"))

    one.submit(PlayCard(player=0, hand_index=0))
    _run(store.save(game_id, one))
    two.submit(PassPriority(player=0))
    with pytest.raises(GameConflictError):
        _run(store.save(game_id, two))

    assert _run(store.get(game_id, "auth0|steve")).log == one.log


def test_loader_failure_writes_nothing() -> None:
    """A game whose sets fail to load is never inserted."""
    db = FakeD1()
    store = D1GameStore(db, fetch=_fake_fetch)
    with pytest.raises(SetFetchError):
        _run(store.create("auth0|steve", ["https://raw.githubusercontent.com/letsbuilda/mundane-cards/main/x.json"]))
    assert db.conn.execute("SELECT count(*) FROM games").fetchone()[0] == 0


class _FakeVerifier:
    """Treat the bearer token as the player's id."""

    def verify(self, token: str) -> str:
        """Return the token itself as the subject."""
        return token


class _RacingStore(D1GameStore):
    """A store where a rival request lands its move right after this request loads the game."""

    async def get(self, game_id: str, owner: str) -> Game:
        """Load the game, then let a rival move first (once)."""
        game = await super().get(game_id, owner)
        rival = await super().get(game_id, owner)
        if not rival.log:
            rival.submit(PlayCard(player=0, hand_index=0))
            await super().save(game_id, rival)
        return game


def test_conflict_returns_409_over_http() -> None:
    """A move that loses the race is reported as 409 and leaves the winner's move in place."""
    db = FakeD1()
    store = _RacingStore(db, fetch=_fake_fetch)
    game_id, _ = _run(store.create("auth0|steve"))
    with TestClient(app=create_app(store=store, verifier=_FakeVerifier())) as client:
        client.headers["Authorization"] = "Bearer auth0|steve"
        move = {"type": "play_card", "player": 0, "hand_index": 0}
        assert client.post(f"/games/{game_id}/actions", json=move).status_code == 409
    assert len(_run(D1GameStore(db, fetch=_fake_fetch).get(game_id, "auth0|steve")).log) == 1


def test_pool_from_snapshot_rebuilds_the_loaded_pool() -> None:
    """The snapshot alone rebuilds the same cards the loader resolved (no refetch needed)."""
    pool = load_sets(DEFAULT_SET_URLS, fetch=_fake_fetch)
    rebuilt = pool_from_snapshot(json.loads(json.dumps(pool.snapshot)))
    assert rebuilt.keys() == pool.cards.keys()
    for card_id, card in pool.cards.items():
        assert (rebuilt[card_id].name, rebuilt[card_id].cost, rebuilt[card_id].type) == (
            card.name,
            card.cost,
            card.type,
        )
