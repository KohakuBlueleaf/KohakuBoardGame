# Other Games for UBGI: Analysis and Recommendations

This document evaluates candidate board games for inclusion in the Universal Board
Game Interface (UBGI) engine. The analysis focuses on games that satisfy the
following constraints:

- **Manageable state space**: not so large that search is impractical at
  reasonable depths.
- **Handcraftable evaluation function**: a human-designed heuristic should be
  able to reach competent play (NNUE can improve later, but there must be a
  reasonable starting point).
- **Alpha-beta friendly**: the game should work well with minimax / alpha-beta /
  PVS search, not require Monte Carlo Tree Search.
- **UBGI compatible**: alternating turns, board state, legal moves, eval score.
  The game should fit naturally into the existing `BaseState` interface (move
  generation, `next_state`, `evaluate`, `hash`, `encode_board`/`decode_board`).

The existing UBGI lineup is **MiniChess** (5x6 chess variant), **MiniShogi**
(5x5 shogi variant), and **Gomoku** (9x9, five-in-a-row). New games should
complement this lineup by exercising different aspects of the engine.

---

## 1. Othello / Reversi

### Rules Summary

Played on an 8x8 board (or 6x6 variant). Two players (Black and White) take
turns placing discs. A move must "sandwich" one or more opponent discs between
the newly placed disc and an existing friendly disc, flipping all sandwiched
discs. If a player has no legal move, they pass. The game ends when neither
player can move; the player with the most discs wins.

### Board Size and State Space

| Variant | Board   | State-Space (log10) | Game-Tree (log10) |
|---------|---------|---------------------|--------------------|
| 6x6     | 36 cells| ~15                 | ~20                |
| 8x8     | 64 cells| ~28                 | ~58                |

The 8x8 game has roughly 10^28 legal positions, which is orders of magnitude
smaller than chess (~10^46). The 6x6 variant is dramatically smaller and has
been strongly solved (White wins with perfect play).

The 8x8 game was **weakly solved** in 2023 by Hiroki Takizawa: perfect play by
both sides leads to a **draw**. The solution used Edax, an alpha-beta engine,
solving ~1.5 billion positions with 36 empty squares.

### Search Depth Feasibility

Othello's average branching factor is approximately 8-10 (much lower than
chess's ~35). Combined with the fixed game length (at most 60 plies), this
makes alpha-beta search very effective:

- Depth 8-10 is fast on modern hardware.
- Depth 12-16 is feasible with good move ordering and transposition tables.
- Endgame solving (last 20-28 empty squares) is standard practice: once few
  squares remain, the engine can search to the end of the game exactly.

Alpha-beta works **extremely well** for Othello. The strongest Othello engines
(Edax, Saio, Logistello) are all alpha-beta based. MCTS has been tried but
alpha-beta consistently outperforms it for Othello.

### Evaluation Function Difficulty: 4/10

Othello has one of the best-understood handcrafted evaluation functions of any
board game. Key features:

- **Disc count**: raw material, but only decisive in endgame.
- **Mobility**: number of legal moves available -- the most important mid-game
  feature. Having more moves means the opponent is more constrained.
- **Corners**: corners can never be flipped and are extremely valuable.
  Corner-adjacent squares (X-squares, C-squares) are dangerous to occupy early.
- **Stability**: discs that can never be flipped (e.g., connected to a corner
  along an edge). Counting stable discs is the strongest positional feature.
- **Edge patterns**: full edge configurations (2^8 patterns per edge, or 6561
  ternary patterns) can be precomputed and scored.
- **Parity**: who makes the last move in a region. Important in endgame.

A simple eval with corners + mobility + stability easily reaches intermediate
strength. Pattern-based eval (Logistello-style) reaches expert level without
neural networks.

### Solved Status

- **4x4**: trivially solved.
- **6x6**: strongly solved (White wins).
- **8x8**: weakly solved (Draw with perfect play, 2023).

### Implementation Effort: Medium

- **Board representation**: a 64-bit bitboard per player is natural (two
  `uint64_t` values). Flipping logic requires directional ray tracing.
- **Move generation**: check all 8 directions from each empty cell for
  bracketing. Moderately complex but well-documented.
- **State encoding**: simple -- 64 cells, each empty/black/white.
- **Move encoding**: placement moves (2-char, like Gomoku).
- **Special rules**: passing when no legal moves exist. The UBGI protocol can
  handle this with a "0000" null move or by auto-passing.
