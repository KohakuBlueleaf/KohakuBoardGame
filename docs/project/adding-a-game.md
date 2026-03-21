# Adding a New Game

A practical, step-by-step tutorial for adding a new two-player board game to the
engine. By the end you will have a working C++ engine binary, a Python GUI, a CLI
runner, and NNUE training support.

**Existing examples to study:**

| Game | Board | Pieces on board | Hand pieces | Move style |
|------|-------|-----------------|-------------|------------|
| MiniChess | `char board[2][H][W]` | 6 types (pawn..king) | No | from-to |
| MiniShogi | `char board[2][H][W]` + `char hand[2][6]` | 11 types (incl. promoted) | Yes (drops) | from-to + drops |
| Gomoku | `char board[H][W]` | 1 type per player | No | placement (from==to) |

Pick the example closest to your game and use it as your primary reference.

---

## Overview: Files to Create and Modify

```
src/games/{game}/
    config.hpp          -- board size, piece constants         [CREATE]
    state.hpp           -- Board struct, State class           [CREATE]
    state.cpp           -- all game logic                      [CREATE]

gui/games/
    {game}_engine.py    -- Python game state for GUI/CLI       [CREATE]
    {game}_renderer.py  -- Pygame piece renderer               [CREATE]

cli/games/
    {game}.py           -- CLI board display, human input      [CREATE]

nnue-train/
    game_config.py      -- add entry to GAME_CONFIGS           [MODIFY]

Makefile               -- add build targets                    [MODIFY]
gui/main.py            -- register in _get_game_module()       [MODIFY]
                          and _configure_board_size()
gui/config.py          -- add piece symbols to GAME_PIECES     [MODIFY]
cli/cli.py             -- register in _init_game()             [MODIFY]
```

---

## Step 1: Create `config.hpp`

**File:** `src/games/{game}/config.hpp`

This file defines board dimensions, piece type constants, and display tables.
It is included by both your `state.hpp` and (via the `-I` flags) by shared
engine code like `ubgi.cpp`, so `BOARD_H`, `BOARD_W`, and `MAX_STEP` must be
macros.

```cpp
#pragma once
#include "../../config.hpp"      // pulls in global settings (USE_NNUE, etc.)

/* === Board Dimensions === */
#ifndef BOARD_H
#define BOARD_H 8                // your board height
#endif
#ifndef BOARD_W
#define BOARD_W 8                // your board width
#endif

#define MAX_STEP 200             // max moves before adjudication (0 = unlimited)

/* === Piece Types ===
 * Use 0 for EMPTY. Number your pieces starting at 1.
 * For games with promotion, continue numbering promoted forms. */
#define EMPTY   0
#define PIECE_A 1
#define PIECE_B 2
// ...
#define KING    6                // if your game has a king

/* === NNUE Constants ===
 * These are used by extract_nnue_features() and the training pipeline.
 * NUM_PIECE_TYPES:  total piece type count (including promoted forms, excluding EMPTY)
 * NUM_PT_NO_KING:   piece types minus king (used in HalfKP feature indexing)
 * KING_ID:          the piece type ID for king (0 if no king) */
#define NUM_PIECE_TYPES 6
#define NUM_PT_NO_KING  5
#define KING_ID         6

/* === Hand Pieces (only for games with captures-to-hand like shogi) ===
 * Set NUM_HAND_TYPES to 0 if your game has no hand.
 * DROP_ROW is the sentinel row used in Move encoding for drop moves. */
// #define NUM_HAND_TYPES 5
// #define DROP_ROW BOARD_H

/* === MVV-LVA Piece Values (for move ordering in alpha-beta search) === */
#define NUM_PIECE_VALS 7
static const int PIECE_VAL[NUM_PIECE_VALS] = {
    /* EMPTY */ 0, /* A */ 2, /* B */ 6, /* C */ 7,
    /* D */ 8, /* E */ 20, /* KING */ 100,
};

/* === Piece Display (used by encode_output / cell_display) === */
#define PIECE_STR_LEN 2
const char PIECE_TABLE[2][NUM_PIECE_VALS][5] = {
    {"  ", "wA", "wB", "wC", "wD", "wE", "wK"},
    {"  ", "bA", "bB", "bC", "bD", "bE", "bK"},
};
```

**Key points:**
- The `#ifndef` guards let you override dimensions at compile time with
  `-DBOARD_H=10 -DBOARD_W=10`.
- For a placement game (like Othello), you still need `NUM_PIECE_TYPES`.
  Othello would use `#define NUM_PIECE_TYPES 1` (one stone type per player)
  and `#define KING_ID 0` (no king).

---

## Step 2: Create `state.hpp`

**File:** `src/games/{game}/state.hpp`

This file declares the `Board` struct and the `State` class. The `State` class
must inherit from `BaseState` (defined in `src/state/base_state.hpp`).

### 2.1 The `Board` Struct

Choose a board representation that suits your game:

```cpp
#pragma once
#include "base_state.hpp"
#include "config.hpp"
#include <cstring>
#include <sstream>

class Board {
public:
    // OPTION A: Two-plane board (chess-like: one plane per player)
    //   board[player][row][col] = piece_type (0 = empty)
    char board[2][BOARD_H][BOARD_W] = {};

    // OPTION B: Single-plane board (Othello/Gomoku: value = 0/1/2)
    //   board[row][col] = cell_value
    // char board[BOARD_H][BOARD_W] = {};

    // OPTION C: Two-plane board + hand (shogi-like)
    //   char hand[2][NUM_HAND_TYPES + 1] = {};
};
```

