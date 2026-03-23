# Gomoku Evaluation Integration: Fitting a Strong Eval into the Game-Agnostic Search

Discussion of how to build a strong gomoku evaluation within the constraints of
the existing multi-game engine architecture. References the codebase as of the
current `main` branch.

---

## Context: The Architecture Constraint

The search engine (PVS, alpha-beta, minimax) is completely game-agnostic. It
interacts with game state exclusively through the `BaseState` interface
(`src/state/base_state.hpp`):

```
state->get_legal_actions()      // populates legal_actions vector
state->next_state(move)         // returns heap-allocated successor
state->evaluate()               // returns int score from current player's perspective
state->game_state               // WIN / DRAW / NONE
state->piece_at(player, r, c)   // used by MVV-LVA move ordering
state->create_null_state()      // used by null-move pruning (returns nullptr for gomoku)
```

The search does NOT know about gomoku patterns, threats, VCF, VCT, or any
game-specific concept. It never inspects board cells directly. All game-specific
intelligence must be embedded in the `State` class methods, principally
`evaluate()` and `get_legal_actions()`.

Key code locations:

| File | Role |
|------|------|
| `src/games/gomoku/state.cpp` | Current gomoku State implementation |
| `src/games/gomoku/state.hpp` | State class definition (lines 12-57) |
| `src/games/gomoku/config.hpp` | Board size (9x9), WIN_LENGTH (5) |
| `src/state/base_state.hpp` | BaseState interface (lines 19-76) |
| `src/policy/pvs.cpp` | PVS search (calls evaluate at line 53) |
| `src/policy/pvs/move_ordering.hpp` | MVV-LVA + killer ordering (lines 16-68) |
| `src/policy/pvs/quiescence.hpp` | Quiescence search, capture-only (lines 54-62) |

---

## 1. Pattern-Based Eval Inside evaluate()

### Current State

The current `count_threats()` function (`state.cpp` lines 183-246) scans the
board for consecutive runs of stones in four directions. For each run, it counts
open ends and classifies the pattern. The `evaluate()` function (lines 274-332)
then checks for decisive compound threats (open-4, double half-4, etc.) and
falls back to a weighted score.

### Gap: Missing Broken/Gap Patterns

The current scanner only finds **consecutive** runs. It completely misses:

- `_XX_X_` (broken three) -- strategically equivalent to an open three
- `_X_XX_` (broken three, mirror)
- `_XXX_X` (broken four) -- strategically equivalent to a half-open four
- `_X_XXX` (broken four, mirror)
- `_XX_XX_` (broken four with central gap)

These are common in real games and represent a major blind spot.

### Recommended Approach: Sliding Window Pattern Table

Replace the consecutive-run scanner with a **6-cell sliding window** and a
**precomputed lookup table**.

**Why 6 cells?** A window of 5 cells detects patterns that can form five-in-a-row.
The 6th cell (one boundary cell on each side) distinguishes "open" from "blocked"
ends. In practice, we scan windows of length 5 through each line, but also
inspect the cells at positions -1 and +5 for boundary classification.

**Encoding:** Each cell in the window is one of three states: empty (0), player
(1), opponent (2). A window of length 5 encodes to a base-3 integer with 243
possible values. Adding one boundary cell on each side (left and right of the
5-cell window) gives 7 cells total, but we only need the boundary cells for
open/closed classification, not full enumeration. Practical approach:

```cpp
// For each line of length >= 5, slide a 5-cell window.
// For each window position, encode the 5 inner cells as base-3 (243 values).
// Also check left_open and right_open (boundary cells empty or not).
// Look up: pattern_table[code][left_open][right_open] -> ThreatType

// Total table size: 243 * 2 * 2 = 972 entries. Tiny.
```

**Alternatively**, use a full 7-cell encoding (3^7 = 2187 entries) where the
boundary cells are part of the code. This is still trivially small and avoids
the separate boundary check.

**Building the table:** At startup, iterate all 2187 patterns and classify each
one programmatically -- count player stones, check for gaps, check boundaries.
Store the threat classification (FIVE, OPEN_4, HALF_4, OPEN_3, BROKEN_3,
HALF_3, OPEN_2, HALF_2, DEAD, NONE).