- **Estimated effort**: 2-3 days for a competent implementation.

### Interesting for NNUE Training: Yes

The WTHOR database contains 100,000+ expert games with exact scores, providing
excellent training data. Othello's fixed-size board and simple piece types
(only two: empty and disc) make it a clean testbed for NNUE architectures.
Neural network evaluation has been extensively studied for Othello, and NNUE's
incremental update property maps well to the flip-based state transitions.

### Overall Recommendation: **ADD** (Priority 1)

Othello is the single best candidate for UBGI expansion. It complements the
existing lineup perfectly:

- Unlike chess/shogi, it has no piece types or drops -- just disc flips.
- Unlike Gomoku, it has a rich positional eval with stability and mobility.
- Alpha-beta is the gold standard for Othello AI.
- The 6x6 variant offers a smaller testbed (like MiniChess vs standard chess).
- The eval function is well-understood but nontrivial, exercising different
  evaluation concepts than the piece-value + piece-square tables of chess.

---

## 2. Connect Four

### Rules Summary

Played on a vertical 7-wide, 6-high grid. Players alternate dropping discs into
columns; discs fall to the lowest available row. The first player to align four
discs horizontally, vertically, or diagonally wins. If the board fills without
four-in-a-row, it is a draw.

### Board Size and State Space

| Metric              | Value          |
|---------------------|----------------|
| Board               | 7 x 6 = 42 cells |
| State-space (log10) | ~14 (about 4.5 trillion positions) |
| Game-tree (log10)   | ~21            |
| Branching factor    | ~4 (at most 7, average lower due to column fills) |

This is a very manageable state space, much smaller than any other candidate.

### Search Depth Feasibility

Connect Four's low branching factor (at most 7, often 4-5 as columns fill)
makes deep search easy:

- Depth 12-16 is fast.
- Depth 20+ is feasible with good move ordering.
- **Perfect play** is achievable with a moderately optimized engine (the game
  has been solved since 1988 by James Dow Allen and independently by Victor
  Allis). First player wins with perfect play starting in the center column.

### Evaluation Function Difficulty: 2/10

Very easy to handcraft:

- **Threats**: count connected groups of 2, 3, and 4 discs with open ends.
- **Center control**: the center column is strategically dominant.
- **Odd/even threat analysis**: odd-row threats for the first player and even-row
  threats for the second player are a well-known strategic concept.
- **Zugzwang detection**: in Connect Four, being forced to move can be
  disadvantageous (unlike most games).

A simple threat-counting eval reaches strong play quickly.

### Solved Status

**Fully solved** (1988). First player wins with perfect play. All positions with
8 or fewer discs have been completely enumerated.

### Implementation Effort: Low

- **Board representation**: 7 columns, each a stack of at most 6 discs. Can use
  a compact bitboard (49 bits suffice).
- **Move generation**: trivial -- just check which columns are not full (at most
  7 legal moves).
- **State encoding**: simple column-based or row-based string.
- **Move encoding**: single column letter (a-g), or placement at the column's
  lowest empty row. Could use the 2-char placement format.
- **Special rules**: gravity (discs fall). This is the only unusual aspect.
- **Estimated effort**: 1-2 days.

### Interesting for NNUE Training: Maybe

Connect Four is simple enough that a handcrafted eval can achieve perfect play,
so NNUE is not strictly necessary. However, it could serve as a quick validation
target: if NNUE cannot solve Connect Four, something is wrong with the training
pipeline. It is a good "sanity check" game.

### Overall Recommendation: **ADD** (Priority 3)

Connect Four is the ideal "warmup" implementation for UBGI:

- Trivial move generation exercises the placement-move path.
- Extremely fast search means rapid iteration during development.
- Being solved provides a ground-truth benchmark.
- The gravity mechanic is a novel constraint not present in other UBGI games.
- However, it is strategically shallow compared to other candidates, so it
  should not be the only addition.

---

## 3. Checkers / Draughts

### Rules Summary

**American Checkers (English Draughts)**: played on the dark squares of an 8x8
board. Each player starts with 12 pieces. Pieces move diagonally forward one
square. Captures are mandatory jumps over adjacent opponent pieces (multi-jump
chains are possible). A piece reaching the far row is promoted to a King, which
can move and capture diagonally in both directions. The player who captures all
opponent pieces or leaves them with no legal moves wins.

