# UBGI -- Universal Board Game Interface

UBGI is a text-based protocol between a board game engine and a GUI or
controller program, backward compatible with UCI. Communication uses
stdin/stdout, one command per line.

This document describes the protocol as implemented in `src/ubgi/ubgi.cpp`.

---

## 1. Handshake

```
[GUI]    ubgi                       (or "uci" for backward compatibility)
[ENGINE] id name <GameName>
[ENGINE] id author <GameName> Team
[ENGINE] option name GameName type string default <game>
[ENGINE] option name BoardWidth type spin default <W> min 1 max 26
[ENGINE] option name BoardHeight type spin default <H> min 1 max 26
[ENGINE] option name Algorithm type combo default pvs var pvs var alphabeta var minimax var random
[ENGINE] option name <param> type <check|spin> default <val> ...
[ENGINE] option name Hash type spin default 18 min 10 max 24
[ENGINE] option name NNUEFile type string default <path>       (if compiled with USE_NNUE)
[ENGINE] ubgiok                     (or "uciok" if GUI sent "uci")
[GUI]    isready
[ENGINE] readyok
```

The engine reports `GameName`, `BoardWidth`, and `BoardHeight` based on the
compiled game (e.g., `MiniChess`/5/6 or `Gomoku`/9/9). Algorithm-specific
parameters (UseNNUE, UseTT, UseQuiescence, etc.) are advertised as options.

---

## 2. Commands: GUI to Engine

### `ubgi` / `uci`

Start the handshake. Engine responds with id, options, and `ubgiok`/`uciok`.

### `isready`

Synchronization ping. Engine responds with `readyok` when ready.

### `setoption name <name> value <value>`

Set an engine option. Supported options:

| Name        | Effect |
|-------------|--------|
| `Algorithm` | Switch search algorithm (pvs, alphabeta, minimax, random) |
| `Hash`      | Resize transposition table to 2^N entries (10-24) |
| `NNUEFile`  | Load NNUE model from the given path |
| `UseNNUE`   | Enable/disable NNUE evaluation (true/false) |
| Any other   | Stored in the parameter map for the search algorithm |

### `position startpos [moves <m1> <m2> ...]`

Set the board to the game's starting position, then replay the given moves.

### `position board <encoded> <side> [moves <m1> <m2> ...]`

Set the board from an encoded string and side-to-move (0 or 1), then replay
moves. The encoded format is game-specific:

- **MiniChess**: FEN-like, rows separated by `/`. Uppercase = white pieces
  (`P R N B Q K`), lowercase = black (`p r n b q k`), `.` = empty.
  Example: `kqbnr/ppppp/...../...../PPPPP/RNBQK`
- **Gomoku**: rows separated by `/`. `X` = player 1, `O` = player 2,
  `.` = empty. Example: `........./........./.....X.../....O..../.........`

### `go [depth <N>] [movetime <N>] [infinite]`

Start searching.

- `depth N` -- search to exactly N plies.
- `movetime N` -- search for approximately N milliseconds.
- `infinite` -- search until `stop` is received.
- If none specified, defaults to depth 6.

### `stop`

Interrupt the current search. Engine sends `bestmove` with the best move
found so far.

### `ubginewgame` / `ucinewgame`

Reset engine state (board, player, step counter).

### `d`

Display the current board position in human-readable format with coordinate
labels and side-to-move indicator.

### `quit`

Terminate the engine process.

---

## 3. Commands: Engine to GUI

### `id name <name>` / `id author <author>`

Engine identification during handshake.

### `ubgiok` / `uciok`

End of handshake.

### `readyok`

Response to `isready`.

### `bestmove <move>`

The engine's chosen move after a search. Sent exactly once per `go` command.

### `info`

Search progress. Fields:

```
info depth <N> seldepth <N> score cp <N> nodes <N> time <ms> nps <N>
     currmove <move> currmovenumber <N> pv <m1> <m2> ...
```

All fields are optional. `score cp` is from the side-to-move's perspective
(positive = good for current player).

---

## 4. Move Encoding

Moves are encoded as algebraic strings. The coordinate system uses column
letters (`a`-`z`) and row numbers (`1`-`N`), where `a1` is the bottom-left
from player 1's perspective.

### Placement moves (Gomoku)

2-character string: column letter + row number.

```
h8    -- place stone at column h, row 8
e5    -- place stone at column e, row 5
```

Internally, placement moves have `from == to` in the Move tuple.

### Board moves (MiniChess)

4-character string: from-square + to-square.

```
a2a3  -- move piece from a2 to a3
c1e3  -- move piece from c1 to e3
```

### Null move

```
0000  -- no legal moves available
```

### Detection heuristic

The UBGI layer distinguishes move types by string length:

- 2 characters: placement move (parse as single square, set `from = to`).
- 4 characters: board move (parse as two squares).

---

## 5. Search Integration

The UBGI loop uses iterative deepening. For each `go` command:

1. A background thread runs the search via the algorithm registry.
2. The `on_root_update` callback sends `info` lines after each root move.
3. After each completed depth, a full `info` line with PV is sent.
4. Search stops when: depth limit reached, time budget exceeded (projected
   next iteration would exceed movetime), a winning score is found, or
   `stop` is received.
5. `bestmove` is sent with the best move found.

The `SearchContext` carries `params` (the `ParamMap`), a `stop` flag
(atomic), and the `on_root_update` callback. The UBGI layer sets `g_ctx.stop`
when `stop` is received; the search thread checks it periodically.

---

## 6. Example Sessions

### MiniChess

```
[GUI]    ubgi
[ENGINE] id name MiniChess
[ENGINE] id author MiniChess Team
[ENGINE] option name GameName type string default MiniChess
[ENGINE] option name BoardWidth type spin default 5 min 1 max 26
[ENGINE] option name BoardHeight type spin default 6 min 1 max 26
[ENGINE] option name Algorithm type combo default pvs var pvs var alphabeta var minimax var random
[ENGINE] option name Hash type spin default 18 min 10 max 24
[ENGINE] ubgiok
[GUI]    isready
[ENGINE] readyok
[GUI]    position startpos
[GUI]    go depth 6
[ENGINE] info depth 1 seldepth 1 score cp 12 nodes 30 time 0 nps 0 currmove a2a3 currmovenumber 1
...
[ENGINE] info depth 6 seldepth 9 score cp 14 nodes 48201 time 120 nps 401675 pv a2a3 e5e4 b1b2
[ENGINE] bestmove a2a3
[GUI]    quit
```

### Gomoku

```
[GUI]    ubgi
[ENGINE] id name Gomoku
[ENGINE] id author Gomoku Team
[ENGINE] option name GameName type string default Gomoku
[ENGINE] option name BoardWidth type spin default 9 min 1 max 26
[ENGINE] option name BoardHeight type spin default 9 min 1 max 26
[ENGINE] option name Algorithm type combo default pvs var pvs var alphabeta var minimax var random
[ENGINE] ubgiok
[GUI]    isready
[ENGINE] readyok
[GUI]    position startpos
[GUI]    go depth 6
[ENGINE] info depth 6 score cp 500 nodes 12000 time 50 nps 240000 pv e5
[ENGINE] bestmove e5
[GUI]    position startpos moves e5 d4
[GUI]    go depth 6
...
[ENGINE] bestmove e4
[GUI]    quit
```

### Using board position

```
[GUI]    position board kqbnr/ppppp/...../...../PPPPP/RNBQK 0 moves a2a3
[GUI]    go depth 8
...
[ENGINE] bestmove e5e4
```
