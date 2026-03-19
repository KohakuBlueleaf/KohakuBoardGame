# Multi-Game State System Design

This document describes the architecture for generalizing the MiniChess engine into a
multi-game framework. The goal is to allow the same search algorithms, UCI interface,
and NNUE evaluation infrastructure to support multiple two-player zero-sum board games
(MiniChess, Gomoku, Othello, MiniShogi, etc.) with no game-specific knowledge in the
shared layers.

---

## 1. Current Architecture

The engine is built around a single, concrete `State` class defined in
`src/state/state.hpp`. All game logic -- board representation, move generation,
evaluation, and state transitions -- lives directly in that class and its
implementation file `src/state/state.cpp`.

Key characteristics of the current design:

- **Board**: `Board` struct containing `char board[2][6][5]`, hard-coded to a 6x5
  MiniChess layout. Piece types 1-6 (pawn, rook, knight, bishop, queen, king) are
  encoded as small integers per player plane.

- **Move**: Defined globally as `typedef std::pair<Point, Point> Move` where
  `Point = std::pair<size_t, size_t>`. This encodes moves as (from_row, from_col)
  to (to_row, to_col) -- a representation that only works for piece-movement games.

- **Evaluation**: `State::evaluate()` supports three strategies at runtime:
  1. NNUE evaluation via `nnue::g_model.evaluate(board, player)`
  2. KP (King-Piece) handcrafted eval with material, piece-square tables, and king
     tropism
  3. Simple material-only eval

- **Search algorithms**: `PVS`, `AlphaBeta`, `MiniMax`, and `Random` all accept
  `State*` directly. The algorithm registry (`src/policy/registry.hpp`) stores
  function pointers typed as `std::function<SearchResult(State*, int, SearchContext&)>`.

- **NNUE**: The `nnue::Model` class in `src/nnue/nnue.hpp` knows about the Board
  struct directly. Feature extraction (`extract_features_ps`, `extract_features_halfkp`)
  is hard-coded to MiniChess piece/square geometry. Constants like `NUM_SQUARES = 30`,
  `NUM_PIECE_TYPES = 6`, and `HALFKP_SIZE = 9000` are compile-time values.

- **UCI**: `src/uci/uci.hpp` defines move-string conversion functions that assume the
  MiniChess coordinate system (columns A-E, rows 1-6).

- **Config**: `src/config.hpp` defines `BOARD_H = 6`, `BOARD_W = 5` as preprocessor
  macros used throughout the codebase.

The central problem: every layer -- from move representation to NNUE feature indexing
-- is coupled to the 6x5 MiniChess geometry and its piece set.

---

## 2. Move Type

The current `Move` type (`pair<Point, Point>`) cannot represent:
- Pass moves (Othello, Go)
- Stone placement from hand (Gomoku, Go)
- Piece drops from captured reserve (Shogi)

A universal move representation replaces it:

```cpp
struct Move {
    int piece_type;  // 0 = irrelevant (gomoku/othello), 1-N = piece types
    int from;        // source square index (row * W + col), -1 = hand/place
    int to;          // destination square index, -1 = pass

    // Convenience predicates
    bool is_pass() const { return to == -1; }
    bool is_drop() const { return from == -1 && to >= 0; }
    bool is_board_move() const { return from >= 0 && to >= 0; }

    // Comparison for use in containers (TT, killer tables, etc.)
    bool operator==(const Move& o) const {
        return piece_type == o.piece_type && from == o.from && to == o.to;
    }
    bool operator!=(const Move& o) const { return !(*this == o); }
};
```

Coverage by game type:

| Game      | piece_type | from     | to        | Example               |
|-----------|------------|----------|-----------|-----------------------|
| MiniChess | 1-6        | sq index | sq index  | Knight c1 -> b3       |
| Gomoku    | 0          | -1       | sq index  | Place stone at (4,7)  |
| Othello   | 0          | -1       | sq index  | Place disc at (3,5)   |
| Othello   | 0          | -1       | -1        | Pass                  |
| MiniShogi | 1-5        | sq index | sq index  | Board move            |
| MiniShogi | 1-5        | -1       | sq index  | Drop from hand        |

The flat square index `row * W + col` is used instead of a (row, col) pair because:
- It maps directly to bitboard indices and NNUE feature indices.
- It requires a single integer comparison in hash tables and killer move slots.
- Each game's `board_w()` provides the column count for decoding when needed.

---

