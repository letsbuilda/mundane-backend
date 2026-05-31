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
     - create a game
   * - GET
     - ``/games/{id}``
     - read current state
   * - POST
     - ``/games/{id}/actions``
     - submit a move (422 if illegal)
   * - GET
     - ``/games/{id}/export``
     - download the game log + final state

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
