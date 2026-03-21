# UBGI Protocol Specification

**Universal Board Game Interface** -- Version 1.0

---

## 1. Overview

UBGI (Universal Board Game Interface) is a text-based communication protocol
between a board-game engine and a GUI or controller program. It is a superset
of the Universal Chess Interface (UCI) protocol, extended to support multiple
game types including piece drops, shogi-style promotions, and placement games.

All communication flows through **stdin** and **stdout**, one command per line,
terminated by a newline character (`\n`). Lines ending with `\r\n` are accepted;
the trailing `\r` is stripped. Empty lines are ignored.

### 1.1 Design Goals

- **UCI backward compatibility.** A controller that speaks UCI can drive a UBGI
  engine by sending `uci` instead of `ubgi`. The engine mirrors the handshake
  token (`uciok`/`ubgiok`) accordingly.
- **Game-agnostic.** The same protocol handles chess-like games (MiniChess),
  shogi-like games (MiniShogi with drops and promotions), and placement games
  (Gomoku). The engine advertises its game type, board dimensions, and
  available options during the handshake.
- **Asynchronous search.** The engine runs the search on a background thread.
  The GUI can send `stop` at any time to interrupt the search and receive the
  best move found so far.

### 1.2 Key Differences from UCI

| Feature | UCI | UBGI |
|---|---|---|
| Handshake command | `uci` | `ubgi` (also accepts `uci`) |
| Handshake response | `uciok` | `ubgiok` (or `uciok` if GUI sent `uci`) |
| New game command | `ucinewgame` | `ubginewgame` (also accepts `ucinewgame`) |
| Drop moves | Not supported | `P*c3` notation (piece type + `*` + destination) |
| Promotion moves | `a7a8q` (promotion piece suffix) | `a4a5+` (trailing `+` means promote) |
| Placement moves | Not supported | 2-character destination string (e.g. `e5`) |
| Board position | FEN string | Game-specific encoded string via `position board` |
| Game metadata | Not provided | `GameName`, `BoardWidth`, `BoardHeight` options |
| Hand pieces | Not applicable | Encoded in board string after `_` separator |

---

## 2. Protocol Lifecycle

```
  GUI                                    ENGINE
   |                                       |
   |-------- ubgi (or uci) -------------->|
   |                                       |
   |<------- id name MiniChess -----------|
   |<------- id author MiniChess Team ----|
   |<------- option name GameName ... ----|
   |<------- option name BoardWidth ... --|
   |<------- option name BoardHeight ... -|
   |<------- option name Algorithm ... ---|
   |<------- option name <param> ... -----|
   |<------- option name Hash ... --------|
   |<------- option name NNUEFile ... ----|  (if compiled with NNUE)
   |<------- ubgiok (or uciok) ----------|
   |                                       |
   |-------- setoption name X value Y --->|  (optional, repeat as needed)
   |-------- isready --------------------->|
   |                                       |  (engine loads NNUE model here)
   |<------- readyok ---------------------|
   |                                       |
   |  [ ... game loop ... ]                |
   |                                       |
   |-------- quit ------------------------>|
```

---

## 3. Command Reference: GUI to Engine

### 3.1 Summary Table

| Command | Description |
|---|---|
| `ubgi` | Initiate UBGI handshake |
| `uci` | Initiate UCI-compatible handshake |
| `isready` | Synchronization ping; engine responds `readyok` |
| `setoption name <N> value <V>` | Set an engine option |
| `position startpos [moves ...]` | Set board to start position, optionally replay moves |
| `position board <encoded> <side> [moves ...]` | Set board from encoded string |
| `go [depth N] [movetime N] [infinite]` | Start searching |
| `stop` | Interrupt search; engine sends `bestmove` |
| `ubginewgame` | Reset engine state for a new game |
| `ucinewgame` | Alias for `ubginewgame` |
| `d` | Display current board (debug) |
| `quit` | Terminate the engine process |

### 3.2 Detailed Command Descriptions

#### `ubgi` / `uci`

Start the protocol handshake. The engine responds with identification lines,
option advertisements, and a terminating `ubgiok` or `uciok` (matching the
command the GUI sent). The GUI must wait for this terminator before sending
further commands.

