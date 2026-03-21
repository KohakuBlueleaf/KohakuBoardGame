# Game System Architecture

This document describes the architecture of the multi-game engine framework.
The same search algorithms, UBGI protocol layer, and infrastructure support
multiple two-player zero-sum board games with no game-specific knowledge in
the shared layers.

Currently implemented games: **MiniChess** (6x5), **MiniShogi** (5x5), and
**Gomoku** (9x9).

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [The State Interface](#2-the-state-interface)
3. [Board Representation](#3-board-representation)
4. [Move Representation](#4-move-representation)
5. [Evaluation System](#5-evaluation-system)
6. [NNUE Feature Extraction](#6-nnue-feature-extraction)
7. [Zobrist Hashing](#7-zobrist-hashing)
8. [Repetition Detection](#8-repetition-detection)
9. [Game-Over Conditions](#9-game-over-conditions)
10. [How to Add a New Game](#10-how-to-add-a-new-game)

---

## 1. Architecture Overview

The engine is organized in three layers: a game-agnostic shared core, a
per-game `State` implementation, and front-end interfaces (UBGI protocol,
GUI, CLI).

```
+--------------------------------------------------+
|           Front-ends (UBGI, GUI, CLI)             |
+--------------------------------------------------+
          |                          |
          v                          v
+-------------------+    +---------------------+
| Search Algorithms |    | NNUE Forward Pass   |
| (PVS, AlphaBeta,  |    | (game-agnostic;     |
|  MiniMax, Random)  |    |  receives feature   |
|                    |    |  indices from State) |
+-------------------+    +---------------------+
          |                          |
          v                          v
+--------------------------------------------------+
|              BaseState (abstract class)           |
|    next_state, get_legal_actions, evaluate,       |
|    hash, encode_board, extract_nnue_features ...  |
+--------------------------------------------------+
     ^              ^              ^
     |              |              |
+---------+   +-----------+   +--------+
|MiniChess|   | MiniShogi |   | Gomoku |
| State   |   |   State   |   | State  |
+---------+   +-----------+   +--------+
```

### BaseState Abstract Class

All game implementations derive from `BaseState` (`src/state/base_state.hpp`).
Search algorithms, the UBGI layer, and selfplay interact **only** through
this interface. No search algorithm inspects the board array, checks piece
types, or uses coordinate geometry directly.

### Per-Game Directory Structure

Each game lives in its own directory under `src/games/`:

```
src/games/{game}/
    config.hpp    -- BOARD_H, BOARD_W, piece types, game-specific constants
    state.hpp     -- Board class, State class (inherits BaseState)
    state.cpp     -- implementation of all virtual methods
```

### Compile-Time Game Selection

Because each game directory contains `config.hpp` and `state.hpp` with
identical file names, the `-I` include flag selects the correct game at
compile time. Shared code (`ubgi.cpp`, `pvs.cpp`, etc.) writes
`#include "state.hpp"` and `#include "config.hpp"` without a path prefix,
and the preprocessor resolves them to whichever game's directory appears
first in the include path.

```makefile
MINICHESS_INC = -Isrc/games/minichess -Isrc/state -Isrc
GOMOKU_INC    = -Isrc/games/gomoku    -Isrc/state -Isrc
MINISHOGI_INC = -Isrc/games/minishogi -Isrc/state -Isrc
```

Each game compiles into a separate binary:

```makefile
minichess:
    $(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o build/minichess-ubgi \
        src/games/minichess/state.cpp src/nnue/nnue.cpp \
        src/policy/*.cpp src/ubgi/ubgi.cpp

gomoku:
    $(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o build/gomoku-ubgi \
        src/games/gomoku/state.cpp src/nnue/nnue.cpp \
        src/policy/*.cpp src/ubgi/ubgi.cpp

minishogi:
    $(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o build/minishogi-ubgi \
        src/games/minishogi/state.cpp src/nnue/nnue.cpp \
        src/policy/*.cpp src/ubgi/ubgi.cpp
```

---

## 2. The State Interface

### Type Aliases

```cpp
typedef std::pair<size_t, size_t> Point;   // (row, col)
typedef std::pair<Point, Point>   Move;    // (from, to)
```

### GameState Enum

```cpp
enum GameState { UNKNOWN = 0, WIN, DRAW, NONE };
```

| Value     | Meaning |
|-----------|---------|
| `UNKNOWN` | `get_legal_actions()` has not been called yet. |
| `WIN`     | The current player can capture the opponent's king (chess/shogi), or the previous player completed a winning line (gomoku). |
| `DRAW`    | Game drawn (repetition, step limit, or board full). |
| `NONE`    | Game is still in progress. |

### Score Bounds

```cpp
constexpr int P_MAX = 100000;    // winning score
constexpr int M_MAX = -100000;   // losing score
```

### BaseState Class

```cpp
class BaseState {
public:
    int player = 0;                        // Side to move: 0 or 1
    GameState game_state = UNKNOWN;
    std::vector<Move> legal_actions;
    std::unordered_map<uint64_t, int> hash_counts;  // position hash -> count

    virtual ~BaseState() = default;

    // --- History management ---
    void inherit_history(const BaseState* parent);
    bool check_repetition(int limit = 4) const;

    // --- Core game mechanics (pure virtual) ---
    virtual BaseState* next_state(const Move& m) = 0;
    virtual void get_legal_actions() = 0;
    virtual int evaluate(bool use_nnue = true, bool use_kp = true,
                         bool use_mobility = true) = 0;

    // --- Game description (pure virtual) ---
    virtual int board_h() const = 0;
    virtual int board_w() const = 0;
    virtual const char* game_name() const = 0;

    // --- Board serialization (pure virtual) ---
    virtual std::string encode_board() const = 0;
    virtual void decode_board(const std::string& s, int side_to_move) = 0;
    virtual std::string encode_output() const = 0;

    // --- Optional overrides (have default implementations) ---
    virtual BaseState* create_null_state() const;         // default: nullptr
    virtual int piece_at(int player, int row, int col) const; // default: 0
    virtual uint64_t hash() const;                        // default: 0
    virtual std::string cell_display(int row, int col) const; // default: " . "
    virtual int hand_count(int player, int piece_type) const; // default: 0
    virtual int num_hand_types() const;                   // default: 0
    virtual int extract_nnue_features(int perspective, int* features) const;
};
```

### Method Contracts

| Method | Contract |
|--------|----------|
| `next_state(m)` | Returns a **heap-allocated** successor. Caller owns the pointer and must `delete`. Calls `inherit_history()` and usually `get_legal_actions()`. |
| `get_legal_actions()` | Populates `legal_actions` and sets `game_state`. Must be called before inspecting legal moves or terminal status. |
| `evaluate(...)` | Returns an integer score from the **current player's** perspective. `P_MAX` = current player wins. Three boolean flags toggle NNUE, KP (material + PST + tropism), and mobility components. |
| `hash()` | Returns a Zobrist hash for the transposition table. |
| `create_null_state()` | Returns a state with side-to-move flipped (for null-move pruning). Returns `nullptr` for games that do not support it (e.g., Gomoku). |
| `piece_at(p, r, c)` | Returns the piece type at `(r, c)` for player `p`. Used by move ordering (MVV-LVA). |
| `encode_board()` / `decode_board()` | Serialize/deserialize the board for the UBGI `position board` command. |
| `encode_output()` | Returns a human-readable string representation of the board. |
| `hand_count(p, pt)` | Returns how many pieces of type `pt` player `p` holds in hand (shogi drops). |
| `extract_nnue_features(perspective, features)` | Writes active feature indices into `features[]` and returns the count. Game-specific; see section 6. |
| `inherit_history(parent)` | Copies the parent's `hash_counts` map and increments the parent's position hash count. Called inside `next_state()`. |
| `check_repetition(limit)` | Returns `true` if the current position has appeared `>= limit` times (default 4). |

---

## 3. Board Representation

### MiniChess (6x5) -- Two-Plane Board

```
src/games/minichess/config.hpp:  BOARD_H=6, BOARD_W=5
```

```cpp
class Board {
public:
    char board[2][BOARD_H][BOARD_W];  // board[player][row][col]
};
```

Two separate planes, one per player. Each cell stores a piece-type integer:

| Value | Piece  |
|-------|--------|
| 0     | Empty  |
| 1     | Pawn   |
| 2     | Rook   |
| 3     | Knight |
| 4     | Bishop |
| 5     | Queen  |
| 6     | King   |

Initial position (player 0 = White, bottom rows; player 1 = Black, top rows):

```
Player 1:  R(6) B(5) K(4) N(3) Q(2)    row 0
           P(1) P(1) P(1) P(1) P(1)    row 1
           .    .    .    .    .        row 2
           .    .    .    .    .        row 3
Player 0:  P(1) P(1) P(1) P(1) P(1)    row 4
           R(2) N(3) B(4) Q(5) K(6)    row 5
```

### MiniShogi (5x5) -- Two-Plane Board with Hand

```
src/games/minishogi/config.hpp:  BOARD_H=5, BOARD_W=5
```

```cpp
class Board {
public:
    char board[2][BOARD_H][BOARD_W];   // board[player][row][col]
    char hand[2][NUM_HAND_TYPES + 1];  // hand[player][piece_type] = count
};
```

Same two-plane structure as MiniChess, but with 11 piece types (6 base + 4
promoted + empty) and a hand array for captured pieces that can be dropped:

| Value | Piece          | Value | Piece (promoted)       |
|-------|----------------|-------|------------------------|
| 0     | Empty          | 7     | Promoted Pawn (Tokin)  |
| 1     | Pawn           | 8     | Promoted Silver        |
| 2     | Silver         | 9     | Promoted Bishop (Horse)|
| 3     | Gold           | 10    | Promoted Rook (Dragon) |
| 4     | Bishop         |       |                        |
| 5     | Rook           |       |                        |
| 6     | King           |       |                        |

The `hand` array is indexed by base piece type (1-5). Gold (3) can be
captured but never promotes, so it goes to hand as-is. Promoted pieces
revert to their base type when captured.

### Gomoku (9x9) -- Single-Plane Board

```
src/games/gomoku/config.hpp:  BOARD_H=9, BOARD_W=9, WIN_LENGTH=5
```

```cpp
class Board {
public:
    char board[BOARD_H][BOARD_W];  // 0=empty, 1=player0 (X), 2=player1 (O)
};
```

A single plane where cell values indicate which player's stone occupies it.
No piece types beyond "stone" exist.

---

## 4. Move Representation

All games share the same `Move` type:

```cpp
typedef std::pair<size_t, size_t> Point;   // (row, col)
typedef std::pair<Point, Point>   Move;    // (from, to)
```

How each game uses this:

### MiniChess Board Moves

Standard board-to-board piece movement:

```
Move( Point(from_row, from_col), Point(to_row, to_col) )
```

**Pawn promotion** is implicit: when a pawn reaches the last rank (row 0 or
row 5), `next_state()` automatically promotes it to a Queen (piece type 5).
No separate promotion encoding is needed.

### MiniShogi Board Moves, Promotions, and Drops

**Regular moves** use the same `(from, to)` format as MiniChess.

**Promotion** is encoded by adding `BOARD_H` to `to.first`:

```
// Normal move:    Move( Point(r, c), Point(tr, tc)             )
// Promoted move:  Move( Point(r, c), Point(tr + BOARD_H, tc)   )
```

When a piece can optionally promote (entering or leaving the promotion zone),
both the promoted and non-promoted versions are added to `legal_actions`. When
promotion is forced (e.g., a pawn reaching the last rank), only the promoted
version is generated.

`next_state()` detects the sentinel via `to.first >= BOARD_H` and applies
the promotion:

```cpp
bool promote = ((int)to.first >= BOARD_H);
int tr = promote ? (int)to.first - BOARD_H : (int)to.first;
```

**Drop moves** use a sentinel row in `from`:

```
Move( Point(DROP_ROW, piece_type), Point(to_row, to_col) )
```

Where `DROP_ROW = BOARD_H` (5 for a 5x5 board). The `from.second` field
stores the piece type being dropped (1-5), not a column. Drop restrictions:
- Cannot drop on an occupied square.
- Pawn cannot be dropped on the last rank (no forward moves).
- No two unpromoted pawns of the same player on the same column (nifu).

### Gomoku Placement Moves

Stone placement uses `from == to`:

```
Move( Point(row, col), Point(row, col) )
```

Legal actions are restricted to empty cells within Manhattan distance 2
of any existing stone (or the center cell on an empty board).

---

## 5. Evaluation System

All games implement `evaluate()` with the same three-flag signature:

```cpp
int evaluate(bool use_nnue = true, bool use_kp = true, bool use_mobility = true);
```

The evaluation priority chain:

```
1. Terminal check:  if game_state == WIN  ->  return P_MAX
2. NNUE:            if use_nnue && model loaded  ->  NNUE forward pass
3. Handcrafted:     KP eval or simple material + optional mobility
```

### 5.1 MiniChess Handcrafted Evaluation

**Material values** (10x scale for KP eval):

```cpp
static const int kp_material[7] = {0, 20, 60, 70, 80, 200, 1000};
//                                    P   R   N   B   Q    K
```

**Piece-Square Tables (PST):** 6 tables, one per piece type, each
`BOARD_H x BOARD_W`. Indexed from White's perspective (mirrored for Black).
Bonuses for central control, advanced pawns, and safe king placement.

**King tropism:** Bonus for attacking pieces near the opponent's king.
Uses Chebyshev distance (max of abs row/col difference). Weighted per piece:

```cpp
static const int tropism_w[7] = {0, 0, 3, 3, 2, 5, 0};
//                                   P  R  N  B  Q  K
```

The bonus formula is `weight * (3 - distance)` when distance <= 2.

**Mobility bonus:** `2 * (self_moves - opponent_moves)`. Requires generating
the opponent's legal moves, so it is toggled by the `use_mobility` flag.

### 5.2 MiniShogi Handcrafted Evaluation

Similar structure to MiniChess but extended for shogi-specific concepts:

**Material values** (11 piece types):

```cpp
static const int material_value[11] = {
    0,       // EMPTY
    10, 40, 50, 70, 90,  0,   // P, S, G, B, R, K
    50, 50, 120, 130           // +P, +S, +B, +R
};
```

**Hand piece values** (premium for drop flexibility):

```cpp
static const int hand_value[6] = {0, 12, 45, 55, 80, 100};
//                                    P   S   G   B   R
```

Hand pieces are valued higher than their on-board equivalents because they
can be dropped anywhere on the board.

**PST tables:** Separate tables for each piece type (including promoted
pieces). Promoted bishop (Horse) and promoted rook (Dragon) use aggressive
forward-biased tables. Promoted pawn and promoted silver use the gold table
(since they move like gold).

**King tropism:** Same Chebyshev-distance formula as MiniChess, with
per-piece weights for all 11 piece types.

### 5.3 Gomoku Threat-Based Evaluation

Gomoku uses a completely different evaluation based on **threat counting**,
since material concepts do not apply. The evaluator scans the board for
line patterns in all four axes (horizontal, vertical, two diagonals):

```
ThreatCounts:
  five   -- 5+ in a row (already won)
  open4  -- 4 in a row, open on both ends (unstoppable)
  half4  -- 4 in a row, open on one end
  open3  -- 3 in a row, open on both ends
  half3  -- 3 in a row, open on one end
  open2  -- 2 in a row, open on both ends
  half2  -- 2 in a row, open on one end
```

**Decisive threats** are detected first and return near-`P_MAX` scores:

| Condition (STM = side to move) | Score |
|-------------------------------|-------|
| STM has five | `P_MAX - 1` |
| STM has open-4 | `P_MAX - 2` |
| STM has 2+ half-4 | `P_MAX - 3` |
| STM has half-4 + open-3 | `P_MAX - 4` |
| STM has 2+ open-3 | `P_MAX - 5` |
| OPP has five | `-(P_MAX - 1)` |
| OPP has open-4 or 2+ half-4 | `-(P_MAX - 10)` |

**Non-decisive positions** use a weighted score:

```cpp
score = open3 * 500 + half3 * 80 + open2 * 60 + half2 * 10;
```

With additional bonuses/penalties for single half-4 threats.

---

## 6. NNUE Feature Extraction

The NNUE system is **game-agnostic**. The `nnue::Model` class
(`src/nnue/nnue.hpp`) receives sparse feature indices from
`state.extract_nnue_features()` and runs the forward pass through
accumulator + hidden layers + output. All game-specific knowledge is
encoded in how features are mapped.

```cpp
// nnue.hpp (game-agnostic)
struct Model {
    int evaluate(const BaseState& state, int player) const;
    // Internally calls: state.extract_nnue_features(perspective, features)
};
```

### 6.1 HalfKP Feature Scheme

Both MiniChess and MiniShogi use a **HalfKP** (Half King-Piece) encoding.
Features are indexed relative to the friendly king's square, making the
network king-position-aware.

**Feature index formula (board pieces):**

```
feature = king_sq * KP_FEAT
        + feat_color * (NUM_PT_NO_KING * NUM_SQ)
        + (piece_type - 1) * NUM_SQ
        + square

where:
    NUM_SQ    = BOARD_H * BOARD_W
    KP_FEAT   = 2 * NUM_PT_NO_KING * NUM_SQ
    king_sq   = king's square index (from perspective's viewpoint)
    feat_color = 0 for friendly pieces, 1 for opponent pieces
    piece_type = 1-based piece type (excluding king)
    square    = piece's square index (from perspective's viewpoint)
```

**Perspective flipping:** When extracting features for player 1, the board
is vertically mirrored: `sq = (BOARD_H - 1 - r) * BOARD_W + c`. This makes
the network symmetric -- the same weights evaluate equivalent positions
regardless of which player is to move.

### 6.2 MiniChess Feature Dimensions

```
NUM_SQ         = 6 * 5 = 30
NUM_PT_NO_KING = 5   (pawn, rook, knight, bishop, queen)
KP_FEAT        = 2 * 5 * 30 = 300
Total HalfKP   = 30 * 300 = 9,000 features
```

### 6.3 MiniShogi Feature Dimensions

MiniShogi extends HalfKP with **hand piece features**:

```
NUM_SQ         = 5 * 5 = 25
NUM_PT_NO_KING = 10  (pawn, silver, gold, bishop, rook,
                       +pawn, +silver, +bishop, +rook,
                       gap at index 5 for king)
KP_FEAT        = 2 * 10 * 25 = 500
HALFKP_SIZE    = 25 * 500 = 12,500

Hand features:
    HALFKP_SIZE + feat_color * NUM_HAND_TYPES + (pt - 1)
    Added 'count' times for each hand piece with count > 0.
    Total hand feature slots = 2 * 5 = 10
```

Hand pieces generate repeated feature indices: if a player holds 2 pawns,
the pawn hand feature index appears twice in the active feature list.

### 6.4 Gomoku

Gomoku defines `NUM_PT_NO_KING = 2` and `KING_ID = 0` in its config but
does not implement `extract_nnue_features()` (it returns 0). Gomoku is
compiled with `-DNO_NNUE` and relies entirely on its threat-based
handcrafted eval.

---

## 7. Zobrist Hashing

All three games implement Zobrist hashing for the transposition table.
The scheme follows the same pattern:

1. **Initialize** a table of random 64-bit values using a deterministic
   xorshift PRNG with a fixed seed (different seed per game).
2. **Compute** the hash by XOR-ing the random values for each piece on
   the board, plus a side-to-move key.

### MiniChess Zobrist

```cpp
static uint64_t zobrist_piece[2][7][BOARD_H][BOARD_W];  // [player][piece_type][row][col]
static uint64_t zobrist_side;                            // XOR'd when player == 1

uint64_t hash = 0;
for each player p:
    for each square (r, c):
        if piece = board[p][r][c]:
            hash ^= zobrist_piece[p][piece][r][c];
if player == 1:
    hash ^= zobrist_side;
```

### MiniShogi Zobrist

Extends the chess scheme with **hand piece hashing**:

```cpp
static uint64_t zobrist_piece[2][NUM_PIECE_TYPES][BOARD_H][BOARD_W];
static uint64_t zobrist_hand[2][NUM_HAND_TYPES + 1][8];  // [player][type][count]
static uint64_t zobrist_side;
```

The hand is hashed by XOR-ing `zobrist_hand[player][type][count]` for each
piece type with a nonzero count. This distinguishes positions that differ
only in hand composition.

### Gomoku Zobrist

Uses cell values (0, 1, 2) rather than per-player planes:

```cpp
static uint64_t gomoku_zobrist[3][BOARD_H][BOARD_W];  // [cell_value][row][col]
static uint64_t gomoku_zobrist_side;
```

### Lazy Initialization

All three implementations use a `static bool zobrist_ready` flag. The
Zobrist tables are initialized on the first call to `hash()`. The PRNG
seed is hard-coded and deterministic, so hash values are reproducible
across runs.

---

## 8. Repetition Detection

Repetition detection is handled in `BaseState` via a shared
`hash_counts` map:

```cpp
std::unordered_map<uint64_t, int> hash_counts;  // position hash -> count
```

**How it works:**

1. `next_state()` calls `inherit_history(parent)`, which copies the
   parent's `hash_counts` and increments the parent's position hash:

   ```cpp
   void inherit_history(const BaseState* parent) {
       hash_counts = parent->hash_counts;
       hash_counts[parent->hash()]++;
   }
   ```

2. `get_legal_actions()` calls `check_repetition()` at the start.
   If the current position has appeared >= 4 times (including the
   current occurrence), the game is declared a draw:

   ```cpp
   bool check_repetition(int limit = 4) const {
       auto it = hash_counts.find(hash());
       int prev = (it != hash_counts.end()) ? it->second : 0;
       return (prev + 1) >= limit;
   }
   ```

3. If `check_repetition()` returns `true`, `get_legal_actions()` sets
   `game_state = DRAW` and clears `legal_actions`.

**4-fold repetition** is used (not 3-fold as in standard chess). Both
MiniChess and MiniShogi check repetition. Gomoku does not need repetition
detection (stones are never moved or removed).

---

## 9. Game-Over Conditions

### MiniChess

| Condition | Result | Detection point |
|-----------|--------|-----------------|
| King capture available | `WIN` for current player | `get_legal_actions()` detects an opponent king on a target square and returns immediately. |
| Checkmate | `WIN` for the side that delivered check | `get_legal_actions()` is called inside `next_state()`. If the new position has `game_state == WIN` (the player who just moved can capture the king), the game is over. |
| 4-fold repetition | `DRAW` | `check_repetition()` at start of `get_legal_actions()`. |
| 100 moves (`MAX_STEP`) | Not directly checked in MiniChess `get_legal_actions()` | Enforced at protocol/search level. |

**Important detail:** MiniChess uses a "king capture" model, not a standard
checkmate model. A position where you can take the king is terminal (`WIN`).
This means the previous move was an illegal move in standard chess (moving
into check), but this engine allows it -- the game just ends when the king
is actually captured.

### MiniShogi

| Condition | Result | Detection point |
|-----------|--------|-----------------|
| King capture available | `WIN` | Same king-capture model as MiniChess. |
| 4-fold repetition | `DRAW` | `check_repetition()` at start of `get_legal_actions()`. |
| Step limit (200 moves) | `DRAW` | `if(step >= MAX_STEP)` in `get_legal_actions()`. |
| No legal moves | `NONE` (extremely rare) | Checked after move generation. |

### Gomoku

| Condition | Result | Detection point |
|-----------|--------|-----------------|
| 5 in a row | `WIN` | `check_win_at()` called in `next_state()` after placing a stone. The win is attributed to the player who placed the stone. |
| Board full / no nearby moves | `DRAW` | `legal_actions.empty()` after generation in `get_legal_actions()`. |
| `MAX_STEP` | Equal to `BOARD_H * BOARD_W` (81) | Implicit via board filling up. |

---

## 10. How to Add a New Game

Follow these steps to add a new game called `mygame`:

### Step 1: Create the game directory

```
src/games/mygame/
    config.hpp
    state.hpp
    state.cpp
```

### Step 2: Write `config.hpp`

Define board dimensions, piece types, and game constants:

```cpp
#pragma once
#include "../../config.hpp"   // inherits USE_NNUE, RANDOM_SEED, etc.

#ifndef BOARD_H
#define BOARD_H 8             // your board height
#endif
#ifndef BOARD_W
#define BOARD_W 8             // your board width
#endif

#define MAX_STEP 200          // draw after this many moves

// Piece types (used by NNUE feature extraction and move ordering)
#define NUM_PIECE_TYPES 6
#define NUM_PT_NO_KING  5
#define KING_ID         6     // set to 0 if no king concept

// MVV-LVA piece values for move ordering
#define NUM_PIECE_VALS 7
static const int PIECE_VAL[NUM_PIECE_VALS] = {
    0, 2, 6, 7, 8, 20, 100
};

// Piece display strings (used by encode_output)
#define PIECE_STR_LEN 2
const char PIECE_TABLE[2][7][5] = {
    {"  ", "wP", "wR", "wN", "wB", "wQ", "wK"},
    {"  ", "bP", "bR", "bN", "bB", "bQ", "bK"},
};
```

### Step 3: Write `state.hpp`

Define the `Board` class and the `State` class inheriting from `BaseState`:

```cpp
#pragma once
#include "base_state.hpp"
#include "config.hpp"

class Board {
public:
    // Choose your representation:
    // Two-plane (chess/shogi):   char board[2][BOARD_H][BOARD_W] = {};
    // Single-plane (gomoku):    char board[BOARD_H][BOARD_W] = {};
    char board[2][BOARD_H][BOARD_W] = {};
};

class State : public BaseState {
public:
    Board board;
    int step = 0;

    State();
    State(int player) { this->player = player; }
    State(Board board, int player) : board(board) { this->player = player; }

    // --- Pure virtual overrides (must implement) ---
    State* next_state(const Move& move) override;
    void get_legal_actions() override;
    int evaluate(bool use_nnue = true, bool use_kp = true,
                 bool use_mobility = true) override;
    std::string encode_output() const override;
    std::string encode_board() const override;
    void decode_board(const std::string& s, int side_to_move) override;

    // --- Game description ---
    int board_h() const override { return BOARD_H; }
    int board_w() const override { return BOARD_W; }
    const char* game_name() const override { return "MyGame"; }

    // --- Recommended overrides ---
    uint64_t hash() const override;
    int piece_at(int player, int row, int col) const override;
    std::string cell_display(int row, int col) const override;
    BaseState* create_null_state() const override;  // nullptr if not applicable

    // --- NNUE (optional) ---
    int extract_nnue_features(int perspective, int* features) const override;
};
```

### Step 4: Implement `state.cpp`

Implement all the virtual methods. The key methods and their expected
behavior:

**`get_legal_actions()`** -- The most important method. Must:
1. Call `check_repetition()` first (if your game can have repeated positions).
2. Check step limit (`if(step >= MAX_STEP) { game_state = DRAW; return; }`).
3. Populate `legal_actions` with all valid moves.
4. Detect terminal conditions (set `game_state = WIN` if opponent king is
   capturable, `game_state = DRAW` if no legal moves in a draw game, etc.).

```cpp
void State::get_legal_actions() {
    game_state = NONE;
    legal_actions.clear();

    if (check_repetition()) {
        game_state = DRAW;
        return;
    }
    if (step >= MAX_STEP) {
        game_state = DRAW;
        return;
    }

    // ... generate moves, detect terminal conditions ...
}
```

**`next_state(move)`** -- Must:
1. Create a new `State` with the move applied.
2. Call `inherit_history(this)` on the new state.
3. Call `get_legal_actions()` on the new state (unless the current position
   is already `WIN`).
4. Return the heap-allocated state.

```cpp
State* State::next_state(const Move& move) {
    Board next_board = this->board;
    // ... apply the move to next_board ...

    State* ns = new State(next_board, 1 - this->player);
    ns->step = this->step + 1;
    ns->inherit_history(this);

    if (this->game_state != WIN) {
        ns->get_legal_actions();
    }
    return ns;
}
```

**`evaluate()`** -- Must return a score from the current player's
perspective. Follow this pattern:

```cpp
int State::evaluate(bool use_nnue, bool use_kp, bool use_mobility) {
    if (game_state == WIN) return P_MAX;

    #ifdef USE_NNUE
    if (use_nnue && nnue::g_model.loaded()) {
        return nnue::g_model.evaluate(*this, this->player);
    }
    #endif

    // ... handcrafted evaluation ...
    return self_score - opponent_score;
}
```

**`hash()`** -- Implement Zobrist hashing. Use a deterministic xorshift
PRNG with a unique seed (different from existing games):

```cpp
static uint64_t zobrist_piece[2][NUM_TYPES][BOARD_H][BOARD_W];
static uint64_t zobrist_side;
static bool zobrist_ready = false;

static void init_zobrist() {
    uint64_t s = 0xYOUR_UNIQUE_SEED_HERE;
    auto rand64 = [&s]() -> uint64_t {
        s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s;
    };
    // ... fill tables ...
    zobrist_ready = true;
}

uint64_t State::hash() const {
    if (!zobrist_ready) init_zobrist();
    uint64_t h = 0;
    // ... XOR piece keys ...
    if (player) h ^= zobrist_side;
    return h;
}
```

### Step 5: Add Makefile targets

```makefile
MYGAME_INC = -Isrc/games/mygame -Isrc/state -Isrc
STATE_SOURCE_MG = $(SOURCES_DIR)/games/mygame/state.cpp

mygame:
    $(CXX) $(CXXFLAGS) $(MYGAME_INC) -o $(BUILD_DIR)/mygame-ubgi \
        $(STATE_SOURCE_MG) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
```

If your game does not use NNUE, add `-DNO_NNUE` to the compile flags
(like Gomoku does). The `NO_NNUE` flag prevents `USE_NNUE` from being
defined in `src/config.hpp`:

```cpp
// src/config.hpp
#ifndef NO_NNUE
#define USE_NNUE
#endif
```

### Step 6: Add GUI and CLI modules (optional)

Create Python modules following the existing pattern:

```
gui/games/mygame_engine.py     -- MyGameState class, format_move, labels
gui/games/mygame_renderer.py   -- draw_pieces(), draw_pv()
cli/games/mygame.py            -- print_board, get_human_move, etc.
```

Register the game in `gui/main.py` (`_get_game_module()` and
`_configure_board_size()`) and `cli/cli.py` (`_init_game()`).

### Checklist

- [ ] `config.hpp` defines `BOARD_H`, `BOARD_W`, `MAX_STEP`, piece types
- [ ] `State` inherits `BaseState` and implements all pure virtual methods
- [ ] `get_legal_actions()` calls `check_repetition()` (if applicable)
- [ ] `get_legal_actions()` sets `game_state` correctly for all terminal cases
- [ ] `next_state()` calls `inherit_history(this)` and `get_legal_actions()`
- [ ] `evaluate()` returns `P_MAX` for `WIN` and scores from current player's view
- [ ] `hash()` uses Zobrist hashing with a unique seed
- [ ] `piece_at()` returns correct values (used by MVV-LVA move ordering)
- [ ] `encode_board()` / `decode_board()` round-trip correctly
- [ ] Makefile target with correct `-I` flags compiles and links
- [ ] NNUE: either implement `extract_nnue_features()` or compile with `-DNO_NNUE`

---

## Appendix: File Layout

```
src/
    config.hpp                      # Global flags: USE_NNUE, RANDOM_SEED, TT size
    search_types.hpp                # SearchResult, SearchContext, RootUpdate
    search_params.hpp               # ParamMap, ParamDef, param_bool, param_int
    state/
        base_state.hpp              # BaseState abstract class, Move/Point typedefs
    games/
        minichess/
            config.hpp              # BOARD_H=6, BOARD_W=5, piece IDs, PIECE_VAL
            state.hpp               # Board (2-plane), State : BaseState
            state.cpp               # movegen (bitboard+naive), eval, hash, NNUE features
        minishogi/
            config.hpp              # BOARD_H=5, BOARD_W=5, 11 piece types, DROP_ROW
            state.hpp               # Board (2-plane+hand), State : BaseState
            state.cpp               # movegen (board+drops), eval, hash, NNUE features
        gomoku/
            config.hpp              # BOARD_H=9, BOARD_W=9, WIN_LENGTH=5
            state.hpp               # Board (single-plane), State : BaseState
            state.cpp               # movegen (proximity), threat eval, hash
    nnue/
        nnue.hpp                    # Model struct, evaluate(), init()
        nnue.cpp                    # Model loading, forward pass
        compute.hpp                 # Scalar accumulator/layer computation
        compute_simd.hpp            # SSE/AVX accelerated computation
        compute_quant.hpp           # Quantized weight computation
    policy/
        pvs.hpp, pvs.cpp            # Principal Variation Search
        pvs/
            tt.hpp                  # Transposition table
            killer_moves.hpp        # Killer move heuristic
            move_ordering.hpp       # MVV-LVA + killer ordering
            quiescence.hpp          # Quiescence search
        alphabeta.hpp, alphabeta.cpp
        minimax.hpp, minimax.cpp
        random.hpp, random.cpp
        registry.hpp                # AlgoEntry, get_algo_table(), find_algo()
    ubgi/
        ubgi.cpp                    # UBGI protocol engine (main loop)
    selfplay.cpp                    # Self-play data generation
    datagen.cpp                     # Training data generation
    benchmark.cpp                   # Search benchmark

gui/
    main.py                         # GUI entry point, GameApp
    config.py                       # Layout constants, piece symbols
    board_renderer.py               # Game-agnostic board renderer
    ubgi_client.py                  # UBGI engine subprocess client
    games/
        minichess_engine.py         # MiniChessState Python port
        minichess_renderer.py       # Chess piece glyph renderer
        gomoku_engine.py            # GomokuState Python implementation
        gomoku_renderer.py          # Stone circle renderer

cli/
    cli.py                          # CLI entry point, game loop
    games/
        minichess.py                # MiniChess CLI module
```