Initialize the default constructor with the starting position. For example,
MiniChess initializes pawn rows and piece rows directly in the member
initializer. You can also zero-initialize and set pieces in the `State`
default constructor.

### 2.2 The `State` Class

```cpp
class State : public BaseState {
public:
    Board board;
    int step = 0;       // move counter (for MAX_STEP adjudication)

    // --- Constructors ---
    State();                                  // starting position
    State(int player) { this->player = player; }
    State(Board board, int player) : board(board) { this->player = player; }

    // --- Pure virtual overrides (REQUIRED) ---
    State* next_state(const Move& move) override;
    void get_legal_actions() override;
    int evaluate(bool use_nnue = true, bool use_kp = true,
                 bool use_mobility = true) override;
    std::string encode_output() const override;
    std::string encode_board() const override;
    void decode_board(const std::string& s, int side_to_move) override;

    // --- Game description (REQUIRED) ---
    int board_h() const override { return BOARD_H; }
    int board_w() const override { return BOARD_W; }
    const char* game_name() const override { return "YourGame"; }

    // --- Strongly recommended overrides ---
    uint64_t hash() const override;
    int piece_at(int player, int row, int col) const override;
    std::string cell_display(int row, int col) const override;
    BaseState* create_null_state() const override;

    // --- NNUE (optional but needed for training) ---
    int extract_nnue_features(int perspective, int* features) const override;

    // --- Hand pieces (only for shogi-like games) ---
    // int hand_count(int player, int piece_type) const override;
    // int num_hand_types() const override;
};
```

**Understanding `BaseState` members you inherit:**

| Member | Type | Purpose |
|--------|------|---------|
| `player` | `int` | Current side to move: 0 or 1 |
| `game_state` | `GameState` | `UNKNOWN`, `NONE`, `WIN`, or `DRAW` |
| `legal_actions` | `vector<Move>` | Populated by `get_legal_actions()` |
| `hash_counts` | `unordered_map<uint64_t,int>` | Repetition tracking |

**Understanding `Move` encoding:**

`Move` is `std::pair<Point, Point>` where `Point = std::pair<size_t, size_t>`.

| Game type | from | to |
|-----------|------|-----|
| Board move (chess) | `(from_row, from_col)` | `(to_row, to_col)` |
| Placement (Gomoku/Othello) | `(row, col)` | `(row, col)` (same as from) |
| Drop (shogi) | `(BOARD_H, piece_type)` | `(to_row, to_col)` |
| Promotion (shogi) | `(from_row, from_col)` | `(to_row + BOARD_H, to_col)` |

The UBGI protocol layer (`src/ubgi/ubgi.cpp`) handles converting between
algebraic strings (e.g. `a2a4`, `P*c3`, `b4c5+`) and `Move` objects
automatically. You do not need to modify `ubgi.cpp`.

---

## Step 3: Implement `state.cpp`

**File:** `src/games/{game}/state.cpp`

This is the core of the game engine. Implement each virtual method.

### 3.1 Default Constructor

Set up the starting position. If the board layout is baked into the `Board`
member initializer (like MiniChess), the default constructor can be empty.

```cpp
#include "state.hpp"
#include "config.hpp"
#ifdef USE_NNUE
#include "../../nnue/nnue.hpp"
#endif

// If your Board has zero-initialized members and you set the starting
// position in the Board class itself, this can just be:
// State::State() {}

// Otherwise, set up the starting position here:
State::State() {
    // Example for Othello 8x8:
    // board.board[0][3][3] = 1;  board.board[0][4][4] = 1;   // white
    // board.board[1][3][4] = 1;  board.board[1][4][3] = 1;   // black
    player = 0;
}
```

### 3.2 `get_legal_actions()`

Populate `this->legal_actions` and set `this->game_state`. This is the most
game-specific method.

**Contract:**
- Set `game_state = NONE` at the start (meaning: non-terminal, game continues).
- Generate all legal moves and push them into `legal_actions`.
- If a move results in an immediate win (e.g., king capture in chess), set
  `game_state = WIN` and return early.
- If no legal moves exist (stalemate/pass scenarios), set `game_state` to
  `DRAW` or handle appropriately.
- For repetition detection, call `check_repetition()` at the top and set
  `game_state = DRAW` if it returns true.

```cpp
void State::get_legal_actions() {
    // --- Repetition check ---
    if (check_repetition()) {
        game_state = DRAW;
        legal_actions.clear();
        return;
    }

    game_state = NONE;
    legal_actions.clear();

    auto self_board = board.board[player];
    auto oppn_board = board.board[1 - player];

    for (int r = 0; r < BOARD_H; r++) {
        for (int c = 0; c < BOARD_W; c++) {
            int piece = self_board[r][c];
            if (!piece) continue;

            // Generate moves for this piece based on its type.
            // For each valid destination (tr, tc):
            //
            //   1. Check that (tr, tc) is in bounds
            //   2. Check that (tr, tc) is not occupied by own piece
            //   3. Push Move(Point(r, c), Point(tr, tc))
            //   4. If capturing opponent's king: set game_state = WIN, return
            //
            // For sliding pieces, iterate along each ray and stop at
            // the first blocker (capture it if it's an opponent piece).
        }
    }
}
```