**Example:**
```
GUI:    ubgi
ENGINE: id name MiniShogi
ENGINE: id author MiniShogi Team
ENGINE: option name GameName type string default MiniShogi
ENGINE: option name BoardWidth type spin default 5 min 1 max 26
ENGINE: option name BoardHeight type spin default 5 min 1 max 26
ENGINE: option name Algorithm type combo default pvs var pvs var alphabeta var minimax var random
ENGINE: option name UseNNUE type check default true
ENGINE: option name Hash type spin default 18 min 10 max 24
ENGINE: option name NNUEFile type string default models/nnue.bin
ENGINE: ubgiok
```

#### `isready`

Synchronization command. The engine must respond with `readyok` when it has
finished processing all previous commands and is ready to accept new ones.

On the first `isready` after the handshake, the engine loads the NNUE model
file (if compiled with NNUE support). This deferred loading allows the GUI to
set `NNUEFile` via `setoption` before the model is loaded.

If NNUE loading fails, the engine automatically sets `UseNNUE` to `false` and
emits an `info string` diagnostic.

**Example:**
```
GUI:    isready
ENGINE: info string NNUE loaded: models/nnue.bin
ENGINE: readyok
```

#### `setoption name <name> value <value>`

Set an engine option. Must be sent after the handshake and before `go`. Option
names are case-sensitive.

Certain options have special handling:

| Option | Behavior |
|---|---|
| `Algorithm` | Switches the search algorithm and resets all algorithm-specific parameters to the new algorithm's defaults. Value is matched case-insensitively. |
| `Hash` | Resizes the transposition table to 2^N entries. Valid range: 10--24. Engine confirms with `info string TT resized to 2^N entries`. |
| `NNUEFile` | Sets the path to the NNUE model file. The model is loaded (or reloaded) on the next `isready`. |
| `UseNNUE` | Enable (`true`) or disable (`false`) NNUE evaluation. If NNUE was not compiled in, the engine responds with an error via `info string`. |
| Any other | Stored in the engine's parameter map and passed to the search algorithm. |

**Examples:**
```
GUI:    setoption name Algorithm value alphabeta
GUI:    setoption name Hash value 20
GUI:    setoption name UseNNUE value false
GUI:    setoption name NNUEFile value models/shogi_nnue.bin
GUI:    setoption name UseQuiescence value true
GUI:    setoption name QuiescenceMaxDepth value 8
```

#### `position startpos [moves <m1> <m2> ...]`

Set the board to the game's compiled-in starting position. If `moves` is
present, the listed moves are replayed sequentially from the start position.

**Examples:**
```
GUI:    position startpos
GUI:    position startpos moves a2a3 e5e4 b1c3
GUI:    position startpos moves e5 d4 e4
GUI:    position startpos moves b4b3+ P*c3 a5a4
```

#### `position board <encoded> <side> [moves <m1> <m2> ...]`

Set the board from a game-specific encoded string. `<side>` is the
side-to-move: `0` for the first player (white/sente/X), `1` for the second
player (black/gote/O). If `moves` is present, those moves are replayed from
the given position.

The encoded board format depends on the game (see Section 5).

**Examples:**
```
GUI:    position board kqbnr/ppppp/...../...../PPPPP/RNBQK 0
GUI:    position board kqbnr/ppppp/...../...../PPPPP/RNBQK 0 moves a2a3
GUI:    position board rbsgk/4p/5/P4/KGSBR_- 0
GUI:    position board rbsgk/4p/5/P4/KGSBR_Sp 0 moves S*c3
```

#### `go [depth <N>] [movetime <N>] [infinite]`

Start searching the current position. The search runs on a background thread.
The engine sends `info` lines during the search and a final `bestmove` when
finished.

| Parameter | Description |
|---|---|
| `depth N` | Search to exactly N plies. |
| `movetime N` | Search for approximately N milliseconds. The engine finishes the current iteration and stops if starting the next iteration would likely exceed the time budget (heuristic: stop when elapsed >= movetime / 2). |
| `infinite` | Search indefinitely until `stop` is received. |
| *(none)* | Defaults to `depth 6`. |

Multiple parameters may be combined. If `depth` and `movetime` are both given,
search stops when either limit is reached.

The search also terminates early if a winning score is detected (score within
100 centipawns of the maximum).