**Integration:** This replaces `count_threats()` entirely. The evaluate()
function structure (decisive checks in Phase 3, weighted scoring in Phase 4)
stays the same; only the scanner changes.

**Performance:** O(H * W * 4) table lookups per evaluation (4 directions).
For a 9x9 board, that is roughly 324 lookups. For 15x15, roughly 900. Each
lookup is a single array access -- faster than the current loop-based scanner.

### Score Calibration

The current `threat_score()` weights (`state.cpp` lines 249-254) are:

```cpp
return t.open3 * 500 + t.half3 * 80 + t.open2 * 60 + t.half2 * 10;
```

This has no broken-3 term and the half4 bonus is handled separately (lines
322-329). Recommended recalibration, integrating half4 into the weighted sum:

```cpp
static int threat_score(const ThreatCounts& t) {
    return t.half4   * 5000
         + t.open3   * 800
         + t.broken3 * 600
         + t.half3   * 150
         + t.open2   * 100
         + t.half2   * 20;
}
```

The key principle: each threat level must dominate all lower levels combined.
No accumulation of open-2s should outweigh a single open-3. The current 500
for open-3 vs 60 for open-2 satisfies this on a 9x9 board (at most ~16
open-2s = 960, less than 2 * open-3 = 1000). But on 15x15 with more space,
the margin is tighter. The recommended values give better separation.

---

## 2. Threat Space Search (TSS) vs Game-Agnostic Search

### The Problem

The gomoku eval discussion (`docs/design/gomoku_eval_discussion.md`, Section 3)
strongly recommends VCF (Victory by Continuous Fours) search at leaf nodes. VCF
is described as "the gomoku analog of quiescence search in chess" -- it extends
the search to resolve forced four-sequences that the main search might miss due
to the horizon effect.

But our search is game-agnostic. There is no hook for "run a gomoku-specific
mini-search at leaf nodes." We need to find a way to integrate VCF within the
existing interface.

### Option A: VCF Inside evaluate() -- RECOMMENDED

Run a VCF solver as part of the `evaluate()` function. When `evaluate()` is
called at a leaf node, before returning the static score, it runs a bounded
VCF search internally.

**How it works:**

```cpp
int State::evaluate(...) {
    // Phase 1-3: terminal and decisive threat checks (unchanged)
    ...

    // Phase 3.5: VCF search (NEW)
    if (vcf_search(board, my_id, VCF_DEPTH_LIMIT)) {
        return P_MAX - 10;  // forced win via continuous fours
    }
    if (vcf_search(board, opp_id, VCF_DEPTH_LIMIT)) {
        return -(P_MAX - 10);  // opponent has forced win
    }

    // Phase 4-5: weighted scoring (unchanged)
    ...
}
```

**VCF implementation:** A dedicated function inside `state.cpp` that:
1. Generates all moves that create a four (half-open or open) for the attacker.
2. For each such move, determines the forced defensive response (block the four).
3. Recurses: does the attacker have another four-creating move?
4. Returns true if the sequence reaches five-in-a-row.

The branching factor is small: typically 3-10 four-creating moves for the
attacker, exactly 1 forced response for the defender. A depth limit of 20-30
plies is practical and catches most forcing sequences.

**Why this works within the architecture:**

- The search calls `state->evaluate()` at leaf nodes (pvs.cpp line 53).
- `evaluate()` is a pure function on the state -- it can do whatever internal
  computation it wants, including running a mini-search.
- No changes to `BaseState`, `PVS`, or any shared code.
- The VCF result is simply reflected in the returned score.

**Cost:** VCF search adds time to each leaf evaluation. On a 9x9 board with
a typical position, VCF with a depth-20 limit might examine 50-500 nodes per
call. Since evaluate() is called at every leaf of the main search, this could
multiply the effective cost by 10-100x. Mitigation strategies:

- Only run VCF when the position has at least one half-4 or multiple open-3s
  for either side (skip quiet positions).
- Cache VCF results using the Zobrist hash (a small local TT inside evaluate).
- Use a conservative depth limit (e.g., 12 plies) and increase it iteratively.

**Verdict:** This is the cleanest integration. The search stays agnostic. The
evaluate() function becomes more expensive but more accurate. The depth limit
controls the cost/benefit tradeoff.

