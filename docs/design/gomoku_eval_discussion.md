# Gomoku Evaluation: From Naive to Strong

A comprehensive discussion of evaluation function design for gomoku (five-in-a-row),
with a focus on what it takes to build a strong engine for 15x15 standard gomoku
using minimax/alpha-beta search. Written in the context of our existing engine which
currently supports 9x9 gomoku with a basic threat-counting eval.

---

## Table of Contents

1. [Gomoku Eval Fundamentals](#1-gomoku-eval-fundamentals)
2. [Pattern-Based Evaluation](#2-pattern-based-evaluation)
3. [Threat Space Search](#3-threat-space-search)
4. [Practical Eval Design](#4-practical-eval-design)
5. [NNUE for Gomoku](#5-nnue-for-gomoku)
6. [15x15 Considerations](#6-15x15-considerations)
7. [Concrete Recommendations](#7-concrete-recommendations)

---

## 1. Gomoku Eval Fundamentals

### What Makes a Strong Gomoku Eval?

Gomoku is fundamentally a game of **threats and forcing sequences**. A position that
looks quiet can be one move away from an unstoppable winning chain. The evaluation
function must understand three things:

1. **Threat detection**: Recognizing patterns that force the opponent to respond
   (open-fours, half-open fours, open-threes, etc.).
2. **Threat combinations**: Two simultaneous threats can be individually blockable
   but jointly unstoppable (e.g., a "double-three" or "four-three fork").
3. **Threat tempo**: Whose turn it is matters enormously. An open-four on your turn
   is a guaranteed win; an open-four on the opponent's turn just means you must block.

### Why "Count Connections" is Terrible

The most naive eval counts how many stones each side has in consecutive sequences
and sums them up. This fails catastrophically because:

- **It misses double threats entirely.** Two separate open-threes that share a
  critical intersection create an unstoppable fork. A simple connection counter
  scores this the same as two unrelated open-threes that can be blocked one at a time.

- **It ignores forcing sequences.** A half-open four forces a single defensive
  response, giving the attacker tempo to set up the next threat. Connection counting
  treats a half-open four the same regardless of what other threats are nearby.

- **It conflates blocked and open formations.** Three-in-a-row blocked on both
  ends (dead formation) scores the same as three-in-a-row open on both ends
  (powerful threat). The difference is night and day.

- **It has no concept of "already won."** An open-four is an immediate win on
  your turn (the opponent cannot block both ends). The eval must return a
  near-mate score, not merely "slightly better."

### The Concept of Threats in Gomoku

Gomoku threats follow a strict hierarchy based on how many moves are needed to win
and how many defensive responses exist:

| Threat Type | Description | Defensive Responses |
|---|---|---|
| **Five** | 5+ in a row | 0 (game over) |
| **Open Four** | 4 in a row, both ends open (`_XXXX_`) | 0 (unstoppable) |
| **Half-Open Four** (aka "simple four" or "rush four") | 4 in a row, one end open (`OXXXX_`) | 1 (must block the open end) |
| **Open Three** (aka "live three") | 3 in a row, both ends open (`_XXX_`) | Opponent must prevent it becoming an open-four |
| **Broken Three** | 3 stones with a gap that can form an open-four (`_XX_X_` or `_X_XX_`) | Harder to see; same threat level as open-three |
| **Half-Open Three** (aka "rush three") | 3 in a row, one end open | Low threat; can be blocked trivially |
| **Open Two** | 2 in a row, both ends open | Developmental; not immediately forcing |

**Key insight**: The threat hierarchy is not linear. Two half-open fours are as
deadly as one open-four (the opponent can only block one). A half-open four combined
with an open-three is also winning (block the four, the three becomes an open-four).
The eval must recognize these **compound threats**.

---

## 2. Pattern-Based Evaluation

### Threat Hierarchy Scoring

The entire evaluation revolves around recognizing patterns on the board and assigning
scores that reflect their strategic value. The hierarchy, from most to least
valuable:

```
Five-in-a-row          >>> everything else (game over)
Open-four              >>> all non-winning patterns (unstoppable win next move)
Double half-open four  >>> very high (opponent can block one, not both)
Half-open four + open-three >>> very high (block four -> three becomes open-four)
Double open-three      >>> very high (opponent can block one, not both)
Single half-open four  >>> high (forces a response, gains tempo)
Single open-three      >>> medium-high (threatens to become open-four)
Broken three           >>> medium (gap pattern; same potential as open-three)
Half-open three        >>> low-medium
Open two               >>> low (developmental)
Half-open two          >>> very low
```

### Enumerating and Scoring Line Patterns Efficiently

The board is scanned in **four directions**: horizontal, vertical, and the two
diagonals. For each direction, we examine every line segment that could contain
a five-in-a-row (every window of 5 consecutive cells, or 6 cells for boundary
detection).

**Approach 1: Consecutive-stone counting (our current approach)**

Our current eval (`state.cpp`) walks each direction, finds runs of consecutive
stones, and counts open ends. This works but misses **gap patterns** like
`_XX_X_` (broken three) which are strategically equivalent to `_XXX_`.

**Approach 2: Sliding window with pattern matching**

A stronger approach uses a **6-cell sliding window** (the extra cell on each side
detects boundary conditions). For each window, we classify the pattern by counting:
- Player stones in the window
- Opponent stones in the window
- Empty cells
- Boundary openness (are positions 0 and 5 open?)

The classification distinguishes "live" (both ends open) from "blocked" (one or more
ends closed). Treating cells outside the board as opponent stones naturally handles
edge positions.

**Approach 3: Pattern lookup table**

The most efficient method precomputes all possible patterns. For a window of length
`L` with 3 possible cell states (empty, player, opponent), there are `3^L` possible
patterns. For `L=11` (used by the Rapfi engine), this gives ~177,000 patterns per
direction. Each pattern maps directly to a feature or score via table lookup.

For a simpler implementation, a window of 5-6 cells gives `3^5 = 243` or `3^6 = 729`
patterns -- small enough to fit in a lookup table that maps each pattern to its
threat classification.

### Direction-Based Scanning

For each cell on the board, examine four line segments passing through it:

```
Horizontal:  (r, c-4) to (r, c+4)
Vertical:    (r-4, c) to (r+4, c)
Diagonal /:  (r-4, c+4) to (r+4, c-4)
Diagonal \:  (r-4, c-4) to (r+4, c+4)
```

To avoid double-counting, scan each line from one end only (e.g., left-to-right for
horizontals, top-to-bottom for verticals). Our current code handles this by only
processing a run when the preceding cell is NOT the same stone.

### Pattern Tables / Lookup Tables

A **pattern table** encodes every possible local configuration into a threat type.
Implementation outline:

```
// Encode a line segment of length L into a single integer
// Each cell is 0 (empty), 1 (player), 2 (opponent)
int encode_line(cells[], length) {
    int code = 0;
    for (int i = 0; i < length; i++)
        code = code * 3 + cells[i];
    return code;
}

// Precompute: for each possible encoded pattern, store the threat type
ThreatType pattern_table[3^L];  // populated at startup

// At eval time: O(1) lookup per window position
ThreatType classify(cells[], length) {
    return pattern_table[encode_line(cells, length)];
}
```

The table is built once at startup by iterating all `3^L` patterns and classifying
each one (count stones, check gaps, check boundaries). This makes the eval extremely
fast: the entire board can be evaluated in O(H * W * 4) lookups.

---

## 3. Threat Space Search

### What is Threat Space Search (TSS)?

Threat Space Search is a **specialized search algorithm** designed for gomoku by
L.V. Allis, H.J. van den Herik, and M.P.H. Huntjens. Rather than exploring the
entire game tree (which is enormous in gomoku), TSS only considers **threat
sequences** -- moves that create threats the opponent must respond to.

The key insight: human gomoku players do not search every possible move. They look
for sequences of threats that, if answered correctly, lead to another threat, and
so on until a winning position is reached. TSS formalizes this strategy.

### How TSS Differs from Standard Alpha-Beta

| Aspect | Standard Alpha-Beta | Threat Space Search |
|---|---|---|
| **Move generation** | All legal moves (or heuristic subset) | Only moves that create threats |
| **Branching factor** | 30-80+ on 15x15 | Typically 5-15 threat moves |
| **Defender moves** | All responses considered | Only defenses to the specific threat |
| **Depth** | Fixed or iterative deepening | As deep as the threat chain goes |
| **Goal** | Best static eval at leaves | Prove a forced win exists |

TSS does not replace alpha-beta; it **complements** it. A typical strong gomoku
engine uses alpha-beta for general search and invokes TSS (specifically VCF/VCT
search) at leaf nodes or when threats are detected.

### VCF: Victory by Continuous Fours

VCF (Victory by Continuous Fours) searches for a winning sequence where:
- The attacker plays a move creating a **four** (half-open or open) on every turn
- The defender has **exactly one** forced response each time (block the four)
- The sequence ends with an unblockable five-in-a-row

Because the defender has no choice at each step, VCF has an extremely small branching
factor on the defender's side (effectively 1). The attacker's branching factor is
the number of moves that create a new four. This makes VCF very cheap to search.

**VCF is the gomoku analog of "quiescence search" in chess.** Just as chess engines
extend the search at leaf nodes to resolve captures and checks, gomoku engines run
a VCF search at leaf nodes to resolve four-sequences. This prevents the horizon
effect where the engine stops searching right before an unstoppable four-sequence.

```
bool vcf_search(board, attacker, depth_limit) {
    // Try every move that creates a four for the attacker
    for each move in generate_four_moves(board, attacker):
        make_move(board, move)
        if is_five(board, attacker):
            return true   // won

        // Defender must block (only one legal response to a four)
        defense = find_forced_block(board, attacker)
        make_move(board, defense)

        if vcf_search(board, attacker, depth_limit - 1):
            return true   // won through continued fours

        undo_move(board, defense)
        undo_move(board, move)
    return false
}
```

### VCT: Victory by Continuous Threats

VCT (Victory by Continuous Threats) is a broader version of VCF. The attacker can
use **any** forcing threat (fours OR open-threes), not just fours. This gives the
attacker more options but also gives the defender more responses.

VCT is significantly more expensive than VCF because:
- The attacker has more candidate moves (all four-creating AND three-creating moves)
- The defender may have multiple valid responses to an open-three
- The defender can counter-attack with their own fours during the sequence

VCT is more powerful but computationally heavier. A practical engine might:
1. Always run VCF at leaf nodes (cheap, high value)
2. Run VCT only in promising positions or with limited depth
3. Use full alpha-beta for everything else

### Why Gomoku Benefits from Threat-Specific Search

Gomoku has a property that chess does not: **threats are extremely local and
classifiable.** A four must be blocked in exactly one way. An open-three has a
small set of effective defenses. This structure makes threat-specific search
feasible and powerful.

In chess, a "threat" is vague -- it could be a pin, a fork, a discovered attack,
an overloaded piece. In gomoku, threats are precisely defined geometric patterns.
This precision is what makes TSS/VCF/VCT work so well.

---

## 4. Practical Eval Design

### Concrete Eval Function Structure

Here is a pseudocode outline for a strong gomoku evaluation function:

```
function evaluate(board, side_to_move):
    // Phase 1: Check terminal states
    if five_in_a_row(board, side_to_move):
        return +INFINITY
    if five_in_a_row(board, opponent):
        return -INFINITY

    // Phase 2: Count threats for both sides
    my_threats  = scan_all_threats(board, side_to_move)
    opp_threats = scan_all_threats(board, opponent)

    // Phase 3: Check for decisive compound threats
    // (these are effectively won/lost regardless of other factors)
    if my_threats.open4 > 0:
        return +WIN_SCORE     // unstoppable
    if my_threats.half4 >= 2:
        return +WIN_SCORE - 1 // can't block both
    if my_threats.half4 >= 1 AND my_threats.open3 >= 1:
        return +WIN_SCORE - 2 // block four -> open-three wins
    if my_threats.open3 >= 2:
        return +WIN_SCORE - 3 // double-three fork

    if opp_threats.open4 > 0:
        return -WIN_SCORE     // opponent wins next move
    if opp_threats.half4 >= 2:
        return -WIN_SCORE + 1

    // Phase 4: Weighted threat scoring
    score = 0

    // Offensive threats
    score += my_threats.half4  * 5000
    score += my_threats.open3  * 800
    score += my_threats.broken3 * 600   // <-- our current eval misses this!
    score += my_threats.half3  * 150
    score += my_threats.open2  * 100
    score += my_threats.half2  * 20

    // Defensive pressure (opponent threats are negative)
    score -= opp_threats.half4  * 5000  // we MUST respond to this
    score -= opp_threats.open3  * 800
    score -= opp_threats.broken3 * 600
    score -= opp_threats.half3  * 150
    score -= opp_threats.open2  * 100
    score -= opp_threats.half2  * 20

    // Phase 5: Positional bonus
    score += positional_bonus(board, side_to_move)

    // Phase 6: Tempo bonus (side to move has initiative)
    score += TEMPO_BONUS   // typically 50-200

    return score
```

### How to Assign Scores to Patterns

The scoring values should reflect the **strategic gap** between threat levels. The
key principle: each level in the threat hierarchy should be worth more than all
lower-level threats combined. This prevents the eval from trading a critical threat
for many weak ones.

**Recommended score ranges:**

| Pattern | Score | Rationale |
|---|---|---|
| Five | +/- INFINITY | Game over |
| Open Four | +/- 100,000 | Unstoppable win |
| Double Half-Four | +/- 90,000 | Cannot block both |
| Half-Four + Open-Three | +/- 80,000 | Block four -> open-four from three |
| Double Open-Three | +/- 70,000 | Cannot block both |
| Single Half-Four | 5,000 | Forces response; gains tempo |
| Open Three | 800 | Threatens to become open-four |
| Broken Three | 600 | Same potential; harder to spot |
| Half-Open Three | 150 | Limited; can be blocked |
| Open Two | 100 | Developmental |
| Half-Open Two | 20 | Marginal |

These values are tuned so that:
- No accumulation of open-twos can outweigh a single half-four
- A half-four dominates the non-decisive scoring
- The decisive compound threats are handled separately (Phase 3) and receive
  near-infinity scores

**Important tuning principle**: The ratio between adjacent threat levels matters more
than the absolute values. Many tournament-winning engines use an exponential formula
like `score = 1.5 * 1.8^threat_level` (where threat_level ranges from 0 to 16)
rather than hand-picked constants.

### Position-Based Bonuses

Center control matters in gomoku because:
- A stone at the center can participate in lines in **all 4 directions**
- A stone on the edge can only participate in 2-3 directions
- A corner stone has the fewest line possibilities

A simple positional bonus table for 15x15:

```
function positional_bonus(board, player):
    bonus = 0
    center_r = BOARD_H / 2
    center_c = BOARD_W / 2
    for each stone of player at (r, c):
        // Manhattan distance from center, inverted
        dist = abs(r - center_r) + abs(c - center_c)
        bonus += max(0, 14 - dist)  // 14 at center, 0 at far corners
    return bonus
```

Alternatively, precompute a table based on how many distinct 5-cell lines pass
through each cell:

```
Lines through center (7,7) on 15x15: ~20 lines
Lines through corner (0,0) on 15x15: ~4 lines
Lines through edge midpoint (0,7): ~10 lines
```

The positional bonus should be small relative to threat scores -- it is a tiebreaker,
not a dominant factor.

### Handling Forbidden Moves (Renju Rules)

Standard gomoku ("freestyle") has no forbidden moves -- either player can make any
pattern. However, **Renju** (the competitive variant) restricts Black:

- **Double-three (3x3 fork)**: Black cannot play a move that simultaneously creates
  two open-threes.
- **Double-four (4x4 fork)**: Black cannot play a move that simultaneously creates
  two fours (open or half-open).
- **Overline**: Black cannot make 6+ in a row.

These restrictions exist because Black (first player) has a proven winning strategy
in freestyle gomoku. Renju forbidden moves balance the game.

**Impact on evaluation:**
- If playing Renju, the eval must check whether a "winning" compound threat for
  Black is actually legal. A double-three that would win in freestyle is a *losing*
  move in Renju (it is forbidden, and the game is forfeited).
- The move generator must filter out forbidden moves for Black.
- White can **exploit** forbidden moves: placing stones to create positions where
  Black's only good move is forbidden.

For a freestyle gomoku engine (our current target), forbidden moves are not relevant,
but the infrastructure should be designed so Renju support can be added later.

### Defensive vs. Offensive Balance

A common mistake is making the eval too aggressive (overvaluing own threats) or too
passive (overvaluing opponent threats). Guidelines:

- **Threats on your turn are worth more** than the same threats on the opponent's
  turn. An open-three when you have the move is a strong attacking asset. An
  open-three when the opponent has the move is just something they might build on.
  This is why the tempo bonus exists.

- **The opponent's half-four is a crisis.** If the opponent has a half-four and
  it is your turn, you MUST block it -- you have no choice. This drastically
  reduces the value of your own non-decisive threats because you cannot exploit
  them this turn.

- **Defensive moves should be scored by the search, not the eval.** The eval
  should report the threat landscape. The *search* (alpha-beta) handles the
  question "what happens after I block?" by exploring the resulting position.

---

## 5. NNUE for Gomoku

### Does NNUE Make Sense for Gomoku?

NNUE (Efficiently Updatable Neural Network) was designed for chess, where the
HalfKP feature set encodes piece-square relationships relative to the king. Gomoku
has no king, no piece types beyond Black/White, and no captures. So the chess-style
NNUE architecture does not translate directly.

However, the **core NNUE principle** -- an efficiently updatable neural network
with sparse binary inputs -- absolutely applies. The question is what feature
representation to use.

### Feature Representations for Gomoku NNUE

**Option A: PieceSquare (simplest)**

Each input feature is "stone of color C is on square S." For a 15x15 board with
2 colors, this gives `2 * 225 = 450` binary input features. This is very sparse
(each position has ~10-50 active features depending on game phase).

Pros: Simple to implement, incrementally updatable (flip one feature on per move).
Cons: Does not encode *relationships* between squares. The network must learn
spatial patterns entirely from weights.

**Option B: Line patterns (Rapfi-style)**

The Rapfi engine (ranked #1 among 520 gomoku agents on Botzone, and GomoCup 2024
champion) uses a revolutionary approach:

1. Decompose the board into **line segments of length 11** in each of the 4
   directions.
2. Each line segment is one of ~397,488 possible patterns (3 states per cell,
   with border handling).
3. A **mapping network** (directional convolutions) converts each pattern to a
   feature vector.
4. After training, the mapping network is **exported losslessly** as a
   pattern-indexed codebook (lookup table).
5. At inference time, each board position looks up 4 patterns (one per direction)
   and sums their feature vectors.

This gives CNN-quality pattern recognition at lookup-table speed. The feature map
is **incrementally updatable**: placing one stone changes at most `4 * 11 = 44`
pattern entries.

Rapfi model sizes and speeds:

| Model | Parameters | Codebook Size | Alpha-Beta NPS |
|---|---|---|---|
| Small | 14K | 28 MB | 428K |
| Medium | 28K | 55 MB | 257K |
| Large | 56K | 111 MB | 104K |

For comparison, a ResNet-20b256f achieves similar accuracy but requires 5.3 billion
FLOPs per evaluation vs. Rapfi-Medium's 146 FLOPs.

**Option C: Raw CNN**

Use a convolutional neural network that takes the full board as input (two binary
planes: one for Black, one for White). This is the AlphaZero approach.

Pros: Learns all spatial patterns naturally; very strong with enough training data.
Cons: Cannot be incrementally updated. Every evaluation requires a full forward pass.
This makes it unsuitable for high-NPS alpha-beta search (but fine for MCTS).

### Recommendation

For an alpha-beta engine, the Rapfi-style pattern codebook is the most promising
NNUE approach. It combines:
- The pattern recognition quality of CNNs
- The speed of table lookups
- Incremental updateability for efficient search

However, implementing a Rapfi-style system is a significant engineering effort.
A strong handcrafted eval should come first. A training pipeline for generating
self-play data at sufficient volume is also a prerequisite.

---

## 6. 15x15 Considerations

### State Space and Search Complexity

| Board Size | Empty Squares | Branching Factor (naive) | Branching Factor (pruned*) |
|---|---|---|---|
| 9x9 | 81 | ~81 early, ~60 mid | ~15-25 |
| 15x15 | 225 | ~225 early, ~180 mid | ~30-80 |

(*) Pruned = only considering moves within Manhattan distance 2 of existing stones.

The 15x15 board has **~3x the branching factor** of 9x9 when using proximity-based
move generation. This means:
- Each additional ply of search is ~3x more expensive
- At the same time budget, 15x15 search reaches ~2 plies less depth than 9x9
- The game tree at 15x15 is astronomically larger

### How Deep Can Alpha-Beta Search at 15x15?

With a well-optimized engine (good move ordering, transposition table, null-move
pruning, proximity-based move generation), rough depth expectations on a modern CPU:

| Time Budget | Expected Depth (basic) | Expected Depth (optimized) |
|---|---|---|
| 100ms | 2-3 ply | 4-6 ply |
| 1 second | 3-4 ply | 6-8 ply |
| 5 seconds | 4-5 ply | 8-12 ply |
| 30 seconds | 5-6 ply | 10-16 ply |

"Basic" = minimax with alpha-beta, no other optimizations.
"Optimized" = iterative deepening + TT + killer moves + null-move + VCF at leaves +
good move ordering + late move reductions.

**Important**: With VCF search at leaf nodes, the effective depth is much greater
for tactical sequences. An engine that searches to depth 8 with VCF extensions can
"see" forced four-sequences 20+ moves deep.

### Move Ordering Strategies

Move ordering is critical for alpha-beta pruning efficiency. On a 15x15 board, the
difference between good and bad move ordering can be the difference between depth 6
and depth 12 search.

**Priority order for move generation:**

1. **Winning moves**: Any move that creates five-in-a-row (check first, instant
   cutoff).
2. **Forced defensive moves**: If the opponent has a four, we MUST block it. Only
   generate the blocking move(s).
3. **Threat-creating moves**: Moves that create half-fours or open-threes. These
   are the most likely to cause cutoffs.
4. **TT move**: The best move from a previous search of this position (from the
   transposition table).
5. **Killer moves**: Moves that caused beta cutoffs at the same depth in sibling
   nodes.
6. **Proximity-ordered**: Among remaining moves, prefer moves closer to existing
   stones and closer to the center.
7. **History heuristic**: Moves that have historically caused cutoffs at any depth.

**Center-first bias**: On an empty or near-empty board, moves near the center
should be explored first. The center of a 15x15 board (7,7) can participate in
~20 five-cell lines, compared to ~4 for a corner. Early game move ordering should
strongly prefer the central region.

**Near-threat-first**: Moves adjacent to existing threats (especially opponent
threats that need blocking) should be prioritized. This naturally emerges from the
proximity mask but can be enhanced by scoring each candidate move by the number of
threats it creates or blocks.

### Pruning Strategies Specific to Gomoku

Beyond standard alpha-beta pruning:

**1. Forced-move extension**: If there is only one legal response (e.g., must block
an opponent's four), do not count it as a ply. Extend the search for free. This
captures forced sequences without wasting depth.

**2. VCF extension at leaf nodes**: Before returning the static eval at a leaf node,
run a VCF search. If a forced win via continuous fours is found, return a win score.
This is the single most impactful improvement for gomoku search.

**3. Null-move pruning**: Skip your turn and search with reduced depth. If the
resulting score is still above beta (opponent can't exploit the tempo loss), prune.
Works well in non-tactical positions. Must be disabled when the side to move is
in a "must-block" situation.

**4. Late Move Reductions (LMR)**: After searching the first few moves at full
depth, search remaining moves at reduced depth. If a reduced-depth search finds a
promising score, re-search at full depth. This saves enormous time on the many
quiet moves in gomoku.

**5. Proximity pruning**: Completely ignore moves far from all existing stones.
On a 15x15 board, moves more than 2-3 squares from any stone are almost never
useful. Our current engine already does this (Manhattan distance <= 2).

**6. Threat-based forward pruning**: In a non-tactical position, only search the
top N candidate moves (sorted by threat potential). Risky but practical at 15x15
where the branching factor is otherwise too high.

---

## 7. Concrete Recommendations

### Recommended Eval Architecture for Our Engine

Based on the analysis above, here is a phased improvement plan:

#### Phase 1: Fix the Current Eval (Immediate)

Our current eval in `src/games/gomoku/state.cpp` is already decent -- it detects
compound threats (open-four, double half-four, half-four + open-three, double
open-three) and assigns near-win scores. However, it has significant gaps:

**Gap 1: No broken/gap patterns.**
The current `count_threats()` function only finds consecutive runs of stones. It
completely misses patterns like `_XX_X_` or `_X_XX_` (broken threes) and
`_XXX_X` or `_X_XXX` (broken fours). These patterns are strategically equivalent
to their non-gapped counterparts and are a major blind spot.

**Gap 2: No per-intersection threat analysis.**
The current eval counts threats globally for each side. A stronger approach
maintains a **threat board**: for each empty cell, what threat would be created
if a stone were placed there? This enables much better move ordering and detects
compound threats more accurately.

**Gap 3: Current score values may not be well-calibrated.**
The current values (open3=500, half3=80, open2=60, half2=10, half4=5000) have a
suspicious gap: there is a 10x jump from open3 (500) to half4 (5000) but only a
6x jump from half3 (80) to open3 (500). The values should follow a more consistent
exponential curve.

**Fix 1**: Extend pattern detection to recognize gap patterns. Scan windows of
length 6 (not just consecutive runs) and classify all patterns including broken
threes and broken fours.

**Fix 2**: Recalibrate scores. Suggested values:

```cpp
static int threat_score(const ThreatCounts& t){
    return t.half4   * 5000
         + t.open3   * 800
         + t.broken3 * 600   // NEW
         + t.half3   * 150
         + t.open2   * 100
         + t.half2   * 20;
}
```

#### Phase 2: Pattern Lookup Table (Medium-term)

Replace the consecutive-run scanner with a **pattern lookup table**:

1. Define a window length of 6 cells (5 interior + 1 boundary indicator).
2. Encode each window as a base-3 integer (729 possible values).
3. Precompute a table mapping each code to its threat classification.
4. Scan the board in 4 directions using O(1) lookups.

This is faster, catches all gap patterns automatically, and is easier to extend
with new pattern types.

#### Phase 3: Threat Board + Move Ordering (Medium-term)

Maintain an incremental **threat board** that tracks, for each empty cell and each
direction, the best threat available. When a stone is placed, update only the
affected cells (at most ~40 cells change per move in 4 directions).

Use the threat board for:
- **Move ordering**: Prioritize cells with the highest combined threat score
- **Compound threat detection**: Check if any cell creates two simultaneous threats
- **Forced move detection**: Instantly identify if a blocking move is required

#### Phase 4: VCF Search at Leaf Nodes (High priority)

Implement VCF search as a quiescence extension. Before returning the static eval
at any leaf node, check if the side to move has a forced win via continuous fours.
This is the single highest-impact improvement for tactical play.

The VCF search is simple to implement (see pseudocode in Section 3) and cheap
to run because the branching factor is very small (only four-creating moves for
the attacker, exactly one response for the defender).

#### Phase 5: NNUE (Long-term)

Once the handcrafted eval and search are solid, consider training an NNUE-style
network. The Rapfi approach (pattern codebook distilled from a CNN) is ideal:

1. Train a small CNN (e.g., 6-block ResNet with 96 filters) on self-play data
2. Use the CNN to generate training targets for a Mixnet-style pattern codebook
3. Export the codebook for O(1) pattern lookups during search
4. Integrate with incremental updates in the alpha-beta search

This requires significant infrastructure (self-play pipeline, training code) but
the payoff is enormous: Rapfi's smallest model (14K parameters) achieves near-CNN
accuracy at 428K nodes/second in alpha-beta search.

### Priority of Improvements

Ranked by impact-to-effort ratio:

1. **VCF search at leaf nodes** -- Highest impact. Eliminates tactical blindness.
   Moderate implementation effort.
2. **Gap pattern detection** -- High impact. Our current eval is blind to broken
   threes/fours. Low implementation effort.
3. **Better move ordering** -- High impact on search depth. Moderate effort (threat
   board needed).
4. **Pattern lookup table** -- Moderate impact (speed + correctness). Moderate effort.
5. **15x15 board support** -- Change `BOARD_H`/`BOARD_W` to 15 and increase
   proximity distance to 2-3. Low effort but search will be shallower.
6. **LMR + null-move pruning** -- Moderate impact at 15x15. May already exist in
   the engine's search framework.
7. **NNUE** -- Highest ceiling but massive effort. Only after everything else is
   solid.

### Minimum Eval for Reasonable Play at 15x15

To play "reasonably" (beat casual humans, avoid obvious blunders) at 15x15 with
alpha-beta, the minimum requirements are:

1. **Threat detection including gap patterns** -- Must recognize broken threes/fours
2. **Compound threat detection** -- Must recognize double-three and four-three forks
   as decisive
3. **Half-four forcing** -- Must understand that opponent's half-four requires
   immediate blocking
4. **Proximity-based move generation** -- Essential to keep branching factor
   manageable (already implemented)
5. **VCF at leaf nodes** -- Without this, the engine will miss forced wins that are
   1-2 moves beyond its search horizon
6. **Search depth >= 6 ply** -- Below this, the engine cannot see threats develop;
   requires good move ordering and TT

With these in place, alpha-beta at depth 6-8 with VCF extensions should produce
play that defeats most casual players and provides a reasonable challenge. For
competitive play against strong engines, NNUE and deeper search (10+ ply with
LMR) become necessary.

---

## References and Further Reading

- [Tournament-winning gomoku AI (Sorting and Searching)](https://sortingsearching.com/2020/05/18/gomoku.html) -- Detailed description of a competition-winning engine with threat-based evaluation and dependency-based search.
- [Rapfi: Distilling Efficient Neural Network for the Game of Gomoku (arXiv)](https://arxiv.org/html/2503.13178v1) -- State-of-the-art gomoku engine using pattern codebook distillation; ranked #1 among 520 agents.
- [Rapfi engine source code (GitHub)](https://github.com/dhbloo/rapfi) -- Reference implementation of the strongest known gomoku/renju engine.
- [Rapfi NNUE trainer (GitHub)](https://github.com/dhbloo/pytorch-nnue-trainer) -- Training code for gomoku NNUE and CNN models.
- [Go-Moku and Threat-Space Search (Allis et al.)](https://www.researchgate.net/publication/2252447_Go-Moku_and_Threat-Space_Search) -- Foundational paper on TSS, VCF, and VCT.
- [Go-Moku Solved by New Search Techniques (AAAI)](https://cdn.aaai.org/Symposia/Fall/1993/FS-93-02/FS93-02-001.pdf) -- Proof-number search and threat-space search for solving gomoku.
- [Pattern Detection in Gomoku AI (DeepWiki)](https://deepwiki.com/whyb/Gomoku-AI/2.3-pattern-detection) -- Six-cell sliding window approach with boundary-aware pattern classification.
- [Design of a Gomoku AI Based on Alpha-Beta Pruning (ResearchGate)](https://www.researchgate.net/publication/385905340_Design_of_a_Gomoku_AI_Based_on_the_Alpha-Beta_Pruning_Search_Algorithm) -- Alpha-beta pruning and pattern evaluation for gomoku.
- [Minimax for Gomoku (Ofek Foundation)](https://blog.theofekfoundation.org/artificial-intelligence/2015/12/11/minimax-for-gomoku-connect-five/) -- Concrete scoring values and minimax implementation.
- [UCT-ADP Progressive Bias Algorithm for Solving Gomoku (arXiv)](https://arxiv.org/pdf/1912.05407) -- MCTS + VCF/VCT pruning strategies.
- [Renju rules and forbidden moves (RenjuNet)](https://www.renju.net/rules/) -- Official rules for Renju including double-three, double-four, and overline restrictions.