**For placement games** (Othello, Gomoku):

```cpp
void State::get_legal_actions() {
    game_state = NONE;
    legal_actions.clear();

    for (int r = 0; r < BOARD_H; r++) {
        for (int c = 0; c < BOARD_W; c++) {
            if (board.board[r][c] == 0 /* && is_valid_placement(r, c) */) {
                // Placement: from == to
                legal_actions.push_back(Move(Point(r, c), Point(r, c)));
            }
        }
    }

    // Check for win condition if applicable
    // if (no legal actions) game_state = DRAW;
}
```

### 3.3 `next_state()`

Create a new heap-allocated `State` with the move applied. Call
`get_legal_actions()` on the child to detect terminal conditions.

```cpp
State* State::next_state(const Move& move) {
    Board next = this->board;
    Point from = move.first, to = move.second;

    // --- Apply the move to `next` ---
    // 1. Get the piece at the source square
    int8_t moved = next.board[player][from.first][from.second];

    // 2. Handle promotion (if applicable)
    //    e.g., pawn reaching last rank becomes queen

    // 3. Handle capture: clear opponent piece at destination
    if (next.board[1 - player][to.first][to.second]) {
        next.board[1 - player][to.first][to.second] = 0;
        // For shogi-like games: add captured piece to hand
    }

    // 4. Move the piece
    next.board[player][from.first][from.second] = 0;
    next.board[player][to.first][to.second] = moved;

    // --- Create child state ---
    State* child = new State(next, 1 - player);
    child->step = this->step + 1;

    // --- Inherit repetition history ---
    child->inherit_history(this);

    // --- Generate legal actions (detects terminal) ---
    if (this->game_state != WIN) {
        child->get_legal_actions();
    }

    return child;
}
```

**Important:** The engine `delete`s states after use, so always allocate
with `new`. The `inherit_history()` call copies the parent's position hash
history and increments the parent's hash count for repetition detection.

### 3.4 `evaluate()`

Return an integer score from the **current player's** perspective.
Use `P_MAX` (100000) for a win, 0 for a draw.

```cpp
int State::evaluate(bool use_nnue, bool use_kp, bool use_mobility) {
    // --- Terminal check ---
    if (game_state == WIN) {
        return P_MAX;
    }

    // --- NNUE evaluation (if compiled and loaded) ---
    #ifdef USE_NNUE
    if (use_nnue && nnue::g_model.loaded()) {
        return nnue::g_model.evaluate(*this, this->player);
    }
    #endif
    (void)use_nnue;

    // --- Handcrafted evaluation ---
    int score = 0;

    // Option 1: Material counting
    // Sum piece values for current player, subtract opponent's.
    //   for each square:
    //     score += material[self_board[r][c]];
    //     score -= material[oppn_board[r][c]];

    // Option 2: Material + Piece-Square Tables (like MiniChess)
    // Add positional bonuses based on piece type and square.

    // Option 3: Pattern-based (like Gomoku threat counting)

    // Option 4: Mobility bonus
    if (use_mobility) {
        int self_mobility = (int)legal_actions.size();
        State oppn_state(board, 1 - player);
        oppn_state.get_legal_actions();
        int oppn_mobility = (int)oppn_state.legal_actions.size();
        score += 2 * (self_mobility - oppn_mobility);
    }

    return score;
}
```

### 3.5 `encode_board()` / `decode_board()`

These serialize the board as a compact string for the UBGI `position board`
command. Use `/` to separate rows. Use single characters for piece identities.

The convention: uppercase for player 0, lowercase for player 1, `.` for empty.

```cpp
static const char* piece_chars = ".ABCDEF";        // player 0
static const char* piece_chars_lower = ".abcdef";   // player 1

std::string State::encode_board() const {
    std::string s;
    for (int r = 0; r < BOARD_H; r++) {
        if (r > 0) s += '/';
        for (int c = 0; c < BOARD_W; c++) {
            int w = board.board[0][r][c];
            int b = board.board[1][r][c];
            if (w > 0)      s += piece_chars[w];
            else if (b > 0) s += piece_chars_lower[b];
            else            s += '.';
        }
    }
    // For hand pieces, append after a space:
    // s += " " + encode_hand();
    return s;
}

void State::decode_board(const std::string& s, int side_to_move) {
    player = side_to_move;
    game_state = UNKNOWN;
    board = Board{};           // zero-initialize
    int r = 0, c = 0;
    for (char ch : s) {
        if (ch == '/') { r++; c = 0; continue; }
        if (ch == ' ') break;  // hand section follows (if applicable)
        if (r >= BOARD_H || c >= BOARD_W) break;
        if (ch >= 'A' && ch <= 'Z') {
            // Map to player 0 piece type
            for (int p = 1; p <= NUM_PIECE_TYPES; p++) {
                if (piece_chars[p] == ch) { board.board[0][r][c] = p; break; }
            }
        } else if (ch >= 'a' && ch <= 'z') {
            // Map to player 1 piece type
            for (int p = 1; p <= NUM_PIECE_TYPES; p++) {
                if (piece_chars_lower[p] == ch) { board.board[1][r][c] = p; break; }
            }
        }
        c++;
    }
    // Parse hand section if applicable
    get_legal_actions();
}
```