### Option B: VCF Inside get_legal_actions() -- PARTIAL SOLUTION

When the opponent has a half-4 (forced block situation), `get_legal_actions()`
could return only the blocking move(s). This eliminates the branching factor
for forced moves.

**Current situation:** `get_legal_actions()` (state.cpp lines 89-146) generates
all empty cells within Manhattan distance 2, regardless of tactical urgency. If
the opponent has a half-open four, the only sensible move is to block it, but
the search must discover this by trying all moves.

**Proposed enhancement:**

```cpp
void State::get_legal_actions() {
    // ... existing proximity mask generation ...

    // NEW: if opponent has a half-4, only return blocking moves
    auto opp_threats = count_threats(board, opp_id);
    if (opp_threats.half4 > 0) {
        // Find the cell(s) that block the four
        legal_actions = find_blocking_moves(board, opp_id);
        return;
    }

    // ... existing collection of nearby empty cells ...
}
```

**Pros:**
- Dramatically reduces branching at forced nodes (from ~30 moves to 1-2 moves).
- The search effectively gets "free" depth for forced sequences.
- No changes to search code.

**Cons:**
- This only handles the simplest case (must-block-four). It does not implement
  full VCF search.
- It changes the semantics of get_legal_actions() from "all legal moves" to
  "all reasonable moves." This is a form of forward pruning that could miss
  counter-attacks (e.g., creating your own five instead of blocking).
- Must be careful: if the opponent has a half-4 but we have an open-4 or five,
  we should play our winning move, not block. The logic must check our threats
  first.

**Verdict:** Worth doing as a supplementary optimization, but not a replacement
for VCF in evaluate(). The forced-block pruning is safe (blocking a four is
almost always the only correct move, except when we can win immediately), and
the search speedup is significant. Combine with Option A for full coverage.

**Refined logic:**

```cpp
void State::get_legal_actions() {
    // ... existing setup ...

    // Check if we can win immediately (five or open-4)
    auto my_threats = count_threats(board, my_id);
    if (my_threats.five > 0 || my_threats.open4 > 0) {
        // Return only the winning move(s)
        legal_actions = find_winning_moves(board, my_id);
        return;
    }

    // Check if opponent has unstoppable threat
    auto opp_threats = count_threats(board, opp_id);
    if (opp_threats.half4 > 0) {
        // Must block; but also check if we can create our own five
        legal_actions = find_blocking_moves(board, opp_id);
        // Also include any move that creates five for us
        add_five_creating_moves(legal_actions, board, my_id);
        return;
    }

    // ... normal proximity-based generation ...
}
```

### Option C: Quiescence Extension -- ARCHITECTURALLY DIFFICULT

Making the quiescence search (`src/policy/pvs/quiescence.hpp`) threat-aware
would require the search to understand gomoku threats, violating the game-
agnostic principle. The current quiescence filters for captures (lines 54-62):

```cpp
for (auto& move : state->legal_actions) {
    int to_r = move.second.first;
    int to_c = move.second.second;
    if (state->piece_at(1 - state->player, to_r, to_c)) {
        captures.push_back(move);
    }
}
```

Since gomoku has no captures, `piece_at()` always returns 0, and quiescence
immediately returns `stand_pat`. The search effectively has no quiescence for
gomoku already.

To make this work for gomoku, we would need either:
- A `get_tactical_moves()` virtual method on BaseState (returns captures for
  chess, threat moves for gomoku). This is the cleanest extension point.
- Overloading `piece_at()` to return nonzero for "threat" squares -- hacky and
  semantically wrong.

**Verdict:** Adding a `get_tactical_moves()` hook is a reasonable architecture
extension if we want to support quiescence for multiple game types. But it is
more invasive than Option A (VCF inside evaluate) and provides less benefit:
quiescence with threat moves has a large branching factor (many moves create
threats), whereas VCF has a tiny branching factor (only four-creating moves).
Defer this unless we find that VCF-in-evaluate is insufficient.

### Option D: Rely on Main Search Depth -- INSUFFICIENT