## 3. BaseState Interface

All game implementations derive from a common abstract class. Search algorithms,
the UCI layer, and the selfplay driver interact only through this interface.

```cpp
class BaseState {
public:
    int player;                       // Side to move: 0 or 1
    GameState game_state;             // WIN, DRAW, NONE
    std::vector<Move> legal_actions;  // Populated by get_legal_actions()

    virtual ~BaseState() = default;

    // ---- Core game mechanics ----

    // Apply move, return a new heap-allocated successor state.
    // Caller owns the returned pointer.
    virtual BaseState* next_state(const Move& m) = 0;

    // Populate this->legal_actions. Also sets game_state if terminal.
    virtual void get_legal_actions() = 0;

    // Evaluate the position from the current player's perspective.
    // Returns centipawn-scale integer. +P_MAX means current player wins.
    virtual int evaluate(bool use_nnue = true,
                         bool use_kp = true,
                         bool use_mobility = true) = 0;

    // ---- Game description (constant per game type) ----

    virtual int board_h() const = 0;           // e.g. 6 for MiniChess
    virtual int board_w() const = 0;           // e.g. 5 for MiniChess
    virtual int num_piece_types() const = 0;   // e.g. 6 for MiniChess, 0 for Gomoku
    virtual const char* game_name() const = 0; // e.g. "minichess"

    // ---- Display / protocol ----

    // Encode the full board state as a human-readable string.
    virtual std::string encode_output() const = 0;

    // Convert between Move and its string form (e.g. "a6c5", "d4", "pass").
    virtual std::string move_to_string(const Move& m) const = 0;
    virtual Move string_to_move(const std::string& s) const = 0;

    // ---- NNUE feature extraction ----

    // Write active feature indices into feature_indices[] from the given
    // perspective (0 = white, 1 = black). Returns the number of active
    // features written. max_features is the buffer capacity.
    virtual int extract_features(int perspective,
                                 int* feature_indices,
                                 int max_features) const = 0;

    // Total feature space dimensionality for this game.
    // This is the input size for the NNUE feature transformer.
    virtual int feature_size() const = 0;
};
```

Design notes:

- **Heap-allocated successors**: `next_state()` returns `BaseState*` (owned by
  caller). This matches the current convention where search algorithms `delete`
  states after backtracking. A future optimization could use an arena allocator
  or a `revert_move()` method to avoid allocation in the search loop.

- **GameState enum**: The existing `GameState { UNKNOWN, WIN, DRAW, NONE }` enum
  is reused. `WIN` means the *previous* player (who just moved) has won. `NONE`
  means the game is still in progress.

- **Evaluation flags**: The `use_nnue`, `use_kp`, `use_mobility` booleans let
  algorithms selectively disable evaluation components. Games that lack a KP
  concept (Gomoku) simply ignore `use_kp`.

---

## 4. Game Implementation Pattern

### 4.1 MiniChess (migration from current State)

```cpp
class MiniChessState : public BaseState {
    Board board;   // char board[2][6][5]
    int step;      // move counter for draw-by-length

public:
    MiniChessState();
    MiniChessState(const Board& b, int player, int step);

    // -- Core mechanics (existing logic, re-typed to new Move) --
    BaseState* next_state(const Move& m) override;
    void get_legal_actions() override;
    int evaluate(bool use_nnue, bool use_kp, bool use_mobility) override;

    // -- Game description --
    int board_h() const override { return 6; }
    int board_w() const override { return 5; }
    int num_piece_types() const override { return 6; }
    const char* game_name() const override { return "minichess"; }

    // -- Display / protocol --
    std::string encode_output() const override;
    std::string move_to_string(const Move& m) const override;
    Move string_to_move(const std::string& s) const override;

    // -- NNUE --
    int extract_features(int perspective, int* features, int max) const override;
    int feature_size() const override;
    // feature_size() returns HALFKP_SIZE (9000) or PS_SIZE (360)
    // depending on the model version.
};
```

The internal move generation still operates on the 2-plane `char board[2][6][5]`
(and optionally bitboards). The only change is converting internal move
representation to/from the universal `Move` struct at the boundary.

### 4.2 Gomoku (new game)