**For single-plane boards** (Gomoku/Othello), use `1`/`2` or `X`/`O` instead
of the two-plane uppercase/lowercase convention.

### 3.6 `encode_output()` and `cell_display()`

`encode_output()` returns a multi-line string for the UBGI `d` command's
board display. `cell_display()` returns a 3-character string for one cell.

```cpp
std::string State::encode_output() const {
    std::stringstream ss;
    for (int r = 0; r < BOARD_H; r++) {
        for (int c = 0; c < BOARD_W; c++) {
            ss << cell_display(r, c);
        }
        ss << "\n";
    }
    return ss.str();
}

std::string State::cell_display(int row, int col) const {
    int w = board.board[0][row][col];
    int b = board.board[1][row][col];
    if (w) return std::string(" ") + piece_chars[w] + " ";
    if (b) return std::string(" ") + piece_chars_lower[b] + " ";
    return " . ";
}
```

### 3.7 `hash()` -- Zobrist Hashing

Implement Zobrist hashing for the transposition table. Initialize random key
tables on first call using a deterministic seed so hashes are reproducible
across runs.

```cpp
// Adjust array dimensions to match your piece types and board size.
static uint64_t zobrist_piece[2][NUM_PIECE_TYPES + 1][BOARD_H][BOARD_W];
static uint64_t zobrist_side;
static bool zobrist_ready = false;

static void init_zobrist() {
    uint64_t s = 0x7A35C9D1E4F02B68ULL;     // fixed seed
    auto rand64 = [&s]() -> uint64_t {
        s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s;
    };
    for (int p = 0; p < 2; p++)
        for (int t = 0; t <= NUM_PIECE_TYPES; t++)
            for (int r = 0; r < BOARD_H; r++)
                for (int c = 0; c < BOARD_W; c++)
                    zobrist_piece[p][t][r][c] = rand64();
    zobrist_side = rand64();
    // For hand pieces, also generate:
    // for (int p = 0; p < 2; p++)
    //     for (int t = 1; t <= NUM_HAND_TYPES; t++)
    //         for (int count = 0; count < MAX_HAND; count++)
    //             zobrist_hand[p][t][count] = rand64();
    zobrist_ready = true;
}

uint64_t State::hash() const {
    if (!zobrist_ready) init_zobrist();
    uint64_t h = 0;
    for (int p = 0; p < 2; p++)
        for (int r = 0; r < BOARD_H; r++)
            for (int c = 0; c < BOARD_W; c++) {
                int piece = board.board[p][r][c];
                if (piece) h ^= zobrist_piece[p][piece][r][c];
            }
    if (player) h ^= zobrist_side;
    return h;
}
```

### 3.8 `create_null_state()`

Return a state with the side-to-move flipped (a "pass"), used by null move
pruning in the search. Return `nullptr` if null move pruning does not make
sense for your game (e.g., Gomoku).

```cpp
BaseState* State::create_null_state() const {
    State* s = new State(board, 1 - player);
    s->get_legal_actions();
    return s;
}
// Or for games where passing is never valid:
// BaseState* State::create_null_state() const { return nullptr; }
```

### 3.9 `piece_at()`

Return the piece type at `(row, col)` for the given player. Used by the
search for MVV-LVA move ordering.

```cpp
int State::piece_at(int player, int row, int col) const {
    return board.board[player][row][col];
}
```

For single-plane boards (Gomoku), adapt:

```cpp
int State::piece_at(int p, int row, int col) const {
    return (board.board[row][col] == p + 1) ? 1 : 0;
}
```

### 3.10 `extract_nnue_features()` (Optional)

This is only needed if you plan to train an NNUE network. It maps the current
board position to a sparse feature vector for the NNUE accumulator.

The feature scheme used by the engine is **HalfKP** (Half King-Piece): each
feature encodes `(king_square, piece_color, piece_type, piece_square)`.

```cpp
int State::extract_nnue_features(int perspective, int* features) const {
    constexpr int NUM_SQ = BOARD_H * BOARD_W;
    constexpr int KP_FEAT = 2 * NUM_PT_NO_KING * NUM_SQ;
    int count = 0;

    // 1. Find king square for this perspective
    int king_sq = 0;
    for (int r = 0; r < BOARD_H; r++)
        for (int c = 0; c < BOARD_W; c++)
            if (board.board[perspective][r][c] == KING_ID)
                king_sq = (perspective == 0)
                    ? (r * BOARD_W + c)
                    : ((BOARD_H - 1 - r) * BOARD_W + c);

    // 2. Encode each non-king piece
    for (int color = 0; color < 2; color++) {
        for (int r = 0; r < BOARD_H; r++) {
            for (int c = 0; c < BOARD_W; c++) {
                int pt = board.board[color][r][c];
                if (pt == 0 || pt == KING_ID) continue;
                int feat_color = (perspective == 0) ? color : 1 - color;
                int sq = (perspective == 0)
                    ? (r * BOARD_W + c)
                    : ((BOARD_H - 1 - r) * BOARD_W + c);
                features[count++] = king_sq * KP_FEAT
                    + feat_color * (NUM_PT_NO_KING * NUM_SQ)
                    + (pt - 1) * NUM_SQ + sq;
            }
        }
    }
    return count;
}
```