### Board Size and State Space

| Variant                | Board     | State-Space (log10) | Game-Tree (log10) |
|------------------------|-----------|---------------------|--------------------|
| 6x6 Checkers           | 18 playable squares | ~10         | ~15               |
| 8x8 American Checkers  | 32 playable squares | ~21 (~5 x 10^20) | ~31        |
| 10x10 International    | 50 playable squares | ~30         | ~54               |

The 8x8 variant has ~5 x 10^20 positions, smaller than Othello 8x8. The
branching factor is roughly 3-4 (forced captures reduce it further).

### Search Depth Feasibility

- Branching factor ~3-4 (lower than chess due to forced captures).
- Depth 12-18 is feasible with alpha-beta.
- Depth 20+ with endgame databases.
- Chinook (the program that solved checkers) used alpha-beta with endgame
  databases containing all positions with 10 or fewer pieces.

Alpha-beta works **perfectly** for checkers. Chinook was the first program to
win a human world championship (1994) and later solved the game (2007).

### Evaluation Function Difficulty: 3/10

Straightforward features:

- **Material**: piece count (men and kings, with kings worth ~1.5x a man).
- **Advancement**: how far pieces have progressed toward promotion.
- **Center control**: center squares are more flexible for movement.
- **King positioning**: kings in the center are stronger than on edges.
- **Back rank**: keeping pieces on the back rank to prevent opponent promotions.
- **Trapped kings**: detecting kings that cannot escape.
- **Tempo**: who has the initiative.

Chinook's handcrafted eval used ~20 features and was world-championship caliber.

### Solved Status

- **8x8 American Checkers**: weakly solved (2007, Chinook). Perfect play leads
  to a **draw**.
- **6x6**: not formally published as solved but computationally trivial.
- **10x10 International**: unsolved, significantly more complex.

### Implementation Effort: Medium

- **Board representation**: 32 usable squares (dark squares only). Bitboard with
  three 32-bit masks (player 1 pieces, player 2 pieces, kings).
- **Move generation**: diagonal moves, forced capture chains with multi-jump.
  Forced captures add complexity to move generation.
- **State encoding**: 32 cells, each empty/black-man/black-king/white-man/white-king.
- **Move encoding**: 4-char board moves (from-to). Multi-jump captures may need
  special handling (sequence of squares).
- **Special rules**: mandatory captures, multi-jump chains, promotion.
- **Estimated effort**: 3-4 days (multi-jump capture logic is the main
  complexity).

### Interesting for NNUE Training: Yes

Checkers has a rich positional evaluation that benefits from learned features.
The small number of piece types (man, king) and the 32-square board make it
efficient for NNUE. Endgame databases provide exact training targets for
positions with few pieces, creating a clean signal for training.

### Overall Recommendation: **ADD** (Priority 2)

Checkers is an excellent addition:

- It exercises the board-move path with a completely different game mechanic
  (diagonal movement, forced captures, promotion).
- The forced-capture rule creates a natural quiescence mechanism.
- Being solved provides a verification benchmark.
- 6x6 Checkers could serve as a "MiniCheckers" variant, analogous to MiniChess.
- The main drawback is the multi-jump capture encoding, which may need a small
  UBGI protocol extension or a convention for encoding multi-step moves.

---

## 4. Nine Men's Morris

### Rules Summary

Played on a board with 24 intersections connected by lines, forming three
concentric squares. The game has three phases:

1. **Placement phase**: players alternate placing 9 pieces (18 total) on empty
   intersections.
2. **Movement phase**: players slide pieces along lines to adjacent empty
   intersections.
3. **Flying phase**: when a player is reduced to 3 pieces, that player can
   move a piece to any empty intersection.

Forming a "mill" (three pieces in a row along a line) allows the player to
remove one opponent piece (not part of a mill, if possible). A player loses when
reduced to 2 pieces or when unable to move.

### Board Size and State Space

| Metric              | Value          |
|---------------------|----------------|
| Board               | 24 intersections |
| State-space         | ~10^10 (largest subspace: 603 million states) |
| Game-tree           | Moderate       |
| Branching factor    | ~5-8 (varies by phase) |

The state space is quite small -- approximately 10 billion states, well within
reach of modern hardware.

### Search Depth Feasibility

