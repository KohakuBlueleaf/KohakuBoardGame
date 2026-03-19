# Search Algorithms

## Overview

The engine provides four search algorithms, selected at runtime via the
`Algorithm` UBGI option. All algorithms operate through the `BaseState`
interface and are game-agnostic.

| Algorithm   | Description |
|-------------|-------------|
| `pvs`       | Principal Variation Search with all enhancements (default) |
| `alphabeta` | Alpha-beta pruning (no TT, no killer moves) |
| `minimax`   | Pure negamax (no pruning) |
| `random`    | Random legal move selection |

---

## Infrastructure

### SearchContext (`src/search_types.hpp`)

Shared state passed through all search functions:

```cpp
struct SearchContext {
    uint64_t nodes = 0;         // Node counter
    int seldepth = 0;           // Maximum depth reached (selective)
    bool stop = false;          // Set by UBGI layer to abort search
    ParamMap params;             // Runtime parameters (key-value strings)
    std::function<void(const RootUpdate&)> on_root_update;  // Callback per root move
};
```

### SearchResult (`src/search_types.hpp`)

Returned by each algorithm's `search()` function:

```cpp
struct SearchResult {
    Move best_move;
    int score = 0;              // Centipawn-scale, from side-to-move perspective
    int depth = 0;
    int seldepth = 0;
    uint64_t nodes = 0;
    double time_ms = 0;
    std::vector<Move> pv;       // Principal variation
};
```

### RootUpdate (`src/search_types.hpp`)

Sent via `on_root_update` callback after each root move is searched:

```cpp
struct RootUpdate {
    Move best_move;
    int score;
    int depth;
    int move_number;
    int total_moves;
};
```

### ParamMap (`src/search_params.hpp`)

Runtime configuration passed from the UBGI layer:

```cpp
using ParamMap = std::map<std::string, std::string>;
```

Helper functions: `param_bool(map, key, default)`, `param_int(map, key, default)`.

Each algorithm defines a typed params struct that is parsed from the ParamMap
once at the root, then threaded through all recursive calls for fast access.

### ParamDef (`src/search_params.hpp`)

Used for UBGI option advertisement:

```cpp
struct ParamDef {
    std::string name;
    enum Type { CHECK, SPIN } type;
    std::string default_val;
    int min_val = 0;
    int max_val = 0;
};
```

### Algorithm Registry (`src/policy/registry.hpp`)

Each algorithm registers itself in a static table:

```cpp
struct AlgoEntry {
    std::string name;
    ParamMap default_params;
    std::vector<ParamDef> param_defs;
    std::function<SearchResult(State*, int, SearchContext&)> search;
};
```

`get_algo_table()` returns the table. `find_algo(name)` looks up an entry.
`default_algo_name()` returns `"pvs"`.

---

## PVS (Principal Variation Search)

**Files:** `src/policy/pvs.hpp`, `src/policy/pvs.cpp`

The most advanced search. Combines iterative deepening with alpha-beta
pruning, zero-window re-search, and several enhancements.

### PVS Parameters

All features are controlled via `PVSParams` (parsed from `ParamMap`):

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| UseNNUE | bool | true | Use NNUE evaluation |
| UseKPEval | bool | true | Use KP handcrafted eval (MiniChess) |
| UseEvalMobility | bool | true | Include mobility bonus |
| UseMoveOrdering | bool | true | Sort moves by heuristic score |
| UseQuiescence | bool | true | Extend search at leaf nodes |
| QuiescenceMaxDepth | int | 16 | Max quiescence search depth |
| UseTT | bool | true | Use transposition table |
| UseKillerMoves | bool | true | Track killer moves per ply |
| KillerSlots | int | 2 | Number of killer move slots |
| UseNullMove | bool | true | Enable null move pruning |
| NullMoveR | int | 2 | Null move reduction depth |
| UseLMR | bool | true | Enable late move reductions |
| LMRFullDepth | int | 3 | Moves searched at full depth |
| LMRDepthLimit | int | 3 | Minimum depth for LMR |
| ReportPartial | bool | true | Send root updates during search |

