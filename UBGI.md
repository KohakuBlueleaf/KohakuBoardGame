# UBGI -- Universal Board Game Interface

**Version 1.0**

## Table of Contents

1. [Introduction](#1-introduction)
2. [Protocol Overview](#2-protocol-overview)
3. [Move Format](#3-move-format)
4. [Command Reference](#4-command-reference)
5. [Option Types](#5-option-types)
6. [Game Description Options](#6-game-description-options)
7. [Example Sessions](#7-example-sessions)
8. [Differences from UCI and USI](#8-differences-from-uci-and-usi)
9. [Implementer Notes](#9-implementer-notes)

---

## 1. Introduction

### 1.1 Purpose

The Universal Board Game Interface (UBGI) is a text-based communication protocol
between a board game engine and a graphical user interface (GUI) or controller
program. It is designed to serve as a single, unified protocol for any
two-player, alternating-turn board game -- including, but not limited to, chess,
shogi, Go, gomoku, Othello/reversi, checkers, and their many variants.

### 1.2 Motivation

The UCI (Universal Chess Interface) protocol, introduced by Stefan-Meyer Kahlen
in 2000, became the de facto standard for chess engine communication. Its
simplicity -- plain text over stdin/stdout, stateless position representation,
asynchronous search -- made it far more practical to implement than its
predecessor, the xboard/WinBoard protocol.

However, UCI is specific to chess. The USI (Universal Shogi Interface) adapted
UCI for shogi, introducing drop-move syntax and minor adjustments, but created a
separate, incompatible protocol. Other games (Go, gomoku, Othello) have their
own protocols (GTP, Gomocup, NBoard), each with different conventions,
coordinate systems, and command sets.

UBGI generalizes UCI to cover any board game while preserving full backward
compatibility with the UCI command vocabulary. An engine that speaks UBGI can
describe its game through mandatory game-description options, and a
UBGI-compatible GUI can adapt its display and input handling accordingly.

### 1.3 Design Goals

- **Simplicity.** Plain text, line-based, no binary framing.
- **Generality.** A single move encoding covers piece moves, drops, placements,
  promotions, and passes for any board game.
- **UCI compatibility.** All UCI commands and conventions are preserved. A
  UCI-only GUI can drive a UBGI engine with minimal adaptation.
- **Statelessness.** The engine does not maintain hidden state between commands.
  The GUI is responsible for sending the complete position before each search.
- **Asynchronous search.** The engine searches in the background and can be
  interrupted at any time with `stop`.

### 1.4 Scope

This specification defines:
- The transport layer (stdin/stdout text protocol).
- The handshake sequence.
- The move encoding format.
- All commands in both directions (GUI to engine, engine to GUI).
- Mandatory game-description options.
- Option types and their syntax.

This specification does not define:
- Game rules, legal move generation, or win/loss/draw adjudication.
- Time control models beyond `movetime`, `depth`, and `infinite`.
- Opening book or endgame tablebase formats.
- Any wire protocol other than stdin/stdout (e.g., TCP, WebSocket).

---

## 2. Protocol Overview

### 2.1 Transport

Communication between the GUI and the engine occurs over the engine process's
standard input (stdin) and standard output (stdout). Each message is a single
line of ASCII text terminated by a newline character (`\n`). Engines SHOULD
accept `\r\n` line endings for portability on Windows. Engines MUST NOT require
`\r\n` and MUST NOT emit `\r` in their output.

Engines SHOULD set stdout to unbuffered or line-buffered mode to ensure messages
are delivered promptly. In C/C++, this is typically achieved with
`std::cout << std::unitbuf;` or `setvbuf(stdout, NULL, _IONBF, 0);`.

### 2.2 Encoding

All messages are 7-bit ASCII. Option values of type `string` MAY contain UTF-8
if both engine and GUI agree, but the protocol itself uses only ASCII.

### 2.3 Message Structure

Each line consists of a command token followed by zero or more space-separated
arguments. Leading and trailing whitespace SHOULD be ignored by the receiver.
Multiple consecutive spaces SHOULD be treated as a single separator, except
within the value portion of `setoption` and `id` commands where the full
remaining text (after the keyword) is significant.

### 2.4 Communication Model

The protocol is asymmetric:

- **GUI to engine:** The GUI sends commands. The engine processes them and may
  send responses.
- **Engine to GUI:** The engine sends responses, search information, and the
  best move. The engine MUST NOT send unsolicited output except `info` lines
  during an active search.

### 2.5 Initialization Sequence

The GUI and engine perform a handshake before any game-related commands:

1. GUI sends `ubgi`.
2. Engine responds with `id name ...`, `id author ...`, zero or more `option`
   lines, and finally `ubgiok`.
3. GUI sends zero or more `setoption` commands.
4. GUI sends `isready`.
5. Engine responds with `readyok` when it has finished all initialization.

After this sequence, the engine is ready to accept `position` and `go` commands.

### 2.6 Search Lifecycle

1. GUI sends `position ...` to set up the board.
2. GUI sends `go ...` to start a search.
3. Engine MAY send `info` lines during the search.
4. Engine sends `bestmove ...` when the search completes.
5. At any point during step 3, the GUI may send `stop`. The engine MUST finish
   promptly and send `bestmove` with the best move found so far.

The engine MUST NOT accept a new `go` command while a search is in progress. The
GUI MUST send `stop` (and wait for `bestmove`) or wait for `bestmove` before
sending another `go`.

---

## 3. Move Format

UBGI defines a universal move encoding that accommodates all common board game
actions. Coordinates use the algebraic system: a column letter (`a`-`z`)
followed by a row number (`1`-`N`), where `a1` is the bottom-left square from
player 1's perspective.

### 3.1 Board Move

A piece moves from one square to another.

```
{from}{to}
```

- `{from}` -- the origin square (column letter + row number).
- `{to}` -- the destination square (column letter + row number).

**Examples:**

| Game       | Move string | Meaning                                  |
|------------|-------------|------------------------------------------|
| Chess      | `e2e4`      | Pawn from e2 to e4                       |
| Chess      | `g1f3`      | Knight from g1 to f3                     |
| MiniChess  | `a2a3`      | Pawn from a2 to a3                       |
| Shogi      | `g7g6`      | Piece from g7 to g6                      |
| Checkers   | `c3d4`      | Piece from c3 to d4                      |

### 3.2 Board Move with Promotion

A piece moves and promotes. The promotion piece is appended as a single
character (lowercase for chess-family games) or as `+` for shogi-style
promotions.

```
{from}{to}{promotion}
```

- `{promotion}` -- a single character identifying the promotion target.

**Examples:**

| Game       | Move string | Meaning                                  |
|------------|-------------|------------------------------------------|
| Chess      | `e7e8q`     | Pawn promotes to queen on e8             |
| Chess      | `a7a8n`     | Pawn promotes to knight on a8            |
| Shogi      | `a3a4+`     | Piece promotes on reaching a4            |

For games where promotion is mandatory and unambiguous, the engine MAY omit the
promotion suffix. However, it is RECOMMENDED to always include it for clarity.

### 3.3 Drop Move

A piece from a player's hand (reserve) is placed onto an empty square. The piece
type is given as an uppercase letter, followed by `*`, followed by the
destination square.

```
{TYPE}*{to}
```

- `{TYPE}` -- an uppercase letter identifying the piece type.
- `*` -- the drop operator (literal asterisk).
- `{to}` -- the destination square.

**Examples:**

| Game       | Move string | Meaning                                  |
|------------|-------------|------------------------------------------|
| Shogi      | `P*c3`      | Drop a pawn on c3                        |
| Shogi      | `B*e5`      | Drop a bishop on e5                      |
| Crazyhouse | `N*f6`      | Drop a knight on f6                      |

### 3.4 Place Move

A stone or piece is placed on an empty square with no origin. This is used in
games where pieces are placed from an unlimited supply (not from a hand with
tracked inventory).

```
{to}
```

- `{to}` -- the destination square.

**Examples:**

| Game       | Move string | Meaning                                  |
|------------|-------------|------------------------------------------|
| Gomoku     | `h8`        | Place stone on h8                        |
| Go (19x19) | `q16`       | Place stone on q16                       |
| Othello    | `d3`        | Place disc on d3                         |
| Connect 4  | `d1`        | Drop piece in column d (row 1 = bottom)  |

### 3.5 Pass

The active player passes their turn without making a move.

```
pass
```

**Examples:**

| Game       | Move string | Meaning                                  |
|------------|-------------|------------------------------------------|
| Go         | `pass`      | Player passes                            |
| Othello    | `pass`      | Player passes (no legal moves)           |

### 3.6 Null Move

A placeholder indicating no real move. Used in search (null-move pruning) and as
a sentinel value when no move is available.

```
0000
```

This is a four-character string of ASCII zeros. It MUST NOT appear in a
`position ... moves ...` sequence. It is valid only as a `bestmove` response
when the engine has no legal move to return.

### 3.7 Coordinate System

Columns are labeled with lowercase letters: `a`, `b`, `c`, ..., `z`. This
supports boards up to 26 columns wide.

Rows are labeled with decimal integers starting at `1`. Row `1` is the bottom
row from player 1's perspective. This supports boards of arbitrary height.

The square at column `a`, row `1` is written `a1`. The square at column `e`,
row `8` is written `e8`.

For games where the board orientation has no canonical "bottom" (e.g., Go),
`a1` is defined as the bottom-left corner when the board is displayed with
player 1 (Black in Go convention) making the first move.

---

## 4. Command Reference

### 4.1 GUI to Engine

#### 4.1.1 `ubgi`

Initiates the UBGI handshake. The engine MUST respond with identification lines
and option advertisements, followed by `ubgiok`.

```
ubgi
```

The engine MUST respond with the following sequence:

```
id name <engine name>
id author <author name>
option name <name> type <type> ...
...
ubgiok
```

The `id` and `option` lines may appear in any order, but `ubgiok` MUST be the
last line of the handshake response. The engine MUST advertise the mandatory
game-description options (see Section 6).

For backward compatibility, engines MAY also accept `uci` as an alias for
`ubgi`. In that case, the engine SHOULD respond with `uciok` instead of
`ubgiok`. An engine that supports both protocols SHOULD detect which command was
sent and respond accordingly.

#### 4.1.2 `isready`

Synchronization command. The GUI sends `isready` and waits for `readyok`. The
engine MUST NOT send `readyok` until all pending initialization (option changes,
new game setup, NNUE weight loading, etc.) is complete.

```
isready
```

Response:

```
readyok
```

This command may be sent at any time, including during a search. It does not
interrupt the search. It is a ping/pong mechanism to verify the engine is alive
and has processed all preceding commands.

#### 4.1.3 `setoption`

Sets an engine option. The GUI sends this after the handshake (before or after
`isready`) and before starting a search.

```
setoption name <name> [value <value>]
```

- `<name>` -- the option name as advertised in the handshake. Case-sensitive.
- `<value>` -- the new value. Omitted for button-type options (not currently
  defined in UBGI).

The `name` and `value` tokens are delimited by the literal keywords `name` and
`value`. The option name is everything between `name` and `value` (or end of
line if `value` is absent). The option value is everything after `value` to the
end of the line. This allows spaces in both names and values.

**Examples:**

```
setoption name Hash value 18
setoption name Algorithm value pvs
setoption name NNUEFile value models/nnue_v1.bin
setoption name UseNNUE value true
```

#### 4.1.4 `ubginewgame`

Informs the engine that the next position will be from a new game. The engine
SHOULD clear any game-specific state (transposition table, history heuristics,
etc.).

```
ubginewgame
```

For backward compatibility, `ucinewgame` is accepted as an alias with identical
semantics.

#### 4.1.5 `position`

Sets the current board position.

```
position startpos [moves <move1> <move2> ...]
```

- `startpos` -- the standard starting position for the game.
- `moves` -- optional sequence of moves from the starting position. Each move
  uses the encoding defined in Section 3.

The engine replays the given moves from the starting position to arrive at the
current board state. The engine does not validate move legality -- the GUI is
responsible for sending only legal moves.

**Examples:**

```
position startpos
position startpos moves e2e4 e7e5 g1f3
position startpos moves a2a3 e5e4 b1b2
```

Future extensions MAY define `position fen <fen-string>` or
`position sfen <sfen-string>` for game-specific position encodings.

#### 4.1.6 `go`

Starts a search on the current position. The engine searches asynchronously and
sends `info` lines during the search, followed by `bestmove` when finished.

```
go [depth <N>] [movetime <N>] [infinite] [nodes <N>]
```

- `depth <N>` -- search to exactly N plies.
- `movetime <N>` -- search for approximately N milliseconds.
- `nodes <N>` -- search approximately N nodes (soft limit).
- `infinite` -- search until `stop` is received.

If none of these are specified, the engine uses a reasonable default (typically
a fixed depth or time).

Only one search may be active at a time. The GUI MUST wait for `bestmove` (or
send `stop` and then wait for `bestmove`) before issuing another `go`.

#### 4.1.7 `stop`

Interrupts the current search. The engine MUST stop searching as soon as
possible and send `bestmove` with the best move found so far.

```
stop
```

If no search is in progress, this command is silently ignored.

#### 4.1.8 `d`

Debug display command. The engine prints a human-readable representation of the
current board position to stdout. The output format is engine-defined and
intended for debugging only. GUIs SHOULD NOT parse this output.

```
d
```

#### 4.1.9 `quit`

Terminates the engine process. The engine MUST exit as soon as possible. If a
search is in progress, it is abandoned without sending `bestmove`.

```
quit
```

### 4.2 Engine to GUI

#### 4.2.1 `id`

Identifies the engine. Sent during the handshake, before `ubgiok`.

```
id name <engine name>
id author <author name>
```

Both `name` and `author` are REQUIRED. The value is the remainder of the line
after the keyword.

**Examples:**

```
id name MiniChess 1.0
id author MiniChess Team
```

#### 4.2.2 `ubgiok`

Signals the end of the handshake. Sent after all `id` and `option` lines.

```
ubgiok
```

For backward compatibility, engines responding to `uci` (not `ubgi`) SHOULD
send `uciok` instead.

#### 4.2.3 `readyok`

Response to `isready`. Indicates that the engine has processed all preceding
commands and is ready.

```
readyok
```

#### 4.2.4 `option`

Advertises a configurable engine option. Sent during the handshake between `id`
lines and `ubgiok`.

```
option name <name> type <type> [default <value>] [min <value>] [max <value>] [var <value> ...]
```

See Section 5 for the full specification of option types and their parameters.

#### 4.2.5 `bestmove`

Reports the engine's chosen move after a search completes.

```
bestmove <move>
```

- `<move>` -- the best move in UBGI move format (Section 3).

The engine MUST send exactly one `bestmove` per `go` command. After sending
`bestmove`, the engine returns to the idle state and awaits the next command.

**Examples:**

```
bestmove e2e4
bestmove a7a8q
bestmove P*c3
bestmove h8
bestmove pass
bestmove 0000
```

#### 4.2.6 `info`

Reports search progress. Sent during an active search, before `bestmove`. All
fields are optional; the engine includes whichever are available.

```
info [depth <N>] [seldepth <N>] [score cp <N>] [score mate <N>] [nodes <N>] [time <N>] [nps <N>] [pv <move1> <move2> ...] [currmove <move>] [currmovenumber <N>] [string <text>]
```

**Fields:**

| Field            | Type    | Description                                        |
|------------------|---------|----------------------------------------------------|
| `depth`          | integer | Search depth in plies                              |
| `seldepth`       | integer | Selective (maximum) depth reached                  |
| `score cp`       | integer | Score in centipawns from the engine's perspective   |
| `score mate`     | integer | Mate in N moves (positive = engine mates, negative = engine is mated) |
| `nodes`          | integer | Total nodes searched                               |
| `time`           | integer | Search time in milliseconds                        |
| `nps`            | integer | Nodes per second                                   |
| `pv`             | moves   | Principal variation (sequence of moves)             |
| `currmove`       | move    | Currently searching this move at the root           |
| `currmovenumber` | integer | Index of the current root move (1-based)            |
| `string`         | text    | Arbitrary debug/status text (rest of line)          |

The `score cp` value is from the perspective of the side to move. Positive means
the side to move is winning. For games without a natural centipawn scale, the
engine defines its own scoring unit and documents the scale in its `info string`
output or external documentation.

**Examples:**

```
info depth 6 seldepth 9 score cp 35 nodes 48201 time 120 nps 401675 pv e2e4 e7e5 g1f3
info depth 4 seldepth 6 score cp -15 nodes 3201 time 45 nps 71133
info currmove d2d4 currmovenumber 3 score cp 28
info string NNUE evaluation enabled
```

---

## 5. Option Types

Options advertised during the handshake use one of the following types. The GUI
uses the type information to render an appropriate input control.

### 5.1 `check`

A boolean option. Values are `true` or `false`.

```
option name <name> type check default <true|false>
```

**Example:**

```
option name UseNNUE type check default true
```

### 5.2 `spin`

An integer option with minimum and maximum bounds.

```
option name <name> type spin default <N> min <N> max <N>
```

The GUI SHOULD enforce the min/max bounds. The engine MAY clamp out-of-range
values silently.

**Example:**

```
option name Hash type spin default 18 min 10 max 24
option name BoardWidth type spin default 5 min 1 max 26
```

### 5.3 `combo`

An enumeration option. The GUI presents a dropdown list of predefined values.

```
option name <name> type combo default <value> var <value1> var <value2> ...
```

Each `var` keyword introduces one legal value. The default MUST be one of the
listed variants.

**Example:**

```
option name Algorithm type combo default pvs var pvs var alphabeta var minimax var random
```

### 5.4 `string`

A free-form text option.

```
option name <name> type string default <value>
```

The default value is the remainder of the line after `default`. An empty default
is represented by `default` followed by nothing (or by the literal `<empty>`).

**Example:**

```
option name NNUEFile type string default models/nnue_v1.bin
option name GameName type string default MiniChess
```

---

## 6. Game Description Options

UBGI extends UCI with mandatory game-description options that allow the engine to
describe the board game it plays. The engine MUST advertise these options during
the handshake. The GUI uses this information to configure its display, coordinate
system, and input handling.

### 6.1 Required Game Description Options

#### `GameName`

The human-readable name of the game.

```
option name GameName type string default MiniChess
```

#### `BoardWidth`

The number of columns on the board.

```
option name BoardWidth type spin default 5 min 1 max 26
```

The maximum of 26 corresponds to the column letters `a` through `z`.

#### `BoardHeight`

The number of rows on the board.

```
option name BoardHeight type spin default 6 min 1 max 26
```

#### `PieceTypes`

The number of distinct piece types used in the game. This informs the GUI how
many different piece kinds exist (e.g., chess has 6: pawn, rook, knight, bishop,
queen, king).

```
option name PieceTypes type spin default 6 min 1 max 32
```

### 6.2 Optional Game Description Options

Engines MAY advertise additional game-description options to provide richer
metadata. These are not required by the protocol but are RECOMMENDED where
applicable.

#### `Players`

The number of players. Default is 2.

```
option name Players type spin default 2 min 2 max 2
```

#### `MaxMoves`

The maximum number of half-moves (plies) before the game is drawn. A value of 0
means no limit.

```
option name MaxMoves type spin default 100 min 0 max 10000
```

#### `HasDrops`

Whether the game supports drop moves (e.g., shogi, crazyhouse).

```
option name HasDrops type check default false
```

#### `HasPasses`

Whether the game allows pass moves (e.g., Go, Othello).

```
option name HasPasses type check default false
```

### 6.3 Semantics

Game-description options are **informational**. The GUI reads them to adapt its
rendering and input but SHOULD NOT send `setoption` to change them unless the
engine explicitly supports reconfiguration (e.g., a multi-game engine that can
switch between games at runtime).

If the GUI sends `setoption name GameName value Shogi`, and the engine supports
it, the engine reconfigures for that game. If the engine does not support
reconfiguration, it SHOULD ignore the command or respond with
`info string ERROR: game change not supported`.

---

## 7. Example Sessions

### 7.1 MiniChess (5x6 board, chess variant)

```
[GUI]    ubgi
[ENGINE] id name MiniChess 1.0
[ENGINE] id author MiniChess Team
[ENGINE] option name GameName type string default MiniChess
[ENGINE] option name BoardWidth type spin default 5 min 1 max 26
[ENGINE] option name BoardHeight type spin default 6 min 1 max 26
[ENGINE] option name PieceTypes type spin default 6 min 1 max 32
[ENGINE] option name Algorithm type combo default pvs var pvs var alphabeta var minimax var random
[ENGINE] option name Hash type spin default 18 min 10 max 24
[ENGINE] option name UseNNUE type check default true
[ENGINE] option name NNUEFile type string default models/nnue_v1.bin
[ENGINE] ubgiok

[GUI]    setoption name Algorithm value pvs
[GUI]    setoption name UseNNUE value true
[GUI]    isready
[ENGINE] readyok

[GUI]    ubginewgame
[GUI]    position startpos
[GUI]    go depth 6
[ENGINE] info depth 1 seldepth 1 score cp 12 nodes 30 time 0 nps 0
[ENGINE] info depth 2 seldepth 3 score cp 8 nodes 187 time 1 nps 187000
[ENGINE] info depth 3 seldepth 5 score cp 15 nodes 892 time 3 nps 297333
[ENGINE] info depth 4 seldepth 7 score cp 10 nodes 4201 time 12 nps 350083
[ENGINE] info depth 5 seldepth 8 score cp 18 nodes 18340 time 48 nps 381666
[ENGINE] info depth 6 seldepth 9 score cp 14 nodes 48201 time 120 nps 401675 pv a2a3 e5e4 b1b2
[ENGINE] bestmove a2a3

[GUI]    position startpos moves a2a3
[GUI]    go movetime 2000
[ENGINE] info depth 1 seldepth 1 score cp -8 nodes 28 time 0 nps 0
[ENGINE] info depth 2 seldepth 3 score cp -12 nodes 165 time 1 nps 165000
...
[ENGINE] info depth 8 seldepth 12 score cp -14 nodes 312440 time 1850 nps 168886 pv e5e4 b1b2
[ENGINE] bestmove e5e4

[GUI]    quit
```

### 7.2 Standard Chess (8x8)

```
[GUI]    ubgi
[ENGINE] id name DeepEngine 4.2
[ENGINE] id author J. Developer
[ENGINE] option name GameName type string default Chess
[ENGINE] option name BoardWidth type spin default 8 min 1 max 26
[ENGINE] option name BoardHeight type spin default 8 min 1 max 26
[ENGINE] option name PieceTypes type spin default 6 min 1 max 32
[ENGINE] option name Hash type spin default 256 min 1 max 4096
[ENGINE] ubgiok

[GUI]    isready
[ENGINE] readyok

[GUI]    ubginewgame
[GUI]    position startpos
[GUI]    go movetime 5000
[ENGINE] info depth 1 seldepth 1 score cp 20 nodes 20 time 0 nps 0
...
[ENGINE] info depth 18 seldepth 24 score cp 35 nodes 14230120 time 4800 nps 2964608 pv e2e4 e7e5 g1f3 b8c6 f1b5
[ENGINE] bestmove e2e4

[GUI]    position startpos moves e2e4 e7e5
[GUI]    go movetime 5000
...
[ENGINE] bestmove g1f3

[GUI]    quit
```

### 7.3 Shogi (9x9, with drops)

```
[GUI]    ubgi
[ENGINE] id name ShogiMaster 2.0
[ENGINE] id author K. Author
[ENGINE] option name GameName type string default Shogi
[ENGINE] option name BoardWidth type spin default 9 min 1 max 26
[ENGINE] option name BoardHeight type spin default 9 min 1 max 26
[ENGINE] option name PieceTypes type spin default 8 min 1 max 32
[ENGINE] option name HasDrops type check default true
[ENGINE] ubgiok

[GUI]    isready
[ENGINE] readyok

[GUI]    ubginewgame
[GUI]    position startpos
[GUI]    go depth 8
...
[ENGINE] info depth 8 seldepth 14 score cp 45 nodes 890000 time 3200 nps 278125 pv g7g6 c3c4
[ENGINE] bestmove g7g6

[GUI]    position startpos moves g7g6 c3c4 b8d7
[GUI]    go depth 8
...
[ENGINE] bestmove P*c3

[GUI]    quit
```

### 7.4 Gomoku (15x15, placement only)

```
[GUI]    ubgi
[ENGINE] id name GomokuAI 1.0
[ENGINE] id author A. Researcher
[ENGINE] option name GameName type string default Gomoku
[ENGINE] option name BoardWidth type spin default 15 min 1 max 26
[ENGINE] option name BoardHeight type spin default 15 min 1 max 26
[ENGINE] option name PieceTypes type spin default 1 min 1 max 32
[ENGINE] option name HasPasses type check default false
[ENGINE] ubgiok

[GUI]    isready
[ENGINE] readyok

[GUI]    ubginewgame
[GUI]    position startpos
[GUI]    go movetime 5000
[ENGINE] info depth 10 score cp 15 nodes 2400000 time 4500 nps 533333
[ENGINE] bestmove h8

[GUI]    position startpos moves h8
[GUI]    go movetime 5000
[ENGINE] info depth 12 score cp -5 nodes 3100000 time 4800 nps 645833
[ENGINE] bestmove h7

[GUI]    position startpos moves h8 h7 g8
[GUI]    go movetime 5000
...
[ENGINE] bestmove i9

[GUI]    quit
```

### 7.5 Go (19x19, with passes)

```
[GUI]    ubgi
[ENGINE] id name GoZero 3.0
[ENGINE] id author B. Scientist
[ENGINE] option name GameName type string default Go
[ENGINE] option name BoardWidth type spin default 19 min 1 max 26
[ENGINE] option name BoardHeight type spin default 19 min 1 max 26
[ENGINE] option name PieceTypes type spin default 1 min 1 max 32
[ENGINE] option name HasPasses type check default true
[ENGINE] option name Komi type string default 6.5
[ENGINE] ubgiok

[GUI]    isready
[ENGINE] readyok

[GUI]    ubginewgame
[GUI]    position startpos
[GUI]    go movetime 10000
[ENGINE] info depth 1 score cp 50 nodes 80000 time 2000 nps 40000
...
[ENGINE] bestmove q16

[GUI]    position startpos moves q16 d4 q4 d16
[GUI]    go movetime 10000
...
[ENGINE] bestmove c17

...

[GUI]    position startpos moves q16 d4 q4 d16 c17 ... pass
[GUI]    go movetime 10000
[ENGINE] bestmove pass

[GUI]    quit
```

### 7.6 Othello (8x8, with forced passes)

```
[GUI]    ubgi
[ENGINE] id name OthelloEngine 1.5
[ENGINE] id author C. Programmer
[ENGINE] option name GameName type string default Othello
[ENGINE] option name BoardWidth type spin default 8 min 1 max 26
[ENGINE] option name BoardHeight type spin default 8 min 1 max 26
[ENGINE] option name PieceTypes type spin default 1 min 1 max 32
[ENGINE] option name HasPasses type check default true
[ENGINE] ubgiok

[GUI]    isready
[ENGINE] readyok

[GUI]    ubginewgame
[GUI]    position startpos
[GUI]    go depth 12
[ENGINE] info depth 12 seldepth 20 score cp 3 nodes 5000000 time 800 nps 6250000
[ENGINE] bestmove d3

[GUI]    position startpos moves d3 c5 d6
[GUI]    go depth 12
...
[ENGINE] bestmove pass

[GUI]    quit
```

---

## 8. Differences from UCI and USI

### 8.1 Differences from UCI (Universal Chess Interface)

| Aspect                | UCI                  | UBGI                                      |
|-----------------------|----------------------|-------------------------------------------|
| Handshake command     | `uci`                | `ubgi` (also accepts `uci`)               |
| Handshake response    | `uciok`              | `ubgiok` (also accepts `uciok`)           |
| New game command      | `ucinewgame`         | `ubginewgame` (also accepts `ucinewgame`) |
| Move format           | Chess-specific       | Universal (see Section 3)                 |
| Game description      | None (chess assumed) | Mandatory game-description options         |
| Drop moves            | Not supported        | `{TYPE}*{to}` syntax                      |
| Place moves           | Not supported        | `{to}` syntax (single square)             |
| Pass moves            | Not supported        | `pass`                                    |
| Board size            | Fixed 8x8            | Variable, up to 26x26                     |
| Coordinate system     | a-h, 1-8             | a-z, 1-N                                  |
| `position fen`        | Supported            | Game-specific; not required                |
| Time control          | Full chess clock     | `movetime`, `depth`, `infinite`, `nodes`  |
| `go wtime/btime/...`  | Supported            | Reserved for future extension              |

UBGI intentionally omits UCI's full chess clock model (`wtime`, `btime`, `winc`,
`binc`, `movestogo`) from the base specification. These are chess-specific
parameters that do not generalize cleanly. Engines MAY support them as
extensions. A future version of UBGI may define a generalized time control
model.

### 8.2 Differences from USI (Universal Shogi Interface)

| Aspect                | USI                  | UBGI                                      |
|-----------------------|----------------------|-------------------------------------------|
| Handshake command     | `usi`                | `ubgi`                                    |
| Handshake response    | `usiok`              | `ubgiok`                                  |
| New game command      | `usinewgame`         | `ubginewgame`                             |
| Move format           | Shogi-specific       | Universal (compatible with USI moves)     |
| Position command      | `position startpos`  | Same                                      |
| SFEN support          | `position sfen ...`  | Reserved for future extension             |
| Drop notation         | `P*5e` (USI coords)  | `P*e5` (algebraic coords)                |
| Coordinate system     | Column 1-9, row a-i  | Column a-z, row 1-N                       |
| Game description      | None (shogi assumed) | Mandatory game-description options         |

The primary coordinate difference from USI is that UBGI uses algebraic notation
(letter columns, numeric rows) rather than USI's numeric columns and letter
rows. Engines bridging between UBGI and USI must transpose accordingly.

### 8.3 Backward Compatibility

A UBGI engine can be driven by a standard UCI GUI with the following constraints:

- The GUI sends `uci`; the engine responds with `uciok`.
- The GUI ignores unrecognized options (the game-description options).
- The move format for chess is identical to UCI (`e2e4`, `e7e8q`).
- All standard UCI commands (`position`, `go`, `stop`, `quit`, `isready`,
  `setoption`) work identically.

A UBGI GUI can drive a standard UCI engine by:

- Sending `ubgi` (a UCI engine will not recognize it and will not respond).
- Falling back to `uci` if `ubgiok` is not received within a timeout.
- Assuming `GameName=Chess`, `BoardWidth=8`, `BoardHeight=8`, `PieceTypes=6`
  when driving a UCI engine.

---

## 9. Implementer Notes

### 9.1 Engine Implementation

#### Buffering

Engines MUST flush stdout after every line. Failure to do so will cause the GUI
to hang waiting for output that is sitting in a buffer. In C++:

```cpp
std::cout << std::unitbuf;  // auto-flush after every insertion
```

Or flush explicitly:

```cpp
std::cout << "bestmove e2e4" << std::endl;  // endl flushes
```

#### Thread Safety

The search typically runs in a background thread. The `stop` command may arrive
at any time. Engines SHOULD use an atomic flag to signal the search thread:

```cpp
std::atomic<bool> stop_flag{false};
```

The search thread checks `stop_flag` periodically (e.g., every N nodes) and
exits promptly when set. The main thread sets `stop_flag = true` upon receiving
`stop` or `quit`.

#### Move Generation

The engine is solely responsible for game rules and legal move generation. UBGI
does not validate moves. The engine SHOULD trust that the GUI sends legal moves
in the `position` command but MAY validate them and respond with
`info string ERROR: illegal move <move>` if validation fails.

#### Score Units

The `score cp` value uses centipawns as the conventional unit for chess-family
games. For games without a natural material scale:

- **Go:** Score in tenths of a point (1 cp = 0.1 point).
- **Gomoku/Othello:** Engine-defined scale; document in engine README.
- The engine MAY use `info string` to describe its scoring convention.

The sign convention is always from the perspective of the side to move: positive
means the side to move is ahead.

### 9.2 GUI Implementation

#### Handshake with Fallback

A robust GUI should support both UBGI and legacy UCI/USI engines:

1. Send `ubgi` and wait up to 2 seconds for `ubgiok`.
2. If no response, send `uci` and wait for `uciok`.
3. If `uciok` is received, assume chess defaults for game-description options.
4. If neither responds, report an error.

#### Coordinate Mapping

The GUI receives `BoardWidth` and `BoardHeight` from the engine. It MUST map
column letters `a` through `chr('a' + BoardWidth - 1)` and row numbers `1`
through `BoardHeight`. For display, row 1 is at the bottom for player 1.

#### Parsing Move Formats

The GUI must distinguish between move types by their structure:

| Pattern                   | Move Type              |
|---------------------------|------------------------|
| `pass`                    | Pass                   |
| `0000`                    | Null move              |
| `[A-Z]\*[a-z][0-9]+`     | Drop move              |
| `[a-z][0-9]+`             | Place move (2-3 chars) |
| `[a-z][0-9]+[a-z][0-9]+` | Board move (4+ chars)  |
| `[a-z][0-9]+[a-z][0-9]+[a-z+]` | Board move with promotion |

A simple heuristic: if the second character is `*`, it is a drop. If the string
is exactly `pass` or `0000`, handle as special cases. If the string length is
2 or 3 and starts with a lowercase letter, it is a place move. Otherwise, it is
a board move, optionally followed by a promotion character.

#### Handling Unknown Options

The GUI SHOULD silently ignore `option` lines with unrecognized names. This
ensures forward compatibility as new optional game-description options are added
in future UBGI versions.

### 9.3 Protocol Extensions

Engines and GUIs MAY agree on protocol extensions through custom option names
prefixed with `X-` (e.g., `option name X-Pondering type check default false`).
Standard UBGI options MUST NOT use the `X-` prefix. This convention prevents
collisions between custom extensions and future standard options.

### 9.4 Error Handling

UBGI does not define a formal error reporting mechanism. Engines SHOULD use
`info string ERROR: <description>` to report errors to the GUI. The GUI SHOULD
display such messages to the user but MUST NOT parse them programmatically for
control flow.

If the engine receives an unrecognized command, it SHOULD silently ignore it.
This allows forward compatibility: a newer GUI can send commands that an older
engine does not understand without causing a crash.

### 9.5 Multiple Game Support

An engine MAY support multiple games. It advertises the default game in the
handshake and lists alternatives via a combo option:

```
option name GameName type combo default MiniChess var MiniChess var Chess var Shogi
```

The GUI switches games with:

```
setoption name GameName value Shogi
isready
```

After `readyok`, the engine has reconfigured. The GUI SHOULD re-read the game-
description options (by issuing `ubgi` again or caching the combo values) to
update its display. Alternatively, the engine MAY re-send updated option values
as `info string` messages after the game switch.

---

*End of specification.*
