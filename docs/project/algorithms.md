# Search Algorithms

## Overview

The engine implements a hierarchy of game-tree search algorithms, each building
on the one before it. All algorithms operate through the `BaseState` interface
and are fully game-agnostic -- the same PVS search drives MiniChess, MiniShogi,
Gomoku, or any other game that implements the `State` class.

| Algorithm   | Description | Key idea |
|-------------|-------------|----------|
| `minimax`   | Pure negamax | Exhaustive search, no pruning |
| `alphabeta` | Negamax + alpha-beta pruning | Prune branches that cannot affect the result |
| `pvs`       | Principal Variation Search (default) | Null-window re-search, TT, killer moves, LMR, quiescence |
| `random`    | Random legal move | No search or evaluation |

The algorithm is selected at runtime via the `Algorithm` UCI/UBGI option.
The default is `pvs`.

---

## 1. Search Algorithm Hierarchy

### 1.1 Minimax (Negamax)

**Files:** `src/policy/minimax.hpp`, `src/policy/minimax.cpp`

The simplest search. Negamax explores the full game tree to a fixed depth with
no pruning at all. Every legal move at every node is expanded.

```
function negamax(state, depth):
    if terminal or depth == 0:
        return evaluate(state)
    best = -infinity
    for each move in legal_actions:
        score = -negamax(next_state(move), depth - 1)
        best = max(best, score)
    return best
```

Because the entire tree is searched, minimax is exponentially expensive but
serves as a correctness baseline: if alpha-beta or PVS return a different score
at the same depth, there is a bug.

**Signature:**
```cpp
int MiniMax::eval_ctx(State *state, int depth, SearchContext& ctx,
                      const MMParams& p, int ply);
```

No alpha/beta window, no pruning. Returns the negamax score.

### 1.2 Alpha-Beta

**Files:** `src/policy/alphabeta.hpp`, `src/policy/alphabeta.cpp`

Adds alpha-beta pruning on top of negamax. The idea: if we already know the
side to move has a guaranteed score of `alpha`, and we discover the opponent can
force a result of `beta <= alpha`, we can stop searching the remaining moves at
that node (beta cutoff).

```
function alphabeta(state, depth, alpha, beta):
    if terminal or depth == 0:
        return evaluate(state)
    for each move in legal_actions:
        score = -alphabeta(next_state(move), depth - 1, -beta, -alpha)
        alpha = max(alpha, score)
        if alpha >= beta:
            break          // beta cutoff
    return alpha
```

This prunes large portions of the tree without changing the result. The
implementation uses no transposition table, no killer moves, and no move
ordering -- moves are searched in whatever order `legal_actions` provides.

**Signature:**
```cpp
int AlphaBeta::eval_ctx(State *state, int depth, int alpha, int beta,
                        SearchContext& ctx, const ABParams& p, int ply);
```

### 1.3 PVS (Principal Variation Search)

**Files:** `src/policy/pvs.hpp`, `src/policy/pvs.cpp`

PVS extends alpha-beta with the assumption that the first move searched (the
"principal variation" move) is the best. All subsequent moves are tested with a
**null window** `(alpha, alpha+1)` -- a window of zero width that only asks
"is this move better than what we already have?" If the null-window search
fails high (the move *is* better), a full re-search confirms the score.

This saves time when move ordering is good: most moves fail the null-window
test cheaply, and only genuinely better moves pay for a full re-search.

On top of this, PVS adds:

- Transposition table (Section 4)
- Move ordering (Section 5)
- Quiescence search (Section 6)
- Null move pruning (Section 7)
- Late move reductions (Section 8)
- Iterative deepening with time management (Section 3)

**Signature:**
```cpp
int PVS::eval_ctx(State *state, int depth, int alpha, int beta,
                  SearchContext& ctx, const PVSParams& p,
                  int ply, bool can_null);
```

---

## 2. PVS Implementation Details

### 2.1 Null-Window Search and Re-Search

Inside `PVS::eval_ctx`, the first child is always searched with the full
`(alpha, beta)` window. Every subsequent child uses the null window:

```cpp
// Non-first move: null-window probe
score = -eval_ctx(next_state(move), depth - 1,
                  -(alpha + 1), -alpha, ...);
if (score > alpha && score < beta) {
    // Null window failed -- re-search with full window
    score = -eval_ctx(next_state(move), depth - 1,
                      -beta, -alpha, ...);
}
```

If the null-window search returns a score `<= alpha`, the move is no better
than what we have, and we saved time by not doing a full search. If it returns
`>= beta`, we have a beta cutoff regardless. Only the rare case where the
score falls strictly between alpha and beta requires the expensive re-search.

### 2.2 Root Search

`PVS::search()` is the entry point called by the UBGI layer for a single depth
iteration. It:

1. Resets the `SearchContext` node counter and selective depth.
2. Parses `PVSParams` from the parameter map (done once, then threaded through
   all recursive calls for speed).
3. Probes the TT at the root for a best-move hint.
4. Orders moves via `get_ordered_moves()`.
5. Searches each root move using the PVS null-window scheme.
6. Fires `on_root_update` callbacks so the UBGI layer can emit `info` lines
   as the search progresses.
7. Extracts the PV from the TT (see Section 9).

The root uses a wide initial window: `alpha = M_MAX - 10 = -100010`,
`beta = P_MAX + 10 = 100010`.

---

## 3. Iterative Deepening with Time Management

Iterative deepening is implemented in the UBGI layer (`src/ubgi/ubgi.cpp`),
not inside the search algorithms themselves. The `do_search` function calls
the selected algorithm's `search()` repeatedly at increasing depths:

```cpp
for (int depth = 1; depth <= depth_limit; depth++) {
    if (!alive()) break;
    SearchResult result = g_algo->search(&state, depth, ctx);
    // ... emit info, update best move, check time ...
}
```

Each algorithm's `search()` function handles a single fixed-depth search and
returns a `SearchResult`. The iterative deepening wrapper handles:

- **Depth limit:** `go depth N` caps the loop at depth N.
- **Time management:** `go movetime N` sets a millisecond budget. After each
  depth completes, if `total_ms * 2 >= movetime_ms`, the loop stops -- the
  heuristic is that the next depth will likely take about twice as long.
- **Infinite search:** `go infinite` runs until `stop` is received.
- **Default:** If none of the above is specified, `max_depth = 6`.
- **Mate detection:** If the score is within 100 centipawns of `P_MAX` or
  `M_MAX` (a forced win/loss), the loop stops early.
- **Abort:** Setting `ctx.stop = true` (via the `stop` UCI command) causes
  the search to bail out at the next node visit. Partial results from an
  interrupted depth are discarded (depth > 1).

After each completed depth, the UBGI layer emits a UCI `info` line with depth,
seldepth, score, nodes, time, nps, and PV.

Because PVS uses a transposition table that persists across depths, later
iterations benefit from the work done in earlier ones: the TT provides best-move
hints that improve move ordering, making each successive search faster than
starting from scratch.

---

## 4. Transposition Table

**File:** `src/policy/pvs/tt.hpp`

The transposition table (TT) caches search results keyed by position hash. If
the same position is reached via a different move order, or revisited at a
different iteration depth, the cached result can either provide an immediate
answer or a best-move hint for move ordering.

### 4.1 Hash Computation

Hash computation is delegated to `State::hash()`, which implements a
game-specific Zobrist hashing scheme. The TT simply calls:

```cpp
uint64_t hash = compute_hash(state);  // == state->hash()
```

### 4.2 Entry Structure

```cpp
struct TTEntry {
    uint64_t hash;          // Full Zobrist hash (for collision detection)
    int      score;         // Search score
    int      depth;         // Depth at which this score was computed
    TTFlag   flag;          // TT_EXACT, TT_LOWER, TT_UPPER, or TT_NONE
    uint8_t  from_r, from_c, to_r, to_c;  // Best move (packed)
};
```

The flag indicates what kind of bound the score represents:

| Flag | Meaning | When stored |
|------|---------|-------------|
| `TT_EXACT` | Score is exact (PV node) | `alpha` improved but stayed below `beta` |
| `TT_LOWER` | Score is a lower bound (fail-high / cut node) | `alpha >= beta` (beta cutoff) |
| `TT_UPPER` | Score is an upper bound (fail-low / all node) | No move improved `alpha` |