- Branching factor is modest (5-8 in movement phase, higher during placement).
- Depth 12-18 is achievable with alpha-beta.
- The game has been solved with retrograde analysis (endgame databases of ~10^10
  states) combined with an 18-ply alpha-beta search.

### Evaluation Function Difficulty: 5/10

More complex than checkers due to the phase-based nature:

- **Phase 1 (placement)**: potential mills, board control, blocking.
- **Phase 2 (movement)**: closed mills (formed this turn), number of mills and
  potential mills, mobility, blocked opponent pieces.
- **Phase 3 (flying)**: piece count becomes dominant.

Each phase requires somewhat different evaluation logic. The multi-phase nature
is the main complexity. Key features:

- Number of mills and potential mills.
- Number of blocked opponent pieces.
- Double mills (pieces that can shuttle between two mills).
- Piece count difference.
- Number of "2-piece configurations" (one piece away from forming a mill).

### Solved Status

**Solved** (1993, by Ralph Gasser). Perfect play leads to a **draw**.

### Implementation Effort: Medium-High

- **Board representation**: 24 intersections, each empty or occupied by player 0
  or player 1. Not a grid -- requires an adjacency graph.
- **Move generation**: three distinct phases with different move types.
  Placement (any empty intersection), sliding (adjacent empty), flying (any
  empty). Mill detection on every move. Removal of opponent piece after forming
  a mill.
- **State encoding**: non-grid board requires a custom encoding. 24 cells plus
  phase information and pieces-remaining counts.
- **Move encoding**: placement (2-char) and sliding (4-char) moves both work.
  Mill-removal needs extra encoding (e.g., 6-char: from-to-remove).
- **Special rules**: three game phases, mill formation triggers piece removal,
  flying phase. The piece-removal-after-mill mechanic is a significant
  complication -- it means a single "turn" involves two actions (move + remove),
  which does not fit cleanly into the UBGI move format.
- **Estimated effort**: 4-5 days (phase management and mill-removal encoding
  are the main challenges).

### Interesting for NNUE Training: Maybe

The non-grid board topology is unusual and would require a custom NNUE input
encoding. The three-phase nature means the network would need to learn very
different evaluation criteria for different stages. This makes it less clean
as an NNUE testbed than grid-based games.

### Overall Recommendation: **MAYBE** (Low Priority)

Nine Men's Morris is a fascinating game but presents several implementation
challenges:

- The non-grid board does not map naturally to the existing renderer and
  coordinate system.
- The three-phase game mechanic is unique but adds significant complexity.
- The mill-removal mechanic (two actions per turn) does not fit the UBGI
  protocol cleanly without extensions.
- The adjacency-graph board topology is unlike anything else in the engine.

It would be a rewarding but expensive addition. Consider it only after the
higher-priority games are implemented.

---

## 5. Hex

### Rules Summary

Played on an NxN rhombus-shaped board of hexagonal cells. Two players alternate
placing stones. One player tries to connect the top and bottom edges; the other
tries to connect the left and right edges. There are no captures. The first
player to complete a connection wins. The game cannot end in a draw (every
filled board has exactly one winner, by a topological argument).

### Board Size and State Space

| Size | Cells | State-Space (log10) | Notes |
|------|-------|---------------------|-------|
| 5x5  | 25    | ~12                 | Solved (first player wins) |
| 7x7  | 49    | ~23                 | Solved |
| 9x9  | 81    | ~39                 | Solved |
| 11x11| 121   | ~58                 | Standard competitive size |

### Search Depth Feasibility

Hex has a moderate branching factor (equal to the number of empty cells, so it
starts high and decreases). On an 11x11 board, the initial branching factor is
121, which is extremely high for alpha-beta.

- On 5x5-7x7: alpha-beta can work with strong move ordering.
- On 9x9+: MCTS significantly outperforms alpha-beta.

The strongest Hex programs (MoHex, Benzene) use MCTS, not alpha-beta. The
earlier alpha-beta engines (Wolve, Six) were competitive but have been
surpassed by MCTS approaches.

### Evaluation Function Difficulty: 8/10

This is the critical weakness of Hex for UBGI:

- Hex evaluation is **notoriously difficult** to handcraft.
- There is no simple material or mobility metric.
- The key concept is "virtual connections" -- sets of cells that guarantee a
  connection regardless of opponent play. Detecting these requires complex
  graph-theoretic analysis.
