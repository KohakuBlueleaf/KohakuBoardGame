# Adding a New Game

Step-by-step guide for adding a new two-player board game to the engine.
Use MiniChess and Gomoku as reference implementations.

---

## 1. C++ Engine (`src/games/{game}/`)

Create three files in a new directory `src/games/{game}/`.

### 1.1 `config.hpp`

Define board dimensions and game-specific constants.

```cpp
#pragma once
#include "../../config.hpp"

#ifndef BOARD_H
#define BOARD_H 8        // your board height
#endif
#ifndef BOARD_W
#define BOARD_W 8        // your board width
#endif

#define MAX_STEP 200     // maximum moves before draw (0 = no limit)
```

The `#ifndef` guards allow the dimensions to be overridden via `-D` flags
at compile time.

**Reference:** `src/games/minichess/config.hpp`, `src/games/gomoku/config.hpp`

### 1.2 `state.hpp`

Define a `Board` class and a `State` class that inherits from `BaseState`.

```cpp
#pragma once
#include "base_state.hpp"
#include "config.hpp"
#include <cstring>
#include <sstream>

class Board {
public:
    // Your board representation. Examples:
    // MiniChess: char board[2][BOARD_H][BOARD_W]  (two planes, one per player)
    // Gomoku:    char board[BOARD_H][BOARD_W]      (single plane, 0/1/2)
};

class State : public BaseState {
public:
    Board board;
    int step = 0;

    State();
    State(Board board, int player);

    // --- Pure virtual overrides (required) ---
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
    const char* game_name() const override { return "YourGame"; }

    // --- Optional overrides ---
    uint64_t hash() const override;
    int piece_at(int player, int row, int col) const override;
    std::string cell_display(int row, int col) const override;
    BaseState* create_null_state() const override;
};
```

**Key decisions:**

- **Move representation**: `Move` is `std::pair<Point, Point>` where
  `Point = std::pair<size_t, size_t>`. For placement games (like Gomoku),
  set `from == to`. For board-move games (like chess), `from != to`.

- **`create_null_state()`**: Return a state with the side-to-move flipped
  if null move pruning makes sense for your game. Return `nullptr` if not
  (e.g., Gomoku returns nullptr).

- **`hash()`**: Implement Zobrist hashing for the transposition table. Use
  a deterministic seed so hashes are reproducible.

### 1.3 `state.cpp`

Implement all virtual methods. The key methods:

**`get_legal_actions()`**: Populate `legal_actions` and set `game_state`.
Set `game_state = WIN` if the current player has a winning move available
(MiniChess: can capture king) or if the game is already won. Set
`game_state = DRAW` if no moves remain and nobody wins.

**`next_state()`**: Create a new heap-allocated `State` with the move
applied. Call `get_legal_actions()` on the new state to detect terminal
conditions.

**`evaluate()`**: Return an integer score from the current player's
perspective. Use `P_MAX` (100000) for a win, 0 for a draw, and a heuristic
value for non-terminal positions. The `use_nnue`, `use_kp`, and
`use_mobility` flags can be ignored if not applicable.

**`encode_board()` / `decode_board()`**: Serialize/deserialize the board
as a compact string for the UBGI `position board` command. Use `/` to
separate rows. Use single characters for piece identities.

**`hash()`**: XOR together random 64-bit keys for each piece/cell and the
side to move. Initialize the key tables lazily on first call.

**Reference:**
- Board-move game: `src/games/minichess/state.cpp`
- Placement game: `src/games/gomoku/state.cpp`

---

## 2. Makefile Target

Add an include-path variable and a build target.

```makefile
YOURGAME_INC = -Isrc/games/yourgame -Isrc/state -Isrc

yourgame:
    $(CXX) $(CXXFLAGS) $(YOURGAME_INC) -o $(BUILD_DIR)/yourgame-ubgi \
        src/games/yourgame/state.cpp $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
```

If your game does not use NNUE, add `-DNO_NNUE`. See the `gomoku` target
for an example.

The `-I` flags ensure that `#include "state.hpp"` and `#include "config.hpp"`
in shared code resolve to your game's files.

Add the target to `.PHONY` and `all` if desired.

---

## 3. GUI (`gui/games/`)

Create two files in `gui/games/`.

### 3.1 `{game}_engine.py`

Python game state for the GUI. Exports:

```python
PLAYER_LABELS = {0: "Player 1", 1: "Player 2"}
PLAYER_COLORS = {0: (20, 20, 20), 1: (240, 240, 240)}

class YourGameState:
    def __init__(self):
        self.board = ...        # board data structure
        self.player = 0         # current player
        self.step = 0
        self.game_state = "none"
        self.legal_actions = []
        self.last_move = None

    @staticmethod
    def initial():
        """Return the starting-position state."""
        ...

    @property
    def current_player(self):
        return self.player

    def next_state(self, move):
        """Return a new state after applying the move."""
        ...

    def check_game_over(self):
        """Return (result, winner) -- result is 'win', 'draw', or None."""
        ...

def format_move(move):
    """Format a move as a human-readable string (e.g., 'E5')."""
    ...
```