Just relying on the main search being deep enough does not work for gomoku.
The problem is fundamental: a VCF sequence can be 15-20 plies long (the
attacker plays 8-10 fours, each forcing a single block). The main search at
depth 8-10 cannot see the end of such sequences. Without VCF, the engine will
evaluate leaf nodes in the middle of a forcing sequence and return a misleading
score.

**Verdict:** Not viable as a standalone approach. The main search depth needed
to resolve VCF sequences naturally would be 20+, which is computationally
infeasible on 15x15 and barely feasible on 9x9.

### Recommendation

**Implement both Option A (VCF in evaluate) and Option B (forced-block pruning
in get_legal_actions).** They complement each other:

- Option B reduces the effective branching factor at forced nodes, giving the
  main search more depth for free.
- Option A catches VCF sequences that extend beyond the main search horizon.
- Neither requires changes to the search engine or BaseState interface.

---

## 3. Move Ordering for Gomoku

### The Problem

The current move ordering system (`src/policy/pvs/move_ordering.hpp`) is
designed for chess-like games. The `score_move()` function (lines 16-35)
scores moves by:

1. **MVV-LVA** for captures: `piece_val[captured] * 100 - piece_val[attacker]`
2. **Killer move bonus**: 50 points for killer moves
3. **Everything else**: 0

For gomoku, there are no captures (`piece_at()` always returns 0 for the
opponent at the target square, since gomoku does not have "capturing" pieces on
the board). Every gomoku move gets a score of 0 unless it is a killer move.
The result: moves are essentially unordered (stable sort preserves the
generation order from `get_legal_actions()`, which is top-left to bottom-right
row scan).

