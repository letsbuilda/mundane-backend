"""
Mundane - minimal game engine skeleton.

The whole point of this file is to show the architecture we talked through:

  * GameState is the single source of truth. Nothing mutates it except apply_action.
  * apply_action(state, action) is the ONE door: it validates against the current
    state, and only then transitions. A whole game is a reduce over an action stream.
  * "Whose turn it is" (active_player) is separate from "who may act right now"
    (priority_player). That separation is what lets a non-active player respond.
  * The stack is a LIFO list. A response goes on top and resolves BEFORE the thing
    it responds to. That is the entire reason "casting in response" is meaningful.

Run it directly to watch Steve's house party get shut down by Alex's noise complaint.
Requires Python 3.10+ (uses structural pattern matching).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import reduce
from itertools import count
from typing import Callable, Optional


# --------------------------------------------------------------------------- #
# Cards
# --------------------------------------------------------------------------- #

class CardType(Enum):
    PERSON = "person"        # creature-like; stays on the board once it resolves
    APPLIANCE = "appliance"  # artifact-like permanent
    HABIT = "habit"          # enchantment-like permanent
    TASK = "task"            # sorcery-speed one-shot; uses the stack
    INSTANT = "instant"      # can be cast any time you hold priority


# An effect is just a function that mutates the state when the card resolves.
# It receives the resolving StackItem so it can see its controller and target.
Effect = Callable[["GameState", "StackItem"], None]


@dataclass
class Card:
    name: str
    cost: int                      # Time required to play it
    type: CardType
    effect: Effect = lambda s, i: None
    text: str = ""


PERMANENTS = (CardType.PERSON, CardType.APPLIANCE, CardType.HABIT)


# --------------------------------------------------------------------------- #
# Game state
# --------------------------------------------------------------------------- #

@dataclass
class Player:
    name: str
    composure: int = 20            # the "life total" - hit 0 and your household falls apart
    time: int = 0                  # resource available this turn
    hand: list[Card] = field(default_factory=list)
    board: list[Card] = field(default_factory=list)
    deck: list[Card] = field(default_factory=list)
    discard: list[Card] = field(default_factory=list)


_stack_ids = count(1)              # gives every stack object a stable id for targeting


@dataclass
class StackItem:
    card: Card
    controller: int                # index into state.players
    target_id: Optional[int] = None
    id: int = field(default_factory=lambda: next(_stack_ids))


PHASES = ["RESET", "WAKE_UP", "PLAN", "DO_STUFF", "WIND_DOWN"]


@dataclass
class GameState:
    players: list[Player]
    active_player: int = 0         # whose TURN it is (slow: changes once per turn)
    priority_player: int = 0       # who may act RIGHT NOW (fast: changes constantly)
    phase: str = "PLAN"
    stack: list[StackItem] = field(default_factory=list)
    passes_in_a_row: int = 0       # consecutive priority passes with nobody acting
    turn: int = 1
    winner: Optional[int] = None

    def next_player(self, i: int) -> int:
        return (i + 1) % len(self.players)

    def opponent(self, i: int) -> int:   # 2-player convenience
        return (i + 1) % len(self.players)


# --------------------------------------------------------------------------- #
# Actions  (data, not method calls - players submit intents)
# --------------------------------------------------------------------------- #

@dataclass
class PlayCard:        # sorcery-speed: a PERSON / APPLIANCE / HABIT / TASK
    player: int
    hand_index: int


@dataclass
class CastInstant:     # any time you hold priority
    player: int
    hand_index: int
    target_id: Optional[int] = None


@dataclass
class PassPriority:    # "I have nothing to add." Notice there is no AdvancePhase
    player: int        # action - the phase advances as a *consequence* of passing.


class IllegalAction(Exception):
    """Raised when an action is rejected. State is never mutated on rejection."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IllegalAction(message)


# --------------------------------------------------------------------------- #
# The one door
# --------------------------------------------------------------------------- #

def apply_action(state: GameState, action) -> GameState:
    """Validate `action` against `state`, then transition. Returns the state so it
    composes as a reducer:  final = reduce(apply_action, actions, initial)."""

    _require(state.winner is None, "the game is over")

    match action:

        case PlayCard(player, idx):
            # --- validate (sorcery speed is the restrictive one) ---
            _require(player == state.priority_player, "you don't have priority")
            _require(player == state.active_player,
                     "only the active player may play sorcery-speed cards")
            _require(state.phase == "PLAN", "sorcery-speed cards only during Plan")
            _require(not state.stack, "the stack must be empty for sorcery-speed cards")
            p = state.players[player]
            _require(0 <= idx < len(p.hand), "no such card in hand")
            card = p.hand[idx]
            _require(card.type != CardType.INSTANT, "use CastInstant for instants")
            _require(p.time >= card.cost, f"not enough Time ({p.time}/{card.cost})")
            # --- mutate ---
            p.hand.pop(idx)
            p.time -= card.cost
            state.stack.append(StackItem(card, player))
            _grant_priority_after_stack_change(state)

        case CastInstant(player, idx, target_id):
            # --- validate (instants are permissive: anyone with priority, any phase) ---
            _require(player == state.priority_player, "you don't have priority")
            p = state.players[player]
            _require(0 <= idx < len(p.hand), "no such card in hand")
            card = p.hand[idx]
            _require(card.type == CardType.INSTANT, "that card isn't an instant")
            _require(p.time >= card.cost, f"not enough Time ({p.time}/{card.cost})")
            # --- mutate ---
            p.hand.pop(idx)
            p.time -= card.cost
            state.stack.append(StackItem(card, player, target_id))
            _grant_priority_after_stack_change(state)

        case PassPriority(player):
            _require(player == state.priority_player, "you don't have priority to pass")
            state.passes_in_a_row += 1
            if state.passes_in_a_row >= len(state.players):
                # everyone passed in a row with nobody acting
                state.passes_in_a_row = 0
                if state.stack:
                    _resolve_top(state)                 # the stack empties one item at a time
                    state.priority_player = state.active_player
                else:
                    _advance_phase(state)               # nothing pending -> move on
            else:
                state.priority_player = state.next_player(player)

        case _:
            raise IllegalAction(f"unknown action: {action!r}")

    _check_win(state)
    return state


