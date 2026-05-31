# mundane

Magic: The Gathering without the, you know, magic.

Two households face off. The engine is a **referee**: a whole game is a fold over a stream of
*actions*, and one function — `apply_action(state, action)` — validates each action against the
current state and then transitions it. Illegal moves are rejected (the state is left untouched), not
crashed on. The HTTP API is a thin shell that translates requests into engine actions; all the rules
live in the engine.

- The rules, in human-readable form: [`game-docs/SPEC.md`](./game-docs/SPEC.md)
- The card catalog: [`game-docs/CARDS.md`](./game-docs/CARDS.md)

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

## Requirements

- Python **3.14+** and [`uv`](https://docs.astral.sh/uv/).
- Litestar 3 is still in development; it is tracked from `main` and pinned to a commit SHA in
  `uv.lock`, so builds are reproducible.

## Setup

```bash
uv sync --group tests --group dev   # create the venv and install everything
```

## Run the demo

Watch Steve's house party get shut down by Alex's noise complaint:

```bash
uv run python examples/demo.py
```

## Run the API

```bash
uv run uvicorn mundane.api.app:app --reload
```

Interactive OpenAPI docs are served at `http://localhost:8000/schema`.

### Endpoints

| Method | Path                       | Purpose                                |
|--------|----------------------------|----------------------------------------|
| POST   | `/games`                   | create a game                          |
| GET    | `/games/{id}`              | read current state                     |
| POST   | `/games/{id}/actions`      | submit a move (422 if illegal)         |
| GET    | `/games/{id}/export`       | download the game log + final state    |

### Exercise it

```bash
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
```

The action body is a tagged union — every action carries a `type`:

| `type`          | fields                                          |
|-----------------|-------------------------------------------------|
| `play_card`     | `player`, `hand_index`                          |
| `cast_instant`  | `player`, `hand_index`, optional `target_id`    |
| `pass_priority` | `player`                                        |

### A note on the store

The game store is an **in-memory dict**, so games are **volatile** — they are lost when the process
restarts. It lives behind a small `GameStore` interface (`create` / `get` / `save`), so swapping it
for Redis or SQLite later is a localised change. Persistence beyond memory is out of scope for the MVP.

## Develop

```bash
uv run pytest              # tests
uv run nox -s lints        # ruff format + ruff check + mypy + ty
```
