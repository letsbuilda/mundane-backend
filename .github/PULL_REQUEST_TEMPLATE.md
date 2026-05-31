## Summary

<!-- What does this PR change, and why? -->

## Related issues

<!-- e.g. Closes #123 -->

## Checklist

- [ ] `uv run nox -s lints` passes (prek + ruff format + ruff check + `mypy --strict` + ty)
- [ ] `uv run nox -s tests` passes, and I added/updated tests for any behavior change
- [ ] Docs in `docs/` updated if public API or behavior changed
- [ ] `uv.lock` updated if dependencies changed
- [ ] Game rules stay in `engine/` and HTTP stays in `api/` (no cross-layer leaks)