def _grant_priority_after_stack_change(state: GameState) -> None:
    # After anything goes on the stack, the active player gets priority first
    # (yes, even to respond to their own spell), and the pass count resets.
    state.priority_player = state.active_player
    state.passes_in_a_row = 0


def _resolve_top(state: GameState) -> None:
    item = state.stack.pop()                            # LIFO: last on, first off
    card = item.card
    if card.type in PERMANENTS:
        state.players[item.controller].board.append(card)
    else:
        card.effect(state, item)
        state.players[item.controller].discard.append(card)


def _advance_phase(state: GameState) -> None:
    i = PHASES.index(state.phase)
    if i + 1 < len(PHASES):
        state.phase = PHASES[i + 1]
        state.priority_player = state.active_player
    else:
        _end_turn(state)


def _end_turn(state: GameState) -> None:
    state.active_player = state.next_player(state.active_player)
    state.priority_player = state.active_player
    state.phase = PHASES[0]
    state.turn += 1
    # "Wake Up" housekeeping (stubbed): refresh Time and draw.
    p = state.players[state.active_player]
    p.time = 5
    if p.deck:
        p.hand.append(p.deck.pop())


def _check_win(state: GameState) -> None:
    for i, p in enumerate(state.players):
        if p.composure <= 0:
            state.winner = state.opponent(i)


# --------------------------------------------------------------------------- #
# A couple of example card effects
# --------------------------------------------------------------------------- #

def throw_a_party(state: GameState, item: StackItem) -> None:
    state.players[state.opponent(item.controller)].composure -= 3


def noise_complaint(state: GameState, item: StackItem) -> None:
    # Counter a spell on the stack. With an explicit target_id, counter that;
    # otherwise counter the spell directly beneath it (the most recent one).
    target = None
    if item.target_id is not None:
        target = next((s for s in state.stack if s.id == item.target_id), None)
    elif state.stack:
        target = state.stack[-1]
    if target is not None:
        state.stack.remove(target)
        state.players[target.controller].discard.append(target.card)


# --------------------------------------------------------------------------- #
# Demo: the exact scenario from the conversation
# --------------------------------------------------------------------------- #

def demo() -> None:
    party = Card("Throw a House Party", 3, CardType.TASK,
                 throw_a_party, "Deal 3 chaos to your opponent's Composure.")
    complaint = Card("Noise Complaint", 1, CardType.INSTANT,
                     noise_complaint, "Counter target task on the stack.")

    steve = Player("Steve", time=5, hand=[party])
    alex = Player("Alex", time=5, hand=[complaint])
    state = GameState(players=[steve, alex], active_player=0,
                      priority_player=0, phase="PLAN")

    # The engine is a referee. Illegal actions are rejected and change nothing:
    try:
        apply_action(state, CastInstant(player=0, hand_index=0))  # party isn't an instant
    except IllegalAction as e:
        print(f"rejected, state untouched: {e}")

    # A legal game is just a fold over a stream of actions. The action stream is
    # INTERLEAVED between players - who acts next is whatever the state says holds
    # priority. This is Steve's turn, yet Alex acts in the middle of it.
    action_log = [
        PlayCard(player=0, hand_index=0),     # Steve casts Throw a House Party -> stack
        PassPriority(player=0),               # Steve passes; priority -> Alex
        CastInstant(player=1, hand_index=0),  # Alex responds; Noise Complaint -> top of stack
        PassPriority(player=0),               # priority went back to active Steve; he passes
        PassPriority(player=1),               # both passed -> resolve top: complaint counters party
        PassPriority(player=0),               # stack empty now; passes again...
        PassPriority(player=1),               # ...both pass -> phase advances
    ]

    final = reduce(apply_action, action_log, state)

    print(f"Alex's Composure: {final.players[1].composure}   (20 = the party never landed)")
    print(f"Steve's discard:  {[c.name for c in final.players[0].discard]}")
    print(f"Alex's discard:   {[c.name for c in final.players[1].discard]}")
    print(f"Phase now:        {final.phase}, stack size: {len(final.stack)}")

    # Interactive play is the SAME engine - it just pulls the next action from
    # whoever currently holds priority, and rejects bad ones instead of crashing:
    #
    #   while state.winner is None:
    #       actor = state.players[state.priority_player]
    #       action = get_action_from(actor, state)   # your CLI / UI / network layer
    #       try:
    #           apply_action(state, action)
    #       except IllegalAction as e:
    #           tell(actor, f"can't do that: {e}")    # state unchanged; ask again


if __name__ == "__main__":
    demo()
