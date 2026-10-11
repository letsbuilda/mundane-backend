"""Auth tests: Auth0 access tokens are verified properly, with a local key standing in for the tenant."""

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from litestar.exceptions import NotAuthorizedException

from mundane.api.auth import Auth0Verifier

DOMAIN = "id.example.test"
AUDIENCE = "https://mundane.example.test"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks(*, kid: str = "k1") -> bytes:
    """Return a JWKS document publishing the test key's public half under ``kid``."""
    jwk = json.loads(RSAAlgorithm.to_jwk(_KEY.public_key()))
    return json.dumps({"keys": [{**jwk, "kid": kid, "use": "sig", "alg": "RS256"}]}).encode()


def _token(*, key: rsa.RSAPrivateKey = _KEY, kid: str = "k1", **overrides: object) -> str:
    """Sign a token the way Auth0 would for this API, with any claim overridden (``None`` drops it)."""
    claims: dict[str, object] = {
        "iss": f"https://{DOMAIN}/",
        "aud": AUDIENCE,
        "sub": "auth0|steve",
        "exp": int(time.time()) + 600,
    }
    claims.update(overrides)
    claims = {name: value for name, value in claims.items() if value is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def _verifier() -> Auth0Verifier:
    """Return a verifier whose JWKS fetch is served locally."""
    return Auth0Verifier(domain=DOMAIN, audience=AUDIENCE, fetch=lambda _url: _jwks())


def test_valid_token_yields_its_subject() -> None:
    """A token signed by the tenant's key, for this API, unexpired, names its player."""
    assert _verifier().verify(_token()) == "auth0|steve"


@pytest.mark.parametrize(
    "token",
    [
        _token(aud="https://some-other-api.example.test"),  # minted for another API
        _token(iss="https://evil.example.test/"),  # another tenant
        _token(exp=int(time.time()) - 60),  # expired
        _token(sub=None),  # no subject
        _token(key=_OTHER_KEY),  # signed by a key the tenant doesn't publish
        _token(kid="unknown"),  # names a key the tenant doesn't publish
        "not-a-jwt",
    ],
)
def test_bad_tokens_are_rejected(token: str) -> None:
    """Anything but a well-formed token from this tenant for this API is a 401."""
    with pytest.raises(NotAuthorizedException):
        _verifier().verify(token)


def test_unsigned_tokens_are_rejected() -> None:
    """``alg: none`` never verifies, even with otherwise perfect claims."""
    claims = {"iss": f"https://{DOMAIN}/", "aud": AUDIENCE, "sub": "auth0|steve", "exp": int(time.time()) + 600}
    token = jwt.encode(claims, key="", algorithm="none", headers={"kid": "k1"})
    with pytest.raises(NotAuthorizedException):
        _verifier().verify(token)


def test_jwks_is_fetched_once_and_reused() -> None:
    """The key set is cached, so verifying many tokens doesn't hit the tenant every time."""
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return _jwks()

    verifier = Auth0Verifier(domain=DOMAIN, audience=AUDIENCE, fetch=fetch)
    for _ in range(3):
        verifier.verify(_token())
    assert calls == [f"https://{DOMAIN}/.well-known/jwks.json"]
