"""The one door: ``apply_action(state, action)`` validates a move, then transitions.

Every state change in the game goes through here. Each branch runs its ``_require`` preconditions
first (which raise :class:`IllegalAction` on a bad move, mutating nothing) and only then mutates.
The function returns the state so it composes as a reducer:
``final = reduce(partial(apply_action, cards=pool), actions, initial)``.
"""

from .actions import Action, CastInstant, IllegalAction, PassPriority, PlayCard
from .state import PERMANENTS, PHASES, Card, CardType, GameState, StackItem


def _require(condition: bool, message: str) -> None:  # noqa: FBT001  (this is the rule-check idiom)
    """Reject the action with ``IllegalAction(message)`` when ``condition`` is false."""
    if not condition:
        raise IllegalAction(message)


def apply_action(state: GameState, action: Action, cards: dict[str, Card]) -> GameState:
    """Validate ``action`` against ``state``, then transition. Returns ``state``."""
    _require(state.winner is None, "the game is over")

    match action:
        case PlayCard(player, idx):
            _require(player == state.priority_player, "you don't have priority")
            _require(
                player == state.active_player,
                "only the active player may play sorcery-speed cards",
            )
            _require(state.phase == "PLAN", "sorcery-speed cards only during Plan")
            _require(not state.stack, "the stack must be empty for sorcery-speed cards")
            p = state.players[player]
            _require(0 <= idx < len(p.hand), "no such card in hand")
            card = cards[p.hand[idx]]
            _require(card.type != CardType.INSTANT, "use CastInstant for instants")
            _require(p.time >= card.cost, f"not enough Time ({p.time}/{card.cost})")
            card_id = p.hand.pop(idx)
            p.time -= card.cost
            _push_stack(state, card_id, player)

        case CastInstant(player, idx, target_id):
            _require(player == state.priority_player, "you don't have priority")
            p = state.players[player]
            _require(0 <= idx < len(p.hand), "no such card in hand")
            card = cards[p.hand[idx]]
            _require(card.type == CardType.INSTANT, "that card isn't an instant")
            _require(p.time >= card.cost, f"not enough Time ({p.time}/{card.cost})")
            card_id = p.hand.pop(idx)
            p.time -= card.cost
            _push_stack(state, card_id, player, target_id)

        case PassPriority(player):
            _require(player == state.priority_player, "you don't have priority to pass")
            state.passes_in_a_row += 1
            if state.passes_in_a_row >= len(state.players):
                state.passes_in_a_row = 0
                if state.stack:
                    _resolve_top(state, cards)  # the stack empties one item at a time
                    state.priority_player = state.active_player
                else:
                    _advance_phase(state)  # nothing pending -> move on
            else:
                state.priority_player = state.next_player(player)

        case _:
            msg = f"unknown action: {action!r}"
            raise IllegalAction(msg)

    _check_win(state)
    return state


def _push_stack(state: GameState, card_id: str, controller: int, target_id: int | None = None) -> None:
    """Put a card on the stack with a fresh id, then hand priority back to the active player."""
    state.stack.append(
        StackItem(card_id=card_id, controller=controller, target_id=target_id, id=state.next_stack_id),
    )
    state.next_stack_id += 1
    _grant_priority_after_stack_change(state)


def _grant_priority_after_stack_change(state: GameState) -> None:
    """After anything goes on the stack, the active player gets priority and the pass count resets."""
    state.priority_player = state.active_player
    state.passes_in_a_row = 0


def _resolve_top(state: GameState, cards: dict[str, Card]) -> None:
    """Resolve the top stack item (LIFO): permanents hit the board, others fire then go to discard."""
    item = state.stack.pop()  # LIFO: last on, first off
    card = cards[item.card_id]
    if card.type in PERMANENTS:
        state.players[item.controller].board.append(item.card_id)
    else:
        card.effect(state, item)
        state.players[item.controller].discard.append(item.card_id)


def _advance_phase(state: GameState) -> None:
    """Move to the next phase, or end the turn after the last phase."""
    i = PHASES.index(state.phase)
    if i + 1 < len(PHASES):
        state.phase = PHASES[i + 1]
        state.priority_player = state.active_player
    else:
        _end_turn(state)


def _end_turn(state: GameState) -> None:
    """Hand the turn to the next player and run Wake Up housekeeping (refresh Time, draw)."""
    state.active_player = state.next_player(state.active_player)
    state.priority_player = state.active_player
    state.phase = PHASES[0]
    state.turn += 1
    p = state.players[state.active_player]
    p.time = 5
    if p.deck:
        p.hand.append(p.deck.pop())


def _check_win(state: GameState) -> None:
    """Set the winner if any player's Composure has dropped to 0."""
    for i, p in enumerate(state.players):
        if p.composure <= 0:
            state.winner = state.opponent(i)
