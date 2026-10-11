"""Cloudflare Workers entry point: serve the Litestar app, with games stored in D1.

This file sits beside the ``mundane`` package (not inside it) because the Worker's module root is the
directory of its entry point. Everything is imported inside ``fetch``: the Workers runtime forbids
randomness while a Worker starts up, and importing httpx (through rich) draws random numbers.
"""

from typing import TYPE_CHECKING, cast

# The runtime inspects ``fetch``'s signature, so its annotations must resolve at runtime.
from workers import Request, Response, WorkerEntrypoint

if TYPE_CHECKING:
    from litestar import Litestar

_app: Litestar | None = None


class Default(WorkerEntrypoint):
    """The Worker's HTTP handler."""

    async def fetch(self, request: Request) -> Response:
        """Hand the request to the ASGI app, built once per Worker instance."""
        from workers import asgi  # noqa: PLC0415  (see the module docstring)

        from mundane.api.app import create_app  # noqa: PLC0415
        from mundane.api.d1_store import D1GameStore  # noqa: PLC0415

        global _app  # noqa: PLW0603  (one app, and one JWKS cache, per Worker instance)
        if _app is None:
            _app = create_app(store=D1GameStore(self.env.DB))
        return cast("Response", await asgi.fetch(_app, request, self.env))
