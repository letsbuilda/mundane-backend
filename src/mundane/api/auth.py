"""Who is calling: verify the caller's Auth0 access token and yield its subject.

The site (letsbuilda.dev) logs players in with Auth0 and sends the resulting access token on every request
as ``Authorization: Bearer <token>``. :class:`Auth0Verifier` checks it the way Auth0 documents for APIs:
an RS256 signature from a key in the tenant's JWKS, plus issuer, audience, and expiry. The token's ``sub``
is the player's stable id; games are owned by it.

Fetching the JWKS is injectable so tests sign tokens with a local key instead of reaching Auth0.
"""

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, cast

import httpx
import jwt
from litestar.exceptions import NotAuthorizedException, ServiceUnavailableException

if TYPE_CHECKING:
    from litestar import Request

FETCH_TIMEOUT_SECONDS = 5.0
JWKS_REFRESH_SECONDS = 300.0
"""How long a fetched JWKS is trusted before an unknown ``kid`` may trigger a refetch (key rotation)."""

JWKSFetcher = Callable[[str], bytes]
"""Fetches the raw JWKS document at a URL. Injectable so tests can serve a local key set."""


class Verifier(Protocol):
    """Anything that turns a bearer token into the caller's subject, or raises ``NotAuthorizedException``."""

    def verify(self, token: str) -> str:
        """Return the subject of a valid ``token``."""


def default_fetch_jwks(url: str) -> bytes:
    """Fetch the JWKS at ``url``; an unreachable tenant is a 503, not a 401 (the token may be fine)."""
    try:
        response = httpx.get(url, timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=False)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        msg = "could not reach the identity provider to verify the token"
        raise ServiceUnavailableException(detail=msg) from exc
    return response.content


class Auth0Verifier:
    """Verify Auth0-issued RS256 access tokens for one API (audience) on one tenant (domain)."""

    def __init__(self, *, domain: str, audience: str, fetch: JWKSFetcher = default_fetch_jwks) -> None:
        """Trust tokens from ``https://{domain}/`` minted for ``audience``."""
        self.issuer = f"https://{domain}/"
        self.audience = audience
        self.jwks_url = f"https://{domain}/.well-known/jwks.json"
        self._fetch = fetch
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = float("-inf")

    def _signing_key(self, kid: str) -> jwt.PyJWK:
        """Return the JWKS key ``kid``, refetching the set at most every few minutes to pick up rotations."""
        if kid not in self._keys and time.monotonic() - self._fetched_at > JWKS_REFRESH_SECONDS:
            key_set = jwt.PyJWKSet.from_json(self._fetch(self.jwks_url).decode())
            self._keys = {key.key_id: key for key in key_set.keys if key.key_id}
            self._fetched_at = time.monotonic()
        try:
            return self._keys[kid]
        except KeyError as exc:
            msg = "access token is signed by an unknown key"
            raise NotAuthorizedException(detail=msg) from exc

    def verify(self, token: str) -> str:
        """Return the ``sub`` of a valid token; raise ``NotAuthorizedException`` (-> 401) otherwise."""
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            key = self._signing_key(kid if isinstance(kid, str) else "")
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            msg = "invalid access token"
            raise NotAuthorizedException(detail=msg) from exc
        return cast("str", claims["sub"])


def bearer_token(request: Request[Any, Any, Any]) -> str:
    """Return the bearer token from the ``Authorization`` header, or raise ``NotAuthorizedException``."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        msg = "sign in to play: missing bearer token"
        raise NotAuthorizedException(detail=msg)
    return token
