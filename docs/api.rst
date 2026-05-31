API
===

Serve the API locally:

.. code-block:: bash

   uv run uvicorn mundane.api.app:app --reload

Interactive OpenAPI docs are served at ``http://localhost:8000/schema``.

Endpoints
---------

.. list-table::
   :header-rows: 1

   * - Method
     - Path
     - Purpose
   * - POST
     - ``/games``
     - create a game (optional ``{"set_urls": [...]}`` body; default the core set)
   * - GET
     - ``/games/{id}``
     - read current state
   * - POST
     - ``/games/{id}/actions``
     - submit a move (422 if illegal)
   * - GET
     - ``/games/{id}/export``
     - download the game log + final state + card snapshot

Exercise it
-----------

.. code-block:: bash

   # create a game and capture its id
   GID=$(curl -s -X POST localhost:8000/games | python -c 'import sys,json; print(json.load(sys.stdin)["game_id"])')

   # read the current state
   curl -s localhost:8000/games/$GID

   # submit a move (the tagged-union body carries a "type" discriminator)
   curl -s -X POST localhost:8000/games/$GID/actions \
     -H 'content-type: application/json' \
     -d '{"type": "play_card", "player": 0, "hand_index": 0}'

   # an illegal move is rejected with 422; the stored game is unchanged
   curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/games/$GID/actions \
     -H 'content-type: application/json' \
     -d '{"type": "cast_instant", "player": 1, "hand_index": 9}'

   # download the game log (saves to mundane-game-$GID.json)
   curl -s -OJ localhost:8000/games/$GID/export

The action body is a tagged union — every action carries a ``type``:

.. list-table::
   :header-rows: 1

   * - ``type``
     - fields
   * - ``play_card``
     - ``player``, ``hand_index``
   * - ``cast_instant``
     - ``player``, ``hand_index``, optional ``target_id``
   * - ``pass_priority``
     - ``player``

Card sets
---------

Cards are loaded at game creation from JSON *sets* published in
`mundane-cards <https://github.com/letsbuilda/mundane-cards>`_. ``POST /games`` accepts an optional
``{"set_urls": [...]}`` body and defaults to the core set. Each URL is **allowlisted** (only the
``mundane-cards`` raw origin, matched by parsed host + path), **fetched** with hardening (https-only,
hard timeout, size cap, content-type check), **validated** against a vendored copy of the card-set
JSON Schema, and **built** into cards by the engine — which rejects unknown effect names, bad params,
and duplicate composed ids. The resolved pool is **snapshotted** with a ``sha256`` content hash into
the game and returned by the export, so a saved game replays self-contained.

Bad input is rejected before anything is stored: a non-allowlisted URL, a schema-invalid set, an
unknown effect, bad params, or a duplicate id give ``422``; a fetch failure, timeout, or oversize
give ``502``.

.. code-block:: bash

   # create a game from an explicit (allowlisted) set URL
   curl -s -X POST localhost:8000/games \
     -H 'content-type: application/json' \
     -d '{"set_urls": ["https://raw.githubusercontent.com/letsbuilda/mundane-cards/main/sets/core.json"]}'