For games without a king (Gomoku, Othello), use a simpler **PS**
(Piece-Square) scheme instead of HalfKP. Set `KING_ID` to 0 and skip the
king-square indexing.

---

## Step 4: Add Makefile Targets

**File:** `Makefile`

Add an include-path variable, state source variable, and build targets.
The `-I` flags are critical: they make `#include "state.hpp"` and
`#include "config.hpp"` in shared code (like `ubgi.cpp`) resolve to YOUR
game's files.

### 4.1 Add Variables (near the top, after existing ones)

```makefile
STATE_SOURCE_YG = $(SOURCES_DIR)/games/yourgame/state.cpp
YOURGAME_INC = -Isrc/games/yourgame -Isrc/state -Isrc
```

### 4.2 Add to `.PHONY` and `all`

```makefile
.PHONY: all clean minichess gomoku minishogi yourgame
.PHONY: yourgame-datagen yourgame-selfplay yourgame-benchmark
```

Add `yourgame` (and its datagen/selfplay/benchmark variants) to the `all`
target list.

### 4.3 Add Build Targets (both Windows and Unix sections)

The Makefile has `ifeq ($(OS), Windows_NT)` / `else` branches. Add your
targets in **both** branches. The only difference is `.exe` on Windows.

```makefile
# === Engine target ===
yourgame:
	$(CXX) $(CXXFLAGS) $(YOURGAME_INC) -o $(BUILD_DIR)/yourgame-ubgi$(EXT) \
	    $(STATE_SOURCE_YG) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp

# === Data generation ===
yourgame-datagen:
	$(CXX) $(CXXFLAGS) $(YOURGAME_INC) -o $(BUILD_DIR)/yourgame-datagen$(EXT) \
	    $(STATE_SOURCE_YG) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp

# === Self-play ===
yourgame-selfplay:
	$(CXX) $(CXXFLAGS) $(YOURGAME_INC) -o $(BUILD_DIR)/yourgame-selfplay$(EXT) \
	    $(STATE_SOURCE_YG) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp

# === Benchmark ===
yourgame-benchmark:
	$(CXX) $(CXXFLAGS) $(YOURGAME_INC) -o $(BUILD_DIR)/yourgame-benchmark$(EXT) \
	    $(STATE_SOURCE_YG) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
```

Where `$(EXT)` is `.exe` on Windows or empty on Unix (follow the pattern of
existing targets -- the actual Makefile uses separate blocks rather than a
variable).

**If your game does not use NNUE**, add `-DNO_NNUE` to the compile flags
(see the `gomoku` target for an example).

### 4.4 Add to `clean`

```makefile
clean:
	rm -f ... $(BUILD_DIR)/yourgame-ubgi* $(BUILD_DIR)/yourgame-datagen* \
	    $(BUILD_DIR)/yourgame-selfplay* $(BUILD_DIR)/yourgame-benchmark*
```

---

## Step 5: Create the Python GUI State Class

**File:** `gui/games/{game}_engine.py`

This is a Python reimplementation of your C++ game state. The GUI uses it to
track the board locally (for display, click handling, legal move highlighting)
and to detect game-over conditions.

### 5.1 Template

