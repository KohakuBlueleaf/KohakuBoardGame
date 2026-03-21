# Kohaku Chess -- Design Document

---

## Table of Contents

1. [Overview](#1-overview)
2. [Initial Position](#2-initial-position)
3. [Complete Rules](#3-complete-rules)
4. [Design Decisions](#4-design-decisions)
5. [Fairness Analysis](#5-fairness-analysis)
6. [Piece Dynamics on 6x7](#6-piece-dynamics-on-6x7)
7. [Game Complexity](#7-game-complexity)
8. [AI/NNUE Feasibility](#8-ainnue-feasibility)
9. [Comparison to Existing Chess Variants](#9-comparison-to-existing-chess-variants)
10. [Fun Factor](#10-fun-factor)

---

## 1. Overview

**Kohaku Chess** is a custom chess variant played on a 6x7 (42-square) board,
designed for computer play and NNUE evaluation training within the MiniChess
engine framework. It is one half of the **Kohaku game family**, paired with
**Kohaku Shogi** -- a custom shogi variant that shares the same board size,
the same corner-king philosophy, and the same asymmetric pawn structure.

### The Name

**Kohaku** (琥珀) is the Japanese word for **amber** -- fossilized tree resin
that preserves ancient organisms in a translucent, protective shell. The name
captures the central design philosophy of both Kohaku variants: the king is
encased in a thick protective formation of pawns and pieces, like something
precious preserved inside amber.

The signature of this amber philosophy is the **inner bishop** (a2 for White,
f6 for Black). This bishop is embedded *inside* the pawn shell -- trapped
behind its own pawns at game start, unable to move without first dismantling
part of the defensive wall. It is the "amber piece": preserved within the
structure, providing passive diagonal defense for the king, and creating a
strategic tension between liberating it for attacking power versus keeping it
sealed as a defender. When you extract the amber, you expose what it was
protecting.

### Key Properties

- **Board**: 6 files x 7 ranks (42 squares)
- **Pieces**: All 6 standard chess piece types (P, R, N, B, Q, K)
- **Pieces per side**: 12 (24 total)
- **Bishops per side**: 2 (one light-squared, one dark-squared)
- **Special rules**: None -- no castling, no en passant, no pawn double-move
- **Win condition**: King capture (consistent with the MiniChess engine convention)
- **Family**: Kohaku (paired with Kohaku Shogi on the same 6x7 board)

---

## 2. Initial Position

```
  a b c d e f
7 r b n . q k   <- Black
6 p p p p . b
5 . . . . p p
4 . . . . . .
3 P P . . . .
2 B . P P P P
1 K Q . N B R   <- White
```

### White Pieces

| Piece       | Square(s)             |
|-------------|-----------------------|
| King        | a1                    |
| Queen       | b1                    |
| Knight      | d1                    |
| Bishop (outer) | e1                 |
| Rook        | f1                    |
| Bishop (inner) | a2                 |
| Pawns (x6)  | c2, d2, e2, f2, a3, b3 |

### Black Pieces

| Piece       | Square(s)             |
|-------------|-----------------------|
| Rook        | a7                    |
| Bishop (inner) | b7                 |
| Knight      | c7                    |
| Queen       | e7                    |
| King        | f7                    |
| Bishop (outer) | f6                 |
| Pawns (x6)  | a6, b6, c6, d6, e5, f5 |

### Symmetry

The position has **180-degree rotational symmetry** about the center of the
board (the midpoint between d4 and c4). Every structural feature White has
in one corner, Black has in the opposite corner. White's king huddles in the
a1 corner with pawns on a3/b3/c2/d2/e2/f2; Black's king huddles in the f7
corner with pawns on e5/f5/a6/b6/c6/d6.

### Wing Structure

Each side's position divides naturally into two wings:

- **King's wing** (defensive): The corner where the king is encased. For White,
  this is the a-file/b-file side (ranks 1-3). For Black, this is the e-file/f-file
  side (ranks 5-7). The pawn wall is thick here, with two advanced pawns providing
  an extra layer of protection.

- **Attacking wing** (offensive): The opposite side of the board, where the Rook,
  outer Bishop, and Knight have room to develop. For White, this is the e-file/f-file
  side. For Black, this is the a-file/b-file side.

---

## 3. Complete Rules

### 3.1 Piece Movement

All pieces move according to standard chess rules:

| Piece  | Movement |
|--------|----------|
| King   | One square in any direction (up to 8 directions). |
| Queen  | Any number of squares orthogonally or diagonally (sliding). |
| Rook   | Any number of squares orthogonally (sliding). |
| Bishop | Any number of squares diagonally (sliding). |
| Knight | L-shape: 2 squares in one direction + 1 square perpendicular. Jumps over pieces. |
| Pawn   | Moves one square forward (toward rank 7 for White, toward rank 1 for Black). Captures one square diagonally forward. |

Sliding pieces (Queen, Rook, Bishop) are blocked by the first piece in their
path, following standard chess obstruction rules.

### 3.2 Capturing

A piece captures by moving to a square occupied by an opponent's piece. The
captured piece is removed from the game permanently. There are no drops -- this
is chess, not shogi.

### 3.3 Pawn Rules

- Pawns move **one square forward only**. There is no double-move from the
  starting rank.
- Pawns capture **one square diagonally forward** (standard chess).
- **No en passant**. This rule is omitted entirely.

### 3.4 Promotion

When a pawn reaches the **last rank** (rank 7 for White, rank 1 for Black),
it **must promote**. The player chooses one of:

- Queen
- Rook
- Bishop
- Knight

Promotion is unrestricted: any piece type is always available regardless of
what pieces remain on the board.

### 3.5 No Castling

There is no castling. The king has no castling rights. The king is already
positioned in the corner behind a pawn shell -- it is effectively "pre-castled."

### 3.6 Win Condition

Win by **capturing the opponent's king**. This is consistent with the MiniChess
engine's existing win-condition model: there is no formal check or checkmate
detection. A player who leaves their king in a position where it can be captured
simply loses on the next move. The engine detects the resulting "king captured"
state as an immediate terminal loss.

### 3.7 Draw Conditions

- **Move limit**: The game is drawn after **200 ply** (MAX_STEP = 200). The
  larger board and deeper pawn structure justify a higher limit than the 100-ply
  used for MiniChess (6x5).
- No stalemate rule is needed under the king-capture model. A player with no
  legal moves that avoid king capture simply loses.

---

## 4. Design Decisions

### 4.1 Why 6x7?

The 6x7 board is the common canvas shared by both Kohaku variants. The
dimensions were chosen for multiple interlocking reasons:

- **Shared DNA with Kohaku Shogi**: Both Kohaku Chess and Kohaku Shogi use a
  6x7 board. This is deliberate -- the two variants are designed as a matched
  pair, exploring how the same board geometry produces different strategic
  landscapes under chess rules versus shogi rules.

- **7 ranks create a 3-row buffer zone**: With piece ranks occupying rows 1-3
  and 5-7, the middle of the board (row 4) plus the two transitional rows create
  a meaningful no-man's-land. Pawns must cross 3 empty ranks before making contact,
  which gives both sides time to develop and reduces the first-mover advantage
  inherent in chess.

- **6 files are enough for full chess**: Six files provide room for all standard
  piece types, including two bishops (one per color complex). The width is narrow
  enough to keep games tactically sharp -- pieces influence the entire board --
  but wide enough to avoid the cramped feeling of 5-file variants.

- **42 squares fits in a uint64_t bitboard**: The 42-square board can be
  represented as a 64-bit integer with bits to spare, enabling efficient
  bitboard-based move generation (the engine uses `USE_BITBOARD`).

### 4.2 Why Corner King?

The corner-king placement is the defining feature of the Kohaku philosophy.
Rather than placing the king in the center of the back rank (as in standard
chess) or offset from center (as in Corridor Chess), the king is pushed all the
way into the corner:

- **Amber encasement**: The king at a1 (White) is surrounded by the Queen at
  b1, the inner Bishop at a2, and pawns at a3/b3/c2. This is the "amber shell"
  -- the king is sealed inside protective material from the very first move.

- **No need for castling**: Because the king starts in the corner behind a pawn
  wall, the entire concept of castling is unnecessary. The king is already in
  its ideal defensive formation. This removes a complex rule without sacrificing
  strategic depth.

- **Directional play**: The corner king creates a natural asymmetry between
  the king's wing (defensive) and the opposite wing (offensive). This mirrors
  the directional play found in shogi, where attacking one side while defending
  the other is the fundamental strategic pattern.

### 4.3 Why Queen as Bodyguard at b1?

The Queen at b1 serves as the king's immediate protector, analogous to the Gold
General adjacent to the King in Kohaku Shogi:

- **Immediate defense**: The Queen covers a1 (the king) and controls the
  b2 square and the b-file, making it very difficult for an opponent to
  infiltrate the king's corner in the opening.

- **Flexible deployment**: Unlike a lesser piece, the Queen can slide out along
  rank 1, the b-file, or the a2-f7 diagonal when the time is right. The
  strategic question of *when* to deploy the Queen away from king defense is a
  recurring decision throughout the game.

- **Kohaku Shogi parallel**: In Kohaku Shogi, the Gold General sits at b1
  adjacent to the King at a1, providing the same immediate defensive role.
  The Queen is the chess analog of this -- the most versatile defensive piece
  placed as the king's bodyguard.

### 4.4 Why 2 Bishops?

Kohaku Chess gives each side two bishops -- one on light squares, one on dark
squares -- which is unusual for minichess variants:

- **Proper bishop pair**: In standard chess, the bishop pair is a significant
  positional advantage because two bishops cover all 64 squares. On a 6x7 board,
  this principle still holds: a single bishop can only access 21 of 42 squares,
  while the pair covers all 42. The bishop pair dynamic adds a layer of strategic
  depth that single-bishop variants lack.

- **Full diagonal coverage**: With 6 files and 7 ranks, there are meaningful long
  diagonals (the a1-f6 diagonal has 6 squares). Two bishops ensure that both
  color complexes are contested.

- **Compensation for no knights/bishops removed**: Many minichess variants cut
  pieces to fit smaller boards. Kohaku Chess instead uses the full 7-rank depth
  to accommodate a larger army (12 pieces per side vs. 10-11 in typical 6x6
  variants), including the extra bishop.

### 4.5 Why Inner Bishop at a2?

The inner bishop at a2 (White) / f6 (Black) is the **signature piece** of
Kohaku Chess -- the "amber" itself:

- **Embedded defense**: The bishop at a2 is completely enclosed by the pawn at
  a3 above it, the pawn at c2 beside it (blocking the diagonal), and the king
  at a1 below it. It cannot move at game start. But it passively defends the
  king by covering the b3 and c4 diagonals once the pawn structure opens.

- **Strategic tension**: The inner bishop creates one of the most interesting
  decisions in the game: *when do you liberate it?* Moving the a3 or b3 pawn
  opens the bishop but weakens the king's pawn shield. Keeping it locked in
  preserves the shell but wastes a piece. This tension between defense and
  mobilization is the heart of Kohaku Chess strategy.

- **Amber metaphor made concrete**: The inner bishop is literally a piece
  preserved inside a protective structure. Extracting it (by advancing pawns)
  is like cracking open amber -- you free what is inside but destroy the
  container in the process.

### 4.6 Why 6 Pawns with 2 Advanced?

Each side has 6 pawns arranged in an L-shaped formation: 4 pawns on the second
rank and 2 advanced pawns on the third rank (on the king's wing side):

- **Kohaku Shogi mirror**: Kohaku Shogi uses the exact same pawn structure --
  4 pawns on rank 2 and 2 advanced pawns on rank 3 (for Sente). This shared
  DNA means both variants feel structurally related despite having completely
  different piece mechanics.

- **Thick defensive wall on the king's wing**: The two advanced pawns (a3, b3
  for White) provide an extra layer of protection in front of the king's corner.
  An attacker must break through two ranks of pawns to reach the king -- a
  significant defensive advantage.

- **Open attacking wing**: The 4 pawns on rank 2 (c2-f2 for White) leave the
  e-file and f-file area more open for piece development. The Rook at f1, Bishop
  at e1, and Knight at d1 can develop without needing to push pawns first.

- **Board density**: 6 pawns on 6 files means every file starts with a pawn on
  it (considering both the rank 2 and rank 3 pawns). This creates meaningful
  pawn structure -- chains, isolated pawns, passed pawns -- without the excessive
  crowding of a full pawn rank on a 6-file board.

### 4.7 Why No Castling or En Passant?

- **No castling**: The king is already in the corner behind a pawn wall. Castling
  would be mechanically meaningless (the king is already "castled") and would add
  implementation complexity for zero strategic benefit. The corner king IS the
  castled position.

- **No en passant**: En passant exists in standard chess to prevent pawns from
  using the double-move to evade capture. Since there is no double pawn move in
  Kohaku Chess, en passant has no purpose. Even if it were added, on a 6-file
  board with single-step pawns, the situations where it would matter are vanishingly
  rare. Removing it simplifies the rule set without losing strategic depth.

- **No pawn double-move**: On a 7-rank board with a 3-row buffer, the single-step
  pawn is already adequate for pawn contact to occur at a reasonable pace. A
  double-move would bring pawns into contact too quickly, compressing the opening
  phase and undermining the buffer zone's purpose.

### 4.8 Why 180-Degree Rotational Symmetry?

The starting position is symmetric under 180-degree rotation about the board
center. This is a strict fairness requirement:

- **Perfect positional fairness**: Every structural advantage White has on one
  side of the board, Black has on the other. White's thick king-side on the left
  matches Black's thick king-side on the right. White's open attacking wing on
  the right matches Black's open attacking wing on the left.

- **No mirror symmetry**: The position is NOT mirror-symmetric (left-right or
  top-bottom). This is intentional -- mirror symmetry on a rectangular board can
  create trivial "copycat" strategies where the second player mirrors the first.
  Rotational symmetry avoids this because the two armies face in opposite
  directions.

- **Standard for minichess variants**: Rotational symmetry is used by Corridor
  Chess, Bastion Chess, Compact Shogi, and Kohaku Shogi in this engine framework.
  It is the established fairness convention.

### 4.9 How Chess and Shogi Variants Share DNA

Kohaku Chess and Kohaku Shogi are designed as a **matched pair** -- the same
architectural skeleton realized under two different rule systems:

| Feature             | Kohaku Chess       | Kohaku Shogi        |
|---------------------|--------------------|---------------------|
| Board size          | 6x7 (42 squares)   | 6x7 (42 squares)    |
| King position       | Corner (a1/f7)     | Corner (a1/f7)      |
| Bodyguard piece     | Queen at b1        | Gold at b1           |
| Inner piece at a2   | Bishop (amber)     | Silver (fortress)    |
| Pawn structure      | 4 on rank 2, 2 on rank 3 | 4 on rank 2, 2 on rank 3 |
| Attacking wing      | Right side (e-f files) | Right side (e-f files) |
| Pieces per side     | 12                 | 12                   |
| Symmetry            | 180-degree rotation | 180-degree rotation  |

The shared skeleton means that intuitions about pawn structure, king safety, and
wing play transfer between the two variants, even though the piece mechanics
(chess sliding pieces vs. shogi drops and promotions) create fundamentally
different tactical textures.

---

## 5. Fairness Analysis

### 5.1 Rotational Symmetry Guarantees Positional Fairness

The 180-degree rotational symmetry of the starting position means that any
positional advantage inherent in the *arrangement* of pieces is perfectly
balanced. If White's king at a1 is safer because of the a3/b3 pawn shield,
Black's king at f7 is equally safe because of the e5/f5 pawn shield. If
White's rook at f1 has good development prospects on the f-file, Black's rook
at a7 has equally good prospects on the a-file.

The only asymmetry is **tempo**: White moves first.

### 5.2 First-Mover Advantage in Chess vs. Shogi

In chess variants (unlike shogi), the first-mover advantage is a real concern.
White gets to develop, push pawns, and seize space one move before Black. The
magnitude of this advantage depends on the board geometry:

- **Standard chess (8x8)**: White's first-mover advantage is moderate. Empirical
  win rates at top level: ~55% White, ~30% Black, ~15% draws.
- **Small boards**: First-mover advantage tends to be *larger* on small boards
  because the king is closer to the action and tempo matters more. Gardner
  MiniChess (5x5) is believed to have a significant White advantage.
- **Kohaku Chess**: The 6x7 board is designed to *mitigate* the first-mover
  advantage through the buffer zone (see below).

### 5.3 The Role of the 3-Row Buffer

The initial pawn lines are on ranks 2-3 (White) and ranks 5-6 (Black), with
rank 4 and portions of ranks 3 and 5 empty. This creates a **3-row buffer
zone** between the two armies:

- **Slows down contact**: With single-step pawns, the first pawn contact cannot
  occur before move 3 (and typically later, because pushing the king-side pawns
  weakens the shell). This gives both sides time to develop before the fighting
  starts.

- **Reduces tempo advantage**: In variants with immediate pawn contact (like
  Gardner MiniChess with a 1-row buffer), the first player's tempo advantage
  translates directly into an initiative advantage. With a 3-row buffer, the
  second player has time to match the first player's development before the
  critical moment arrives.

- **Encourages piece development**: The buffer zone means that simply pushing
  pawns forward is not immediately threatening. Players must develop pieces
  behind the pawn wall first, which equalizes the tempo disparity because both
  sides have room to develop.

### 5.4 Comparison to First-Mover Advantage in Other Variants

| Variant            | Board  | Buffer Rows | Estimated White Win% |
|--------------------|--------|-------------|---------------------|
| Gardner MiniChess  | 5x5    | 1           | ~60%+ (strong White edge) |
| Los Alamos Chess   | 6x6    | 2           | ~55-58% |
| MiniChess (6x5)    | 6x5    | 2           | ~55-58% |
| Kohaku Chess       | 6x7    | 3           | ~52-56% (estimated) |
| Standard Chess     | 8x8    | 4           | ~55% (with draws) |

The 3-row buffer in Kohaku Chess is expected to produce a first-mover advantage
comparable to or slightly less than standard chess, which is a desirable range
for competitive play.

### 5.5 Structural Fairness of the Pawn Formation

Both sides have identical pawn structures (6 pawns in an L-shape) rotated
180 degrees. The advanced pawns protect the king's corner equally for both
sides. The open wing is equally open for both sides. There is no structural
bias in pawn placement.

---

## 6. Piece Dynamics on 6x7

### 6.1 The Bishop Pair

Each side has two bishops -- one on light squares, one on dark squares. On a
6x7 board:

- **Light squares**: 21 squares. **Dark squares**: 21 squares. The board is
  perfectly evenly divided between the two color complexes.

- **Longest diagonal**: 6 squares (e.g., a1-f6 or a2-f7). This is long enough
  for bishops to be powerful sliding pieces, but short enough that they cannot
  dominate the entire board from a single position.

- **Bishop pair value**: The bishop pair is very strong on a 6x7 board. Together,
  they cover all 42 squares and can create devastating crossfire attacks,
  especially in open positions. Losing one bishop leaves 21 squares permanently
  uncontrolled by your remaining bishop, which is proportionally a bigger
  liability on a small board than on an 8x8 board (where the remaining bishop
  still covers 32 squares).

- **Practical implication**: Trading one bishop for a knight is a more significant
  decision in Kohaku Chess than in standard chess, because the remaining bishop
  is more limited proportionally.

### 6.2 Knight

The knight is **proportionally more powerful** on a 6x7 board than on an 8x8 board:

- **Reach**: From the center of a 6x7 board (c4 or d4), a knight can reach up
  to 8 squares -- the same as on an 8x8 board. But the board only has 42
  squares, so those 8 squares represent ~19% of the board (vs. ~12.5% on 8x8).

- **No dead zones**: On an 8x8 board, a knight in the corner attacks only 2
  squares. On a 6x7 board, corners still attack only 2 squares, but the
  knight can cross the entire board in 3-4 moves (vs. 4-6 on 8x8). This means
  a misplaced knight can recover more quickly.

- **Knight vs. Bishop**: The knight's ability to reach both color complexes makes
  it a natural counter to a lone bishop (which is restricted to one color). In
  endgames where one side has lost a bishop, a knight can exploit the color
  weakness.

### 6.3 Queen

The Queen is **extremely powerful** on a 6x7 board:

- **Dominance**: From a central square, the Queen can influence up to 23 of 42
  squares (~55% of the board). For comparison, on 8x8, a centralized Queen
  influences ~42% of the board. The Queen's relative power is significantly
  higher on the smaller board.

- **Tactical omnipresence**: The Queen can shift from defense to attack in 1-2
  moves on a 6x7 board. This makes Queen trades extremely impactful -- the side
  that loses its Queen first suffers a proportionally greater loss of attacking
  and defensive potential.

- **Bodyguard tension**: The Queen starts as the king's bodyguard at b1 (White).
  Its enormous attacking potential creates constant tension: deploying the Queen
  to attack means stripping the king of its most powerful defender. This is a
  feature, not a bug -- it is the central strategic tension of the game.

### 6.4 Rook

Rooks are strong but initially constrained:

- **Open files are critical**: On a 6-file board, there are only 6 files total.
  Creating an open file (by exchanging pawns) gives the rook tremendous influence
  because there are fewer alternative files for the opponent to defend on. A rook
  on an open file on a 6-file board is proportionally more powerful than on an
  8-file board.

- **Starting position**: The Rook at f1 (White) / a7 (Black) is on the attacking
  wing, already positioned on a semi-open file (only one pawn in its file). This
  makes rook activation relatively straightforward compared to variants where the
  rook is boxed in.

- **Back rank threats**: With only 6 files, back-rank mates and rook infiltration
  along the 7th rank (for White) or 1st rank (for Black) are significant threats.
  The narrow board makes it harder to create escape squares for the king.

### 6.5 The Inner Bishop vs. Outer Bishop Dynamic

This is the unique piece dynamic that defines Kohaku Chess:

- **Inner bishop (a2 / f6)**: Starts completely locked in. Cannot move until at
  least one of its neighboring pawns (a3, b3, or c2 for White) advances or is
  captured. Its initial role is purely passive defense -- it watches over the
  king's diagonal neighborhood. Liberating it requires weakening the pawn shell.

- **Outer bishop (e1 / b7)**: Starts on the back rank with more room to develop.
  Can be developed via pawn advances on the attacking wing (e.g., pushing d2-d3
  or c2-c3 opens diagonals). The outer bishop is the "attacking" bishop.

- **Strategic asymmetry**: The two bishops create a natural division of labor.
  The inner bishop is the defensive specialist (when it finally enters the game,
  it often stays near the king). The outer bishop is the attacking specialist
  (it develops toward the opponent's king). This is reminiscent of the "good
  bishop vs. bad bishop" dynamic in standard chess, but more explicit because
  of the starting positions.

- **Endgame transformation**: If the pawn structure opens up significantly in
  the middlegame, the inner bishop can transform from a defensive piece into a
  powerful long-range attacker. This transformation often signals the transition
  from middlegame to endgame.

---

## 7. Game Complexity

### 7.1 Starting Position Statistics

| Metric                         | Value       |
|--------------------------------|-------------|
| Board squares                  | 42          |
| Pieces per side                | 12          |
| Total pieces                   | 24          |
| Board density (pieces/squares) | 57.1% (24/42) |
| Empty squares                  | 18          |
| Pawns per side                 | 6           |
| Officers per side              | 6 (K, Q, R, N, B, B) |

### 7.2 Complexity Estimates

| Metric                    | Estimate     |
|---------------------------|--------------|
| Average branching factor  | ~25-35       |
| Average game length       | 40-60 moves (80-120 ply) |
| State space               | ~10^20 - 10^25 |
| Game tree complexity      | ~10^40 - 10^50 |

**Reasoning**:

- **Branching factor (25-35)**: With 12 pieces per side on 42 squares, the
  average number of legal moves is comparable to Los Alamos Chess (~22-28) but
  slightly higher due to the extra bishop and the 7th rank providing more room
  for sliding pieces. The 57% board density is moderate -- high enough that pieces
  interact frequently, but low enough that sliding pieces have open lanes.

- **Game length (40-60 moves)**: The 3-row buffer zone and the thick pawn
  structure slow the game down compared to 6x5 MiniChess (~30-40 moves). The
  need to break through the opponent's pawn shell before reaching the king adds
  10-20 moves to the typical game. Games rarely reach the 200-ply move limit.

- **State space (10^20-25)**: With 42 squares and up to 24 pieces of various
  types, the number of legal board positions is vastly larger than MiniChess
  (6x5, ~10^13-15) but smaller than standard chess (~10^44). The extra rank and
  the extra bishop per side significantly expand the state space compared to
  6x6 variants.

- **Game tree complexity (10^40-50)**: The product of branching factor and game
  length yields a game tree of approximately 30^50 to 30^100 (in ply), which
  gives roughly 10^40-50. This places Kohaku Chess firmly in the "not solvable
  by brute force" category while remaining tractable for deep NNUE-assisted
  search.

### 7.3 Comparison to Other Chess Variants

| Variant          | Board  | Pieces | Branching | Game Length | State Space | Game Tree |
|------------------|--------|--------|-----------|-------------|-------------|-----------|
| Gardner MiniChess | 5x5   | 10     | ~15-20    | 20-30       | ~10^12      | ~10^25-30 |
| MiniChess (6x5)  | 6x5   | 20     | ~20-25    | 30-40       | ~10^13-15   | ~10^30-35 |
| Los Alamos Chess  | 6x6   | 24     | ~22-28    | 35-50       | ~10^17-20   | ~10^36-40 |
| **Kohaku Chess**  | **6x7** | **24** | **~25-35** | **40-60** | **~10^20-25** | **~10^40-50** |
| Standard Chess    | 8x8   | 32     | ~30-35    | 40-80       | ~10^44      | ~10^120   |
| Capablanca Chess  | 10x8  | 40     | ~40-50    | 50-90       | ~10^50      | ~10^140   |

Kohaku Chess sits in a sweet spot: complex enough to be strategically rich and
resistant to brute-force solving, but small enough that NNUE training is
tractable with modest hardware (see Section 8).

---

## 8. AI/NNUE Feasibility

### 8.1 HalfKP Feature Size Calculation

The NNUE evaluation uses HalfKP (Half King-Piece) features, where each feature
encodes the relationship between the king's square and every other piece on the
board. The feature size is:

```
num_squares         = 7 * 6 = 42
num_piece_features  = 2 (colors) * NUM_PT_NO_KING (5) * num_squares (42)
                    = 2 * 5 * 42 = 420
halfkp_size         = num_squares (42) * num_piece_features (420)
                    = 42 * 420 = 17,640
hand_feature_size   = 0  (no drops in chess)
total_feature_size  = 17,640
```

### 8.2 Feature Size Comparison

| Game          | Board  | HalfKP Size | Notes |
|---------------|--------|-------------|-------|
| MiniChess     | 6x5    | 9,000       | 30 * (2 * 5 * 30) |
| **Kohaku Chess** | **6x7** | **17,640** | 42 * (2 * 5 * 42) |
| MiniShogi     | 5x5    | 12,500      | 25 * (2 * 10 * 25), plus hand features |
| Standard Chess | 8x8   | 40,960*     | Typically uses HalfKA (different scheme) |

Kohaku Chess's 17,640 HalfKP features are roughly 2x the size of MiniChess's
feature space. This is well within the capacity of the existing NNUE
architecture (128-unit accumulator with SCReLU activation, AVX2/NEON SIMD).

### 8.3 Why NNUE Is Valuable for This Variant

NNUE evaluation is particularly well-suited for Kohaku Chess because:

- **Positional complexity**: The corner-king position, the inner/outer bishop
  dynamic, the thick pawn structures, and the wing-based play all create
  positional patterns that are difficult to capture with simple piece-square
  tables. NNUE can learn these patterns from self-play data.

- **King safety is non-trivial**: The king's safety depends not just on its
  position but on the integrity of the surrounding pawn shell. NNUE's HalfKP
  features explicitly encode king-piece relationships, making it naturally suited
  to evaluate king safety in the amber formation.

- **Bishop pair awareness**: The strategic value of maintaining or trading the
  bishop pair is something NNUE can learn from data. A KP-eval (material +
  piece-square tables) cannot distinguish between having two bishops and having
  bishop + knight, but NNUE can learn the bishop pair bonus implicitly.

- **Pawn structure evaluation**: The L-shaped pawn formation creates
  characteristic pawn structures (chains, isolated pawns, passed pawns) that
  NNUE can learn to evaluate. The pawn structure around the king is especially
  critical and maps directly to HalfKP features.

### 8.4 Comparison to MiniChess NNUE Training Experience

The existing MiniChess (6x5) NNUE training pipeline provides a strong baseline:

- **MiniChess NNUE**: Trained on ~10M self-play positions, 128-unit accumulator,
  achieves significant Elo gains over KP-eval (~200+ Elo).

- **Kohaku Chess NNUE (expected)**: The ~2x larger feature space means slightly
  longer training times per epoch. However, the game's greater complexity should
  also produce more diverse training data (more distinct positions per game), which
  may compensate. The same 128-unit accumulator architecture should be sufficient
  -- the feature space is 17,640 (vs. 9,000 for MiniChess), but the accumulator
  compresses this to 128 features regardless.

### 8.5 Expected Training Requirements

| Parameter            | MiniChess (reference) | Kohaku Chess (expected) |
|----------------------|-----------------------|-------------------------|
| Feature size         | 9,000                 | 17,640                  |
| Accumulator size     | 128                   | 128                     |
| Training positions   | ~10M                  | ~15-30M                 |
| Epochs to converge   | ~30-50                | ~40-60                  |
| Data generation      | ~2 hours (depth 8)    | ~3-5 hours (depth 8)    |
| Training time        | ~1 hour (GPU)         | ~2-3 hours (GPU)        |

The larger board and deeper games mean each self-play game takes longer, and
more training data is needed to cover the larger state space. But the overall
training pipeline remains feasible on a single GPU workstation.

### 8.6 game_config.py Entry

The following configuration would be added to `game_config.py` for NNUE
training:

```python
"kohaku_chess": {
    "board_h": 7,
    "board_w": 6,
    "num_piece_types": 6,
    "num_pt_no_king": 5,
    "king_id": 6,
    "piece_names": [".", "P", "R", "N", "B", "Q", "K"],
    "has_hand": False,
    "num_hand_types": 0,
},
```

---

## 9. Comparison to Existing Chess Variants

| Feature             | Kohaku Chess | MiniChess (6x5) | Los Alamos (6x6) | Gardner (5x5) | Standard (8x8) | Capablanca (10x8) |
|---------------------|-------------|------------------|-------------------|----------------|-----------------|---------------------|
| **Board**           | 6x7         | 6x5              | 6x6               | 5x5            | 8x8             | 10x8                |
| **Squares**         | 42          | 30               | 36                | 25             | 64              | 80                  |
| **Pieces/side**     | 12          | 10               | 12                | 5              | 16              | 20                  |
| **Piece types**     | 6           | 6                | 5 (no bishop)     | 6              | 6               | 8 (+archbishop, chancellor) |
| **Bishops/side**    | 2           | 1                | 0                 | 1              | 2               | 2 (+archbishop)     |
| **Pawns/side**      | 6           | 5                | 6                 | 5              | 8               | 10                  |
| **Castling**        | No          | No               | No                | No             | Yes             | Yes                 |
| **En passant**      | No          | No               | No                | No             | Yes             | Yes                 |
| **Pawn double-move**| No          | No               | No                | No             | Yes             | Yes                 |
| **Win condition**   | King capture | King capture    | Checkmate         | King capture   | Checkmate       | Checkmate           |
| **Buffer rows**     | 3           | 2                | 2                 | 1              | 4               | 4                   |
| **King position**   | Corner      | Center           | Center            | Center         | Center          | Center              |
| **Density**         | 57%         | 67%              | 67%               | 40%            | 50%             | 50%                 |
| **Branching**       | ~25-35      | ~20-25           | ~22-28            | ~15-20         | ~30-35          | ~40-50              |
| **HalfKP size**     | 17,640      | 9,000            | N/A               | N/A            | ~40,960         | N/A                 |
| **State space**     | ~10^20-25   | ~10^13-15        | ~10^17-20         | ~10^12         | ~10^44          | ~10^50              |

### Key Differentiators

- **vs. MiniChess (6x5)**: Kohaku Chess has a larger board (+12 squares), more
  pieces (+2 per side), a deeper buffer zone, and the unique corner-king /
  amber-bishop dynamic. It is a more complex game with richer positional play.

- **vs. Los Alamos Chess (6x6)**: Kohaku Chess has bishops (Los Alamos does not),
  an extra rank, the corner-king philosophy, and a more open pawn structure. Los
  Alamos tends toward cramped, knight-dominated play; Kohaku Chess encourages
  diverse piece interactions.

- **vs. Gardner MiniChess (5x5)**: Gardner is extremely small with only a 1-row
  buffer, leading to very short, tactically dominated games. Kohaku Chess has
  nearly twice the squares and a much more strategic character.

- **vs. Standard Chess (8x8)**: Kohaku Chess distills many of standard chess's
  strategic elements (bishop pair, pawn structure, king safety, wing play) into
  a smaller board. The corner king and eliminated special rules (castling, en
  passant) simplify the rule set while the 6x7 board keeps complexity high enough
  for deep play.

---

## 10. Fun Factor

### 10.1 What Makes Kohaku Chess Interesting to Play

The fundamental appeal of Kohaku Chess is **asymmetric wing play**: one side of
your position is locked down (the king's corner), and the other side is where
the action is. This creates a natural strategic narrative in every game:

- **Attack on the wing, defend in the corner**: You develop your attacking
  pieces (Rook, outer Bishop, Knight) on the open wing while keeping your king
  safe in the amber shell. Your opponent does the same, but from the opposite
  corner. The game becomes a race to crack the opponent's shell before they crack
  yours.

- **The breaking point**: Every game has a critical moment when one side decides
  to open up their king's wing -- either voluntarily (to activate the inner
  bishop) or involuntarily (because the opponent's attack forced pawn exchanges).
  Recognizing and timing this breaking point is the key skill.

### 10.2 The Inner Bishop Dynamic

The inner bishop is the most strategically interesting piece on the board:

- **When to liberate it**: Early liberation (pushing a3-a4 or b3-b4 for White)
  activates the bishop but exposes the king. Late liberation means playing the
  entire middlegame with one piece less. The timing of this decision defines the
  character of the game.

- **Keep it as a defender**: Sometimes the best use of the inner bishop is to
  never liberate it. If the opponent's attack is focused on the king's wing,
  the bishop behind the pawn wall provides crucial diagonal coverage. It is a
  "fortress bishop" -- immobile but structurally important.

- **Exchange sacrifice**: In some positions, allowing the inner bishop to be
  captured (by opening the pawn wall under duress) is acceptable if it slows
  the opponent's attack. The inner bishop becomes a "sacrifice piece" -- amber
  that shatters to absorb an impact.

### 10.3 Expected Opening Strategies

Several natural opening approaches emerge from the starting position:

- **Attacking wing development**: Develop the Knight (d1-e3 or d1-c3), push
  c2-c3 or d2-d3 to open diagonals for the outer Bishop, connect the Rook on
  f1 to the center. This is the "natural" approach -- develop your attacking
  pieces first, worry about the inner bishop later.

- **Early inner bishop activation**: Push a3-a4 or b3-b4 early to free the
  inner bishop. Aggressive but weakening -- the exposed king may face a
  counterattack. This strategy works best if you can redeploy the bishop to
  an active diagonal quickly.

- **Pawn storm**: Push the attacking-wing pawns (c2-c4, d2-d4, etc.) to gain
  space on the open wing and cramp the opponent's development. Risky because
  overextended pawns can become targets, but can be powerful with piece support.

- **Positional squeeze**: Develop pieces to optimal squares, maintain the pawn
  shell, and wait for the opponent to weaken themselves. Use the Queen as a
  flexible piece that can shift between defense and attack depending on the
  opponent's plan. This is the "solid" approach.

### 10.4 Why This Is Better Than "Just Removing Pieces from Standard Chess"

Many minichess variants are created by simply removing rows, columns, or pieces
from the standard chess setup. This approach has well-known problems:

- **Proportional imbalance**: Removing files but keeping the same piece types
  can make certain pieces disproportionately strong or weak. A bishop on a 5x5
  board covers 40% of squares from the center; on 8x8, only 25%.

- **Aesthetic incoherence**: Chopping a standard chess position often results in
  a position that feels "wrong" -- pieces are awkwardly placed, the pawn
  structure is artificial, and there is no overarching design philosophy.

- **Missing strategic depth**: Removed pieces mean missing piece interactions.
  Los Alamos Chess has no bishops, which eliminates an entire strategic dimension
  (bishop pair, color complexes, bishop vs. knight).

Kohaku Chess avoids all of these problems:

- **Purpose-built position**: Every piece is placed for a reason. The inner
  bishop is not a leftover from removing a row -- it is the centerpiece of
  the design philosophy. The advanced pawns are not an accident of board size
  -- they mirror the Kohaku Shogi structure.

- **Full piece set with extras**: Rather than removing pieces, Kohaku Chess
  *adds* a second bishop. This makes the piece interactions richer than standard
  minichess variants, not poorer.

- **Coherent design philosophy**: The amber metaphor gives the position a
  thematic coherence that "reduced chess" variants lack. The corner king, the
  bodyguard queen, the amber bishop, the thick shell, the open attacking wing
  -- all of these elements work together to create a position that feels
  *designed* rather than *derived*.

- **Cross-variant DNA**: The shared architecture with Kohaku Shogi means the
  variant exists within a larger design family, not as an isolated experiment.
  Lessons from one variant inform the other, and the comparison between chess
  rules and shogi rules on the same board is itself a source of insight.

---

*Kohaku Chess is implemented in the MiniChess engine framework at
`src/games/kohaku_chess/`. The NNUE feature extraction follows the same HalfKP
scheme as MiniChess, with the game-specific configuration defined in
`config.hpp` and the board initialization in `state.hpp`.*
