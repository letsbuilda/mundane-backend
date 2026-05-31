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

   The game's rules live in the meta/spec repository, not here: the
   `specification <https://github.com/letsbuilda/mundane/blob/main/specs/>`_ and
   `rulebook <https://github.com/letsbuilda/mundane/blob/main/rulebook/>`_. Card *content* is published
   as JSON `card sets <https://github.com/letsbuilda/mundane/blob/main/specs/card-sets.md>`_ in
   `mundane-cards <https://github.com/letsbuilda/mundane-cards>`_. This site documents the
   *implementation*; the spec describes the *game*.

Architecture
------------

The engine
~~~~~~~~~~

:func:`mundane.engine.rules.apply_action` is the one door: every state change goes through it. Each
move checks its preconditions first — a failed check raises :class:`mundane.engine.actions.IllegalAction`
and mutates nothing — and only then transitions. Because it returns the state, it composes as a
reducer::

   final_state = reduce(apply_action, actions, initial_state)

The state is fully JSON-serialisable. Cards are referenced **by id** everywhere (the composed
``set_id:id``); card *objects* — built from JSON sets by :func:`mundane.engine.cards.build_card` — and
the effect closures they carry live only in the per-game pool, never in the state. That separation is
what lets a whole :class:`mundane.engine.state.GameState` round-trip through JSON. A
:class:`mundane.engine.game.Game` pairs that state with the card pool, the ordered log of accepted
actions, and a card snapshot, so games are event-sourced: the log plus the snapshot can rebuild — and
replay — the state.

The API
~~~~~~~

:mod:`mundane.api` is a `Litestar <https://litestar.dev>`_ application. It never mutates game state
directly: it parses each request body into an engine action, calls ``Game.submit``, and maps a
rejected move (:class:`~mundane.engine.actions.IllegalAction`) onto **HTTP 422**. Games are kept in an
in-memory store behind a small ``create`` / ``get`` / ``save`` interface, so they are volatile (lost
when the process restarts) but the store is swappable for Redis or SQLite later.

Loading a game's cards — allowlisting set URLs, fetching them with hardening, validating against a
vendored copy of the card-set JSON Schema, and snapshotting the resolved pool with a content hash —
lives in :mod:`mundane.api.set_loader`. The engine never reaches the network; it receives only the
resolved pool. A non-allowlisted URL, a schema-invalid set, an unknown effect, bad params, or a
duplicate id give **HTTP 422**; an upstream fetch failure gives **HTTP 502**. Either way the store is
left untouched.

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Method and path
     - Purpose
   * - ``POST /games``
     - Create a game (optional ``{"set_urls": [...]}`` body, default the core set); return its id and
       initial state.
   * - ``GET /games/{id}``
     - Read the current state.
   * - ``POST /games/{id}/actions``
     - Submit a move (HTTP 422 if illegal; the stored game is unchanged).
   * - ``GET /games/{id}/export``
     - Download the action log, final state, and card snapshot (resolved cards + hash).

API reference
-------------

The full module reference is generated from the source.

.. toctree::
   :maxdepth: 1

   api
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
