"""Cloudflare D1 game store: games survive restarts and are shared by every Worker instance.

A game is event-sourced (see :mod:`mundane.engine.game`), so D1 stores exactly what replays it: the card
snapshot once, when the game is created, and each accepted action as its own row (schema in
``migrations/``). Loading a game rebuilds the pool from its snapshot and folds the actions back over the
opening position; live state is never stored, so there is nothing to drift from the log.

Two requests racing on one game both try to append action number ``n``. The ``(game_id, seq)`` primary
key lets the first win; the second sees zero rows changed and raises :class:`GameConflictError`
(HTTP 409), so a move is never silently lost or applied on top of a stale state.

The binding is typed structurally (:class:`D1Database`) so tests can drive this store with a small
``sqlite3`` stand-in; inside a Worker it is the real ``env.DB`` binding.
"""

import json
from typing import TYPE_CHECKING, Any, Protocol, cast
from uuid import uuid4

from mundane.engine.serialize import action_to_dict

from .set_loader import Fetcher, default_fetch
from .store import GameConflictError, GameStore, not_found, replay_game, start_game

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mundane.engine.game import Game


class D1Statement(Protocol):
    """A prepared D1 statement: bind parameters, then run it or read rows."""

    def bind(self, *values: object) -> D1Statement:
        """Return the statement with ``values`` bound to its ``?`` placeholders."""
        ...

    async def run(self) -> object:
        """Execute the statement; the result's ``meta.changes`` counts affected rows."""
        ...

    async def first(self) -> object:
        """Return the first row (or ``None``)."""
        ...

    async def all(self) -> object:
        """Return every row, under ``results``."""
        ...


class D1Database(Protocol):
    """The slice of the D1 binding this store uses."""

    def prepare(self, query: str) -> D1Statement:
        """Prepare ``query``."""
        ...


def _py(value: object) -> Any:  # noqa: ANN401  (D1 rows are untyped JSON-shaped data)
    """Convert a JavaScript result to Python data (a no-op for values that already are)."""
    to_py = getattr(value, "to_py", None)
    return to_py() if callable(to_py) else value


class D1GameStore(GameStore):
    """Game store backed by a Cloudflare D1 database (see the module docstring for the data model)."""

    def __init__(self, db: D1Database, *, fetch: Fetcher = default_fetch) -> None:
        """Store games in ``db``, using ``fetch`` to retrieve card sets for new games."""
        self._db = db
        self._fetch = fetch

    async def create(self, owner: str, set_urls: Sequence[str] | None = None) -> tuple[str, Game]:
        """Resolve ``set_urls``, then insert the game. A loader error raises before anything is written."""
        game = start_game(set_urls, self._fetch)
        game_id = uuid4().hex
        await (
            self._db.prepare("INSERT INTO games (id, owner, card_snapshot) VALUES (?, ?, ?)")
            .bind(game_id, owner, json.dumps(game.card_snapshot))
            .run()
        )
        return game_id, game

    async def get(self, game_id: str, owner: str) -> Game:
        """Replay the stored game, or raise ``NotFoundException`` (-> 404) if it is missing or not ``owner``'s."""
        row = _py(await self._db.prepare("SELECT owner, card_snapshot FROM games WHERE id = ?").bind(game_id).first())
        if row is None or row["owner"] != owner:
            raise not_found(game_id)
        rows = _py(
            await self._db.prepare("SELECT action FROM actions WHERE game_id = ? ORDER BY seq").bind(game_id).all(),
        )["results"]
        return replay_game(json.loads(row["card_snapshot"]), (json.loads(r["action"]) for r in rows))

    async def save(self, game_id: str, game: Game) -> None:
        """Append the game's newest action; raise :class:`GameConflictError` if another request beat it."""
        if not game.log:
            return
        seq = len(game.log) - 1
        result = _py(
            await self._db.prepare(
                "INSERT INTO actions (game_id, seq, action) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            )
            .bind(game_id, seq, json.dumps(action_to_dict(game.log[-1])))
            .run(),
        )
        if cast("int", result["meta"]["changes"]) == 0:
            msg = "the game moved on before this move landed; reload and try again"
            raise GameConflictError(msg)
