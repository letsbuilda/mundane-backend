Changelog
=========

* :feature:`0` The Mundane rules engine — :func:`mundane.engine.rules.apply_action` as the single
  state-transition function, an event-sourced :class:`mundane.engine.game.Game` log, and a fully
  JSON-serialisable :class:`mundane.engine.state.GameState` that stores cards by id.
* :feature:`0` A thin `Litestar <https://litestar.dev>`_ HTTP API (:mod:`mundane.api`) to create
  games, read state, submit moves (rejected moves become HTTP 422), and export the action log.