### Search flow

1. **Iterative deepening**: Search depth 1, 2, 3, ... up to the limit.
2. **Transposition table probe** (`src/policy/pvs/tt.hpp`): If a position
   was seen before at sufficient depth, reuse the score or best move.
3. **Null move pruning**: If not in check and depth is sufficient, try
   passing the turn at reduced depth. If the score still beats beta, prune.
   Uses `state->create_null_state()` -- skipped if it returns `nullptr`.
4. **Move ordering** (`src/policy/pvs/move_ordering.hpp`):
   - TT best move first
   - Captures by MVV-LVA (Most Valuable Victim, Least Valuable Attacker)
   - Killer moves (quiet moves that caused cutoffs at the same ply)
   - Remaining quiet moves
5. **PVS zero-window**: First move searched with full window. Remaining
   moves searched with null window `(alpha, alpha+1)`. If a move beats
   alpha, re-search with full window.
6. **Late move reduction (LMR)**: Moves searched late in the ordering
   (after `LMRFullDepth` moves, at depth >= `LMRDepthLimit`) are searched
   at reduced depth first. Only re-searched at full depth if they beat alpha.
7. **Quiescence search** (`src/policy/pvs/quiescence.hpp`): At depth 0,
   continues searching capture moves until the position is quiet. Uses
   stand-pat (static eval) as a lower bound. Detects captures by checking
   `piece_at()` on the destination square.

### PV extraction

After each depth completes, `extract_pv()` walks the TT from the root
to reconstruct the principal variation as a `std::vector<Move>`.

---

## Alpha-Beta

**Files:** `src/policy/alphabeta.hpp`, `src/policy/alphabeta.cpp`

Standard alpha-beta pruning in negamax form. No transposition table, no
killer moves, no null move pruning. Uses the same evaluation flags as PVS.

Parameters: `UseNNUE`, `UseKPEval`, `UseEvalMobility`, `ReportPartial`.

---

## MiniMax

**Files:** `src/policy/minimax.hpp`, `src/policy/minimax.cpp`

Pure negamax without any pruning. Explores the full game tree to the given
depth. Useful as a correctness baseline.

Parameters: `UseNNUE`, `UseKPEval`, `UseEvalMobility`, `ReportPartial`.

---

## Random

**Files:** `src/policy/random.hpp`, `src/policy/random.cpp`

Selects a random legal move. No search or evaluation.

---

## Evaluation

Evaluation is game-specific, implemented in each game's `State::evaluate()`.

### MiniChess evaluation

Three strategies, selected by boolean flags:

1. **NNUE** (`use_nnue`): If compiled with `USE_NNUE` and model is loaded,
   uses the neural network. Feature extraction is HalfKP (king-square x
   piece-square) or piece-square only.

2. **KP eval** (`use_kp_eval`): Material (scaled values), piece-square
   tables, and king tropism (bonus for pieces near the enemy king).

3. **Simple material** (fallback): Raw material counting with basic values.

Optional **mobility bonus** (`use_eval_mobility`): Difference in legal move
counts between the two sides.

### Gomoku evaluation

Threat-counting heuristic with decisive threat detection:

- **Decisive wins** (return immediately):
  - Five in a row, open-4, two half-4s, half-4 + open-3, two open-3s.
- **Decisive losses**: Mirror of above for the opponent.
- **Non-decisive**: Weighted sum of open-3, half-3, open-2, half-2 threats.

The `use_nnue`, `use_kp`, and `use_mobility` flags are ignored by Gomoku.

### Transposition Table

The TT (`src/policy/pvs/tt.hpp`) is shared across all games. It stores
entries keyed by Zobrist hash (from `state->hash()`), with depth, score,
flag (exact/lower/upper), and best move. Resizable via the `Hash` UBGI
option (2^N entries, N from 10 to 24).
