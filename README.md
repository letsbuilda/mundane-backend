# Mundane, backened

*Part of https://github.com/letsbuilda/mundane*

No dragons. No spells. Just Tuesday.

Two households face off. The engine is a **referee**: a whole game is a fold over a stream of
*actions*, and one function — `apply_action(state, action)` — validates each action against the
current state and then transitions it. Illegal moves are rejected (the state is left untouched), not
crashed on. The HTTP API is a thin shell that translates requests into engine actions; all the rules
live in the engine.

## Card sets

Cards are **content**, not code. Each game loads its cards at creation from JSON
[card sets](https://github.com/letsbuilda/mundane/blob/main/specs/card-sets.md) published in
[`mundane-cards`](https://github.com/letsbuilda/mundane-cards) — a card names an *effect* from the
engine's fixed vocabulary and supplies `params`; it cannot define new behaviour. `POST /games` takes
an optional `{"set_urls": [...]}` body (default: the core set). Each URL is **allowlisted** (only the
`mundane-cards` raw origin, matched by parsed host + path), **fetched** with hardening (https-only,
hard timeout, size cap, content-type check), **validated** against a vendored copy of the card-set
JSON Schema, **built** into cards (the engine rejects unknown effects, bad params, and duplicate
composed ids), and **snapshotted** with a sha256 hash into the game so `GET /games/{id}/export`
replays self-contained. Bad input is rejected before anything is stored: non-allowlisted URL /
schema-invalid set / unknown effect / bad params / duplicate id → **422**; fetch failure / timeout /
oversize → **502**.