This is catastrophic for alpha-beta pruning efficiency. Good move ordering can
be the difference between searching to depth 6 and depth 12. In gomoku, the
best move is almost always a threat-creating move (creates a four or open-three)
or a defensive move (blocks an opponent's threat). These should be searched first.

### Option 1: Sort in get_legal_actions() -- RECOMMENDED

The simplest approach: `get_legal_actions()` returns moves pre-sorted by
priority. The search preserves order for equally-scored moves (all non-captures
score 0 in `score_move`), so the generation order directly determines the
search order for quiet moves.

**Implementation sketch:**

```cpp
void State::get_legal_actions() {
    // ... existing proximity mask and move collection ...

    // Score each move by the threats it creates/blocks
    struct ScoredMove {
        Move move;
        int priority;
    };
    std::vector<ScoredMove> scored;

    for (auto& m : legal_actions) {
        int r = m.second.first;
        int c = m.second.second;
        int priority = 0;

        // Check what threats this move creates for us
        board.board[r][c] = my_id;
        auto after_my = count_threats_at(board, r, c, my_id);
        board.board[r][c] = 0;

        // Check what threats this move blocks for opponent
        board.board[r][c] = opp_id;
        auto after_opp = count_threats_at(board, r, c, opp_id);
        board.board[r][c] = 0;

        // Priority: winning moves > blocking opponent fours >
        //           creating own fours > creating open-3s > ...
        if (after_my.five > 0)       priority = 10000;
        else if (after_opp.five > 0) priority = 9000;   // blocks opponent five
        else if (after_my.open4 > 0) priority = 8000;
        else if (after_my.half4 > 0) priority = 7000;
        else if (after_opp.open4 > 0) priority = 6000;  // blocks opponent open-4
        else if (after_my.open3 > 0) priority = 5000;
        else {
            // Positional: center preference
            int dr = abs(r - BOARD_H / 2);
            int dc = abs(c - BOARD_W / 2);
            priority = 100 - (dr + dc) * 5;
        }

        scored.push_back({m, priority});
    }

    std::sort(scored.begin(), scored.end(),
        [](const ScoredMove& a, const ScoredMove& b) {
            return a.priority > b.priority;
        });

    legal_actions.clear();
    for (auto& s : scored) {
        legal_actions.push_back(s.move);
    }
}
```

**Cost:** `count_threats_at()` (a localized version of `count_threats` that
only scans the 4 lines through a given cell) is O(4 * WIN_LENGTH) per move.
With ~30 candidate moves, that is ~600 cell inspections per get_legal_actions()
call. Affordable.

**Pros:**
- No changes to the search engine.
- Naturally works with all search algorithms (PVS, alpha-beta, minimax).
- The TT best move still gets promoted to first by the search's existing
  `get_ordered_moves()` (move_ordering.hpp lines 58-65).

**Cons:**
- Sorting cost is paid even if the search prunes after the first move.
- The priority scoring is coarse (does not distinguish between different types
  of four-creating moves). But even coarse ordering is vastly better than none.

### Option 2: Override score_move via piece_at() -- HACKY, NOT RECOMMENDED

We could abuse `piece_at()` to return a nonzero "virtual piece value" encoding
the threat priority at each square. Then `score_move()` would pick it up via
the capture check. But this is semantically wrong (`piece_at` is supposed to
return actual piece types), would confuse LMR (which checks `is_capture` via
`piece_at`, pvs.cpp line 147), and would break other assumptions.

**Verdict:** Do not do this.

### Option 3: Add a game-specific score_move() Hook to BaseState

Add a virtual method like:

```cpp
virtual int score_move(const Move& m) const { return 0; }
```

The move ordering code would call `state->score_move(m)` and add it to the
MVV-LVA score. Gomoku would override this to return threat-based priorities.
Chess/shogi would return 0 (their ordering already works via MVV-LVA).

**Pros:** Clean separation. The search remains game-agnostic but allows games
to provide ordering hints.

**Cons:** Adds a virtual method to BaseState that most games do not need. The
performance cost of a virtual call per move per node could be significant
(though likely dwarfed by the search savings from better ordering).

**Verdict:** A reasonable architecture extension, but Option 1 (sorting in
get_legal_actions) achieves the same result with zero interface changes. Prefer
Option 1 for now; consider Option 3 if we find that the generation-order
approach interacts badly with the TT-move-first logic in the search.

### Interaction with TT and Killers

The existing `get_ordered_moves()` (move_ordering.hpp line 41) copies
`state->legal_actions`, sorts by `score_move()`, then swaps the TT move to
front. If we pre-sort `legal_actions` in `get_legal_actions()`, the
`score_move()` sort is a no-op (all moves score 0, so sort is stable and
preserves our order), and the TT swap still works correctly. Killers also work:
they score 50 and will be promoted above the 0-scoring quiet moves, which is
correct behavior (a killer that caused a cutoff at a sibling node is a good
hint).

**One subtlety:** With pre-sorted legal_actions, the killer move bonus of 50
would reorder a killer above *all* quiet moves but below any captures (which
don't exist in gomoku). Since there are no captures, killers just go to the
front of the quiet moves, which is fine -- the TT move still gets ultimate
priority via the swap.

---

## 4. Quiescence Search

### Current Behavior for Gomoku

The quiescence search (`src/policy/pvs/quiescence.hpp`) filters moves to
captures only (lines 54-62). Since gomoku has no captures, the `captures`
vector is always empty. Quiescence immediately returns `stand_pat` (the static
eval). This means the search leaf nodes are evaluated with `evaluate()` only --
no search extension happens.

This is effectively "quiescence disabled." The search option `UseQuiescence`
is on by default, but it does nothing for gomoku.

### Option A: Make Quiescence Check for Threat Moves -- COMPLEX

Modify quiescence to search "tactical" moves for gomoku -- moves that create
fours or respond to fours. This would require a game-specific definition of
"tactical move" in the quiescence code, breaking the game-agnostic principle.

**Possible clean approach:** Add a virtual method to BaseState:

```cpp
virtual void get_tactical_moves(std::vector<Move>& moves) const {
    // Default: captures (current behavior)
    for (auto& m : legal_actions) {
        if (piece_at(1 - player, m.second.first, m.second.second))
            moves.push_back(m);
    }
}
```

Gomoku overrides to return four-creating and four-blocking moves. Chess/shogi
use the default (captures).

**Pros:** Clean extension point. Quiescence gains game-specific tactical
awareness while the search code stays generic.

**Cons:**
- For gomoku, "threat moves" in quiescence have a much higher branching factor
  than captures in chess. A typical position might have 5-15 threat moves.
  Quiescence with that branching factor could explode.
- VCF search (Option A from Section 2) is strictly better for resolving
  four-sequences because it constrains both sides (attacker plays fours,
  defender blocks fours), while quiescence with threat moves allows the
  defender to play any response.

**Verdict:** Not worth the complexity. VCF inside evaluate() achieves the same
goal more efficiently and with no interface changes. If we later want general
quiescence for gomoku, the `get_tactical_moves()` hook is the right approach,
but it is lower priority than VCF.

### Option B: Disable Quiescence for Gomoku -- CURRENT STATE

Quiescence is already effectively disabled for gomoku (no captures -> no
quiescence moves). We could make this explicit by compiling gomoku with
`UseQuiescence=false`, but it makes no functional difference since the empty
capture list causes an immediate return anyway.

**Verdict:** Leave as-is. The one-extra-evaluate cost of entering quiescence
and immediately returning is negligible.

### Option C: VCF as Quiescence Substitute

As discussed in Section 2 Option A, implement VCF inside `evaluate()`. This
serves the same purpose as quiescence -- resolving tactical sequences at leaf
nodes -- but is tailored to gomoku's threat structure.

**Verdict:** This is the recommended approach (see Section 2).

---

## 5. Practical Recommendation

### What to Do (Ordered by Priority)

Here is the recommended implementation plan, balancing impact, effort, and
respect for the game-agnostic architecture:

#### Step 1: Forced-Block Pruning in get_legal_actions() [LOW EFFORT, HIGH IMPACT]

**What:** When the opponent has a half-open four, return only blocking move(s)
plus any immediate winning moves for the current player. When the current player
has a winning move (five or open-4), return only that move.

**Where:** `src/games/gomoku/state.cpp`, modify `get_legal_actions()` (lines
89-146).

**Architecture impact:** None. The search just sees fewer legal moves, which is
entirely within the State's prerogative. The `legal_actions` vector has always
been the State's to populate however it sees fit.

**Why first:** This is the cheapest change with the biggest search speedup.
Forced positions currently waste search effort on ~30 moves when only 1-2 are
meaningful. Eliminating this waste effectively gives 3-5 extra plies of depth
in forcing lines.

#### Step 2: Pattern Table Eval [MEDIUM EFFORT, HIGH IMPACT]

**What:** Replace `count_threats()` with a sliding-window pattern lookup table.
Add broken-3 and broken-4 recognition. Recalibrate scoring weights.

**Where:** `src/games/gomoku/state.cpp`. Replace lines 173-254 with the pattern
table system. Add a `ThreatType pattern_table[2187]` (3^7 for 7-cell windows)
with lazy initialization.

**Architecture impact:** None. Internal to evaluate().

**Why second:** The current eval is blind to gap patterns, which are common and
strategically important. The pattern table also makes the eval faster (O(1)
lookups vs. loop-based scanning), which helps with the VCF search in Step 3.

#### Step 3: Move Ordering in get_legal_actions() [MEDIUM EFFORT, HIGH IMPACT]

**What:** Pre-sort legal_actions by threat priority: winning moves first, then
blocking moves, then threat-creating moves, then positional (center-preference).

**Where:** `src/games/gomoku/state.cpp`, at the end of `get_legal_actions()`.

**Architecture impact:** None. The search's `get_ordered_moves()` will
still place the TT move first and promote killers, but the underlying move order
becomes much better than the current row-scan order.

**Synergy:** Dramatically improves alpha-beta pruning, allowing deeper search
at the same time budget. Combined with Step 1, the effective search depth
could increase by 4-6 plies.

#### Step 4: VCF Search in evaluate() [MEDIUM-HIGH EFFORT, VERY HIGH IMPACT]

**What:** Implement a VCF solver inside `state.cpp`. Call it from `evaluate()`
between the decisive-threat check and the weighted scoring. Use a depth limit
(start with 12, tune upward).

**Where:** `src/games/gomoku/state.cpp`. Add `vcf_search()` as a static helper
function. Add a small Zobrist-keyed cache (separate from the main TT) for
VCF results.

**Architecture impact:** None. Entirely internal to evaluate().

**Why not first:** VCF needs the pattern table (Step 2) to efficiently detect
four-creating moves and the blocking square. Without the pattern infrastructure,
VCF implementation is harder and slower.

**Expected impact:** This is the single most important improvement for tactical
play. With VCF, the engine can "see" forced wins 20+ moves deep in the threat
space, even if the main search only reaches depth 8. Without it, the engine
will miss forced wins that any intermediate human player would spot.

#### Step 5: Null Move Support [LOW EFFORT, MEDIUM IMPACT]

**What:** Implement `create_null_state()` for gomoku (currently returns
`nullptr`, state.hpp line 52). A null state simply flips the side to move
without placing a stone.

**Where:** `src/games/gomoku/state.hpp` and `state.cpp`.

```cpp
BaseState* State::create_null_state() const {
    State* ns = new State(this->board, 1 - this->player);
    ns->step = this->step;
    ns->game_state = NONE;
    ns->get_legal_actions();
    return ns;
}
```

**Architecture impact:** None. The search already supports null-move pruning
(pvs.cpp lines 95-116) and checks for `nullptr` return.

**Caution:** Null-move pruning must be disabled in zugzwang-like positions.
In gomoku, zugzwang is rare (passing is almost never beneficial), so null-move
pruning should be safe. However, when the current player has a must-block
situation (opponent half-4), the null-move search might incorrectly suggest
the position is fine. The VCF-in-evaluate and forced-block-in-get_legal_actions
mitigations handle this: if the opponent has a half-4, get_legal_actions only
returns blocking moves, and the null-move child (which skips the block) will
see the opponent's winning follow-up.

#### Step 6 (Optional): get_tactical_moves() Hook [MEDIUM EFFORT, LOW MARGINAL IMPACT]

**What:** Add a `virtual void get_tactical_moves(vector<Move>&)` to BaseState.
Default implementation filters for captures. Gomoku overrides to return
four-creating and four-blocking moves. Quiescence uses this instead of its
hardcoded capture filter.

**Where:** `src/state/base_state.hpp` (new virtual method),
`src/policy/pvs/quiescence.hpp` (use the hook), gomoku `state.cpp` (override).

**Architecture impact:** Minor -- adds one virtual method to BaseState. All
existing games get the default (captures) for free.

**Why optional:** With VCF in evaluate(), quiescence extension for gomoku
threats adds marginal value. The VCF solver is more targeted and efficient.
This hook becomes valuable if we want a more general threat-resolution mechanism
or if we add other games with non-capture tactical moves (e.g., check extension
in chess-like games could also use this hook).

### What NOT to Change

1. **The search algorithms.** PVS, alpha-beta, and minimax should remain
   game-agnostic. All gomoku intelligence goes through the existing interface.

2. **The move_ordering.hpp score_move() function.** It works correctly for
   gomoku (returns 0 for all moves, deferring to generation order). No need
   to hack it.

3. **The quiescence search.** It naturally does nothing for gomoku (no captures).
   No need to disable it explicitly or add gomoku-specific logic.

4. **The BaseState interface.** All recommended changes (Steps 1-5) require
   zero modifications to BaseState. Step 6 (optional) adds one virtual method
   but is low priority.

### Summary Table

| Step | Change | Where | Architecture Impact | Effort | Impact |
|------|--------|-------|---------------------|--------|--------|
| 1 | Forced-block pruning | get_legal_actions() | None | Low | High |
| 2 | Pattern table eval | evaluate() internals | None | Medium | High |
| 3 | Threat-aware move ordering | get_legal_actions() | None | Medium | High |
| 4 | VCF in evaluate() | evaluate() internals | None | Med-High | Very High |
| 5 | Null-move support | create_null_state() | None | Low | Medium |
| 6 | get_tactical_moves() hook | BaseState + quiescence | Minor | Medium | Low (marginal) |

The first five steps require **zero changes to any shared code**. All work
happens inside `src/games/gomoku/state.cpp` and `state.hpp`. This is exactly
the architecture's intent: game-specific intelligence lives in the State class,
and the search engine handles game-agnostic tree exploration.

After implementing Steps 1-5, the gomoku engine should be capable of:
- Detecting all pattern types including gap patterns
- Seeing forced wins via continuous fours 20+ plies deep
- Efficiently pruning the search at forced positions
- Achieving effective search depth of 10-16 plies on 9x9 (6-10 on 15x15)
- Defeating casual-to-intermediate human players consistently
