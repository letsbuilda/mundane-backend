# Contributing to mundane

Thanks for your interest in contributing! This guide covers how to set up, develop, and submit
changes. For a project overview and API walkthrough, see the [README](README.md). If you use an AI
coding assistant, point it at [`AGENTS.md`](AGENTS.md).

## Code of Conduct

This project follows the
[Contributor Covenant Code of Conduct](https://github.com/letsbuilda/.github/blob/main/CODE_OF_CONDUCT.md),
maintained org-wide for @letsbuilda. By participating, you agree to uphold it.

## Prerequisites

- **Python 3.14+**
- **[`uv`](https://docs.astral.sh/uv/) >= 0.11.8**

Litestar 3 is still in development; it is tracked from `main` and pinned to a commit SHA in
`uv.lock`, so builds are reproducible.

## Getting set up

```bash
git clone https://github.com/letsbuilda/mundane-backend
cd mundane-backend
uv sync --group tests --group dev   # create the venv and install everything
```

## Running it locally

```bash
uv run python examples/demo.py                 # run the demo scenario
uv run uvicorn mundane.api.app:app --reload    # serve the API; OpenAPI docs at /schema
```

The [API docs](docs/api.rst) have the endpoint table and `curl` examples for exercising the API.

## Development workflow

1. Create a branch off `main`.
2. Make your change, **with tests**.
3. Run the checks below until everything is green.
4. Open a pull request, fill in the template, and link any related issue.

## Checks (run before you push)

Run everything CI runs, in one shot:

```bash
uv run nox -s lints     # prek + ruff format + ruff check --fix + mypy --strict + ty
uv run nox -s tests     # pytest  (equivalently: uv run pytest)
```

Or install the git hooks so the fast checks run automatically on commit:

```bash
uv run prek install
```

`.github/workflows/ci.yaml` is the source of truth for what must pass: lint, tests, coverage
(uploaded to Codecov), plus the docs build (`.github/workflows/docs.yaml`).

## Code style

- **Formatting & linting:** [ruff](https://docs.astral.sh/ruff/) with `line-length = 120` and
  `select = ["ALL"]`. Auto-fix with `uv run ruff check --fix .` and `uv run ruff format .`.
- **Types:** all code must pass `uv run mypy --strict`.
- **Docstrings:** numpy convention.
- If you must silence a lint, scope it narrowly and add a reason: `# noqa: CODE  (why)`.

## Architecture you should respect

mundane is split so the rules are testable without HTTP — please keep these boundaries:

- `src/mundane/engine/` is the game and has **no HTTP knowledge**; `src/mundane/api/` is the only
  HTTP layer. Don't import `api` from `engine`.
- Every state change goes through **`apply_action(state, action)`** in `engine/rules.py` — "the one
  door". It validates preconditions first (rejecting illegal moves with `IllegalAction` and changing
  nothing), then transitions. Add new rules there.
- HTTP action bodies are a **tagged union** keyed by `type`; `api/schemas.py` only translates (no
  rules) and maps bad bodies to HTTP 422. Keep the tags in step with the engine's actions.

`AGENTS.md` has the same boundaries spelled out in more detail.

## Tests

- Add or update tests under `tests/` for any behavior change.
- Tests run in **random order** (`pytest-randomly`) — don't rely on ordering or shared state.
- Run `uv run pytest` locally; CI runs them with coverage and uploads to Codecov.

## Docs

Docs are built with Sphinx from `docs/` and published to <https://docs.letsbuilda.dev/mundane/>.
Update them when you change public API or behavior. Build locally:

```bash
uv sync --group docs
uv run sphinx-build --builder dirhtml --nitpicky docs site
```

## Dependencies

Dependencies are managed by uv. If you add or upgrade one, run `uv lock` and commit the updated
`uv.lock` (the `uv-lock` pre-commit hook enforces this).

## Pull requests

- Keep PRs focused and reasonably small; explain *what* changed and *why*.
- Make sure CI is green and the PR checklist is complete.
- Changes are reviewed by the code owner (see [`.github/CODEOWNERS`](.github/CODEOWNERS)).

## Security

Please **don't** open public issues for security vulnerabilities. Use the
[security policy](https://github.com/letsbuilda/mundane-backend/security/policy) (provided org-wide)
to report them privately.
