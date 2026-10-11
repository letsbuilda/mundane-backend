-- A game is event-sourced: the card snapshot it was created with, plus every accepted action in order.
-- Live state is never stored; loading a game replays its actions over the snapshot.
CREATE TABLE games (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    card_snapshot TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX games_owner ON games (owner);

CREATE TABLE actions (
    game_id TEXT NOT NULL REFERENCES games (id),
    seq INTEGER NOT NULL,
    action TEXT NOT NULL,
    PRIMARY KEY (game_id, seq)
);
