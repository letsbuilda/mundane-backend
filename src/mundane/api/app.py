"""The Litestar application: HTTP in, engine actions out, state back as JSON.

The API is a thin translator. It never mutates :class:`GameState` directly — it parses requests into
engine actions and calls ``Game.submit``, then maps the engine's :class:`IllegalAction` onto HTTP 422.
All game legality lives in the engine. Loading a game's cards (allowlist, fetch, schema-validate,
snapshot) lives in :mod:`mundane.api.set_loader`; the engine receives only the resolved pool.

Every game route needs a signed-in player: the caller's Auth0 access token (see :mod:`mundane.api.auth`)
names the ``player``, games belong to the player who created them, and anyone else gets 404. Where games
live is the injected :class:`~mundane.api.store.GameStore`: in memory by default (volatile), or
Cloudflare D1 when running as a Worker (``src/worker.py``).
"""

from typing import TYPE_CHECKING, Any, cast

from litestar import Litestar, MediaType, Request, Response, get, post
from litestar.config.cors import CORSConfig
from litestar.di import Provide
from litestar.status_codes import HTTP_409_CONFLICT, HTTP_422_UNPROCESSABLE_ENTITY, HTTP_502_BAD_GATEWAY
from pydantic_settings import BaseSettings, SettingsConfigDict

from mundane.engine.actions import IllegalAction
from mundane.engine.cards import DuplicateCardError, InvalidEffectParamsError, UnknownEffectError
from mundane.engine.serialize import state_to_dict

from .auth import Auth0Verifier, Verifier, bearer_token
from .schemas import parse_action
from .set_loader import SetFetchError, SetSchemaError, SetURLNotAllowedError
from .store import GameConflictError, GameStore, MemoryGameStore

if TYPE_CHECKING:
    from collections.abc import Sequence


class Settings(BaseSettings):
    """Deployment settings. The defaults are production's; override with ``MUNDANE_*`` environment variables.

    None of these are secrets: the Auth0 domain and audience are public identifiers, like the site's.
    """

    model_config = SettingsConfigDict(env_prefix="MUNDANE_")

    auth0_domain: str = "id.letsbuilda.dev"
    """The Auth0 tenant (custom domain) that issues players' access tokens."""
    auth0_audience: str = "https://mundane.letsbuilda.dev"
    """The Auth0 API identifier the site requests tokens for."""
    cors_origins: list[str] = ["https://letsbuilda.dev", "http://localhost:4321"]
    """Browser origins allowed to call the API: the site, and its local dev server."""


def _unprocessable_handler(_request: Request[Any, Any, Any], exc: Exception) -> Response[dict[str, str]]:
    """Map a rejected move or bad set input onto HTTP 422; the stored game is left unchanged."""
    return Response(
        content={"detail": str(exc)},
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        media_type=MediaType.JSON,
    )


def _conflict_handler(_request: Request[Any, Any, Any], exc: Exception) -> Response[dict[str, str]]:
    """Map a lost race between two moves in the same game onto HTTP 409; the later move was not recorded."""
    return Response(
        content={"detail": str(exc)},
        status_code=HTTP_409_CONFLICT,
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


@post("/games")
async def create_game(store: GameStore, player: str, data: dict[str, object] | None = None) -> dict[str, object]:
    """Create a new game from ``set_urls`` (default: the core set); return its id and initial state."""
    game_id, game = await store.create(player, _parse_set_urls(data))
    return {"game_id": game_id, "state": state_to_dict(game.state)}


@get("/games/{game_id:str}")
async def read_game(game_id: str, store: GameStore, player: str) -> dict[str, object]:
    """Return the current state of a game."""
    return state_to_dict((await store.get(game_id, player)).state)


@post("/games/{game_id:str}/actions")
async def submit_action(game_id: str, data: dict[str, object], store: GameStore, player: str) -> dict[str, object]:
    """Submit a move. An illegal move raises ``IllegalAction`` (-> 422) and changes nothing."""
    game = await store.get(game_id, player)
    state = game.submit(parse_action(data))
    await store.save(game_id, game)
    return state_to_dict(state)


@get("/games/{game_id:str}/export")
async def export_game(game_id: str, store: GameStore, player: str) -> Response[dict[str, object]]:
    """Return the game's log, final state, and card snapshot as a downloadable JSON attachment.

    The snapshot (resolved cards + content hash) makes the download self-contained: it replays
    without reaching the cards repo. The Content-Disposition attachment header is what the
    "Download game log" button on the game-over screen points at.
    """
    export = (await store.get(game_id, player)).export()
    filename = f"mundane-game-{game_id}.json"
    return Response(
        content=export,
        media_type=MediaType.JSON,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def create_app(
    store: GameStore | None = None,
    verifier: Verifier | None = None,
    settings: Settings | None = None,
) -> Litestar:
    """Build the Litestar app. Tests pass their own ``store`` and ``verifier``; otherwise from ``settings``."""
    settings = settings if settings is not None else Settings()
    shared_store = store if store is not None else MemoryGameStore()
    shared_verifier = (
        verifier
        if verifier is not None
        else Auth0Verifier(domain=settings.auth0_domain, audience=settings.auth0_audience)
    )

    def provide_store() -> GameStore:
        """Provide the single store shared across every request."""
        return shared_store

    def provide_player(request: Request[Any, Any, Any]) -> str:
        """Provide the signed-in player's id (the token's ``sub``); no valid token is a 401."""
        return shared_verifier.verify(bearer_token(request))

    return Litestar(
        route_handlers=[create_game, read_game, submit_action, export_game],
        dependencies={
            "store": Provide(provide_store, sync_to_thread=False),
            "player": Provide(provide_player, sync_to_thread=False),
        },
        cors_config=CORSConfig(
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
            expose_headers=["Content-Disposition"],
        ),
        # Bad input -> 422 (the store is left untouched); a lost race -> 409; an upstream fetch failure -> 502.
        exception_handlers={
            IllegalAction: _unprocessable_handler,
            SetURLNotAllowedError: _unprocessable_handler,
            SetSchemaError: _unprocessable_handler,
            UnknownEffectError: _unprocessable_handler,
            InvalidEffectParamsError: _unprocessable_handler,
            DuplicateCardError: _unprocessable_handler,
            GameConflictError: _conflict_handler,
            SetFetchError: _bad_gateway_handler,
        },
    )


app = create_app()
