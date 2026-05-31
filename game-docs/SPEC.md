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

## 6. Turn structure — the five phases

A turn proceeds through five phases, in order:

```
RESET  ->  WAKE_UP  ->  PLAN  ->  DO_STUFF  ->  WIND_DOWN
```

There is **no "advance phase" action**. A phase ends — and the next begins — purely as a *consequence*
of every player passing priority in a row while the stack is empty (see §7). When the final phase
(`WIND_DOWN`) ends:

- the turn passes to the next player;
- the phase resets to `RESET`;
- the turn counter increments;
- the new active player's **Wake Up housekeeping** runs: their Time refreshes to **5**, and they draw
  a card from their deck if it is non-empty.

(Wake Up housekeeping is currently applied at end-of-turn, a deliberate stub. Combat in `DO_STUFF` —
People assigning to Problems — is also stubbed and out of scope for the MVP.)

## 7. Priority — who may act, and how it passes

Two notions are deliberately kept separate:

- **`active_player`** — whose *turn* it is. Slow: changes once per turn.
- **`priority_player`** — who may act *right now*. Fast: changes constantly.

That separation is the whole reason a non-active player can respond during the active player's turn.

**Granting priority after a stack change.** Whenever a card goes on the stack, the **active player**
receives priority (yes, even to respond to their own card), and the consecutive-pass counter resets.

**Passing priority.** When a player passes:

- the consecutive-pass counter increments;
- if it has **not** yet reached the number of players, priority moves to the next player;
- if it **has** reached the number of players (everyone passed in a row with nobody acting), the
  counter resets and either:
  - the **top item of the stack resolves** (if the stack is non-empty), after which the active player
    receives priority again; or
  - the **phase advances** (if the stack is empty).

**Timing.**

- *Sorcery speed* (`PlayCard` — PERSON / APPLIANCE / HABIT / TASK) is the restrictive timing: legal
  only for the **active player**, only during **PLAN**, and only when the **stack is empty**.
- *Instant speed* (`CastInstant` — INSTANT) is the permissive timing: legal for whoever currently
  holds priority, in any phase, regardless of what is on the stack.

## 8. The stack and LIFO resolution

The stack is a list; the most recently added item is the **top**.

- Items resolve one at a time, **top first (LIFO)**. After each resolution the active player receives
  priority again, so further responses are possible before the next item resolves.
- A response goes on top of the thing it responds to and therefore resolves **first**. This is the
  entire point of "casting in response": Noise Complaint, cast while Throw a House Party is on the
  stack, sits on top and resolves first — countering the party before it can ever deal its damage.
- Each stack item carries an `id` (assigned from `GameState.next_stack_id`), unique within the game,
  so an effect can target a specific item.
- On resolution: a **permanent** (PERSON / APPLIANCE / HABIT) goes onto its controller's **board**; a
  **one-shot** (TASK / INSTANT) applies its effect and then goes to its controller's **discard**.

## 9. Action legality — the preconditions, one-for-one

Each action is validated *before* anything is mutated, so a rejected action changes nothing. The
messages below are the exact rejection messages the engine raises.

**Global (every action):** the game must not be over (`winner is None`), else **"the game is over"**.

### `PlayCard(player, hand_index)` — sorcery speed

Checked in this order:

1. The player holds priority — **"you don't have priority"**.
2. The player is the active player — **"only the active player may play sorcery-speed cards"**.
3. The phase is PLAN — **"sorcery-speed cards only during Plan"**.
4. The stack is empty — **"the stack must be empty for sorcery-speed cards"**.
5. `hand_index` is a valid index into the player's hand — **"no such card in hand"**.
6. The card is not an INSTANT — **"use CastInstant for instants"**.
7. The player has enough Time (`time >= cost`) — **"not enough Time (have/cost)"**.

On success: the card leaves the hand, its cost is paid in Time, it goes on the stack, and the active
player receives priority.

### `CastInstant(player, hand_index, target_id=None)` — instant speed

1. The player holds priority — **"you don't have priority"**.
2. `hand_index` is a valid index into the player's hand — **"no such card in hand"**.
3. The card is an INSTANT — **"that card isn't an instant"**.
4. The player has enough Time (`time >= cost`) — **"not enough Time (have/cost)"**.

On success: as above, and the optional `target_id` is recorded on the new stack item.

### `PassPriority(player)`

1. The player holds priority — **"you don't have priority to pass"**.

On success: priority passes as described in §7 (resolve the top of the stack, advance the phase, or
hand priority to the next player).

### Anything else

An unrecognised action is rejected — **"unknown action: ..."**.