**Reference:** `gui/games/gomoku_engine.py`, `gui/games/minichess_engine.py`

### 3.2 `{game}_renderer.py`

Pygame renderer for game-specific pieces. Exports a class with at least
`draw_pieces(state)`:

```python
import pygame
try:
    import gui.config as cfg
except ImportError:
    import config as cfg

class YourGameRenderer:
    def __init__(self, surface):
        self.surface = surface

    def draw_pieces(self, state):
        """Render pieces/stones on the board."""
        for row in range(cfg.BOARD_H):
            for col in range(cfg.BOARD_W):
                # Read state.board[row][col] and draw at the right pixel coords
                sx = cfg.BOARD_X + col * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                sy = cfg.BOARD_Y + row * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                ...

    def draw_pv(self, state, pv_moves):
        """Optional: render principal variation ghost pieces."""
        ...
```

**Reference:** `gui/games/gomoku_renderer.py` (stones as circles),
`gui/games/minichess_renderer.py` (chess pieces as Unicode glyphs)

### 3.3 Register in `gui/main.py`

Add your game to `_get_game_module()`:

```python
def _get_game_module(game_name):
    if game_name in ("YourGame", "yourgame"):
        from gui.games.yourgame_engine import YourGameState, format_move, PLAYER_LABELS, PLAYER_COLORS
        from gui.games.yourgame_renderer import YourGameRenderer
        return YourGameState, format_move, YourGameRenderer, PLAYER_LABELS, PLAYER_COLORS
    # ... existing games ...
```

Add your game to `_configure_board_size()`:

```python
def _configure_board_size(game_name):
    if game_name in ("YourGame", "yourgame"):
        _cfg.BOARD_H = 8
        _cfg.BOARD_W = 8
        _cfg.SQUARE_SIZE = 60
        _cfg.MAX_STEP = 200
    # ... existing games ...
    # Recalculate derived layout values (BOARD_PIXEL_W, etc.)
```

---

## 4. CLI (`cli/games/`)

Create `cli/games/{game}.py` with these functions:

```python
def print_board(state, game_ctx):
    """Print the board to the terminal."""
    ...

def get_human_move(state, game_ctx):
    """Prompt the human player for a move. Return the move tuple."""
    ...

def check_game_over(state):
    """Return (result, winner) or (None, None)."""
    ...

def apply_move(state, uci_str, game_ctx):
    """Apply a UBGI move string. Return (new_state, move_tuple)."""
    ...

def get_context():
    """Return a dict with game-specific functions and constants."""
    return {
        "name": "yourgame",
        "state_class": YourGameState,
        "format_move": format_move,
        "uci_to_move": ...,
        "move_to_uci": ...,
        "board_h": 8, "board_w": 8,
        "max_step": 200,
        "col_labels": "ABCDEFGH",
        "row_labels": "87654321",
        "print_board": print_board,
        "get_human_move": get_human_move,
        "check_game_over": check_game_over,
        "apply_move": apply_move,
    }
```

Register in `cli/cli.py` by adding a branch to `_init_game()`:

```python
def _init_game(game_name, board_size=None):
    if game_name == "yourgame":
        from cli.games.yourgame import get_context
        _game_ctx.update(get_context())
    # ... existing games ...
```

**Reference:** `cli/games/minichess.py`

---

## 5. Build and Test

### Build

```bash
make yourgame
```

### Test with UBGI protocol

Run the engine and interact manually:

```
$ ./build/yourgame-ubgi
ubgi
# Verify: id, options, ubgiok
isready
# Verify: readyok
position startpos
go depth 4
# Verify: info lines and bestmove
d
# Verify: board display looks correct
quit
```

### Test with CLI

```bash
python -m cli.cli --game yourgame \
    --white build/yourgame-ubgi --black build/yourgame-ubgi \
    --depth 4 --games 2
```

### Test with GUI

```bash
python -m gui.main --game yourgame
```

Select the engine executable in the GUI's engine selector.

---

## Checklist

- [ ] `src/games/{game}/config.hpp` -- board dimensions, constants
- [ ] `src/games/{game}/state.hpp` -- Board class, State class
- [ ] `src/games/{game}/state.cpp` -- all virtual method implementations
- [ ] `Makefile` -- new target with correct `-I` flags
- [ ] Build and run: `make {game} && ./build/{game}-ubgi`
- [ ] UBGI handshake: correct GameName, BoardWidth, BoardHeight
- [ ] `position startpos` + `go depth 4` returns a valid bestmove
- [ ] `position board ...` + `go` works with encoded board
- [ ] `d` command displays the board correctly
- [ ] `gui/games/{game}_engine.py` -- Python state class
- [ ] `gui/games/{game}_renderer.py` -- piece/stone renderer
- [ ] `gui/main.py` -- registered in `_get_game_module()` and `_configure_board_size()`
- [ ] `cli/games/{game}.py` -- CLI module
- [ ] `cli/cli.py` -- registered in `_init_game()`