```cpp
template<int H = 9, int W = 9>
class GomokuState : public BaseState {
    // Simple: one plane per player, 0 = empty, 1 = occupied
    char stones[2][H][W];

public:
    BaseState* next_state(const Move& m) override;
    void get_legal_actions() override;      // all empty squares
    int evaluate(bool use_nnue, bool, bool) override;

    int board_h() const override { return H; }
    int board_w() const override { return W; }
    int num_piece_types() const override { return 0; }
    const char* game_name() const override { return "gomoku9"; }

    std::string encode_output() const override;
    std::string move_to_string(const Move& m) const override;
    // Format: "d4" -- column letter + row number
    Move string_to_move(const std::string& s) const override;

    int extract_features(int perspective, int* features, int max) const override;
    int feature_size() const override { return 2 * H * W; }
    // Feature index: color * H*W + row*W + col
};
```

Since Gomoku has no piece types, `piece_type` is always 0 and `from` is always -1.
Moves are pure placements: `Move{0, -1, row*W+col}`.

### 4.3 Othello (new game)

```cpp
class OthelloState : public BaseState {
    uint64_t discs[2];  // bitboard per player (8x8 = 64 bits)

public:
    BaseState* next_state(const Move& m) override;
    void get_legal_actions() override;  // legal placements + possible pass
    int evaluate(bool use_nnue, bool, bool) override;

    int board_h() const override { return 8; }
    int board_w() const override { return 8; }
    int num_piece_types() const override { return 0; }
    const char* game_name() const override { return "othello"; }

    std::string encode_output() const override;
    std::string move_to_string(const Move& m) const override;
    // "d3" for placement, "pass" for pass
    Move string_to_move(const std::string& s) const override;

    int extract_features(int perspective, int* features, int max) const override;
    int feature_size() const override { return 2 * 64; }
    // Feature: color * 64 + square
};
```

Pass moves are `Move{0, -1, -1}`. The search framework handles them naturally
because `next_state()` simply flips the side to move without altering the board.

### 4.4 MiniShogi (future game)

```cpp
class MiniShogiState : public BaseState {
    char board[2][5][5];   // piece types on board
    int hand[2][5];        // captured pieces in hand, by type

public:
    BaseState* next_state(const Move& m) override;
    void get_legal_actions() override;  // board moves + drops
    int evaluate(bool use_nnue, bool use_kp, bool use_mobility) override;

    int board_h() const override { return 5; }
    int board_w() const override { return 5; }
    int num_piece_types() const override { return 5; }
    const char* game_name() const override { return "minishogi"; }

    std::string move_to_string(const Move& m) const override;
    // Board move: "b3c4", Drop: "P*c3"
    Move string_to_move(const std::string& s) const override;

    // ...
};
```

Drops use `Move{piece_type, -1, to_square}`. Board moves use
`Move{piece_type, from_square, to_square}`. The `piece_type` field is essential
for drops because it specifies which piece to place from hand.

---

## 5. Search Algorithm Compatibility

Search algorithms (PVS, AlphaBeta, MiniMax, Random) interact with game state
exclusively through the `BaseState` interface. They require no game-specific
knowledge.

### 5.1 Interface contract used by search

Every search algorithm uses only these members and methods:

```
state->player            // who is to move
state->game_state        // terminal check (WIN / DRAW / NONE)
state->legal_actions     // list of moves (after get_legal_actions())
state->get_legal_actions()
state->next_state(move)  // generate successor
state->evaluate(...)     // static evaluation
```

No search algorithm inspects the board array, checks piece types, or uses
coordinate geometry. This means the same PVS implementation that plays MiniChess
can play Othello or Gomoku without modification.

### 5.2 Required signature changes

The current signatures use `State*`:

```cpp
// Current (game-specific)
static SearchResult PVS::search(State *state, int depth, SearchContext& ctx);
static int PVS::eval_ctx(State *state, int depth, int alpha, int beta,
                          SearchContext& ctx, const PVSParams& p, int ply, bool can_null);
```

These become:

```cpp
// New (game-generic)
static SearchResult PVS::search(BaseState *state, int depth, SearchContext& ctx);
static int PVS::eval_ctx(BaseState *state, int depth, int alpha, int beta,
                          SearchContext& ctx, const PVSParams& p, int ply, bool can_null);
```

The algorithm registry type changes accordingly:

```cpp
struct AlgoEntry {
    std::string name;
    ParamMap default_params;
    std::vector<ParamDef> param_defs;
    std::function<SearchResult(BaseState*, int, SearchContext&)> search;
};
```

### 5.3 Move-dependent components

Some search internals reference `Move` directly:

- **Transposition table**: Stores `Move best_move` per entry. The new `Move`
  struct is a plain-old-data type with three ints, so it slots into the TT
  without changes.

- **Killer moves**: Stores `Move` per ply. Same: no changes needed.

- **Move ordering**: Sorts `legal_actions` by heuristic scores. Uses
  `state->evaluate()` on child states. No game-specific logic.

- **PV extraction**: Walks the TT to reconstruct the principal variation as
  `std::vector<Move>`. No changes needed.

- **Quiescence search**: Currently relies on MiniChess-specific capture
  detection. This must be abstracted. Options:
  1. Add `virtual bool is_capture(const Move& m) const` to BaseState.
  2. Add `virtual bool is_quiet() const` to indicate if a position is quiet.
  3. Games that lack a capture concept (Gomoku) return `true` from `is_quiet()`
     to disable quiescence entirely.

### 5.4 Null move pruning

Null move pruning passes the turn without making a move. In the current code this
creates a `State` with the opponent to move. With the new system:

- Games that support null move: provide a `next_state(null_move)` where
  `null_move = Move{0, -1, -1}` (a pass).
- Games where passing is illegal (MiniChess): the null move is a search-internal
  fiction. `next_state(pass_move)` just flips `player` without changing the board.
- Games where passing is a legal move (Othello): care must be taken to
  distinguish a "real pass" (legal action) from a "null move" (search pruning).
  The search should skip null move pruning when a pass is in `legal_actions`.

---

## 6. NNUE Per-Game

### 6.1 Architecture overview

The NNUE network has two logical halves:

1. **Feature transformer** (game-specific): Maps a sparse set of active feature
   indices to a dense accumulator vector. The feature vocabulary and extraction
   logic are entirely game-dependent.

2. **Dense layers** (shared architecture): Accumulator -> L1 -> L2 -> output.
   The layer sizes are stored in the model file header and are not hard-coded.

### 6.2 Game-specific feature extraction

Feature extraction moves from `nnue::Model` to the `BaseState` subclass via the
virtual method:

```cpp
int extract_features(int perspective, int* feature_indices, int max_features) const;
int feature_size() const;
```

Each game defines its own feature scheme:

| Game      | Feature scheme                | feature_size | Typical active |
|-----------|-------------------------------|--------------|----------------|
| MiniChess | HalfKP (king-sq x piece-sq)  | 9000         | ~10-15         |
| MiniChess | PS (piece-square only)        | 360          | ~10-15         |
| Gomoku 9  | Stone positions per color     | 162          | ~20-40         |
| Othello   | Disc positions per color      | 128          | ~4-60          |
| MiniShogi | HalfKP + hand pieces          | ~7000        | ~10-15         |

### 6.3 Model structure

The model file already stores dimensions in its header:

```
[version][feature_size][accum_size][l1_size][l2_size]
[ft_weight: feature_size * accum_size floats]
[ft_bias: accum_size floats]
[l1_weight: l1_size * (accum_size * 2) floats]
[l1_bias: l1_size floats]
[l2_weight: l2_size * l1_size floats]
[l2_bias: l2_size floats]
[out_weight: l2_size floats]
[out_bias: 1 float]
```

Because `feature_size` is read from the file (not a compile-time constant), the
same `Model::load()` and inference code can handle any game's model -- as long as
the feature indices produced by `extract_features()` fall within `[0, feature_size)`.

### 6.4 Model loading by game name

Each game uses a separate trained model file:

```cpp
namespace nnue {
    // Instead of a single global model, maintain a registry:
    Model* get_model(const std::string& game_name);

    bool init_game(const std::string& game_name, const char* path);
    // "minichess" -> loads "models/minichess_nnue.bin"
    // "gomoku9"   -> loads "models/gomoku9_nnue.bin"
    // "othello"   -> loads "models/othello_nnue.bin"
}
```

The evaluate method in each BaseState subclass calls:

```cpp
int MiniChessState::evaluate(bool use_nnue, bool use_kp, bool use_mobility) {
    if (use_nnue) {
        auto* model = nnue::get_model("minichess");
        if (model && model->loaded()) {
            int features[MAX_ACTIVE];
            // ... use extract_features + model->forward()
        }
    }
    // fall back to handcrafted eval
}
```

### 6.5 Decoupling Model::evaluate from Board

The current `Model::evaluate(const Board& board, int player)` directly accesses
`board.board[2][6][5]`. This is replaced with a generic interface:

