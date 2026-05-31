"""The Litestar application: HTTP in, engine actions out, state back as JSON.

The API is a thin translator. It never mutates :class:`GameState` directly — it parses requests into
engine actions and calls ``Game.submit``, then maps the engine's :class:`IllegalAction` onto HTTP 422.
All game legality lives in the engine.

The game store is an in-memory ``dict``, supplied via dependency injection. It is **volatile** (lost
on restart); see the README. Keeping it behind the small :class:`GameStore` interface
(create / get / save) makes swapping it for Redis or SQLite a localised change.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from litestar import Litestar, MediaType, Request, Response, get, post
from litestar.di import Provide
from litestar.exceptions import NotFoundException
from litestar.status_codes import HTTP_422_UNPROCESSABLE_ENTITY

from mundane.engine.actions import IllegalAction
from mundane.engine.game import Game, new_game
from mundane.engine.serialize import state_to_dict

from .schemas import parse_action


class GameStore:
    """In-memory game store. Volatile: its contents are lost when the process restarts.

    Deliberately an opaque service (not a dataclass), so the framework treats it as an injected
    dependency rather than request data to introspect. Swapping in Redis or SQLite later means
    reimplementing just create / get / save behind this same interface.
    """

    def __init__(self) -> None:
        """Start with no games."""
        self.games: dict[str, Game] = {}

    def create(self) -> tuple[str, Game]:
        """Create and store a new game, returning its id and the game."""
        game_id = uuid4().hex
        game = new_game()
        self.games[game_id] = game
        return game_id, game

    def get(self, game_id: str) -> Game:
        """Return the stored game, or raise ``NotFoundException`` (-> 404) if there is none."""
        try:
            return self.games[game_id]
        except KeyError as exc:
            msg = f"no game with id {game_id!r}"
            raise NotFoundException(detail=msg) from exc

    def save(self, game_id: str, game: Game) -> None:
        """Persist the game. A no-op for the in-memory store (games already mutate in place)."""
        self.games[game_id] = game


def _illegal_action_handler(_request: Request[Any, Any, Any], exc: Exception) -> Response[dict[str, str]]:
    """Map a rejected move (``IllegalAction``) onto HTTP 422; the stored game is left unchanged."""
    return Response(
        content={"detail": str(exc)},
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        media_type=MediaType.JSON,
    )


@post("/games", sync_to_thread=False)
def create_game(store: GameStore) -> dict[str, object]:
    """Create a new game; return its id and initial state."""
    game_id, game = store.create()
    return {"game_id": game_id, "state": state_to_dict(game.state)}


@get("/games/{game_id:str}", sync_to_thread=False)
def read_game(game_id: str, store: GameStore) -> dict[str, object]:
    """Return the current state of a game."""
    return state_to_dict(store.get(game_id).state)


@post("/games/{game_id:str}/actions", sync_to_thread=False)
def submit_action(game_id: str, data: dict[str, object], store: GameStore) -> dict[str, object]:
    """Submit a move. An illegal move raises ``IllegalAction`` (-> 422) and changes nothing."""
    game = store.get(game_id)
    state = game.submit(parse_action(data))
    store.save(game_id, game)
    return state_to_dict(state)


@get("/games/{game_id:str}/export", sync_to_thread=False)
def export_game(game_id: str, store: GameStore) -> Response[dict[str, object]]:
    """Return the game's action log and final state as a downloadable JSON attachment.

    The Content-Disposition attachment header is what turns this response into a saved file — it is
    all the "Download game log" button on the game-over screen needs to point at.
    """
    export = store.get(game_id).export()
    filename = f"mundane-game-{game_id}.json"
    return Response(
        content=export,
        media_type=MediaType.JSON,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def create_app(store: GameStore | None = None) -> Litestar:
    """Build the Litestar app. Pass a ``store`` to share/inspect it (tests do); else a fresh one."""
    shared_store = store if store is not None else GameStore()

    def provide_store() -> GameStore:
        """Provide the single in-memory store shared across every request."""
        return shared_store

    return Litestar(
        route_handlers=[create_game, read_game, submit_action, export_game],
        dependencies={"store": Provide(provide_store, sync_to_thread=False)},
        exception_handlers={IllegalAction: _illegal_action_handler},
    )


app = create_app()
