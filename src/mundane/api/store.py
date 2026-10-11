"""Where games live between requests: the :class:`GameStore` interface and its in-memory implementation.

A store creates games (resolving their card sets first), hands a game back only to the player who owns
it, and persists each accepted move. :class:`MemoryGameStore` keeps everything in a ``dict`` and is lost
on restart, which suits tests and local ``uvicorn``. The deployed Worker uses
:class:`mundane.api.d1_store.D1GameStore`, which persists the same event-sourced record in Cloudflare D1.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import uuid4

from litestar.exceptions import NotFoundException

from mundane.engine.game import Game, new_game

from .schemas import parse_action
from .set_loader import DEFAULT_SET_URLS, Fetcher, default_fetch, load_sets, pool_from_snapshot

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


class GameConflictError(Exception):
    """Another request moved first in the same game; this move was not recorded. Maps to HTTP 409."""


class GameStore(ABC):
    """Create, load, and persist games. Every implementation hides other players' games behind 404.

    An ABC rather than a ``Protocol``: Litestar builds each handler's signature model from its
    annotations, and a ``Protocol``-typed dependency breaks request-body parsing in that model.
    """

    @abstractmethod
    async def create(self, owner: str, set_urls: Sequence[str] | None = None) -> tuple[str, Game]:
        """Resolve ``set_urls`` (default: the core set), then create and store a game owned by ``owner``."""

    @abstractmethod
    async def get(self, game_id: str, owner: str) -> Game:
        """Return the game if ``owner`` owns it, else raise ``NotFoundException`` (-> 404)."""

    @abstractmethod
    async def save(self, game_id: str, game: Game) -> None:
        """Persist the game after ``Game.submit`` accepted one more action."""


def start_game(set_urls: Sequence[str] | None, fetch: Fetcher) -> Game:
    """Resolve the sets and deal the opening position. Raises (422/502) before anything is stored."""
    pool = load_sets(set_urls or DEFAULT_SET_URLS, fetch=fetch)
    game = new_game(pool.cards)
    game.card_snapshot = pool.snapshot
    return game


def replay_game(card_snapshot: dict[str, object], log: Iterable[dict[str, object]]) -> Game:
    """Rebuild a stored game: a fresh opening over the snapshotted pool, then every logged action, in order."""
    game = new_game(pool_from_snapshot(card_snapshot))
    game.card_snapshot = card_snapshot
    for action in log:
        game.submit(parse_action(action))
    return game


def not_found(game_id: str) -> NotFoundException:
    """Build the one 404 for both "no such game" and "not your game", so ids don't leak whose games exist."""
    return NotFoundException(detail=f"no game with id {game_id!r}")


class MemoryGameStore(GameStore):
    """In-memory game store. Volatile: its contents are lost when the process restarts.

    Deliberately an opaque service (not a dataclass), so the framework treats it as an injected
    dependency rather than request data to introspect. ``fetch`` is injectable so tests can resolve set
    URLs from a local fixture instead of the network.
    """

    def __init__(self, *, fetch: Fetcher = default_fetch) -> None:
        """Start with no games, using ``fetch`` to retrieve card sets."""
        self.games: dict[str, Game] = {}
        self.owners: dict[str, str] = {}
        self._fetch = fetch

    async def create(self, owner: str, set_urls: Sequence[str] | None = None) -> tuple[str, Game]:
        """Resolve ``set_urls``, then create and store a new game. A loader error leaves the store unchanged."""
        game = start_game(set_urls, self._fetch)
        game_id = uuid4().hex
        self.games[game_id] = game
        self.owners[game_id] = owner
        return game_id, game

    async def get(self, game_id: str, owner: str) -> Game:
        """Return the stored game, or raise ``NotFoundException`` (-> 404) if it is missing or not ``owner``'s."""
        if self.owners.get(game_id) != owner:
            raise not_found(game_id)
        return self.games[game_id]

    async def save(self, game_id: str, game: Game) -> None:
        """Persist the game. A no-op for the in-memory store (games already mutate in place)."""
        self.games[game_id] = game
