"""The Litestar application: HTTP in, engine actions out, state back as JSON.

The API is a thin translator. It never mutates :class:`GameState` directly — it parses requests into
engine actions and calls ``Game.submit``, then maps the engine's :class:`IllegalAction` onto HTTP 422.
All game legality lives in the engine. Loading a game's cards (allowlist, fetch, schema-validate,
snapshot) lives in :mod:`mundane.api.set_loader`; the engine receives only the resolved pool.

The game store is an in-memory ``dict``, supplied via dependency injection. It is **volatile** (lost
on restart); see the README. Keeping it behind the small :class:`GameStore` interface
(create / get / save) makes swapping it for Redis or SQLite a localised change.
"""

from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from litestar import Litestar, MediaType, Request, Response, get, post
from litestar.di import Provide
from litestar.exceptions import NotFoundException
from litestar.status_codes import HTTP_422_UNPROCESSABLE_ENTITY, HTTP_502_BAD_GATEWAY

from mundane.engine.actions import IllegalAction
from mundane.engine.cards import DuplicateCardError, InvalidEffectParamsError, UnknownEffectError
from mundane.engine.game import Game, new_game
from mundane.engine.serialize import state_to_dict

from .schemas import parse_action
from .set_loader import (
    DEFAULT_SET_URLS,
    Fetcher,
    SetFetchError,
    SetSchemaError,
    SetURLNotAllowedError,
    default_fetch,
    load_sets,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class GameStore:
    """In-memory game store. Volatile: its contents are lost when the process restarts.

    Deliberately an opaque service (not a dataclass), so the framework treats it as an injected
    dependency rather than request data to introspect. Swapping in Redis or SQLite later means
    reimplementing just create / get / save behind this same interface. ``fetch`` is injectable so
    tests can resolve set URLs from a local fixture instead of the network.
    """

    def __init__(self, *, fetch: Fetcher = default_fetch) -> None:
        """Start with no games, using ``fetch`` to retrieve card sets."""
        self.games: dict[str, Game] = {}
        self._fetch = fetch

    def create(self, set_urls: Sequence[str] | None = None) -> tuple[str, Game]:
        """Resolve ``set_urls`` (default: the core set), then create and store a new game.

        Loading happens **before** the store is touched, so any loader error leaves it unchanged.
        """
        pool = load_sets(set_urls or DEFAULT_SET_URLS, fetch=self._fetch)
        game_id = uuid4().hex
        game = new_game(pool.cards)
        game.card_snapshot = pool.snapshot
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


def _unprocessable_handler(_request: Request[Any, Any, Any], exc: Exception) -> Response[dict[str, str]]:
    """Map a rejected move or bad set input onto HTTP 422; the stored game is left unchanged."""
    return Response(
        content={"detail": str(exc)},
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        media_type=MediaType.JSON,
    )


def _bad_gateway_handler(_request: Request[Any, Any, Any], exc: Exception) -> Response[dict[str, str]]:
    """Map an upstream set-fetch failure (network/timeout/oversize) onto HTTP 502."""
    return Response(
        content={"detail": str(exc)},
        status_code=HTTP_502_BAD_GATEWAY,
        media_type=MediaType.JSON,
    )


def _parse_set_urls(data: dict[str, object] | None) -> Sequence[str] | None:
    """Pull ``set_urls`` out of the request body, rejecting anything that isn't a list of strings."""
    if data is None or "set_urls" not in data:
        return None
    set_urls = data["set_urls"]
    if not isinstance(set_urls, list) or not all(isinstance(url, str) for url in set_urls):
        msg = "'set_urls' must be a list of strings"
        raise SetURLNotAllowedError(msg)
    return cast("list[str]", set_urls)


@post("/games", sync_to_thread=False)
def create_game(store: GameStore, data: dict[str, object] | None = None) -> dict[str, object]:
    """Create a new game from ``set_urls`` (default: the core set); return its id and initial state."""
    game_id, game = store.create(_parse_set_urls(data))
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
    """Return the game's log, final state, and card snapshot as a downloadable JSON attachment.

    The snapshot (resolved cards + content hash) makes the download self-contained: it replays
    without reaching the cards repo. The Content-Disposition attachment header is what the
    "Download game log" button on the game-over screen points at.
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
        # Bad input -> 422 (the store is left untouched); an upstream fetch failure -> 502.
        exception_handlers={
            IllegalAction: _unprocessable_handler,
            SetURLNotAllowedError: _unprocessable_handler,
            SetSchemaError: _unprocessable_handler,
            UnknownEffectError: _unprocessable_handler,
            InvalidEffectParamsError: _unprocessable_handler,
            DuplicateCardError: _unprocessable_handler,
            SetFetchError: _bad_gateway_handler,
        },
    )


app = create_app()
