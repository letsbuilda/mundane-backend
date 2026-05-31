"""Fetch, allowlist, validate, and snapshot external card sets — the only HTTP-aware card code.

The engine never reaches the network; this module does. Given a list of set URLs it: (1) allowlists
each (only the ``mundane-cards`` raw origin), (2) fetches with hardening (https, timeout, no
redirects, size cap, content-type check), (3) validates each body against the **vendored** schema,
(4) builds the cards via the engine loader, rejecting duplicate composed ids, and (5) returns the
resolved pool plus a JSON-ready snapshot with a content hash so an exported game replays
self-contained. On any failure it raises before the caller stores anything.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from importlib import resources
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JSONSchemaValidationError

from mundane.engine.cards import DuplicateCardError, build_card
from mundane.engine.serialize import canonical_json

if TYPE_CHECKING:
    from mundane.engine.state import Card

DEFAULT_SET_URLS: tuple[str, ...] = ("https://raw.githubusercontent.com/letsbuilda/mundane-cards/main/sets/core.json",)
ALLOWLIST_HOST = "raw.githubusercontent.com"
ALLOWLIST_PATH_PREFIX = "/letsbuilda/mundane-cards/"
MAX_SET_BYTES = 1 << 20  # 1 MiB is plenty for a JSON card set
FETCH_TIMEOUT_SECONDS = 5.0

_SCHEMA: dict[str, object] = json.loads(
    resources.files("mundane.api.card_schema").joinpath("card-set.schema.json").read_text(encoding="utf-8"),
)
_VALIDATOR = Draft202012Validator(_SCHEMA)

Fetcher = Callable[[str], bytes]
"""Fetches the raw bytes of a set at a URL. Injectable so tests can serve a fixture offline."""


class SetURLNotAllowedError(Exception):
    """A requested set URL is not on the allowlist. Maps to HTTP 422."""


class SetFetchError(Exception):
    """A set could not be fetched (network, timeout, status, content-type, or size). Maps to 502."""


class SetSchemaError(Exception):
    """A fetched set was not valid JSON or failed schema validation. Maps to HTTP 422."""


@dataclass(frozen=True)
class ResolvedPool:
    """The engine-facing pool plus the serialisable snapshot (resolved cards + content hash)."""

    cards: dict[str, Card]
    snapshot: dict[str, object]


def _check_allowed(url: str, host: str, prefix: str) -> None:
    """Reject ``url`` unless it is https, exactly on ``host``, and under ``prefix`` (parsed, not substring)."""
    parts = urlsplit(url)
    host_ok = (parts.hostname or "").lower() == host.lower()
    if parts.scheme != "https" or not host_ok or not parts.path.startswith(prefix):
        msg = f"set URL is not allowlisted: {url!r}"
        raise SetURLNotAllowedError(msg)


def default_fetch(url: str) -> bytes:
    """Fetch ``url`` with hardening: a hard timeout, no redirects, a size cap, and a content-type check."""
    try:
        with (
            httpx.Client(timeout=httpx.Timeout(FETCH_TIMEOUT_SECONDS), follow_redirects=False) as client,
            client.stream("GET", url) as response,
        ):
            if response.status_code != httpx.codes.OK:
                msg = f"failed to fetch {url!r}: HTTP {response.status_code}"
                raise SetFetchError(msg)
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith(("application/json", "text/plain")):
                msg = f"unexpected content-type for {url!r}: {content_type!r}"
                raise SetFetchError(msg)
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_SET_BYTES:
                    msg = f"set at {url!r} exceeds {MAX_SET_BYTES} bytes"
                    raise SetFetchError(msg)
                chunks.append(chunk)
    except httpx.HTTPError as exc:
        msg = f"failed to fetch {url!r}: {exc}"
        raise SetFetchError(msg) from exc
    return b"".join(chunks)


def load_sets(
    set_urls: Sequence[str],
    *,
    fetch: Fetcher = default_fetch,
    allowlist_host: str = ALLOWLIST_HOST,
    allowlist_prefix: str = ALLOWLIST_PATH_PREFIX,
) -> ResolvedPool:
    """Allowlist, fetch, validate, and build the combined pool + snapshot for ``set_urls``.

    Raises before returning on any problem: :class:`SetURLNotAllowedError` /
    :class:`SetSchemaError` / engine ``UnknownEffectError`` / ``InvalidEffectParamsError`` /
    ``DuplicateCardError`` (all 422 at the API), or :class:`SetFetchError` (502).
    """
    pool: dict[str, Card] = {}
    snapshot_cards: list[dict[str, object]] = []
    for url in set_urls:
        _check_allowed(url, allowlist_host, allowlist_prefix)
        raw = fetch(url)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            msg = f"set at {url!r} is not valid JSON: {exc}"
            raise SetSchemaError(msg) from exc
        try:
            _VALIDATOR.validate(body)
        except JSONSchemaValidationError as exc:
            msg = f"set at {url!r} failed schema validation: {exc.message}"
            raise SetSchemaError(msg) from exc
        set_id = body["set_id"]
        for card_dict in body["cards"]:
            card = build_card(set_id, card_dict)
            if card.id in pool:
                msg = f"duplicate card id {card.id!r}"
                raise DuplicateCardError(msg)
            pool[card.id] = card
            snapshot_cards.append({**card_dict, "id": card.id})
    content_hash = "sha256:" + sha256(canonical_json(snapshot_cards).encode()).hexdigest()
    return ResolvedPool(cards=pool, snapshot={"cards": snapshot_cards, "content_hash": content_hash})
