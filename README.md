# Mundane, backened

*Part of https://github.com/letsbuilda/mundane*

No dragons. No spells. Just Tuesday.

Two households face off. The engine is a **referee**: a whole game is a fold over a stream of
*actions*, and one function — `apply_action(state, action)` — validates each action against the
current state and then transitions it. Illegal moves are rejected (the state is left untouched), not
crashed on. The HTTP API is a thin shell that translates requests into engine actions; all the rules
live in the engine.