If the position has no legal moves, the engine immediately responds with
`bestmove 0000`.

**Examples:**
```
GUI:    go depth 10
GUI:    go movetime 5000
GUI:    go infinite
GUI:    go
```

#### `stop`

Interrupt the current search. The engine sets an internal stop flag, waits for
the search thread to terminate, and the search thread sends `bestmove` with
the best move found so far. If no search is running, the command is harmless.

#### `ubginewgame` / `ucinewgame`

Reset the engine's internal state: the board is restored to the starting
position, the side-to-move is reset to player 0, and the step counter is
cleared. This does not reset engine options or the algorithm selection.

#### `d`

Debug command. The engine prints the current board position in a human-readable
format with coordinate labels, side-to-move indicator, step counter, and the
name of the active algorithm. Output is sent as a single multi-line response.

**Example output (MiniChess):**
```
   a  b  c  d  e
6 bK bQ bB bn bR  6
5 bP bP bP bP bP  5
4  .  .  .  .  .  4
3  .  .  .  .  .  3
2 wP wP wP wP wP  2
1 wR wn wB wQ wK  1
   a  b  c  d  e
Side to move: white
Step: 0
Algorithm: pvs
```

#### `quit`

Terminate the engine process. The engine stops any running search and exits.

---

## 4. Command Reference: Engine to GUI

### 4.1 Summary Table

| Response | Description |
|---|---|
| `id name <name>` | Engine name (game-specific, e.g. `MiniChess`) |
| `id author <author>` | Engine author (e.g. `MiniChess Team`) |
| `option name <N> type <T> ...` | Advertise a configurable option |
| `ubgiok` / `uciok` | End of handshake |
| `readyok` | Response to `isready` |
| `info ...` | Search progress information |
| `bestmove <move>` | Final move after search completes |

### 4.2 Detailed Response Descriptions

#### `id name <name>` / `id author <author>`

Engine identification, sent during the handshake. The name matches the
compiled game's `game_name()` (e.g. `MiniChess`, `MiniShogi`, `Gomoku`).

#### `option name <N> type <T> [default <D>] [min <min> max <max>] [var <v> ...]`

Advertise a configurable option. Sent during the handshake, one line per
option. Supported option types:

| Type | Format | Description |
|---|---|---|
| `check` | `option name X type check default true` | Boolean toggle (`true`/`false`) |
| `spin` | `option name X type spin default 5 min 1 max 10` | Integer in a range |
| `combo` | `option name X type combo default a var a var b` | Selection from a list |
| `string` | `option name X type string default path/to/file` | Free-form string |

#### `ubgiok` / `uciok`

Signals the end of the handshake. The engine mirrors the GUI's initial
command: if the GUI sent `ubgi`, the engine responds `ubgiok`; if the GUI sent
`uci`, the engine responds `uciok`.

#### `readyok`

Sent in response to `isready` once the engine has finished all pending work
(including NNUE model loading on first call).

#### `info ...`

Search progress information. Sent during a search, both after each root move
evaluation and after each completed iteration (depth). All fields are optional
and may appear in any order, except `pv` which must be last.

| Field | Type | Description |
|---|---|---|
| `depth <N>` | int | Current search depth in plies |
| `seldepth <N>` | int | Maximum selective depth reached (including quiescence) |
| `score cp <N>` | int | Evaluation in centipawns from the side-to-move's perspective. Positive means the current player is ahead. |
| `nodes <N>` | uint64 | Total nodes searched so far (cumulative across all iterations) |
| `time <N>` | int64 | Elapsed time in milliseconds since search started |
| `nps <N>` | uint64 | Nodes per second for the current iteration |
| `currmove <move>` | string | The root move currently being evaluated |
| `currmovenumber <N>` | int | Index of `currmove` among root moves (1-based) |
| `pv <m1> <m2> ...` | strings | Principal variation (best line found at this depth). Must appear at end of line; all remaining tokens are treated as PV moves. |
| `string <text>` | string | Free-form diagnostic message. All remaining tokens are the message text. |

**Example info lines:**
```
info depth 3 seldepth 5 score cp 18 nodes 1240 time 12 nps 103333 currmove b1c3 currmovenumber 4
info depth 6 seldepth 12 score cp 25 nodes 48201 time 120 nps 401675 pv a2a3 e5e4 b1c3
info string NNUE loaded: models/nnue.bin
info string TT resized to 2^20 entries
```

