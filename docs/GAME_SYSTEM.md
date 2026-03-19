# Multi-Game System

This document describes the architecture of the multi-game engine framework.
The same search algorithms, UBGI protocol layer, and infrastructure support
multiple two-player zero-sum board games with no game-specific knowledge in
the shared layers.

Currently implemented games: **MiniChess** (6x5) and **Gomoku** (9x9).

---

## 1. BaseState Interface

All game implementations derive from `BaseState` defined in
`src/state/base_state.hpp`. Search algorithms, the UBGI layer, and selfplay
interact only through this interface.

### Move type

```cpp
typedef std::pair<size_t, size_t> Point;
typedef std::pair<Point, Point> Move;
```

- **Board moves** (MiniChess): `Move(from_point, to_point)` where each point
  is `(row, col)`.
- **Placement moves** (Gomoku): `Move(point, point)` where `from == to`,
  representing a stone placement at that cell.

### GameState enum

```cpp
enum GameState { UNKNOWN = 0, WIN, DRAW, NONE };
```

`WIN` means the current player can capture the king (MiniChess) or the
previous player completed a winning line (Gomoku). `NONE` means the game
is still in progress.

### BaseState members and virtual methods

```cpp
class BaseState {
public:
    int player = 0;                        // Side to move: 0 or 1
    GameState game_state = UNKNOWN;
    std::vector<Move> legal_actions;

    virtual ~BaseState() = default;

    // --- Core game mechanics (pure virtual) ---
    virtual BaseState* next_state(const Move& m) = 0;
    virtual void get_legal_actions() = 0;
    virtual int evaluate(bool use_nnue = true, bool use_kp = true,
                         bool use_mobility = true) = 0;

    // --- Game description (pure virtual) ---
    virtual int board_h() const = 0;
    virtual int board_w() const = 0;
    virtual const char* game_name() const = 0;

    // --- Board serialization for UBGI protocol (pure virtual) ---
    virtual std::string encode_board() const = 0;
    virtual void decode_board(const std::string& s, int side_to_move) = 0;
    virtual std::string encode_output() const = 0;

    // --- Optional overrides (have default implementations) ---
    virtual BaseState* create_null_state() const;   // default: nullptr
    virtual int piece_at(int player, int row, int col) const; // default: 0
    virtual uint64_t hash() const;                  // default: 0
    virtual std::string cell_display(int row, int col) const; // default: " . "
};
```

**Key contracts:**

- `next_state()` returns a heap-allocated successor. Caller owns the pointer
  and is responsible for `delete`.
- `get_legal_actions()` populates `legal_actions` and sets `game_state` if
  the position is terminal.
- `evaluate()` returns an integer score from the current player's perspective.
  `P_MAX` (100000) means the current player wins.
- `hash()` returns a Zobrist hash for the transposition table.
- `create_null_state()` returns a state with the side-to-move flipped (for
  null move pruning). Returns `nullptr` for games that do not support it.
- `encode_board()` / `decode_board()` serialize the board for the UBGI
  `position board` command.

---

## 2. Per-Game Directory Structure

Each game lives in its own directory under `src/games/`:

```
src/games/{game}/
    config.hpp    -- BOARD_H, BOARD_W, game-specific constants
    state.hpp     -- Board class, State class (inherits BaseState)
    state.cpp     -- implementation of all virtual methods
```

Both MiniChess and Gomoku define a local `Board` class and a `State` class
that derives from `BaseState`. The `config.hpp` sets `BOARD_H` and `BOARD_W`
as preprocessor macros (guarded by `#ifndef` so they can be overridden at
compile time).

### MiniChess (`src/games/minichess/`)

- `config.hpp`: `BOARD_H=6`, `BOARD_W=5`, `MAX_STEP=100`, `USE_BITBOARD`
- `Board`: `char board[2][BOARD_H][BOARD_W]` -- two planes (one per player),
  piece types 1-6 (pawn, rook, knight, bishop, queen, king).
- `State::game_name()` returns `"MiniChess"`.
- Evaluation: NNUE (if compiled with `USE_NNUE`), KP eval (material +
  piece-square tables + king tropism), or simple material count.
- Move generation: bitboard-based (`get_legal_actions_bitboard()`) with a
  naive fallback.
- `create_null_state()`: returns a state with the side-to-move flipped.

### Gomoku (`src/games/gomoku/`)

- `config.hpp`: `BOARD_H=9`, `BOARD_W=9`, `WIN_LENGTH=5`
- `Board`: `char board[BOARD_H][BOARD_W]` -- single plane, 0=empty, 1=player1,
  2=player2.
- `State::game_name()` returns `"Gomoku"`.
- Evaluation: threat-counting heuristic (five-in-a-row, open-4, half-4,
  open-3, etc.) with decisive threat detection.
- Legal actions: empty cells within Manhattan distance 2 of existing stones.
- `create_null_state()`: returns `nullptr` (no null move pruning for Gomoku).

---

## 3. Build System

The `Makefile` defines per-game targets with different include paths:

```makefile
MINICHESS_INC = -Isrc/games/minichess -Isrc/state -Isrc
GOMOKU_INC    = -Isrc/games/gomoku -Isrc/state -Isrc
```

Each game compiles against the same shared source files (search algorithms,
UBGI protocol, NNUE) but links its own `state.cpp`:

```makefile
minichess:
    $(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o build/minichess-ubgi \
        src/games/minichess/state.cpp src/nnue/nnue.cpp \
        src/policy/*.cpp src/ubgi/ubgi.cpp

gomoku:
    $(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o build/gomoku-ubgi \
        src/games/gomoku/state.cpp src/nnue/nnue.cpp \
        src/policy/*.cpp src/ubgi/ubgi.cpp
```

