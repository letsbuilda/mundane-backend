"""The effect vocabulary (the fixed set of behaviours) and the JSON-card loader.

This is the ONLY place effect functions live. A JSON card names an effect from :data:`EFFECTS` and
supplies ``params``; it cannot define new behaviour. :func:`build_card` composes the namespaced id
``set_id:id`` and binds the named effect's ``params`` into a closure. The hardcoded ``CARD_LIBRARY``
is gone: card *content* now lives in JSON sets (see ``mundane-cards``), fetched and validated by the
API, while card *behaviour* stays here as code.
"""

from collections.abc import Callable, Mapping
from typing import cast

from .state import Card, CardType, Effect, GameState, StackItem


class UnknownEffectError(Exception):
    """A JSON card names an effect that is not in the :data:`EFFECTS` vocabulary."""


class InvalidEffectParamsError(Exception):
    """A JSON card's ``params`` are missing or the wrong type for its named effect."""


class DuplicateCardError(Exception):
    """Two cards resolved to the same composed id."""


type EffectFactory = Callable[[Mapping[str, object]], Effect]
"""Takes a card's ``params`` and returns a bound :data:`~mundane.engine.state.Effect` closure."""


def _require_int_param(params: Mapping[str, object], key: str) -> int:
    """Return ``params[key]`` as an int, or reject the card with :class:`InvalidEffectParamsError`."""
    value = params.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"effect param {key!r} must be an integer"
        raise InvalidEffectParamsError(msg)
    return value


def damage_composure(params: Mapping[str, object]) -> Effect:
    """Return an effect that deals ``params['amount']`` chaos to the opponent's Composure."""
    amount = _require_int_param(params, "amount")

    def effect(state: GameState, item: StackItem) -> None:
        """Deal the bound amount of chaos to the opponent's Composure."""
        opponent = state.opponent(item.controller)
        state.players[opponent].composure -= amount

    return effect


def counter_task(_params: Mapping[str, object]) -> Effect:
    """Return an effect that counters a task on the stack (the old Noise Complaint). No params."""

    def effect(state: GameState, item: StackItem) -> None:
        """Counter the targeted stack item, or the one directly beneath, if any."""
        target: StackItem | None = None
        if item.target_id is not None:
            target = next((s for s in state.stack if s.id == item.target_id), None)
        elif state.stack:
            target = state.stack[-1]
        if target is not None:
            state.stack.remove(target)
            state.players[target.controller].discard.append(target.card_id)

    return effect


def none(_params: Mapping[str, object]) -> Effect:
    """Return a no-op effect. Permanents name this so that every JSON card names an effect."""

    def effect(_state: GameState, _item: StackItem) -> None:
        """Do nothing. Permanents resolve onto the board, so their effect never fires."""

    return effect


EFFECTS: dict[str, EffectFactory] = {
    "damage_composure": damage_composure,
    "counter_task": counter_task,
    "none": none,
}
"""The fixed effect vocabulary: name -> factory. The engine is the sole authority on what's valid."""


def build_card(set_id: str, card_dict: Mapping[str, object]) -> Card:
    """Build one :class:`Card` from a (schema-validated) JSON card dict in set ``set_id``.

    Composes the namespaced id ``set_id:id``, looks the ``effect`` name up in :data:`EFFECTS`
    (raising :class:`UnknownEffectError` if absent), and binds ``params`` into the effect closure
    (the factory raises :class:`InvalidEffectParamsError` on bad params).
    """
    effect_name = cast("str", card_dict["effect"])
    try:
        factory = EFFECTS[effect_name]
    except KeyError as exc:
        msg = f"unknown effect {effect_name!r} (known: {sorted(EFFECTS)})"
        raise UnknownEffectError(msg) from exc
    params = cast("Mapping[str, object]", card_dict.get("params", {}))
    bound = factory(params)  # may raise InvalidEffectParamsError
    return Card(
        id=f"{set_id}:{cast('str', card_dict['id'])}",
        name=cast("str", card_dict["name"]),
        cost=cast("int", card_dict["cost"]),
        type=CardType(cast("str", card_dict["type"])),
        effect=bound,
        text=cast("str", card_dict.get("text", "")),
        flavor=cast("str", card_dict.get("flavor", "")),
    )


def build_pool(set_dict: Mapping[str, object]) -> dict[str, Card]:
    """Build ``{composed_id: Card}`` from one parsed set dict (offline; used by tests and the demo).

    The API's ``set_loader`` does the same across multiple fetched sets; this is the pure, no-I/O
    helper for a single already-parsed set. Raises :class:`DuplicateCardError` on a repeated id.
    """
    set_id = cast("str", set_dict["set_id"])
    pool: dict[str, Card] = {}
    for raw in cast("list[Mapping[str, object]]", set_dict["cards"]):
        card = build_card(set_id, raw)
        if card.id in pool:
            msg = f"duplicate card id {card.id!r}"
            raise DuplicateCardError(msg)
        pool[card.id] = card
    return pool