### 4.3 Probing

```cpp
TTEntry* tt_probe(uint64_t hash) {
    TTEntry& e = tt[hash & tt_mask];
    if (e.flag != TT_NONE && e.hash == hash)
        return &e;
    return nullptr;
}
```

The table uses direct mapping: `index = hash & tt_mask`. Collision detection
compares the stored full hash against the probe hash. A probe returns `nullptr`
on miss.

During search, a TT hit is used in two ways:

1. **Score cutoff** (if `tte->depth >= depth`):
   - `TT_EXACT`: Return the score immediately.
   - `TT_LOWER` with `score >= beta`: Beta cutoff.
   - `TT_UPPER` with `score <= alpha`: Alpha cutoff.
2. **Best-move hint** (regardless of depth): The stored move is used for move
   ordering even if the depth is insufficient for a score cutoff.

### 4.4 Storing

```cpp
void tt_store(uint64_t hash, int depth, int score, TTFlag flag, const Move& best) {
    TTEntry& e = tt[hash & tt_mask];
    if (e.flag == TT_NONE || e.depth <= depth) {
        e = {hash, score, depth, flag, ...best...};
    }
}
```

**Replacement policy:** A new entry overwrites an existing one only if the
existing slot is empty (`TT_NONE`) or the new search was at equal or greater
depth. This "depth-preferred" policy keeps deeper, more valuable results in
the table.

### 4.5 Sizing

The TT is dynamically allocated as a `std::vector<TTEntry>` with `2^N`
entries. `N` defaults to `DEFAULT_TT_SIZE_BITS = 18` (262,144 entries) and can
be changed at runtime via the UCI `Hash` option (range: 10 to 24).

```
setoption name Hash value 20    // 2^20 = 1,048,576 entries
```

`tt_resize(bits)` reallocates and clears the table. `tt_clear()` zeros all
entries without reallocating.

---

## 5. Move Ordering

**File:** `src/policy/pvs/move_ordering.hpp`

Good move ordering is critical for alpha-beta and PVS efficiency. The earlier
a strong move appears, the more branches can be pruned. Moves are scored and
sorted into the following priority tiers:

### 5.1 Priority Tiers (Highest to Lowest)

1. **TT best move:** If the transposition table contains a best move for the
   current position, it is placed first (swapped to index 0 after sorting).
   This is the single most important ordering heuristic -- the TT move is
   often the PV move from the previous iteration.

2. **Captures by MVV-LVA:** Captures are scored by Most Valuable Victim,
   Least Valuable Attacker:
   ```cpp
   score = piece_val[captured] * 100 - piece_val[attacker]
   ```
   This prioritizes capturing a high-value piece with a low-value piece.
   Piece values used for ordering: `{0, 2, 6, 7, 8, 20, 100}` (indexed by
   piece type: none, pawn, silver, gold, bishop, rook, king).

3. **Killer moves (score = 50):** Quiet moves that caused beta cutoffs at
   the same ply in sibling nodes. These are not captures, but they were "good
   enough to refute" a previous move at this depth.

4. **Remaining quiet moves (score = 0):** All other moves, in their natural
   order.

### 5.2 Implementation

```cpp
std::vector<Move> get_ordered_moves(
    const State* state,
    const Move* tt_move,     // nullptr if no TT move
    int ply,
    const PVSParams& params
);
```

The function copies `legal_actions`, sorts by `score_move()`, then swaps the
TT move to the front if present. Move ordering can be disabled entirely via
`UseMoveOrdering = false`, in which case moves are searched in generation order.

---

## 6. Quiescence Search

**File:** `src/policy/pvs/quiescence.hpp`

When the main search reaches depth 0, the position may be in the middle of a
tactical exchange (e.g., a piece is hanging). Evaluating such a position
statically produces an unreliable score -- the so-called "horizon effect."

Quiescence search resolves this by continuing to search **capture moves only**
until the position is "quiet" (no more captures) or a depth limit is reached.

### 6.1 Algorithm