```cpp
// New: Model receives pre-extracted feature indices
int Model::evaluate(const int* w_features, int w_count,
                    const int* b_features, int b_count,
                    int player) const;
```

The game-specific BaseState subclass calls `extract_features()` for both
perspectives and passes the results to the model. The model itself becomes
game-agnostic.

### 6.6 Training

Training data generation (selfplay) writes positions in a format that includes:
- Game name (to select the correct feature extractor during training)
- Board state (game-specific serialization)
- Evaluation target (search score or game outcome)

The Python training script (`scripts/train_nnue.py`) loads data per game and
trains separate models. The network architecture (accumulator size, layer sizes)
can vary per game but the training pipeline is shared.

---

## 7. Factory Pattern

A factory function creates the initial state for any supported game:

```cpp
#include "state/base_state.hpp"
#include "state/minichess_state.hpp"
#include "state/gomoku_state.hpp"
#include "state/othello_state.hpp"

BaseState* create_initial_state(const std::string& game_name) {
    if (game_name == "minichess")  return new MiniChessState();
    if (game_name == "gomoku9")    return new GomokuState<9,9>();
    if (game_name == "gomoku15")   return new GomokuState<15,15>();
    if (game_name == "othello")    return new OthelloState();
    return nullptr;  // unknown game
}
```

Usage in the UCI loop:

```cpp
void uci::loop() {
    std::string game = "minichess";  // default, or set via "game" command
    BaseState* state = create_initial_state(game);

    // ... handle "position", "go", etc. using state-> interface
}
```

Usage in selfplay:

```cpp
int main(int argc, char* argv[]) {
    std::string game = (argc > 1) ? argv[1] : "minichess";
    BaseState* state = create_initial_state(game);
    // ... run games using state-> interface
}
```

### 7.1 Game registration (optional, for extensibility)

For a plugin-like system where new games can be added without modifying the
factory function:

```cpp
using GameFactory = std::function<BaseState*()>;

class GameRegistry {
    static std::map<std::string, GameFactory>& registry() {
        static std::map<std::string, GameFactory> r;
        return r;
    }
public:
    static void register_game(const std::string& name, GameFactory f) {
        registry()[name] = f;
    }
    static BaseState* create(const std::string& name) {
        auto it = registry().find(name);
        return (it != registry().end()) ? it->second() : nullptr;
    }
    static std::vector<std::string> list_games() {
        std::vector<std::string> names;
        for (auto& [k, v] : registry()) names.push_back(k);
        return names;
    }
};

// In minichess_state.cpp:
static bool _reg = [] {
    GameRegistry::register_game("minichess", []{ return new MiniChessState(); });
    return true;
}();
```

---

## 8. Migration Plan

The migration is designed to be incremental. At every step the engine remains
fully functional for MiniChess. New games are added after the abstraction is in
place.

### Phase 1: Define BaseState interface

1. Create `src/state/base_state.hpp` with the `BaseState` abstract class and the
   new `Move` struct (as defined in sections 2-3).

2. Keep the existing `State` class and `Move` typedef unchanged. Both old and
   new types coexist during migration.

**Files created**: `src/state/base_state.hpp`
**Files modified**: none
**Risk**: none -- purely additive

### Phase 2: Make current State extend BaseState

1. Make `State` inherit from `BaseState`:
   ```cpp
   class State : public BaseState { ... };
   ```

2. Add the new virtual methods to `State` with implementations that delegate to
   existing logic. For example, `move_to_string()` wraps the existing UCI
   conversion.

3. Convert internal `Move` representation: replace
   `typedef std::pair<Point, Point> Move` with the new `Move` struct. Update
   `get_legal_actions()`, `next_state()`, and all call sites that construct or
   destructure moves.

4. Add `extract_features()` and `feature_size()` to `State`, moving the feature
   extraction logic out of `nnue::Model` and into the state class.

**Files modified**:
- `src/state/state.hpp` -- inherit BaseState, add virtual overrides
- `src/state/state.cpp` -- implement new methods, adapt Move usage
- `src/nnue/nnue.hpp` / `nnue.cpp` -- decouple from Board
- `src/uci/uci.cpp` -- adapt move string conversion
- `src/selfplay.cpp` -- adapt Move construction

**Risk**: medium -- touching the Move type affects many files. Mitigate by doing
this in a single focused commit and running the full test/selfplay suite.

### Phase 3: Update search to use BaseState*

