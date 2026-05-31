# Mundane — Game Specification

*Magic: The Gathering without the, you know, magic.*

This document is the human-readable mirror of the engine. The engine is the source of truth: every
rule below corresponds to a check (`_require(...)`) or a transition in `apply_action`. When the code
and this document disagree, the code wins — and the document is wrong and should be fixed.

> Companion document: [`CARDS.md`](./CARDS.md) lists every card in the library.

## 1. Overview

Two households face off. The engine is a **referee**, not a player: the entire game is a fold over a
stream of *actions*, and the one function `apply_action(state, action)` validates each action against
the current state and then transitions it. Illegal actions are **rejected** — the engine raises
`IllegalAction` and the state is left exactly as it was. There is no other door: nothing mutates the
game except `apply_action`.

```
final_state = reduce(apply_action, actions, initial_state)
```

## 2. Winning and losing — Composure

`Composure` is the household's "life total". Each player starts at **20**.

- When any player's Composure drops to **0 or below**, their household falls apart and **their
  opponent wins**.
- Once a winner is decided, the game is over and **every further action is rejected**
  ("the game is over").

## 3. The resource — Time

`Time` is the resource spent to play cards.

- Every card has a `cost`. Playing it spends that much Time.
- You cannot spend Time you do not have — attempting to overspend is rejected
  ("not enough Time (have/cost)").
- At the start of a player's turn (the Wake Up phase, currently stubbed), their Time refreshes to
  **5** and they draw a card if their deck is non-empty.

## 4. Card types

There are five card types. The first three are **permanents**: when they resolve they stay on their
controller's board. The last two are **one-shots**: when they resolve they take effect and go to the
controller's discard.

| Type        | Value         | Permanent? | Timing                                   | Flavour                       |
|-------------|---------------|------------|------------------------------------------|-------------------------------|
| `PERSON`    | `"person"`    | yes        | sorcery speed (Plan, empty stack)        | creature-like                 |
| `APPLIANCE` | `"appliance"` | yes        | sorcery speed (Plan, empty stack)        | artifact-like permanent       |
| `HABIT`     | `"habit"`     | yes        | sorcery speed (Plan, empty stack)        | enchantment-like permanent    |
| `TASK`      | `"task"`      | no         | sorcery speed (Plan, empty stack)        | one-shot; uses the stack      |
| `INSTANT`   | `"instant"`   | no         | any time you hold priority               | one-shot; can respond         |

"Sorcery speed" is the restrictive timing (see the turn-structure and priority sections, added in a
later milestone); "instant speed" is the permissive one.

## 5. Card-definition format

Cards are **data plus an effect**. A full card definition lives in exactly one place — the card
library — and the game state never stores card objects, only their string `id`. This is the linchpin
that lets the entire state round-trip through JSON: effects are *code*, not *data*, so they are never
serialised.

A card definition has these fields:

| Field    | Type                              | Meaning                                                   |
|----------|-----------------------------------|-----------------------------------------------------------|
| `id`     | `str`                             | Stable identifier; this is what state stores.             |
| `name`   | `str`                             | Display name.                                             |
| `cost`   | `int`                             | Time required to play it.                                 |
| `type`   | `CardType`                        | One of the five types above.                              |
| `effect` | `(state, stack_item) -> None`     | Mutates state when the card resolves. Permanents use a no-op (they resolve onto the board instead). |
| `text`   | `str`                             | Rules text shown to players.                              |

When the engine needs a card's type, cost, or effect, it resolves the `id` through the library. Player
collections (`hand`, `board`, `deck`, `discard`) and stack items therefore hold ids, never objects.
