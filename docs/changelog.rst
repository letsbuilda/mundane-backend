Changelog
=========

* :feature:`0` Hosted as a Cloudflare Worker with games persisted in D1 (:mod:`mundane.api.d1_store`).
  Every game route now needs an Auth0 access token (:mod:`mundane.api.auth`), and games belong to the
  player who created them. A move that loses a race with another move returns 409.
* :feature:`0` The Mundane rules engine — :func:`mundane.engine.rules.apply_action` as the single
  state-transition function, an event-sourced :class:`mundane.engine.game.Game` log, and a fully
  JSON-serialisable :class:`mundane.engine.state.GameState` that stores cards by id.
* :feature:`0` A thin `Litestar <https://litestar.dev>`_ HTTP API (:mod:`mundane.api`) to create
  games, read state, submit moves (rejected moves become HTTP 422), and export the action log.
* :feature:`0` Externalised the card library: cards load from allowlisted JSON sets in
  `mundane-cards <https://github.com/letsbuilda/mundane-cards>`_, validated against a vendored schema
  and snapshotted with a content hash into each game (:mod:`mundane.api.set_loader`). ``POST /games``
  takes an optional ``set_urls`` body; the export now includes the card snapshot.
