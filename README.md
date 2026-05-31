# mundane

No dragons. No spells. Just Tuesday.

Two households face off. The engine is a **referee**: a whole game is a fold over a stream of
*actions*, and one function — `apply_action(state, action)` — validates each action against the
current state and then transitions it. Illegal moves are rejected (the state is left untouched), not
crashed on. The HTTP API is a thin shell that translates requests into engine actions; all the rules
live in the engine.

The rules and card catalog live in the [`mundane`](https://github.com/letsbuilda/mundane) meta/spec
repo:

- The rules, in human-readable form:
  [`game-docs/SPEC.md`](https://github.com/letsbuilda/mundane/blob/main/game-docs/SPEC.md)
- The card catalog:
  [`game-docs/CARDS.md`](https://github.com/letsbuilda/mundane/blob/main/game-docs/CARDS.md)

## Layout

```
src/mundane/
  engine/        # the game, with no HTTP knowledge
    state.py       # Card, CardType, Player, StackItem, GameState
    actions.py     # PlayCard, CastInstant, PassPriority, IllegalAction
    rules.py       # apply_action + helpers — the one door
    cards.py       # CARD_LIBRARY (id -> Card) + effect functions
    serialize.py   # state/action -> JSON-ready data
    game.py        # Game: state + action log + submit() / export()
  api/
    app.py         # Litestar app, in-memory store, exception handler
    schemas.py     # action JSON (tagged union) -> action dataclasses
examples/
  demo.py          # runnable scenario (python examples/demo.py)
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, running the demo and API, and the development
workflow.