```
function quiescence(state, alpha, beta, qdepth):
    stand_pat = evaluate(state)
    if stand_pat >= beta:
        return beta                // standing pat is good enough
    alpha = max(alpha, stand_pat)  // stand-pat as lower bound

    if qdepth >= max_depth:
        return alpha               // depth limit

    for each capture in legal_actions (sorted by MVV-LVA):
        score = -quiescence(next_state(capture), -beta, -alpha, qdepth + 1)
        if score >= beta:
            return beta            // beta cutoff
        alpha = max(alpha, score)

    return alpha
```

Key points:

- **Stand-pat:** The static evaluation serves as a lower bound. The side to
  move can always "do nothing" (decline to capture), so the evaluation should
  be at least as good as the static score.
- **Only captures:** A move is a capture if `state->piece_at(opponent, to_r, to_c)`
  returns a non-zero piece type.
- **MVV-LVA ordering:** Captures are sorted by the same MVV-LVA scheme used in
  the main search (killer moves are not used in quiescence).
- **Depth limit:** Controlled by `QuiescenceMaxDepth` (default 16). Prevents
  pathological positions from causing unbounded recursion.
- **Node counting:** Quiescence nodes are included in `ctx.nodes` and update
  `ctx.seldepth`, which is why `seldepth` often exceeds the nominal search
  depth.

### 6.2 Integration

The main PVS search calls quiescence at depth 0:

```cpp
if (depth == 0) {
    if (p.use_quiescence)
        return quiescence_ctx(state, alpha, beta, 0, ctx, p, ply);
    else
        return state->evaluate(...);
}
```

Quiescence can be disabled via `UseQuiescence = false`, in which case leaf
nodes use a plain static evaluation.

---

## 7. Null Move Pruning

Null move pruning is based on the observation that in most positions, having
the right to move is an advantage. If we skip our turn entirely (a "null move")
and the opponent still cannot beat beta, then the position is so good that we
can prune it without searching any real moves.

### 7.1 Implementation

```cpp
if (use_null_move && can_null && depth >= null_move_r + 1) {
    State* null_state = state->create_null_state();
    if (null_state != nullptr) {
        // Search with null window (beta-1, beta) at reduced depth
        int null_score = -eval_ctx(null_state, depth - 1 - null_move_r,
                                   -beta, -(beta - 1), ..., can_null=false);
        if (null_score >= beta) {
            return beta;    // null move cutoff
        }
    }
}
```

Key details:

- **Reduction (R):** The null move search runs at `depth - 1 - R`. With
  `NullMoveR = 2` (default), this is 3 plies shallower than a normal search.
- **Null window:** The null move uses the window `(beta-1, beta)` -- we only
  care whether the score beats beta.
- **`can_null = false`:** After a null move, the recursive call disables further
  null moves. This prevents two consecutive null moves (which would be
  equivalent to no search at all).
- **`create_null_state()`:** Returns a state with the side to move flipped but
  no move made. Games that do not support null moves (e.g., where passing is
  illegal) return `nullptr`, which skips the pruning.
- **Safety checks:** Null move pruning is skipped if the null state is terminal
  (win or draw), or if depth is too shallow (`depth < R + 1`).

### 7.2 When Null Move Pruning Fails

Null move pruning assumes the null move hypothesis -- that having the move is
always an advantage. This fails in "zugzwang" positions where every move makes
the position worse. The engine does not currently implement verification search
or other zugzwang-detection safeguards, so null move pruning can cause missed
wins/losses in rare endgame positions.

---

## 8. Late Move Reductions (LMR)

LMR reduces the search depth for moves that are searched late in the move
ordering and are unlikely to be the best move. The assumption: if move ordering
is good, moves appearing late are probably weak.

### 8.1 Eligibility

A move is reduced only if all of the following hold:

1. It is **not the first move** (PV move is always searched at full depth).
2. `move_index >= LMRFullDepth` (default: 3). The first 3 moves are always
   searched at full depth.
3. `depth >= LMRDepthLimit` (default: 3). At shallow depths, the cost of a
   full search is small enough that reduction is not worthwhile.
4. The move is **not a capture** (captures are tactically important).
5. The move is **not a killer move** (killers have already proven their worth).

### 8.2 Three-Phase Search

When a move qualifies for LMR, it goes through up to three search phases:

```
Phase 1: Null window, reduced depth (depth - 2)
    score = -eval_ctx(next_state, depth - 2, -(alpha+1), -alpha, ...)

Phase 2: If score > alpha, re-search at full depth with null window
    score = -eval_ctx(next_state, depth - 1, -(alpha+1), -alpha, ...)

Phase 3: If score > alpha AND score < beta, full window re-search
    score = -eval_ctx(next_state, depth - 1, -beta, -alpha, ...)
```

Most reduced moves fail at Phase 1 and cost only a shallow search. Moves that
survive Phase 1 might still fail the null window at Phase 2. Only moves that
truly improve alpha go through the expensive Phase 3.

---

## 9. PV Extraction from the Transposition Table

**Function:** `PVS::extract_pv(State *state, int max_len)`

After each depth completes, the principal variation is reconstructed by walking
the TT from the root position:

```
function extract_pv(state, max_len):
    pv = []
    for i in 0..max_len:
        hash = compute_hash(state)
        if hash in seen_hashes: break     // cycle detection
        entry = tt_probe(hash)
        if no entry or entry is TT_NONE: break
        move = entry.best_move
        if move not in state.legal_actions: break   // legality check
        pv.append(move)
        state = next_state(move)
    return pv
```

Three safety checks protect against corrupted PV lines:

1. **Cycle detection:** A set of seen hashes prevents infinite loops when the
   TT contains a cycle.
2. **Legality validation:** Each extracted move is checked against the current
   position's legal moves. A TT collision (different position, same hash index)
   would produce an illegal move -- this check catches it.
3. **TT_NONE check:** An empty TT slot terminates extraction.

### 9.1 The TT PV Mismatch Bug (and Fix)

**Commit:** `74250e1`

A subtle bug occurred when the TT's best move at the root hash disagreed with
the root search's actual best move. This happens because the TT is shared
across all iterative deepening depths and may be overwritten by a later search
of a different subtree.

**The bug:** The old code detected the mismatch and replaced `pv[0]` with the
correct `best_move`, but kept `pv[1..]` unchanged. The problem is that
`pv[1..]` was the continuation from the *wrong* first move -- a completely
different subtree. This produced PV lines containing illegal or nonsensical
moves after the first one.

**The fix:** When a mismatch is detected, the engine now plays `best_move` on
the root position to obtain the child state, then re-extracts the PV tail from
that child:

```cpp
if (best_move != Move() && (result.pv.empty() || result.pv[0] != best_move)) {
    State* child = state->next_state(best_move);
    auto tail = extract_pv(child, depth + 9);
    delete child;
    result.pv.clear();
    result.pv.push_back(best_move);
    result.pv.insert(result.pv.end(), tail.begin(), tail.end());
}
```

This ensures the entire PV is a legal, coherent sequence of moves starting from
the root best move.

---

## 10. Search Parameters and UCI Tuning

### 10.1 Parameter Infrastructure

**File:** `src/search_params.hpp`

Parameters flow from the UCI/UBGI layer as string key-value pairs in a
`ParamMap` (`std::map<std::string, std::string>`). Each algorithm parses these
into a typed struct once at the root of the search, then passes the struct by
const reference through all recursive calls. This avoids repeated map lookups
in the hot path.

Helper functions:
- `param_bool(map, key, default)` -- reads "true"/"1" as true, anything else
  as false.
- `param_int(map, key, default)` -- reads an integer, falls back to default on
  missing key.

### 10.2 ParamDef (UCI Option Advertisement)

```cpp
struct ParamDef {
    std::string name;
    enum Type { CHECK, SPIN } type;
    std::string default_val;
    int min_val, max_val;       // only for SPIN
};
```

Each algorithm returns a `std::vector<ParamDef>` that the UBGI layer uses to
emit `option` lines during the UCI handshake. GUIs can then display toggles and
sliders for each parameter.

### 10.3 PVS Parameters

All PVS features can be independently toggled and tuned:

| UCI Option | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `UseNNUE` | check | true | -- | Use NNUE neural network evaluation |
| `UseKPEval` | check | true | -- | Use handcrafted KP evaluation |
| `UseEvalMobility` | check | true | -- | Include mobility bonus in evaluation |
| `UseMoveOrdering` | check | true | -- | Sort moves by heuristic score |
| `UseQuiescence` | check | true | -- | Extend search with quiescence at leaves |
| `QuiescenceMaxDepth` | spin | 16 | 1-64 | Maximum quiescence search depth |
| `UseTT` | check | true | -- | Use transposition table |
| `UseKillerMoves` | check | true | -- | Track killer moves per ply |
| `KillerSlots` | spin | 2 | 1-4 | Number of killer move slots per ply |
| `UseNullMove` | check | true | -- | Enable null move pruning |
| `NullMoveR` | spin | 2 | 1-4 | Null move depth reduction |
| `UseLMR` | check | true | -- | Enable late move reductions |
| `LMRFullDepth` | spin | 3 | 1-10 | Moves searched at full depth before LMR |
| `LMRDepthLimit` | spin | 3 | 1-10 | Minimum remaining depth for LMR |
| `ReportPartial` | check | true | -- | Send root move updates during search |

### 10.4 Alpha-Beta and Minimax Parameters

Both simpler algorithms accept a subset of evaluation flags:

| UCI Option | Type | Default |
|-----------|------|---------|
| `UseNNUE` | check | true |
| `UseKPEval` | check | true |
| `UseEvalMobility` | check | true |
| `ReportPartial` | check | true |

### 10.5 Global Options

| UCI Option | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `Algorithm` | combo | pvs | pvs/alphabeta/minimax/random | Select search algorithm |
| `Hash` | spin | 18 | 10-24 | TT size as 2^N entries |
| `NNUEFile` | string | models/nnue.bin | -- | Path to NNUE model file |

### 10.6 Tuning Workflow

To A/B test parameter changes, disable individual features and observe the
effect on search speed and playing strength:

```
setoption name UseLMR value false        // disable LMR
setoption name UseNullMove value false   // disable null move pruning
setoption name KillerSlots value 3       // try 3 killer slots instead of 2
setoption name Hash value 20             // larger TT (2^20 entries)
```

---

## 11. SearchContext: Statistics and Control

**File:** `src/search_types.hpp`

`SearchContext` is the shared mutable state threaded through every search call:

```cpp
struct SearchContext {
    uint64_t nodes = 0;         // Total node counter (main + quiescence)
    int seldepth = 0;           // Maximum ply reached (selective depth)
    bool stop = false;          // Abort flag, set by UBGI "stop" command
    ParamMap params;            // Runtime parameters (string key-value)
    std::function<void(const RootUpdate&)> on_root_update;  // Callback
};
```

### 11.1 Statistics Tracked

- **`nodes`:** Incremented at every call to `eval_ctx()` and
  `quiescence_ctx()`. Includes interior nodes, leaf nodes, TT cutoff nodes,
  null move nodes, and quiescence nodes. This is the total work done.

- **`seldepth`:** The deepest ply reached during the search, including
  quiescence extensions. For example, a depth-6 search with quiescence might
  reach `seldepth = 18`.

- **`stop`:** Checked at the top of every `eval_ctx()` and `quiescence_ctx()`
  call. When true, the search returns 0 immediately and unwinds. The UBGI
  layer sets this flag when it receives the `stop` command or when the search
  thread is superseded.

### 11.2 SearchResult

Returned by each algorithm's `search()` function:

```cpp
struct SearchResult {
    Move best_move;             // Best move found
    int score = 0;              // Centipawn score, from side-to-move perspective
    int depth = 0;              // Nominal search depth
    int seldepth = 0;           // Selective depth (max ply reached)
    uint64_t nodes = 0;         // Nodes searched at this depth
    double time_ms = 0;         // Time spent (filled by UBGI layer)
    std::vector<Move> pv;       // Principal variation
};
```

### 11.3 RootUpdate

Sent via `on_root_update` callback whenever a new best move is found at the
root during search:

```cpp
struct RootUpdate {
    Move best_move;
    int score;
    int depth;
    int move_number;        // 1-based index of this move in the ordering
    int total_moves;        // total root moves
};
```

The UBGI layer uses this to emit `info currmove` lines, giving real-time
feedback during long searches.

### 11.4 `reset()`

