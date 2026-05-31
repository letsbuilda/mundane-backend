# AGENTS.md

Guidance for AI coding agents working in **mundane-backend**. This is the canonical, full set of
agent instructions; tool-specific files (e.g. `.github/copilot-instructions.md`) defer to it.
Humans should start with [`README.md`](README.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Project overview

mundane-backend is *Magic: The Gathering without the magic* — a turn-based game **engine** plus a
thin **HTTP API**. The engine is a referee: a whole game is a fold over a stream of *actions*, and
one function, `apply_action(state, action)`, validates each action against the current state and
then transitions it. The API is a thin shell that translates HTTP requests into engine actions; all
the rules live in the engine.

- **Stack:** Python 3.14+, [Litestar](https://litestar.dev) 3 (pre-release, tracked from git
  `main`), Pydantic, Uvicorn. Managed with [`uv`](https://docs.astral.sh/uv/).
- **Rules & cards spec** live in the meta repo, not here:
  [SPEC.md](https://github.com/letsbuilda/mundane/blob/main/game-docs/SPEC.md) and
  [CARDS.md](https://github.com/letsbuilda/mundane/blob/main/game-docs/CARDS.md).

## Setup

Requires Python 3.14+ and `uv` >= 0.11.8.

```bash
uv sync --group tests --group dev   # create the venv and install everything
```

## Build & run

```bash
uv run python examples/demo.py                    # run the demo scenario
uv run uvicorn mundane.api.app:app --reload       # serve the API (OpenAPI at /schema)
```

## Testing

```bash
uv run pytest
# as CI runs it (coverage + reports):
uv run coverage run -m pytest -v --junitxml=junit.xml --alluredir allure-results
```

- Tests live in `tests/`. `pythonpath = ["examples"]` lets tests import the demo.
- `pytest-randomly` randomizes test order — **keep tests order-independent and free of shared
  state.** `--strict-markers` is enabled.
- Add or update tests for every behavior change.

## Lint, format & type-check

Run the whole local suite in one shot:

```bash
uv run nox -s lints
```

That runs, in order: `prek run --all-files`, `ruff format .`, `ruff check --fix .`,
`mypy --strict src/ tests/ examples/`, `ty check .`. Individual tools:

```bash
uv run ruff format .                          # CI checks with --check
uv run ruff check --output-format=github .
uv run mypy --strict src/                      # CI scope; nox also checks tests/ and examples/
uv run ty check .
```

`.github/workflows/ci.yaml` is the source of truth for the checks that must pass.

## Code style

- **ruff** with `line-length = 120` and `select = ["ALL"]`. Documented ignores: global `CPY001`;
  `tests/*` allow `S101`/`PLR2004`; `examples/*` allow `T201`/`INP001`; `docs/*` allow `INP001`.
- Don't add blanket suppressions. If a lint must be silenced, scope it and give a reason, matching
  the repo idiom: `# noqa: CODE  (reason)`.
- **Docstrings:** numpy convention (pydocstyle). Match the existing terse, explanatory voice.
- **Types:** all code must pass `mypy --strict`; the Pydantic mypy plugin is enabled.
- isort first-party package is `mundane`.

## Architecture & layout

```
src/mundane/
  engine/        # the game, with NO HTTP knowledge
    state.py       # Card, CardType, Player, StackItem, GameState
    actions.py     # PlayCard, CastInstant, PassPriority, IllegalAction
    rules.py       # apply_action + helpers — the one door
    cards.py       # CARD_LIBRARY (id -> Card) + effect functions
    serialize.py   # state/action -> JSON-ready data
    game.py        # Game: state + action log + submit() / export()
  api/
    app.py         # Litestar app, in-memory GameStore, exception handler
    schemas.py     # action JSON (tagged union) -> action dataclasses
examples/demo.py   # runnable scenario
tests/             # pytest suite
docs/              # Sphinx docs
```

Invariants to preserve when changing code:

- **The engine never imports from `api/`.** All rules live in `engine/`; all HTTP lives in `api/`.
  Keep Litestar/HTTP concerns out of the engine.
- **`apply_action` is the one door.** Every state change goes through
  `engine/rules.py::apply_action`. It runs `_require(...)` preconditions *first* — raising
  `IllegalAction` and **mutating nothing** on a bad move — and only then transitions the state in
  place and returns it, so it composes as a reducer: `reduce(apply_action, actions, initial)`. Never
  mutate before validating, and never let an illegal move leave a partially-mutated state.
- **Actions are a tagged union.** Each action body carries a `type` discriminator whose tags match
  the engine's actions. `api/schemas.py::parse_action` is *pure translation* — no game rules — and
  raises `IllegalAction` (which the app maps to **HTTP 422**) for unknown or malformed bodies. Keep
  the tags in lockstep with the engine; the `action_to_dict` -> `parse_action` round-trip is the
  identity (there's a test for it).
- The game store is an in-memory dict behind a small `GameStore` interface (`create`/`get`/`save`);
  games are volatile. Prefer extending this interface over reaching around it.

## Making changes

- Add/adjust tests in `tests/` for behavior changes.
- Update the Sphinx docs in `docs/` when public API or behavior changes.
- If you change dependencies, run `uv lock` and commit `uv.lock` (the `uv-lock` pre-commit hook
  enforces this).
- Keep changes focused; ensure `nox -s lints` and `nox -s tests` pass before pushing.

## Gotchas

- **Litestar 3 is pre-release**, pinned to a git `main` commit in `uv.lock`. APIs can shift between
  versions — use current Litestar 3 patterns and don't reintroduce removed/deprecated APIs.
- CI resolves dependencies with the **lowest** compatible versions (`resolution-strategy: lowest`)
  and an `exclude-newer` window; don't assume the newest library APIs are present.
- GitHub Actions workflows are linted by **zizmor**; keep `persist-credentials: false` and SHA-pinned
  actions.
- Never commit secrets.

## For humans

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the contributor workflow. The Code of Conduct and
Security policy are provided org-wide by [`letsbuilda/.github`](https://github.com/letsbuilda/.github).