#### `bestmove <move>`

The engine's chosen move after a search. Sent exactly once per `go` command.
The move uses the notation described in Section 6. If no legal moves exist,
the engine sends `bestmove 0000`.

---

## 5. Board Encoding Formats

The `position board` command uses a game-specific encoded string. The format
depends on which game the engine was compiled for.

### 5.1 MiniChess (5x6)

Rows are listed top-to-bottom (row 6 first, row 1 last), separated by `/`.
Each cell is one character:

| Character | Meaning |
|---|---|
| `.` | Empty square |
| `P R N B Q K` | White (player 0) pawn, rook, knight, bishop, queen, king |
| `p r n b q k` | Black (player 1) pawn, rook, knight, bishop, queen, king |

**Example (starting position):**
```
kqbnr/ppppp/...../...../PPPPP/RNBQK
```

Reading top-to-bottom: row 6 has black's king, queen, bishop, knight, rook;
row 5 has black's pawns; rows 4--3 are empty; row 2 has white's pawns; row 1
has white's rook, knight, bishop, queen, king.

### 5.2 Gomoku (9x9)

Rows are listed top-to-bottom (row 9 first, row 1 last), separated by `/`.
Each cell is one character:

| Character | Meaning |
|---|---|
| `.` | Empty intersection |
| `X` | Player 0 stone |
| `O` | Player 1 stone |

**Example:**
```
........./........./........./........./.....X.../....O..../........./........./.........
```

### 5.3 MiniShogi (5x5)

Uses SFEN-like encoding. Rows are listed top-to-bottom (row 5 first, row 1
last), separated by `/`. Pieces use letter codes; consecutive empty squares
are compressed as a digit (run-length encoding). Uppercase letters represent
sente (player 0) and lowercase represent gote (player 1). Promoted pieces
are prefixed with `+`.

| Character | Sente (player 0) | Gote (player 1) |
|---|---|---|
| `P` / `p` | Pawn | Pawn |
| `S` / `s` | Silver | Silver |
| `G` / `g` | Gold | Gold |
| `B` / `b` | Bishop | Bishop |
| `R` / `r` | Rook | Rook |
| `K` / `k` | King | King |
| `+P` / `+p` | Promoted pawn (Tokin) | Promoted pawn |
| `+S` / `+s` | Promoted silver | Promoted silver |
| `+B` / `+b` | Promoted bishop (Horse) | Promoted bishop |
| `+R` / `+r` | Promoted rook (Dragon) | Promoted rook |
| `1`--`5` | That many empty squares | -- |

After the board section, an underscore `_` separates the **hand** (captured
pieces available for dropping). Hand pieces are listed as uppercase letters
for sente and lowercase for gote. A count digit precedes the letter if more
than one of that type is held. A `-` means both hands are empty.

**Examples:**
```
rbsgk/4p/5/P4/KGSBR_-          (starting position, empty hands)
rbsgk/4p/5/P4/KGSBR_Sp         (sente holds a Silver, gote holds a pawn)
rb1gk/4p/+P4/5/KGSBR_S2p       (sente holds Silver; gote holds 2 pawns)
```

---

## 6. Move Notation

All moves are represented as ASCII strings. The coordinate system uses column
letters `a`--`z` (left to right) and row numbers `1`--`N` (bottom to top),
where `a1` is the bottom-left square from player 0's perspective.

### 6.1 Move Types

| Type | Format | Length | Description |
|---|---|---|---|
| Board move | `<from><to>` | 4 chars | Move a piece from one square to another |
| Promotion move | `<from><to>+` | 5 chars | Move a piece and promote it |
| Drop move | `<P>*<to>` | 4 chars | Drop a hand piece onto the board |
| Placement move | `<sq>` | 2 chars | Place a stone (Gomoku) |
| Null move | `0000` | 4 chars | No legal moves available |

### 6.2 Board Moves (MiniChess, MiniShogi)

A 4-character string consisting of the origin square followed by the
destination square.

```
a2a3    move piece from a2 to a3
c1e3    move piece from c1 to e3
e1d2    move piece from e1 to d2
```

### 6.3 Promotion Moves (MiniShogi)