Called at the start of each depth iteration by `search()`. Zeros `nodes` and
`seldepth` but does *not* clear `stop` or `params`. This means `nodes` in the
`SearchResult` reflects work done at a single depth, while the UBGI layer
accumulates `total_nodes` across all depths.

---

## 12. How the Components Fit Together

The following shows the call stack during a PVS search, from the top-level
UBGI command down to the leaf evaluation:

```
ubgi::do_search()                        [UBGI layer - iterative deepening]
  |
  +-- for depth = 1, 2, 3, ...
       |
       +-- PVS::search(state, depth)     [Root search for one depth]
            |
            +-- PVSParams::from_map()    [Parse params once]
            +-- tt_probe() at root       [TT best-move hint]
            +-- get_ordered_moves()      [Move ordering]
            |
            +-- for each root move:
            |    |
            |    +-- PVS::eval_ctx()     [Recursive PVS search]
            |         |
            |         +-- tt_probe()           [TT probe: score cutoff or best-move hint]
            |         +-- null move pruning    [Skip turn, search at depth - 1 - R]
            |         |    +-- eval_ctx(..., can_null=false)
            |         |
            |         +-- get_ordered_moves()  [TT move + MVV-LVA + killers]
            |         |
            |         +-- for each child move:
            |              +-- eval_ctx()      [Full window for first move]
            |              +-- eval_ctx()      [Null window for others]
            |              +-- eval_ctx()      [Re-search on fail-high]
            |              +-- LMR: eval_ctx() [Reduced depth for late quiet moves]
            |              +-- store_killer()  [On beta cutoff of quiet move]
            |         |
            |         +-- tt_store()           [Cache result]
            |
            |    (at depth == 0)
            |    +-- quiescence_ctx()    [Capture-only extension]
            |         +-- evaluate()     [Static evaluation: NNUE or handcrafted]
            |         +-- for each capture:
            |              +-- quiescence_ctx()  [Recursive]
            |
            +-- extract_pv()            [Walk TT to build PV line]
            +-- PV mismatch fixup       [Rebuild tail if TT disagrees with root]
```

### 12.1 Killer Move Table

**File:** `src/policy/pvs/killer_moves.hpp`

The killer table is a global 2D array indexed by `[ply][slot]`:

```cpp
Move killer_table[MAX_PLY][MAX_KILLER_SLOTS];  // MAX_PLY=64, MAX_KILLER_SLOTS=4
```

- **`store_killer(ply, move, slots)`:** On a beta cutoff from a quiet (non-capture)
  move, the move is inserted at slot 0 and existing killers shift down. If the
  move is already at slot 0, no work is done (avoids duplicates).
- **`is_killer(ply, move, slots)`:** Checks whether the move appears in any of
  the active killer slots at the given ply.

The number of active slots is controlled by `KillerSlots` (default 2, max 4).
Killer moves are ply-specific: a killer at ply 3 is only used when ordering
moves at ply 3, not at ply 4.

### 12.2 Algorithm Registry

**File:** `src/policy/registry.hpp`

All four algorithms register themselves in a static table via `AlgoEntry`:

```cpp
struct AlgoEntry {
    std::string name;
    ParamMap default_params;
    std::vector<ParamDef> param_defs;
    std::function<SearchResult(State*, int, SearchContext&)> search;
};
```

`find_algo(name)` looks up an algorithm by name. `default_algo_name()` returns
`"pvs"`. The UBGI layer holds a pointer to the current `AlgoEntry` and calls
its `search` function pointer.

---

## 13. Constants

| Constant | Value | Location | Meaning |
|----------|-------|----------|---------|
| `P_MAX` | 100,000 | `base_state.hpp` | Score for a won position (from winner's perspective) |
| `M_MAX` | -100,000 | `base_state.hpp` | Score for a lost position |
| `DEFAULT_TT_SIZE_BITS` | 18 | `config.hpp` | Default TT has 2^18 = 262,144 entries |
| `MAX_PLY` | 64 | `killer_moves.hpp` | Maximum supported search ply |
| `MAX_KILLER_SLOTS` | 4 | `killer_moves.hpp` | Maximum killer slots (runtime param caps actual use) |