- Resistance-based evaluation (treating the board as an electrical circuit)
  is the most successful handcrafted approach, but it is complex to implement.
- Connection strength is inherently a global, non-local property.

### Solved Status

- **Up to 9x9**: solved (first player wins with swap rule).
- **10x10+**: unsolved.
- First player always wins (Nash's strategy-stealing argument), so a swap rule
  is needed for fair play.

### Implementation Effort: Medium-High

- **Board representation**: hexagonal grid with different adjacency from
  square grids. Each cell has 6 neighbors.
- **Move generation**: trivial (place on any empty cell).
- **Rendering**: hex grid requires custom rendering, not the standard square
  grid used by the existing GUI.
- **Connection detection**: BFS/DFS for win detection is easy, but evaluation
  requires virtual connection analysis.

### Interesting for NNUE Training: Yes

Hex is one of the games where neural network evaluation dramatically
outperforms handcrafted heuristics. This makes it an excellent NNUE showcase,
but a poor candidate for the handcrafted-eval-first approach that UBGI uses.

### Overall Recommendation: **SKIP**

Hex fails the handcrafted-eval requirement. While it is a beautiful game and
a great NNUE candidate, the UBGI philosophy is to start with a reasonable
handcrafted eval and optionally add NNUE later. With Hex, the handcrafted
eval would be so weak that the engine would not be interesting to play against
without NNUE. Additionally, the hex grid topology requires custom GUI work.

---

## 6. Breakthrough

### Rules Summary

Played on a rectangular board (originally 7x7, but 6x6 and 8x8 are common).
Each player starts with two rows of pawns. Pawns move one square straight
forward or diagonally forward. A pawn captures by moving diagonally forward
(only captures diagonally, like chess pawns). A player wins by advancing any
pawn to the opponent's home row, or by capturing all opponent pawns.

### Board Size and State Space

| Size | Pieces | State-Space (log10) | Notes |
|------|--------|---------------------|-------|
| 5x5  | 10 each| ~10                 | Very small |
| 6x6  | 12 each| ~16 (1.5 x 10^16)  | Solved (first player wins) |
| 7x7  | 14 each| ~21                 | Original size |
| 8x8  | 16 each| ~25                 | Most common variant |

### Search Depth Feasibility

- Branching factor: ~8-15 (depends on position and board size).
- On 6x6: depth 10-14 is fast, deep endgame searches are feasible.
- On 8x8: depth 8-12 is comfortable with alpha-beta + TT.
- The game is relatively short (typically 20-40 plies), so deep search often
  reaches terminal states.

Alpha-beta works well for Breakthrough. The game has been used extensively as
a testbed for game AI research, with both alpha-beta and MCTS approaches
showing good results.

### Evaluation Function Difficulty: 3/10

Straightforward features:

- **Piece count**: more pieces is generally better.
- **Advancement**: how far each pawn has progressed. Pawns closer to the goal
  row are more valuable.
- **Most advanced pawn**: the single most advanced pawn is the most critical.
- **Support structures**: pawns protecting each other diagonally.
- **Breakthrough threats**: detecting pawns that cannot be stopped from reaching
  the goal row.
- **Piece connectivity**: groups of connected pawns are stronger.

The evaluation is simpler than chess because there is only one piece type.
Positional patterns (who has the most advanced unstoppable pawn) dominate.

### Solved Status

- **5x5**: solved (first player wins).
- **6x6**: solved (first player wins).
- **7x7**: first player believed to win; not formally solved.
- **8x8**: unsolved.

### Implementation Effort: Low

- **Board representation**: standard grid, one piece type per player. A simple
  2D array or two bitboards.
- **Move generation**: very simple -- each pawn has at most 3 moves (forward,
  diagonal-left, diagonal-right). Captures only diagonal.
- **State encoding**: trivial -- each cell is empty, player 0, or player 1.
  Same format as Gomoku.
- **Move encoding**: 4-char board moves (from-to), identical to MiniChess.
- **Win detection**: check if any pawn reached the last row.
- **Estimated effort**: 1-2 days. This is arguably the simplest board-move
  game to implement.

### Interesting for NNUE Training: Yes

Breakthrough has only one piece type, making the NNUE input encoding simple.
The game has clear tactical and positional elements that benefit from learned
evaluation. The small state space on 6x6 means the game can be fully explored
during self-play training, providing clean training signals.

### Overall Recommendation: **ADD** (Priority 2, tied with Checkers)

Breakthrough is an outstanding candidate:

- It is the simplest board-move game to implement -- simpler even than
  MiniChess due to a single piece type and no special moves.
- It exercises the board-move path with a different strategic flavor
  (racing game rather than material-capture game).
- The eval function is easy to handcraft but interesting (advancement vs safety).
- Multiple board sizes allow scaling from trivially small to challenging.
- It is widely used in AI research, so there is good literature for comparison.
- The 6x6 variant is solved, providing a verification benchmark.

---

## 7. Additional Candidates

### 7a. Mancala / Kalah

**Rules**: Two-row board with 6 pits per side and a store for each player.
Players pick up all seeds from one of their pits and sow them counter-clockwise.
Landing in an empty pit on your side captures opposite seeds. Extra turn if
the last seed lands in your store.

| Metric              | Value          |
|---------------------|----------------|
| Board               | 14 pits (6+1 per side) |
| State-space (log10) | ~13 for standard Kalah(6,4) |
| Branching factor    | ~3-5           |
| Eval difficulty     | 3/10           |

**Evaluation**: seed count difference, seeds on your side, store count, extra
turn potential.

**Solved status**: Kalah(6,4) is solved (first player wins by 10 with perfect
play). Various Kalah configurations have been solved.

**UBGI fit**: The sowing mechanic is unusual -- moves are "pick a pit" (6
choices), but the effect involves distributing seeds across multiple pits. This
is a placement-style move (single pit selection) but with complex board
mutations. The non-grid board (two rows of pits + stores) requires custom
rendering but could work with the existing grid by mapping pits to cells.

**Recommendation**: **MAYBE**. Interesting but the sowing mechanic is quite
different from any existing UBGI game, and the board topology is unusual.

### 7b. Tablut / Hnefatafl (Viking Chess)

**Rules**: Asymmetric game on a 9x9 board. The defender has a king and 8
defenders; the attacker has 16 pieces. The king must reach a corner to win
(defender victory); the attackers must surround and capture the king (attacker
victory). Pieces move like rooks (any number of squares in a straight line).
Captures by custodial method (sandwiching a piece between two of yours).

| Metric              | Value          |
|---------------------|----------------|
| Board               | 9x9 = 81 cells |
| State-space (log10) | ~20-25 (estimated) |
| Branching factor    | ~20-40 (rook-like moves create high branching) |
| Eval difficulty     | 5/10           |

**Evaluation**: piece count, king distance to corners, blocking positions,
custodial capture threats.

**UBGI fit**: Board-move game on a standard grid. Rook-like movement is
familiar from chess. The asymmetric objectives are the main novelty.

**Recommendation**: **MAYBE**. Interesting asymmetric game, but the high
branching factor (rook-like moves) and asymmetric goals add complexity. The
game is not well-studied computationally compared to other candidates. Would
be a unique addition but with more implementation risk.

### 7c. Dots and Boxes

**Rules**: Players alternate drawing lines between adjacent dots on a grid.
Completing the fourth side of a 1x1 box scores a point and grants an extra
turn. The player with the most boxes when all lines are drawn wins.

| Metric              | Value          |
|---------------------|----------------|
| Board               | NxN dots, 2N(N-1) possible lines |
| 3x3 dots            | 12 lines, ~10^7 states |
| 5x5 dots            | 40 lines, ~10^12 states |
| Branching factor    | Starts high (~40 for 5x5), decreases |
| Eval difficulty     | 6/10           |

**Evaluation**: box count difference, chain analysis (long chains determine
endgame strategy), double-cross strategy. The chain-based strategy is deep and
not trivial to encode.

**UBGI fit**: The "extra turn on box completion" mechanic breaks the strict
alternating-turns assumption of UBGI. Additionally, moves are line placements
(not piece placements or moves), requiring a different coordinate system.

**Recommendation**: **SKIP**. The non-alternating-turn mechanic (extra turn on
box capture) and the line-based move system do not fit the UBGI protocol without
significant modifications.

### 7d. Konane (Hawaiian Checkers)

**Rules**: Played on an NxN board (commonly 6x6 or 8x8) fully filled with
alternating black and white stones. Players remove stones by jumping over
adjacent opponent stones (like checkers captures, but orthogonal not diagonal).
Multi-jumps are allowed. The first player unable to make a capture loses.

| Metric              | Value          |
|---------------------|----------------|
| Board               | 6x6 = 36 cells (common small variant) |
| State-space (log10) | ~10-15 for 6x6 |
| Branching factor    | ~5-10          |
| Eval difficulty     | 3/10           |

**Evaluation**: mobility (number of legal moves), piece count, board control.
Mobility is the dominant factor since you lose when you cannot move.

**UBGI fit**: Board-move game, orthogonal jumps. Multi-jump captures have the
same encoding challenge as checkers. The fully-filled starting position and
capture-only movement are distinctive.

**Recommendation**: **MAYBE**. Interesting capture-only game with a unique
flavor, but it overlaps significantly with checkers. If checkers is added,
Konane becomes less necessary.

### 7e. Surakarta

**Rules**: Played on a 6x6 board with curved capture loops at the corners.
Each player has 12 pieces. Pieces move one square orthogonally or diagonally
(like a king in chess). Captures are made by moving a piece along a curved loop
that passes through corner arcs -- the piece travels along the arc and captures
the first opponent piece it encounters.

| Metric              | Value          |
|---------------------|----------------|
| Board               | 6x6 = 36 cells |
| State-space (log10) | ~15 (estimated) |
| Branching factor    | ~10-20         |
| Eval difficulty     | 5/10           |

**UBGI fit**: The curved capture loops are the main challenge. The board is a
standard grid, but the capture mechanic requires encoding the loop paths, which
is unlike any other game. Move encoding for loop captures may need special
handling.

**Recommendation**: **SKIP**. The curved-loop capture mechanic is unique but
hard to encode and render in the existing framework. The game is relatively
obscure and not well-studied computationally.

---

## Summary Comparison Table

| Game              | State-Space | Branching | Eval Diff | Solved?    | Impl. Effort | NNUE? | Rec.    |
|-------------------|-------------|-----------|-----------|------------|--------------|-------|---------|
| Othello 8x8       | 10^28       | 8-10      | 4/10      | Weak (Draw)| Medium       | Yes   | **ADD** |
| Othello 6x6       | 10^15       | 6-8       | 4/10      | Strong (W) | Medium       | Yes   | **ADD** |
| Connect Four       | 10^14       | 4-7       | 2/10      | Strong (P1)| Low          | Maybe | **ADD** |
| Checkers 8x8       | 10^21       | 3-4       | 3/10      | Weak (Draw)| Medium       | Yes   | **ADD** |
| Breakthrough 6x6   | 10^16       | 8-12      | 3/10      | Strong (P1)| Low          | Yes   | **ADD** |
| Breakthrough 8x8   | 10^25       | 10-15     | 3/10      | No         | Low          | Yes   | **ADD** |
| Nine Men's Morris   | 10^10       | 5-8       | 5/10      | Strong (Draw)| Med-High  | Maybe | Maybe  |
| Mancala/Kalah       | 10^13       | 3-5       | 3/10      | Yes (P1)   | Medium       | Maybe | Maybe  |
| Tablut              | 10^22       | 20-40     | 5/10      | No         | Medium       | Maybe | Maybe  |
| Hex 11x11           | 10^58       | 50-121    | 8/10      | No         | Med-High     | Yes   | Skip   |
| Dots and Boxes      | 10^12       | 10-40     | 6/10      | Small only | Medium       | Maybe | Skip   |
| Surakarta           | 10^15       | 10-20     | 5/10      | No         | High         | No    | Skip   |

---

## Final Ranking

Games ranked by suitability for the UBGI project, considering complementarity
with the existing chess/shogi/gomoku lineup, how well they exercise different
engine aspects, and development value.

### Tier 1: Strongly Recommended

1. **Othello (8x8, with 6x6 variant)**
   - Best overall candidate. Exercises flip-based mechanics, stability/mobility
     evaluation, and endgame solving. Alpha-beta is the gold standard.
     Complements chess (no piece types) and gomoku (rich positional eval).
     Excellent NNUE training candidate with abundant training data (WTHOR
     database). The 6x6 variant provides a solved smaller testbed.

2. **Breakthrough (6x6 or 8x8)**
   - Simplest implementation of any board-move game. Single piece type, simple
     movement rules, clear evaluation features. Exercises the racing/advancement
     dimension of game strategy not present in other UBGI games. Multiple board
     sizes. Widely used in AI research. Outstanding effort-to-value ratio.

3. **Checkers (8x8, with potential 6x6 variant)**
   - Classic game that exercises forced captures, multi-jump chains, and
     promotion. The solved status provides a benchmark. The forced-capture
     rule creates natural quiescence opportunities. The main cost is the
     multi-jump encoding complexity.

### Tier 2: Worth Considering

4. **Connect Four**
   - Excellent warmup implementation. Trivially easy to implement, fast to
     search, solved for verification. The gravity mechanic is unique. However,
     it is strategically shallow and the smallest game in the set. Best value
     as a testing and validation tool rather than a showcase game.

5. **Mancala / Kalah**
   - Unique sowing mechanic exercises a completely different game paradigm.
     Small branching factor, solved for verification. The non-grid board and
     unusual move semantics require more adaptation than grid games.

### Tier 3: Interesting but Lower Priority

6. **Nine Men's Morris**
   - Fascinating multi-phase game but the non-grid board, three game phases,
     and mill-removal mechanic (two actions per turn) create significant
     implementation and protocol challenges.

7. **Tablut / Hnefatafl**
   - Unique asymmetric game, but high branching factor and less computational
     research make it a riskier choice.

### Not Recommended

8. **Hex** -- Eval function is too hard to handcraft; needs MCTS.
9. **Dots and Boxes** -- Non-alternating turns break UBGI protocol.
10. **Surakarta** -- Curved-loop capture mechanic is too exotic for the
    framework.

---

## Recommended Implementation Order

For maximum value with incremental effort:

1. **Breakthrough 6x6** -- simplest possible new game, 1-2 days, validates the
   "adding a new game" workflow.
2. **Connect Four** -- second simplest, introduces gravity mechanic, 1-2 days.
3. **Othello 8x8** -- the flagship new game, richest eval features, 2-3 days.
4. **Checkers 8x8** -- most complex of the recommendations, exercises forced
   captures and multi-jump, 3-4 days.

This order progresses from simplest to most complex, with each game exercising
new aspects of the engine. Total estimated effort: 7-11 days for all four games.

---

## References and Further Reading

- [Othello is Solved (Takizawa, 2023)](https://arxiv.org/html/2310.19387v3)
- [Othello AI with Alpha-Beta Search](https://medium.com/@jackychoi26/how-to-write-an-othello-ai-with-alpha-beta-search-58131ffe67eb)
- [Alpha-Beta vs Scout Algorithms for Othello](https://ceur-ws.org/Vol-2486/icaiw_wdea_3.pdf)
- [Neural Reversi -- NNUE-style Othello Engine](https://github.com/natsutteatsuiyone/neural-reversi)
- [Learning to Play Othello with Deep Neural Networks](https://arxiv.org/abs/1711.06583)
- [Connect Four -- Wikipedia](https://en.wikipedia.org/wiki/Connect_Four)
- [Evaluation of Minimax in Connect-4](https://www.scirp.org/journal/paperinformation?paperid=125554)
- [Checkers Is Solved (Schaeffer et al., 2007)](https://www.science.org/cms/asset/7f2147df-b2f1-4748-9e98-1ac3afccfb76/pap.pdf)
- [Alpha-Beta Pruning and Checkers](http://www.cs.columbia.edu/~devans/TIC/AB.html)
- [Solving Nine Men's Morris (Gasser)](https://www.cs.brandeis.edu/~storer/JimPuzzles/GAMES/NineMensMorris/INFO/GasserArticle.pdf)
- [Nine Men's Morris Evaluation Functions](https://kartikkukreja.wordpress.com/2014/03/17/heuristicevaluation-function-for-nine-mens-morris/)
- [Monte Carlo Tree Search in Hex](https://webdocs.cs.ualberta.ca/~hayward/papers/mcts-hex.pdf)
- [Breakthrough -- Wikipedia](https://en.wikipedia.org/wiki/Breakthrough_(board_game))
- [Solving Breakthrough for the 6x6 Board](https://skemman.is/bitstream/1946/50478/1/Solving-Breakthrough-for-the-6x6-board.pdf)
- [Simple AI for the Game of Breakthrough](https://www.codeproject.com/Articles/37024/Simple-AI-for-the-Game-of-Breakthrough)
- [Game Complexity -- Wikipedia](https://en.wikipedia.org/wiki/Game_complexity)
- [Computer Othello -- Wikipedia](https://en.wikipedia.org/wiki/Computer_Othello)