A 5-character string: origin square, destination square, followed by `+`.
When a piece enters, exits, or moves within the promotion zone, it may
(or in some cases must) promote. The `+` suffix indicates that the piece
promotes upon completing the move.

Internally, promotion is encoded by adding `BOARD_H` to the destination row
in the `Move` tuple.

```
a4a5+   move piece from a4 to a5 and promote
b1b2+   move piece from b1 to b2 and promote
d3c2+   move piece from d3 to c2 and promote
```

### 6.4 Drop Moves (MiniShogi)

A 4-character string: piece letter, asterisk `*`, then the destination square.
The piece letter is always uppercase regardless of which player is dropping.

| Letter | Piece |
|---|---|
| `P` | Pawn |
| `S` | Silver |
| `G` | Gold |
| `B` | Bishop |
| `R` | Rook |

Internally, drop moves are encoded with the origin point set to
`(BOARD_H, piece_type)` as a sentinel value.

```
P*c3    drop a Pawn on c3
B*d4    drop a Bishop on d4
R*a1    drop a Rook on a1
S*e5    drop a Silver on e5
```

### 6.5 Placement Moves (Gomoku)

A 2-character string consisting of just the destination square. There is no
origin square because stones are placed from outside the board.

Internally, placement moves have `from == to` in the `Move` tuple.

```
e5      place stone at e5
h8      place stone at h8
a1      place stone at a1
```

### 6.6 Null Move

The string `0000` indicates that no legal moves are available. The engine
sends `bestmove 0000` in this case.

### 6.7 Detection Heuristic

The UBGI layer distinguishes move types by pattern matching:

1. If the string contains `*` at position 1: **drop move** (e.g. `P*c3`).
2. If the string length is 2: **placement move** (e.g. `e5`).
3. If the string length is 5 and ends with `+`: **promotion move** (e.g. `a4a5+`).
4. If the string length is 4: **board move** (e.g. `a2a3`).

---

## 7. Engine Options

Options are advertised during the handshake and set via `setoption`. The
available options depend on the compiled game and the selected algorithm.

### 7.1 Global Options (Always Present)

| Name | Type | Default | Range | Description |
|---|---|---|---|---|
| `GameName` | string | *(game-specific)* | -- | Read-only game identifier (e.g. `MiniChess`, `MiniShogi`, `Gomoku`) |
| `BoardWidth` | spin | *(game-specific)* | 1--26 | Read-only board width in columns |
| `BoardHeight` | spin | *(game-specific)* | 1--26 | Read-only board height in rows |
| `Algorithm` | combo | `pvs` | `pvs`, `alphabeta`, `minimax`, `random` | Active search algorithm. Changing this resets all algorithm-specific parameters. |
| `Hash` | spin | `18` | 10--24 | Transposition table size as log2 of number of entries (2^18 = 262144 entries by default) |

### 7.2 NNUE Options (When Compiled with USE_NNUE)

| Name | Type | Default | Description |
|---|---|---|---|
| `NNUEFile` | string | `models/nnue.bin` | Path to the NNUE model file. Loaded on the next `isready`. |

### 7.3 PVS Algorithm Options (Algorithm = pvs)

These options are advertised when the PVS algorithm is active (the default).

| Name | Type | Default | Range | Description |
|---|---|---|---|---|
| `UseNNUE` | check | `true` | -- | Use NNUE evaluation when available |
| `UseKPEval` | check | `true` | -- | Use King-Piece evaluation tables |
| `UseEvalMobility` | check | `true` | -- | Include mobility in evaluation |
| `UseMoveOrdering` | check | `true` | -- | Enable MVV-LVA and history-based move ordering |
| `UseQuiescence` | check | `true` | -- | Enable quiescence search at leaf nodes |
| `QuiescenceMaxDepth` | spin | `16` | 1--64 | Maximum depth for quiescence search |
| `UseTT` | check | `true` | -- | Enable transposition table probing and storing |
| `UseKillerMoves` | check | `true` | -- | Enable killer move heuristic |
| `KillerSlots` | spin | `2` | 1--4 | Number of killer move slots per ply |
| `UseNullMove` | check | `true` | -- | Enable null-move pruning |
| `NullMoveR` | spin | `2` | 1--4 | Null-move reduction depth (R) |
| `UseLMR` | check | `true` | -- | Enable Late Move Reductions |
| `LMRFullDepth` | spin | `3` | 1--10 | Number of moves to search at full depth before applying LMR |
| `LMRDepthLimit` | spin | `3` | 1--10 | Minimum remaining depth to apply LMR |
| `ReportPartial` | check | `true` | -- | Send `info` lines after each root move evaluation |