1. Change all search function signatures from `State*` to `BaseState*`:
   - `PVS::search`, `PVS::eval_ctx`
   - `AlphaBeta::search`, `AlphaBeta::eval_ctx`
   - `MiniMax::search`, `MiniMax::eval_ctx`
   - `Random::search`

2. Update the algorithm registry (`src/policy/registry.hpp`) to use `BaseState*`.

3. Update `SearchResult` and `RootUpdate` in `src/search_types.hpp` -- these
   already use `Move` which is now the universal type.

4. Abstract game-specific search components:
   - Move ordering: if it uses capture detection, add `is_capture()` to BaseState.
   - Quiescence search: guard with `num_piece_types() > 0` or add `is_quiet()`.
   - Transposition table: no changes needed (already uses `Move` and `int` score).

**Files modified**:
- `src/policy/pvs.hpp`, `pvs.cpp`
- `src/policy/alphabeta.hpp`, `alphabeta.cpp`
- `src/policy/minimax.hpp`, `minimax.cpp`
- `src/policy/random.hpp`, `random.cpp`
- `src/policy/registry.hpp`
- `src/policy/pvs/move_ordering.hpp` (if it references State directly)
- `src/policy/pvs/quiescence.hpp` (abstract capture concept)
- `src/search_types.hpp`

**Risk**: low -- mechanical signature changes. All behavior is unchanged because
`State` now IS-A `BaseState`.

### Phase 4: Update UCI to use BaseState*

1. Change `uci::loop()` to work with `BaseState*` instead of constructing
   `State` directly.

2. Move MiniChess-specific move string parsing into `MiniChessState::move_to_string()`
   and `MiniChessState::string_to_move()`. The UCI layer calls the virtual methods
   instead of its own `uci::move_to_str()` / `uci::str_to_move()`.

3. Add a `game` UCI command (or use a compile-time/config selection) to choose
   which game to play. The factory pattern creates the appropriate initial state.

4. The `position startpos moves ...` command uses `state->string_to_move()` to
   parse each move token, then applies `state->next_state()`.

**Files modified**:
- `src/uci/uci.hpp`, `uci.cpp`

**Risk**: low -- the UCI protocol is a thin wrapper.

### Phase 5: Add new games

With the framework in place, each new game is a self-contained addition:

1. Create `src/state/<game>_state.hpp` and `<game>_state.cpp`.
2. Implement all `BaseState` virtual methods.
3. Register in the factory function.
4. Train an NNUE model for the game (optional -- handcrafted eval works first).
5. Place the model file in `models/<game>_nnue.bin`.

**No existing files need modification** (beyond adding the include to the factory).

### Phase 6: Cleanup

1. Remove `BOARD_H` / `BOARD_W` macros from `config.hpp` (replaced by virtual
   `board_h()` / `board_w()`).
2. Remove MiniChess-specific constants from `src/nnue/nnue.hpp` (replaced by
   `feature_size()` from the state).
3. Remove the old `typedef std::pair<Point, Point> Move` if any lingering
   references remain.
4. Update `PIECE_TABLE` in config to be game-specific (moved into each state class).

---

## Appendix: File Layout After Migration

```
src/
  state/
    base_state.hpp          # BaseState abstract class + Move struct
    minichess_state.hpp     # MiniChessState : BaseState
    minichess_state.cpp
    gomoku_state.hpp        # GomokuState<H,W> : BaseState
    gomoku_state.cpp
    othello_state.hpp       # OthelloState : BaseState
    othello_state.cpp
    game_factory.hpp        # create_initial_state()
  policy/
    pvs.hpp                 # PVS (uses BaseState*)
    pvs.cpp
    pvs/
      tt.hpp
      killer_moves.hpp
      move_ordering.hpp
      quiescence.hpp
    alphabeta.hpp
    alphabeta.cpp
    minimax.hpp
    minimax.cpp
    random.hpp
    random.cpp
    registry.hpp            # AlgoEntry uses BaseState*
  nnue/
    nnue.hpp                # Model (game-agnostic inference)
    nnue.cpp
    model_registry.hpp      # Per-game model loading
    compute.hpp
    compute_simd.hpp
    compute_quant.hpp
  uci/
    uci.hpp
    uci.cpp                 # Uses BaseState*, factory pattern
  search_types.hpp          # Move, SearchResult, SearchContext
  search_params.hpp         # ParamMap, ParamDef
  config.hpp                # Compile-time flags only (no board dims)
```
