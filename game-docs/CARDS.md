# Mundane — Card Catalog

Every card in the library, with its id, cost, type, and rules text. This mirrors `CARD_LIBRARY` in
the engine; the library is the source of truth. See [`SPEC.md`](./SPEC.md) for what the types and
costs mean.

| Id                    | Name                | Cost | Type        | Text                                                       |
|-----------------------|---------------------|------|-------------|------------------------------------------------------------|
| `throw_a_house_party` | Throw a House Party | 3    | `TASK`      | Deal 3 chaos to your opponent's Composure.                 |
| `noise_complaint`     | Noise Complaint     | 1    | `INSTANT`   | Counter target task on the stack.                          |
| `helpful_roommate`    | Helpful Roommate    | 2    | `PERSON`    | A dependable body around the house. Resolves onto your board. |
| `espresso_machine`    | Espresso Machine    | 2    | `APPLIANCE` | A trusty appliance. Resolves onto your board.              |
| `morning_jog`         | Morning Jog         | 1    | `HABIT`     | A wholesome routine. Resolves onto your board.             |

## Notes on effects

- **Throw a House Party** (`TASK`): on resolution, subtracts 3 from the opponent's Composure.
- **Noise Complaint** (`INSTANT`): on resolution, removes a spell from the stack and sends it to its
  controller's discard. With an explicit target it counters that spell; otherwise it counters the
  spell immediately beneath it (the most recent one). Because it is an instant, it can be cast in
  response to a card already on the stack and — being last on — resolves first.
- **Helpful Roommate** / **Espresso Machine** / **Morning Jog** (permanents): these have no
  resolution effect. A permanent resolves directly onto its controller's board and stays there.