### 7.4 Alpha-Beta Algorithm Options (Algorithm = alphabeta)

| Name | Type | Default | Description |
|---|---|---|---|
| `UseNNUE` | check | `true` | Use NNUE evaluation when available |
| `UseKPEval` | check | `true` | Use King-Piece evaluation tables |
| `UseEvalMobility` | check | `true` | Include mobility in evaluation |
| `ReportPartial` | check | `true` | Send `info` lines after each root move evaluation |

### 7.5 Minimax Algorithm Options (Algorithm = minimax)

| Name | Type | Default | Description |
|---|---|---|---|
| `UseNNUE` | check | `true` | Use NNUE evaluation when available |
| `UseKPEval` | check | `true` | Use King-Piece evaluation tables |
| `UseEvalMobility` | check | `true` | Include mobility in evaluation |
| `ReportPartial` | check | `true` | Send `info` lines after each root move evaluation |

### 7.6 Random Algorithm Options (Algorithm = random)

The random algorithm has no configurable options. It selects a uniformly
random legal move.

---

## 8. Search Behavior

### 8.1 Iterative Deepening

For each `go` command, the engine uses iterative deepening:

1. A background thread is spawned to run the search.
2. The engine searches depth 1, then depth 2, and so on up to the requested
   depth limit (or indefinitely for `infinite`).
3. After each completed depth, a full `info` line is emitted with the PV.
4. If `ReportPartial` is enabled, partial `info` lines with `currmove` and
   `currmovenumber` are sent after each root move evaluation.
5. When the search completes, `bestmove` is sent with the best move found.

### 8.2 Search Termination Conditions

The search stops when any of the following conditions are met:

- The requested depth limit is reached.
- The time budget is exceeded (the engine estimates whether the next iteration
  would finish in time; it stops if `elapsed * 2 >= movetime`).
- A winning score is found (within 100 centipawns of the theoretical maximum
  of +/-100000).
- The `stop` command is received from the GUI.

### 8.3 Score Interpretation

Scores are reported in centipawns from the perspective of the side to move.
A positive score means the side to move is ahead. The theoretical maximum
score is `100000` (checkmate/winning).

### 8.4 Generation Counter

The engine uses an internal generation counter to handle rapid `go`/`stop`
sequences. Each search checks that its generation matches the current global
generation. If a new `go` is issued before the old search finishes, the old
search silently exits without sending `bestmove`.

---

## 9. GUI Integration

### 9.1 Subprocess Communication

The GUI spawns the engine as a subprocess with piped stdin/stdout. A Python
reference implementation is provided in `gui/ubgi_client.py` via the
`UBGIEngine` class.

**Startup sequence:**

1. Launch the engine executable with stdin/stdout pipes.
2. Send `ubgi` and read lines until `ubgiok` or `uciok` is received, parsing
   `option` lines along the way to discover the engine's capabilities.
3. Extract `GameName`, `BoardWidth`, and `BoardHeight` from the option
   defaults to configure the GUI layout.
4. Optionally send `setoption` commands (e.g. `NNUEFile`).
5. Send `isready` and wait for `readyok`.

**Game loop:**

1. Send `position startpos moves <move_list>` (or `position board ...`).
2. Send `go depth N` (or `go movetime N`, etc.).
3. Read `info` lines asynchronously to update the GUI's analysis display.
4. Read the `bestmove` line to receive the engine's chosen move.
5. If the user wants to abort, send `stop` first.

### 9.2 Move Conversion (GUI Coordinates to UBGI Strings)

The GUI stores moves as `((from_row, from_col), (to_row, to_col))` tuples
using internal array indices (row 0 = top of board). The `UBGIEngine` class
provides static methods to convert between these tuples and UBGI move strings:

- `move_to_uci(move)` -- converts a tuple to a UBGI string.
- `uci_to_move(uci_str)` -- converts a UBGI string to a tuple.