```python
"""YourGame engine -- Python state tracking for GUI."""

try:
    import gui.config as cfg
except ImportError:
    import config as cfg

# Player display names and colors (used by the GUI side panel)
PLAYER_LABELS = {0: "Player 1", 1: "Player 2"}
PLAYER_COLORS = {0: (240, 240, 240), 1: (30, 30, 30)}

# Piece constants (must match C++ config.hpp)
EMPTY = 0
PIECE_A = 1
PIECE_B = 2
# ...

# Material values for MAX_STEP adjudication
_MATERIAL_TABLE = {EMPTY: 0, PIECE_A: 2, PIECE_B: 6, ...}


def _make_initial_board():
    """Return the starting position."""
    # For two-plane: board[2][BOARD_H][BOARD_W]
    board = [[[0] * cfg.BOARD_W for _ in range(cfg.BOARD_H)] for _ in range(2)]
    # Set up starting pieces...
    return board


def _deep_copy_board(board):
    """Deep-copy a board[2][BOARD_H][BOARD_W] list."""
    return [[row[:] for row in player_board] for player_board in board]


class YourGameState:
    """Game state matching the C++ State class."""

    def __init__(self, board=None, player=0, step=1):
        if board is None:
            self.board = _make_initial_board()
        else:
            self.board = _deep_copy_board(board)
        self.player = player
        self.step = step
        self.game_state = "unknown"    # "unknown", "none", "win", "draw"
        self.legal_actions = []
        self.last_move = None
        self.hash_counts = {}          # position_key -> count

    @property
    def current_player(self):
        return self.player

    @staticmethod
    def initial():
        """Return the starting-position state with legal actions computed."""
        s = YourGameState()
        s.get_legal_actions()
        return s

    def position_key(self):
        """Hashable key for repetition detection."""
        return (self.player, tuple(
            self.board[p][r][c]
            for p in range(2)
            for r in range(cfg.BOARD_H)
            for c in range(cfg.BOARD_W)
        ))

    def get_legal_actions(self):
        """Populate self.legal_actions and set self.game_state.

        Must match the C++ get_legal_actions() logic exactly, or the GUI
        will desync from the engine.
        """
        self.game_state = "none"
        actions = []

        # ... generate all legal moves ...
        # For each valid move:
        #   actions.append(((from_r, from_c), (to_r, to_c)))
        # If immediate win detected:
        #   self.game_state = "win"
        #   self.legal_actions = actions
        #   return

        self.legal_actions = actions

    def next_state(self, move):
        """Return a new state after applying the move."""
        frm, to = move
        fr, fc = frm
        tr, tc = to

        new_board = _deep_copy_board(self.board)

        # Apply the move to new_board (mirror your C++ next_state logic)
        # ...

        ns = YourGameState(new_board, 1 - self.player, self.step + 1)
        ns.last_move = move
        ns.hash_counts = dict(self.hash_counts)
        key = self.position_key()
        ns.hash_counts[key] = ns.hash_counts.get(key, 0) + 1

        if self.game_state != "win":
            ns.get_legal_actions()

        return ns

    def check_game_over(self):
        """Check if the game is over.

        Returns:
            ("win", winner_player)
            ("checkmate", winner_player)   -- for chess-like games
            ("draw", None)
            (None, None)                   -- game continues
        """
        if self.game_state == "win":
            return ("win", self.player)

        # 4-fold repetition
        key = self.position_key()
        if self.hash_counts.get(key, 0) + 1 >= 4:
            return ("draw", None)

        # MAX_STEP adjudication
        if self.step > cfg.MAX_STEP:
            # Compare material...
            return ("draw", None)  # or ("win", winner)

        return (None, None)

    def copy(self):
        """Return a deep copy."""
        s = YourGameState.__new__(YourGameState)
        s.board = _deep_copy_board(self.board)
        s.player = self.player
        s.step = self.step
        s.game_state = self.game_state
        s.legal_actions = list(self.legal_actions)
        s.last_move = self.last_move
        s.hash_counts = dict(self.hash_counts)
        return s


def format_move(move):
    """Format a move as a human-readable string (e.g. 'A1->B2')."""
    (fr, fc), (tr, tc) = move
    return (
        f"{cfg.COL_LABELS[fc]}{cfg.ROW_LABELS[fr]}->"
        f"{cfg.COL_LABELS[tc]}{cfg.ROW_LABELS[tr]}"
    )
```

### 5.2 Create the Renderer

**File:** `gui/games/{game}_renderer.py`

```python
"""YourGame renderer -- draws pieces on the board."""

import pygame

try:
    import gui.config as cfg
except ImportError:
    import config as cfg


class YourGameRenderer:
    def __init__(self, surface):
        self.surface = surface
        self.font = pygame.font.SysFont("segoeuisymbol", cfg.FONT_SIZE_PIECE)

    def draw_pieces(self, state):
        """Render all pieces on the board."""
        for row in range(cfg.BOARD_H):
            for col in range(cfg.BOARD_W):
                # Determine what piece is here
                piece_char = None
                color = None
                for p in range(2):
                    pt = state.board[p][row][col]
                    if pt:
                        piece_char = "?"  # map to Unicode/symbol
                        color = cfg.PLAYER_COLORS.get(p, (200, 200, 200))
                        break
                if piece_char is None:
                    continue

                sx = cfg.BOARD_X + col * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                sy = cfg.BOARD_Y + row * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                text_surf = self.font.render(piece_char, True, color)
                rect = text_surf.get_rect(center=(sx, sy))
                self.surface.blit(text_surf, rect)

    def draw_pv(self, state, pv_moves):
        """Optional: render principal variation ghost pieces."""
        pass
```

Study `gui/games/minichess_renderer.py` for chess pieces (Unicode glyphs)
or `gui/games/gomoku_renderer.py` for stones (drawn as circles).

---

## Step 6: Add NNUE Training Config

**File:** `nnue-train/game_config.py`

Add an entry to the `GAME_CONFIGS` dictionary:

```python
GAME_CONFIGS: Dict[str, dict] = {
    # ... existing entries ...
    "yourgame": {
        "board_h": 8,
        "board_w": 8,
        "num_piece_types": 6,          # total types (excl. EMPTY)
        "num_pt_no_king": 5,           # types minus king
        "king_id": 6,                  # piece ID for king (None if no king)
        "piece_names": [".", "A", "B", "C", "D", "E", "K"],
        "has_hand": False,             # True for shogi-like games
        "num_hand_types": 0,           # number of droppable piece types
    },
}
```

The `get_game_config()` function automatically derives computed fields
(`num_squares`, `halfkp_size`, `ps_size`, `policy_size`, etc.) from these
base values, so you only need to specify the base config.

---

## Step 7: Register in GUI, CLI, and Config

### 7.1 Register in `gui/main.py`

**`_get_game_module()`** -- Add a branch before the default (MiniChess)
fallback:

```python
def _get_game_module(game_name):
    if game_name in ("YourGame", "yourgame"):
        try:
            from gui.games.yourgame_engine import (
                YourGameState, format_move, PLAYER_LABELS, PLAYER_COLORS,
            )
            from gui.games.yourgame_renderer import YourGameRenderer
        except ImportError:
            from games.yourgame_engine import (
                YourGameState, format_move, PLAYER_LABELS, PLAYER_COLORS,
            )
            from games.yourgame_renderer import YourGameRenderer
        return YourGameState, format_move, YourGameRenderer, PLAYER_LABELS, PLAYER_COLORS
    # ... existing games ...
```

**`_configure_board_size()`** -- Add a branch:

```python
def _configure_board_size(game_name):
    if game_name in ("YourGame", "yourgame"):
        _cfg.BOARD_H = 8
        _cfg.BOARD_W = 8
        _cfg.SQUARE_SIZE = 60
        _cfg.MAX_STEP = 200
        _cfg.SCORE_PLOT_MAX_CP = 500
        _cfg.SCORE_DISPLAY_DIV = 100
    # ... existing games ...
```

### 7.2 Register in `gui/config.py`

Add piece symbols to `GAME_PIECES`:

```python
GAME_PIECES = {
    # ... existing entries ...
    "YourGame": {
        0: {1: "A", 2: "B", ...},    # player 0 piece symbols
        1: {1: "a", 2: "b", ...},    # player 1 piece symbols
    },
}
```

### 7.3 Register in `cli/cli.py`

Add a branch to `_init_game()`:

```python
def _init_game(game_name, board_size=None):
    if game_name == "yourgame":
        from cli.games.yourgame import get_context
        _game_ctx.update(get_context())
    # ... existing games ...
```

### 7.4 Create the CLI Module

**File:** `cli/games/{game}.py`

```python
"""YourGame CLI module -- board display, human input, game logic."""

import sys

try:
    from gui.games.yourgame_engine import YourGameState, format_move
    from gui.ubgi_client import UBGIEngine
except ImportError:
    raise ImportError("CLI requires gui.games.yourgame_engine on sys.path.")

BOARD_H = 8
BOARD_W = 8
MAX_STEP = 200
COL_LABELS = "ABCDEFGH"
ROW_LABELS = "87654321"

# Unicode symbols for terminal display
PIECE_UNICODE = {
    0: {1: "A", 2: "B", ...},
    1: {1: "a", 2: "b", ...},
}


def print_board(state, game_ctx):
    """Print the board to the terminal."""
    print()
    print("    " + "  ".join(game_ctx["col_labels"]))
    for r in range(game_ctx["board_h"]):
        rank_label = game_ctx["row_labels"][r]
        row_chars = []
        for c in range(game_ctx["board_w"]):
            w_piece = state.board[0][r][c]
            b_piece = state.board[1][r][c]
            if w_piece:
                row_chars.append(game_ctx["piece_unicode"][0][w_piece])
            elif b_piece:
                row_chars.append(game_ctx["piece_unicode"][1][b_piece])
            else:
                row_chars.append(".")
        print(f" {rank_label}  " + "  ".join(row_chars) + f"  {rank_label}")
    print("    " + "  ".join(game_ctx["col_labels"]))
    print()


def get_human_move(state, game_ctx):
    """Prompt the human for a move. Return the move tuple."""
    legal = state.legal_actions
    player_name = "P1" if state.player == 0 else "P2"

    print(f"  {player_name}'s legal moves:")
    for i, mv in enumerate(legal):
        print(f"  {i + 1:>3}. {game_ctx['format_move'](mv)}", end="")
        if (i + 1) % 4 == 0:
            print()
    print()

    while True:
        try:
            raw = input("  Enter move number or algebraic: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGame aborted.")
            sys.exit(0)
        if not raw:
            continue
        try:
            num = int(raw)
            if 1 <= num <= len(legal):
                return legal[num - 1]
        except ValueError:
            pass
        uci_str = raw.replace("-", "").replace(">", "").lower()
        try:
            move = game_ctx["uci_to_move"](uci_str)
            if move in legal:
                return move
        except (ValueError, IndexError, KeyError):
            pass
        print(f"  Could not parse '{raw}'.")


def check_game_over(state):
    """Return (result, winner) or (None, None)."""
    result, winner = state.check_game_over()
    if result:
        return (result, winner)
    if not state.legal_actions:
        return ("no_moves", 1 - state.player)
    return (None, None)


def apply_move(state, uci_str, game_ctx):
    """Apply a UBGI move string. Return (new_state, move_tuple)."""
    move = game_ctx["uci_to_move"](uci_str)
    return state.next_state(move), move


def get_context():
    """Return the game context dict."""
    return {
        "name": "yourgame",
        "state_class": YourGameState,
        "format_move": format_move,
        "uci_to_move": UBGIEngine.uci_to_move,
        "move_to_uci": UBGIEngine.move_to_uci,
        "board_h": BOARD_H,
        "board_w": BOARD_W,
        "max_step": MAX_STEP,
        "piece_unicode": PIECE_UNICODE,
        "col_labels": COL_LABELS,
        "row_labels": ROW_LABELS,
        "print_board": print_board,
        "get_human_move": get_human_move,
        "check_game_over": check_game_over,
        "apply_move": apply_move,
    }
```

---

## Build and Test

### Build

```bash
make yourgame
```

### Test the UBGI Protocol

