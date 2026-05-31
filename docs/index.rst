Mundane Backend
===============

*No dragons. No spells. Just Tuesday.*

This is the reference implementation of `Mundane <https://github.com/letsbuilda/mundane>`_: a rules
**engine** and a thin HTTP **API** over it. The engine is a referee, not a player — a whole game is a
fold over a stream of *actions*, and one function, :func:`mundane.engine.rules.apply_action`,
validates each action against the current state and then transitions it. Illegal moves are rejected
and the state is left untouched, never crashed on. The API is a thin shell that turns HTTP requests
into engine actions; all the rules live in the engine.

.. note::

   The game's rules and card catalog live in the meta/spec repository, not here:
   `SPEC.md <https://github.com/letsbuilda/mundane/blob/main/game-docs/SPEC.md>`_ and
   `CARDS.md <https://github.com/letsbuilda/mundane/blob/main/game-docs/CARDS.md>`_. This site
   documents the *implementation*; the spec describes the *game*.

Architecture
------------

The engine
~~~~~~~~~~

:func:`mundane.engine.rules.apply_action` is the one door: every state change goes through it. Each
move checks its preconditions first — a failed check raises :class:`mundane.engine.actions.IllegalAction`
and mutates nothing — and only then transitions. Because it returns the state, it composes as a
reducer::

   final_state = reduce(apply_action, actions, initial_state)

The state is fully JSON-serialisable. Cards are referenced **by id** everywhere; card *objects* and
the effect functions they carry live only in :data:`mundane.engine.cards.CARD_LIBRARY`, never in the
state. That separation is what lets a whole :class:`mundane.engine.state.GameState` round-trip through
JSON. A :class:`mundane.engine.game.Game` pairs that state with the ordered log of accepted actions,
so games are event-sourced: the log alone can rebuild — and replay — the state.

The API
~~~~~~~

:mod:`mundane.api` is a `Litestar <https://litestar.dev>`_ application. It never mutates game state
directly: it parses each request body into an engine action, calls ``Game.submit``, and maps a
rejected move (:class:`~mundane.engine.actions.IllegalAction`) onto **HTTP 422**. Games are kept in an
in-memory store behind a small ``create`` / ``get`` / ``save`` interface, so they are volatile (lost
when the process restarts) but the store is swappable for Redis or SQLite later.

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Method and path
     - Purpose
   * - ``POST /games``
     - Create a game; return its id and initial state.
   * - ``GET /games/{id}``
     - Read the current state.
   * - ``POST /games/{id}/actions``
     - Submit a move (HTTP 422 if illegal; the stored game is unchanged).
   * - ``GET /games/{id}/export``
     - Download the action log and final state.

API reference
-------------

The full module reference is generated from the source.

.. toctree::
   :maxdepth: 1

   autoapi/index

.. toctree::
   :caption: Other:
   :hidden:

   changelog

Extras
------

* :ref:`genindex`
* :ref:`search`
* :doc:`changelog`