These methods handle all move types: board moves, promotions, drops, and
placements.

### 9.3 Persistent Reader Thread

The GUI client uses a single persistent reader thread that survives across
multiple `go`/`stop` cycles. The thread dispatches:

- `info` lines to the current `info_callback` for live search display.
- `bestmove` lines to the current `done_callback`.
- `readyok` lines to the current `ready_callback`.

---

## 10. Example Sessions

### 10.1 MiniChess: Full Game Start

```
GUI:    ubgi
ENGINE: id name MiniChess
ENGINE: id author MiniChess Team
ENGINE: option name GameName type string default MiniChess
ENGINE: option name BoardWidth type spin default 5 min 1 max 26
ENGINE: option name BoardHeight type spin default 6 min 1 max 26
ENGINE: option name Algorithm type combo default pvs var pvs var alphabeta var minimax var random
ENGINE: option name UseNNUE type check default true
ENGINE: option name UseKPEval type check default true
ENGINE: option name UseEvalMobility type check default true
ENGINE: option name UseMoveOrdering type check default true
ENGINE: option name UseQuiescence type check default true
ENGINE: option name QuiescenceMaxDepth type spin default 16 min 1 max 64
ENGINE: option name UseTT type check default true
ENGINE: option name UseKillerMoves type check default true
ENGINE: option name KillerSlots type spin default 2 min 1 max 4
ENGINE: option name UseNullMove type check default true
ENGINE: option name NullMoveR type spin default 2 min 1 max 4
ENGINE: option name UseLMR type check default true
ENGINE: option name LMRFullDepth type spin default 3 min 1 max 10
ENGINE: option name LMRDepthLimit type spin default 3 min 1 max 10
ENGINE: option name ReportPartial type check default true
ENGINE: option name Hash type spin default 18 min 10 max 24
ENGINE: option name NNUEFile type string default models/nnue.bin
ENGINE: ubgiok
GUI:    isready
ENGINE: info string NNUE loaded: models/nnue.bin
ENGINE: readyok
GUI:    position startpos
GUI:    go depth 6
ENGINE: info depth 1 seldepth 1 score cp 12 nodes 30 time 0 nps 0 currmove a2a3 currmovenumber 1
ENGINE: info depth 1 seldepth 2 score cp 12 nodes 30 time 0 nps 0 pv a2a3
ENGINE: info depth 2 seldepth 4 score cp 8 nodes 180 time 1 nps 180000 pv a2a3 e5e4
...
ENGINE: info depth 6 seldepth 12 score cp 25 nodes 48201 time 120 nps 401675 pv a2a3 e5e4 b1c3
ENGINE: bestmove a2a3
GUI:    position startpos moves a2a3 e5e4
GUI:    go depth 6
...
ENGINE: bestmove b1c3
GUI:    quit
```

### 10.2 MiniShogi: Drops and Promotions

```
GUI:    ubgi
ENGINE: id name MiniShogi
ENGINE: id author MiniShogi Team
ENGINE: option name GameName type string default MiniShogi
ENGINE: option name BoardWidth type spin default 5 min 1 max 26
ENGINE: option name BoardHeight type spin default 5 min 1 max 26
ENGINE: option name Algorithm type combo default pvs var pvs var alphabeta var minimax var random
...
ENGINE: ubgiok
GUI:    isready
ENGINE: readyok
GUI:    position startpos
GUI:    go depth 8
ENGINE: info depth 1 seldepth 1 score cp 0 nodes 14 time 0 nps 0 currmove a2a3 currmovenumber 1
...
ENGINE: info depth 8 seldepth 15 score cp 120 nodes 95420 time 450 nps 212044 pv a2a3 e4e3 d1c2 c5d4 c2b3+
ENGINE: bestmove a2a3
GUI:    position startpos moves a2a3 e4e3 b1b2+
GUI:    go depth 8
...
ENGINE: bestmove P*c3
GUI:    position startpos moves a2a3 e4e3 b1b2+ d5d4 P*c3
GUI:    go depth 8
...
ENGINE: bestmove S*b4
GUI:    quit
```

### 10.3 Gomoku: Placement Game

