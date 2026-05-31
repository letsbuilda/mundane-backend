# GitHub Copilot instructions — mundane-backend

General project context, setup, commands, and architecture live in [`/AGENTS.md`](../AGENTS.md);
read it first. This file adds Copilot-specific guidance, especially for **code review**.

**In one line:** a Python 3.14 + Litestar game **engine** plus a thin HTTP **API**. All game rules
live in `engine/` (no HTTP knowledge); `api/` is the only HTTP layer. Managed with `uv`; linted with
ruff (`select = ALL`, line-length 120); type-checked with `mypy --strict`; numpy-style docstrings.

## Code review focus

When reviewing pull requests in this repository, prioritize:

- **Layering.** Flag any import of `mundane.api` from `mundane.engine`, or HTTP/Litestar concerns
  leaking into `engine/`. Rules belong in `engine/`, HTTP in `api/`.
- **The one door.** Every game state change must go through `engine/rules.py::apply_action`. Flag
  mutations that bypass it. `apply_action` must check `_require(...)` preconditions *before*
  mutating, so a rejected move leaves state unchanged — call out any reordering that mutates first.
- **Illegal moves.** Invalid actions must raise `IllegalAction` (mapped to HTTP 422), never crash
  with an unhandled exception or return a partially-mutated state.
- **Action schemas.** `api/schemas.py` is pure translation — no game rules there. Keep the
  tagged-union `type` tags in lockstep with engine actions and preserve the dict round-trip identity.
- **Types & docs.** Code must pass `mypy --strict`; public functions need numpy-style docstrings.
  Flag missing type annotations or docstrings.
- **Style.** Expect ruff `select = ALL` (line-length 120). Inline suppressions need a reason comment
  (`# noqa: CODE  (why)`); don't approve unjustified `# noqa` / `# type: ignore`.
- **Tests.** Behavior changes need tests in `tests/`. Tests run in random order (`pytest-randomly`),
  so flag order- or shared-state-dependent tests.
- **Dependencies.** If `pyproject.toml` dependencies change, `uv.lock` must be updated in the same PR.
- **Litestar 3 is pre-release** (pinned to git `main`): don't recommend deprecated or removed
  Litestar APIs; match the pinned version.

## When generating code

Apply the same rules and mirror the existing terse, well-commented style. Prefer reusing `_require`,
`CARD_LIBRARY`, the `GameStore` interface, and the existing serializers over inventing new
abstractions.