Run the engine binary and verify the handshake:

```
$ ./build/yourgame-ubgi
ubgi
# Expected: id name YourGame
#           option name GameName ...
#           option name BoardWidth type spin default 8 ...
#           option name BoardHeight type spin default 8 ...
#           ubgiok
isready
# Expected: readyok
position startpos
go depth 4
# Expected: info depth 1 ... info depth 4 ... bestmove <move>
d
# Expected: board display with correct layout
quit
```

### Test with CLI (AI vs AI)

```bash
python -m cli.cli --game yourgame \
    --white build/yourgame-ubgi --black build/yourgame-ubgi \
    --depth 4 --games 2
```

### Test with GUI

```bash
python -m gui.main --game yourgame
```

Select the engine executable in the GUI's engine selector. Verify that:
- The board renders correctly
- Clicking shows legal move highlights
- Moves apply and the game progresses
- Game-over is detected

### Generate Training Data (Optional)

```bash
make yourgame-datagen
./build/yourgame-datagen -n 1000 -d 6 -o data/yourgame_train.bin
```

---

## Common Pitfalls

1. **`game_state` not set correctly.** If `get_legal_actions()` does not set
   `game_state = NONE` at the start, the search will malfunction. If you
   forget to set `game_state = WIN` when a king capture is available, the
   engine will play past checkmate.

2. **Python state desyncs from C++.** The GUI's Python state must produce
   exactly the same legal moves in the same encoding as the C++ engine.
   If they disagree, the GUI will reject engine moves. Test by running
   AI-vs-AI in the GUI and watching for errors in the console.

3. **Forgetting `inherit_history()` in `next_state()`.** Without this call,
   repetition detection will not work and the engine may loop forever.

4. **Wrong `-I` flags in Makefile.** The include path must list your game
   directory FIRST (`-Isrc/games/yourgame`), then `-Isrc/state -Isrc`.
   If the order is wrong, the compiler may pick up another game's
   `config.hpp` or `state.hpp`.

5. **Heap allocation.** `next_state()` must return `new State(...)`. The
   search engine expects to `delete` child states. Stack-allocated or
   `shared_ptr` states will cause crashes.

6. **`encode_board` / `decode_board` mismatch.** If encoding and decoding are
   not perfect inverses, `position board` commands will produce corrupt
   states. Test round-trip: `encode_board()` then `decode_board()` should
   produce an identical board.

---

## Checklist

**C++ Engine:**
- [ ] `src/games/{game}/config.hpp` -- `BOARD_H`, `BOARD_W`, `MAX_STEP`, piece types, `NUM_PIECE_TYPES`
- [ ] `src/games/{game}/state.hpp` -- `Board` struct with starting position, `State` class declaration
- [ ] `src/games/{game}/state.cpp` -- all virtual methods implemented:
  - [ ] Default constructor (starting position)
  - [ ] `get_legal_actions()` -- sets `game_state`, populates `legal_actions`
  - [ ] `next_state()` -- applies move, calls `inherit_history()`, calls `get_legal_actions()`
  - [ ] `evaluate()` -- returns score from current player's perspective
  - [ ] `encode_board()` / `decode_board()` -- round-trip serialization
  - [ ] `encode_output()` -- display string
  - [ ] `cell_display()` -- 3-char cell string
  - [ ] `hash()` -- Zobrist hashing
  - [ ] `piece_at()` -- piece query for move ordering
  - [ ] `create_null_state()` -- null move pruning support
  - [ ] `extract_nnue_features()` -- NNUE feature extraction (if training)
  - [ ] `game_name()` returns your game name
  - [ ] `board_h()` / `board_w()` return correct dimensions

**Build:**
- [ ] `Makefile` -- include paths, engine target, datagen/selfplay/benchmark targets
- [ ] `make {game}` compiles without errors
- [ ] `./build/{game}-ubgi` starts and responds to `ubgi` / `isready` / `quit`

**UBGI Protocol:**
- [ ] `ubgi` response shows correct `GameName`, `BoardWidth`, `BoardHeight`
- [ ] `position startpos` + `go depth 4` returns a valid `bestmove`
- [ ] `position board <encoded> <side>` + `go` works
- [ ] `d` command displays the board correctly

**Python GUI:**
- [ ] `gui/games/{game}_engine.py` -- state class with `initial()`, `get_legal_actions()`, `next_state()`, `check_game_over()`, `format_move()`
- [ ] `gui/games/{game}_renderer.py` -- `draw_pieces()` renders correctly
- [ ] `gui/main.py` -- registered in `_get_game_module()` and `_configure_board_size()`
- [ ] `gui/config.py` -- piece symbols added to `GAME_PIECES`
- [ ] `python -m gui.main --game yourgame` launches and renders

**CLI:**
- [ ] `cli/games/{game}.py` -- `get_context()` returns complete context dict
- [ ] `cli/cli.py` -- registered in `_init_game()`
- [ ] `python -m cli.cli --game yourgame --white human --black build/{game}-ubgi` works

**NNUE Training:**
- [ ] `nnue-train/game_config.py` -- entry added to `GAME_CONFIGS`
- [ ] `make {game}-datagen` compiles
- [ ] `./build/{game}-datagen -n 10 -d 4` produces a valid data file
