"""Vendored, pinned copy of the Mundane card-set JSON Schema (the validation contract).

This mirrors the meta repo (``mundane``) ``schemas/card-set.schema.json`` and tracks its ``schema-v1``
tag. It is **vendored** — never fetched at runtime — so set validation never depends on the network
or on unrelated changes to the schema's ``main``. Re-vendor this file when ``schema-v1`` is bumped.
"""