```
GUI:    ubgi
ENGINE: id name Gomoku
ENGINE: id author Gomoku Team
ENGINE: option name GameName type string default Gomoku
ENGINE: option name BoardWidth type spin default 9 min 1 max 26
ENGINE: option name BoardHeight type spin default 9 min 1 max 26
ENGINE: option name Algorithm type combo default pvs var pvs var alphabeta var minimax var random
ENGINE: ubgiok
GUI:    isready
ENGINE: readyok
GUI:    position startpos
GUI:    go depth 6
ENGINE: info depth 6 seldepth 6 score cp 500 nodes 12000 time 50 nps 240000 pv e5
ENGINE: bestmove e5
GUI:    position startpos moves e5 d4
GUI:    go depth 6
ENGINE: info depth 6 seldepth 6 score cp 300 nodes 15000 time 60 nps 250000 pv e4
ENGINE: bestmove e4
GUI:    quit
```

### 10.4 Analysis with Board Position

```
GUI:    ubgi
ENGINE: id name MiniChess
...
ENGINE: ubgiok
GUI:    isready
ENGINE: readyok
GUI:    position board kqbnr/ppppp/...../...../PPPPP/RNBQK 0 moves a2a3
GUI:    go depth 8
ENGINE: info depth 1 seldepth 1 score cp -5 nodes 25 time 0 nps 0 currmove e5e4 currmovenumber 1
...
ENGINE: info depth 8 seldepth 14 score cp -12 nodes 320000 time 800 nps 400000 pv e5e4 b1c3 d5d4
ENGINE: bestmove e5e4
GUI:    quit
```

### 10.5 Changing Algorithm Mid-Session

```
GUI:    ubgi
ENGINE: id name MiniChess
...
ENGINE: ubgiok
GUI:    setoption name Algorithm value alphabeta
GUI:    setoption name UseNNUE value false
GUI:    setoption name Hash value 20
GUI:    isready
ENGINE: info string TT resized to 2^20 entries
ENGINE: readyok
GUI:    position startpos
GUI:    go depth 4
...
ENGINE: bestmove a2a3
GUI:    quit
```

### 10.6 Infinite Analysis with Stop

```
GUI:    ubgi
...
ENGINE: ubgiok
GUI:    isready
ENGINE: readyok
GUI:    position startpos
GUI:    go infinite
ENGINE: info depth 1 seldepth 1 score cp 12 nodes 30 time 0 nps 0 pv a2a3
ENGINE: info depth 2 seldepth 4 score cp 8 nodes 180 time 1 nps 180000 pv a2a3 e5e4
ENGINE: info depth 3 seldepth 6 score cp 15 nodes 900 time 5 nps 180000 pv a2a3 e5e4 b1c3
ENGINE: info depth 4 seldepth 9 score cp 10 nodes 4500 time 20 nps 225000 pv a2a3 e5e4 b1c3 d6d5
GUI:    stop
ENGINE: bestmove a2a3
```

---

## 11. Implementation Notes

### 11.1 Thread Safety

- All output (`info`, `bestmove`, etc.) is serialized through a global I/O
  mutex, so messages are never interleaved.
- The `stop` flag in `SearchContext` is an atomic boolean. The GUI thread sets
  it, and the search thread polls it periodically.
- The main thread reads commands from stdin. The search runs on a separate
  thread. A new `go` command joins the old search thread before starting a new
  one.

### 11.2 Output Buffering

The engine sets `std::cout` to unbuffered mode (`std::unitbuf`) at startup to
ensure that every line is flushed immediately. This is critical for
stdin/stdout communication with a GUI.

### 11.3 Source Files

| File | Description |
|---|---|
| `src/ubgi/ubgi.cpp` | Protocol implementation: command parsing, search dispatch, move conversion |
| `src/ubgi/ubgi.hpp` | Public API: `loop()`, `move_to_str()`, `str_to_move()`, `set_position()` |
| `gui/ubgi_client.py` | Python GUI client: `UBGIEngine` class for subprocess communication |
| `src/policy/registry.hpp` | Algorithm registry: maps algorithm names to search functions |
| `src/search_params.hpp` | `ParamMap`, `ParamDef` types and helpers |
| `src/search_types.hpp` | `SearchContext`, `SearchResult`, `RootUpdate` structs |
| `src/state/base_state.hpp` | `BaseState` interface, `Move` and `Point` type aliases |
