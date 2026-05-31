"""The card library: id -> Card definitions, and the effect functions they carry.

This is the ONLY place effect functions (code) live. State references cards by id; resolving an id
through :data:`CARD_LIBRARY` is how the engine recovers a card's type, cost, and effect.
"""

from .state import Card, CardType, GameState, StackItem


def throw_a_party(state: GameState, item: StackItem) -> None:
    """Deal 3 chaos to the opponent's Composure."""
    opponent = state.opponent(item.controller)
    state.players[opponent].composure -= 3


def noise_complaint(state: GameState, item: StackItem) -> None:
    """Counter a spell on the stack.

    With an explicit ``target_id``, counter that item; otherwise counter the spell directly beneath
    it (the most recent one). A countered card goes to its controller's discard.
    """
    target: StackItem | None = None
    if item.target_id is not None:
        target = next((s for s in state.stack if s.id == item.target_id), None)
    elif state.stack:
        target = state.stack[-1]
    if target is not None:
        state.stack.remove(target)
        state.players[target.controller].discard.append(target.card_id)


CARD_LIBRARY: dict[str, Card] = {
    card.id: card
    for card in (
        Card(
            id="throw_a_house_party",
            name="Throw a House Party",
            cost=3,
            type=CardType.TASK,
            effect=throw_a_party,
            text="Deal 3 chaos to your opponent's Composure.",
        ),
        Card(
            id="noise_complaint",
            name="Noise Complaint",
            cost=1,
            type=CardType.INSTANT,
            effect=noise_complaint,
            text="Counter target task on the stack.",
        ),
        Card(
            id="helpful_roommate",
            name="Helpful Roommate",
            cost=2,
            type=CardType.PERSON,
            text="A dependable body around the house. Resolves onto your board.",
        ),
        Card(
            id="espresso_machine",
            name="Espresso Machine",
            cost=2,
            type=CardType.APPLIANCE,
            text="A trusty appliance. Resolves onto your board.",
        ),
        Card(
            id="morning_jog",
            name="Morning Jog",
            cost=1,
            type=CardType.HABIT,
            text="A wholesome routine. Resolves onto your board.",
        ),
    )
}