Because each game's directory contains `config.hpp` and `state.hpp` with the
same file names, the `-I` flag selects the correct game at compile time. The
shared code (`ubgi.cpp`, `pvs.cpp`, etc.) includes `"state.hpp"` and
`"config.hpp"` without a path prefix, resolving to whichever game's directory
is first in the include path.

---

## 4. UBGI Protocol Integration

The UBGI engine (`src/ubgi/ubgi.cpp`) is game-agnostic. It:

1. Constructs `State` and `Board` objects using the game-specific headers
   resolved by the include path.
2. Converts between UBGI move strings and internal `Move` tuples via
   `move_to_str()` / `str_to_move()` functions that detect placement moves
   (2-char, `from == to`) vs board moves (4-char).
3. Reports `GameName`, `BoardWidth`, `BoardHeight` from the compiled game's
   constants during the UBGI handshake.
4. Delegates search to the algorithm registry (`src/policy/registry.hpp`).

The `position board <encoded> <side> [moves ...]` command uses
`State::decode_board()` to load an arbitrary board position.

---

## 5. GUI Per-Game Modules

The Python GUI (`gui/`) uses a per-game module pattern:

```
gui/games/
    {game}_engine.py    -- Python state class, format_move, PLAYER_LABELS, PLAYER_COLORS
    {game}_renderer.py  -- draw_pieces(), optionally draw_pv()
```

### Engine modules

Each engine module exports:

- A state class (e.g., `MiniChessState`, `GomokuState`) with `initial()`,
  `next_state()`, `check_game_over()`, `legal_actions`, `current_player`.
- `format_move(move)` -- human-readable move string.
- `PLAYER_LABELS` -- dict `{0: "White", 1: "Black"}` (or similar).
- `PLAYER_COLORS` -- dict of RGB tuples for rendering.

### Renderer modules

Each renderer class implements:

- `draw_pieces(state)` -- renders the board pieces on the Pygame surface.
- `draw_pv(state, pv_moves)` (optional) -- renders principal variation ghosts.

### Registration

Games are registered in `gui/main.py`:

- `_get_game_module(game_name)` -- returns `(StateClass, format_move,
  RendererClass, player_labels, player_colors)` for the given game name.
- `_configure_board_size(game_name)` -- sets `config.BOARD_H`, `BOARD_W`,
  `SQUARE_SIZE`, and recalculates layout dimensions.

The `BoardRenderer` class (`gui/board_renderer.py`) is game-agnostic. It
draws squares, labels, highlights, and legal move indicators. It delegates
piece rendering to the game-specific renderer via `self.game_renderer`.

---

## 6. CLI Per-Game Modules

The CLI (`cli/`) uses a similar per-game module pattern:

```
cli/games/
    {game}.py   -- print_board, get_human_move, get_context, check_game_over, apply_move
```

Each module exports:

- `print_board(state, game_ctx)` -- terminal board display.
- `get_human_move(state, game_ctx)` -- interactive move input.
- `check_game_over(state)` -- returns `(result, winner)`.
- `apply_move(state, uci_str, game_ctx)` -- applies a UBGI move string.
- `get_context()` -- returns a dict with game-specific functions and constants.

The CLI dispatcher (`cli/cli.py`) calls `_init_game(game_name)` to populate
a game context dict, then runs the game loop using game-agnostic engine
communication via the UBGI protocol.

---

## 7. Search Algorithm Compatibility

Search algorithms (PVS, AlphaBeta, MiniMax, Random) interact with game state
exclusively through the `State` class, which inherits `BaseState`. They use
only these members:

```
state->player
state->game_state
state->legal_actions
state->get_legal_actions()
state->next_state(move)
state->evaluate(...)
state->hash()
state->create_null_state()
```

The algorithm registry (`src/policy/registry.hpp`) stores:

```cpp
struct AlgoEntry {
    std::string name;
    ParamMap default_params;
    std::vector<ParamDef> param_defs;
    std::function<SearchResult(State*, int, SearchContext&)> search;
};
```

No search algorithm inspects the board array, checks piece types, or uses
coordinate geometry. The same compiled PVS that plays MiniChess plays Gomoku
(each compiled as a separate binary with different include paths).

---

## 8. File Layout

```
src/
    state/
        base_state.hpp              # BaseState abstract class + Move typedef
    games/
        minichess/
            config.hpp              # BOARD_H=6, BOARD_W=5, piece display
            state.hpp               # Board, State : BaseState
            state.cpp               # move gen, eval, hash, serialization
        gomoku/
            config.hpp              # BOARD_H=9, BOARD_W=9, WIN_LENGTH=5
            state.hpp               # Board, State : BaseState
            state.cpp               # move gen, threat eval, hash, serialization
    policy/
        pvs.hpp, pvs.cpp            # PVS search (uses State*)
        pvs/
            tt.hpp                  # Transposition table
            killer_moves.hpp        # Killer move heuristic
            move_ordering.hpp       # MVV-LVA and killer ordering
            quiescence.hpp          # Quiescence search
        alphabeta.hpp, alphabeta.cpp
        minimax.hpp, minimax.cpp
        random.hpp, random.cpp
        registry.hpp                # AlgoEntry, get_algo_table(), find_algo()
    ubgi/
        ubgi.cpp                    # UBGI protocol engine (main loop)
    search_types.hpp                # SearchResult, SearchContext, RootUpdate
    search_params.hpp               # ParamMap, ParamDef, param_bool, param_int
    config.hpp                      # Shared compile-time flags

gui/
    main.py                         # GUI entry point, GameApp
    config.py                       # Layout constants, piece symbols
    board_renderer.py               # Game-agnostic board renderer
    ubgi_client.py                  # UBGI engine subprocess client
    ui_panels.py                    # Side panel, eval bar, score plot
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
