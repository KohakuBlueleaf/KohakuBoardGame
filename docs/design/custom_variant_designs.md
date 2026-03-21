# Custom Chess/Shogi Variant Designs for Computer Play

Designed for the MiniChess engine framework. Each variant targets 6x6 or 6x7
boards and is engineered for interesting NNUE training, non-trivial search
complexity, and reasonable first-player fairness. All variants are implementable
within the existing `BaseState` interface (~500-1000 lines of C++ each).

---

## Table of Contents

1. [Chess-type Variants](#chess-type-variants)
   - [1. Bastion Chess (6x6)](#1-bastion-chess-6x6)
   - [2. Corridor Chess (6x7)](#2-corridor-chess-6x7)
   - [3. Citadel Chess (6x6)](#3-citadel-chess-6x6)
2. [Shogi-type Variants](#shogi-type-variants)
   - [4. Hayate Shogi (6x6)](#4-hayate-shogi-6x6)
   - [5. Renmei Shogi (6x7)](#5-renmei-shogi-6x7)
   - [6. Tsurugi Shogi (6x6)](#6-tsurugi-shogi-6x6)
3. [Comparison Table](#comparison-table)
4. [Recommendations](#recommendations)
5. [What Makes a Variant Good for NNUE Training](#what-makes-a-variant-good-for-nnue-training)

---

## Chess-type Variants

---

### 1. Bastion Chess (6x6)

#### Name

**Bastion Chess** -- named for the defensive pawn wall that both sides must
breach. The 4-pawn front creates a "bastion" that requires strategic piece
coordination to crack.

#### Board Size

6 ranks x 6 files (6x6).

#### Piece Set

Each side has **10 pieces**:

| Piece  | Count | ID |
|--------|-------|----|
| King   | 1     | K  |
| Queen  | 1     | Q  |
| Rook   | 1     | R  |
| Bishop | 1     | B  |
| Knight | 1     | N  |
| Pawn   | 4     | P  |

Pawns occupy the 4 center files (b-e), leaving the a-file and f-file open.
This gives the rook, bishop, and knight immediate outpost potential on the
flanks.

#### ASCII Art Initial Position

```
  a  b  c  d  e  f
6 r  n  b  q  k  .   <- Black
5 .  p  p  p  p  .
4 .  .  .  .  .  .
3 .  .  .  .  .  .
2 .  P  P  P  P  .
1 .  K  Q  B  N  R   <- White
```

White: King(b1), Queen(c1), Bishop(d1), Knight(e1), Rook(f1), Pawns b2-e2.
Black: Rook(a6), Knight(b6), Bishop(c6), Queen(d6), King(e6), Pawns b5-e5.

Note the **asymmetric piece placement**: White's back rank is shifted right
(b1-f1), Black's back rank is shifted left (a6-e6). Both arrangements are
internally mirrored, but the left-right offset creates subtle positional
asymmetry while maintaining strategic balance through piece-type symmetry.

#### Rules Summary

- Standard chess piece movement (King, Queen, Rook, Bishop, Knight, Pawn).
- **No castling**.
- **No en passant**.
- **No pawn double-move** (pawns advance one square only).
- Pawns capture diagonally forward as normal.
- Win by capturing the opponent's king (consistent with the MiniChess engine's
  existing win condition -- no checkmate detection required, just king capture).
- Draw on move 100 (MAX_STEP = 100).

#### Promotion Rules

Pawns promote on the last rank (rank 6 for White, rank 1 for Black).
A pawn may promote to **Queen, Rook, Bishop, or Knight** (player's choice).
There is no restriction based on captured pieces -- any promotion target is
always available.

#### Fairness Analysis

- **Piece-type symmetry**: Both sides have identical piece sets (1 of each
  piece type + 4 pawns). The material is perfectly balanced.
- **Positional balance via offset**: White's back rank occupies files b-f,
  Black's back rank occupies files a-e. This means neither side has a natural
  kingside or queenside advantage -- the asymmetry forces different plans
  rather than giving one side a structural edge.
- **Open flanks**: The empty a-file and f-file give both sides immediate
  avenues for rook activity and flank attacks. This mitigates the first-move
  advantage because the second player also has active piece development options.
- **4 pawns (not 5 or 6)**: With 4 pawns instead of a full rank, the center
  is contestable but not locked. This avoids the problem seen in Los Alamos
  chess where 6 pawns can create early blockades that favor the first player.
- **Expected first-player advantage**: Moderate. The open flanks allow Black
  to generate counterplay immediately. Estimated White win rate: ~52-54%.

#### Complexity Estimate

| Metric | Estimate |
|---|---|
| Pieces on board (start) | 20 (10 per side) |
| Avg. branching factor | ~28 |
| Avg. game length | ~50 ply |
| State space (positions) | ~10^16 |
| Game tree complexity | ~10^36 |

Reasoning: 20 pieces on 36 squares with moderate mobility. The open flanks
give pieces more room than Los Alamos chess (which has 24 pieces on 36
squares), but the 4 pawns create enough structure to prevent trivially short
games. The branching factor is slightly higher than Los Alamos (~22) due to
bishops being present.

#### Why This Is Good for Computer Chess

- **All piece types present**: Unlike Los Alamos chess (no bishops), Bastion
  Chess includes all 6 standard chess piece types. This makes NNUE training
  more relevant because the network must learn interactions between all piece
  types (e.g., bishop-knight imbalances, queen-vs-two-pieces trades).
- **Open flanks create tactical diversity**: The empty a-file and f-file
  mean rook lifts, flank attacks, and piece infiltration happen frequently.
  These create the kind of positional and tactical diversity that NNUE thrives
  on.
- **Not easily solvable**: With ~10^16 positions and ~10^36 game tree
  complexity, this is well beyond brute-force solvability (Gardner MiniChess
  at 10^34 was barely weakly solved).
- **Promotion dynamics**: With 4 pawns per side, promotions are common enough
  to be strategically important but not so frequent as to dominate every game.

#### Comparison to Existing Variants

- **vs. Los Alamos Chess (6x6)**: Los Alamos has no bishops and 6 pawns per
  side, creating a cramped, knight-dominated game. Bastion Chess includes
  bishops and uses only 4 pawns, creating a more open, piece-oriented game
  with richer tactical possibilities. The offset back rank is unique.
- **vs. Gardner MiniChess (5x5)**: Gardner has 5 pawns on a 5x5 board
  (very cramped). Bastion has more room for piece play. Gardner is weakly
  solved; Bastion should be far from solvable.
- **vs. Diana Chess (6x6)**: Diana removes queens; Bastion keeps all pieces.
  Diana uses 6 pawns; Bastion uses 4.

---

### 2. Corridor Chess (6x7)

#### Name

**Corridor Chess** -- the 6x7 board (6 files, 7 ranks) creates a deeper
"corridor" that pieces must traverse. The extra rank compared to a 6x6 board
adds strategic depth and gives both sides more time to develop.

#### Board Size

7 ranks x 6 files (6x7). The taller board (7 ranks vs. 6 files) creates an
elongated battlefield.

#### Piece Set

Each side has **11 pieces**:

| Piece  | Count | ID |
|--------|-------|----|
| King   | 1     | K  |
| Queen  | 1     | Q  |
| Rook   | 1     | R  |
| Bishop | 1     | B  |
| Knight | 1     | N  |
| Pawn   | 5     | P  |

5 pawns fill files a-e, leaving file f open on both sides.

#### ASCII Art Initial Position

```
  a  b  c  d  e  f
7 r  n  b  q  k  .   <- Black
6 p  p  p  p  p  .
5 .  .  .  .  .  .
4 .  .  .  .  .  .
3 .  .  .  .  .  .
2 .  P  P  P  P  P
1 .  K  Q  B  N  R   <- White
```

White: King(b1), Queen(c1), Bishop(d1), Knight(e1), Rook(f1), Pawns b2-f2.
Black: Rook(a7), Knight(b7), Bishop(c7), Queen(d7), King(e7), Pawns a6-e6.

Note the **rotational symmetry**: White's pieces occupy files b-f and ranks
1-2; Black's pieces occupy files a-e and ranks 6-7. The position is
180-degree rotationally symmetric about the board center. This is the
strongest form of positional fairness for an even-file board.

#### Rules Summary

- Standard chess piece movement.
- **No castling, no en passant, no pawn double-move**.
- Win by king capture.
- Draw on move 120 (MAX_STEP = 120). The longer board justifies a higher
  move limit.

#### Promotion Rules

Pawns promote on the last rank (rank 7 for White, rank 1 for Black).
A pawn may promote to **Queen, Rook, Bishop, or Knight** (free choice, no
restrictions).

#### Fairness Analysis

- **Rotational symmetry**: The 180-degree rotational symmetry ensures that
  neither side has a structural positional advantage. Every square advantage
  White has on the right flank, Black has on the left flank.
- **3-rank buffer zone**: With 7 ranks and pieces occupying ranks 1-2 and
  6-7, there are 3 empty ranks between the armies (ranks 3-5). This larger
  neutral zone reduces the first-move advantage because it takes longer for
  White to establish a meaningful positional lead.
- **5 pawns with open file**: The f-file (for White) and a-file (for Black)
  are open, providing rook activity channels. These open files are on opposite
  sides of the board, creating asymmetric attack directions that enrich the
  game.
- **Expected first-player advantage**: Low-moderate. The 3-rank buffer and
  rotational symmetry should keep White's advantage minimal. Estimated White
  win rate: ~51-53%.

#### Complexity Estimate

| Metric | Estimate |
|---|---|
| Pieces on board (start) | 22 (11 per side) |
| Avg. branching factor | ~30 |
| Avg. game length | ~60 ply |
| State space (positions) | ~10^19 |
| Game tree complexity | ~10^44 |

Reasoning: 42 squares (vs. 36 for 6x6) significantly increases the state
space. The extra rank adds depth to pawn-push plans and piece maneuvering.
The 5 pawns per side provide enough structure for meaningful pawn play. The
larger board increases average game length, which multiplies game tree
complexity.

#### Why This Is Good for Computer Chess

- **Novel board dimensions**: 6x7 is rarely explored in chess variants. The
  rectangular board creates unique bishop diagonal structures (the bishop
  covers different patterns than on a square board) and changes the relative
  value of pieces. This is excellent for NNUE because the network cannot
  rely on patterns learned from square-board training.
- **Deeper strategy**: The 3-rank buffer zone means games take longer to
  develop, creating more complex middle-game positions where NNUE evaluation
  matters most.
- **Asymmetric open files**: White's open f-file and Black's open a-file
  create directional asymmetry that enriches the position space.
- **Pawn promotion journey**: Pawns must cross 5 ranks to promote (vs. 4 in
  6x6 variants). This makes pawn advancement a more strategic decision.

#### Comparison to Existing Variants

- **vs. Los Alamos Chess (6x6)**: Corridor Chess adds a 7th rank, includes
  bishops, and uses 5 pawns instead of 6. The longer board creates a very
  different strategic tempo.
- **vs. Petty Chess (5x6)**: Similar piece count, but Corridor's 6-file
  width gives pieces more lateral room. Petty uses a 5x6 board with castling
  allowed.
- **Unique aspect**: The 6x7 board with rotational symmetry is, to our
  knowledge, not found in any published chess variant.

---

### 3. Citadel Chess (6x6)

#### Name

**Citadel Chess** -- each king begins surrounded by its "citadel" of pieces
in the corner. Breaking into the enemy citadel is the strategic challenge.

#### Board Size

6 ranks x 6 files (6x6).

#### Piece Set

Each side has **9 pieces**:

| Piece  | Count | ID |
|--------|-------|----|
| King   | 1     | K  |
| Queen  | 1     | Q  |
| Rook   | 1     | R  |
| Bishop | 1     | B  |
| Knight | 1     | N  |
| Pawn   | 3     | P  |

The reduced pawn count (only 3) creates an extremely open, tactical game
from the very first move.

#### ASCII Art Initial Position

```
  a  b  c  d  e  f
6 k  .  .  .  .  .   <- Black
5 q  b  .  .  p  .
4 r  n  .  .  p  .
3 .  p  p  .  .  r
2 .  p  .  .  B  Q
1 .  .  .  .  .  K   <- White
```

White: King(f1), Queen(f2), Bishop(e2), Rook(f3), Knight -- wait, let me
redesign this more cleanly.

```
  a  b  c  d  e  f
6 r  .  .  .  .  k   <- Black
5 n  .  .  .  .  q
4 b  p  p  p  .  .
3 .  .  P  P  P  B
2 Q  .  .  .  .  N
1 K  .  .  .  .  R   <- White
```

White: King(a1), Queen(a2), Bishop(f3), Knight(f2), Rook(f1), Pawns c3,d3,e3.
Black: Rook(a6), Knight(a5), Bishop(a4), Queen(f5), King(f6), Pawns b4,c4,d4.

The arrangement is **anti-diagonal mirror symmetric**: White's king is in the
bottom-left corner (a1), Black's king is in the top-right corner (f6). Pieces
radiate outward from each king. The 3 pawns form a "shield wall" across the
center.

#### Rules Summary

- Standard chess piece movement.
- **No castling, no en passant, no pawn double-move**.
- Win by king capture.
- Draw on move 100 (MAX_STEP = 100).

#### Promotion Rules

Pawns promote on the last rank (rank 6 for White, rank 1 for Black).
Promotion is restricted to **captured pieces only**: a pawn may only promote
to a piece type that the opponent has previously captured from the promoting
player. If no pieces have been captured, the pawn cannot promote (it is stuck
on the last rank until a capture occurs, though it can still make captures
itself). If multiple piece types have been captured, the player chooses.

This creates a strategic tension: you want to trade pieces to enable
promotion, but trading also weakens your army. In practice, by the time a
pawn reaches the last rank, at least one piece has usually been captured.

#### Fairness Analysis

- **Anti-diagonal symmetry**: The position has 180-degree rotational symmetry
  (equivalent to anti-diagonal mirroring on a square board). This ensures
  perfect structural balance.
- **Corner kings**: Both kings start in opposite corners, at maximum distance
  from each other. This delays direct king attacks and gives both sides time
  to organize.
- **3 pawns**: The minimal pawn count means the board is very open. This
  reduces the positional advantage of moving first because there are fewer
  pawn-structure commitments to make.
- **Scattered pieces**: The queen and rook are separated from the knight and
  bishop, creating coordination challenges for both sides equally.
- **Expected first-player advantage**: Low. The extreme openness and corner
  kings mitigate tempo advantage. Estimated White win rate: ~51-52%.

#### Complexity Estimate

| Metric | Estimate |
|---|---|
| Pieces on board (start) | 18 (9 per side) |
| Avg. branching factor | ~32 |
| Avg. game length | ~45 ply |
| State space (positions) | ~10^15 |
| Game tree complexity | ~10^34 |

Reasoning: Only 18 pieces but the open board (3 pawns) means each piece has
high mobility, pushing the branching factor above average. The capture-only
promotion rule adds complexity to the evaluation function but doesn't
dramatically change move count. Games may be slightly shorter due to the
tactical openness.

#### Why This Is Good for Computer Chess

- **Capture-based promotion** creates a novel evaluation dimension. NNUE must
  learn that the value of advancing a pawn depends on what pieces have been
  captured -- a non-trivial conditional relationship.
- **Extreme openness**: With only 3 pawns, most squares are available for
  piece maneuvering from move 1. This creates a huge diversity of positions
  in the opening, forcing NNUE to generalize rather than memorize openings.
- **Corner kings** create unique king-safety patterns. The king is initially
  safe in the corner but can become trapped there. NNUE must learn when the
  corner is safe vs. when it's a liability.
- **Piece coordination**: The scattered initial placement means development
  and coordination are key themes -- exactly the kind of positional judgment
  that NNUE excels at learning.

#### Comparison to Existing Variants

- **vs. Los Alamos Chess (6x6)**: Citadel has far fewer pawns (3 vs. 6),
  includes bishops, and uses a unique scattered/corner starting position
  instead of the standard back-rank arrangement.
- **vs. Gardner MiniChess (5x5)**: Both are open, tactical games, but
  Citadel's larger board and corner-king placement create very different
  strategic patterns. Citadel's capture-based promotion is unique.
- **Unique aspects**: The corner-king arrangement and capture-based promotion
  rule are not found in any standard small chess variant.

---

## Shogi-type Variants

---

### 4. Hayate Shogi (6x6)

#### Name

**Hayate Shogi** (hayate = "swift wind") -- a fast-paced 6x6 shogi variant
that adds the Lance to the Judkins Shogi piece set, creating a 3-pawn front
with aggressive potential.

#### Board Size

6 ranks x 6 files (6x6).

#### Piece Set

Each side has **9 pieces on board**:

| Piece  | Count | Movement | Promoted Form |
|--------|-------|----------|---------------|
| King (K/k) | 1 | 1 step any direction | -- |
| Gold (G/g) | 1 | 1 step any except diag-back | -- |
| Silver (S/s) | 1 | 1 step forward/diag | +S (Gold movement) |
| Bishop (B/b) | 1 | Any diag | +B / Horse (Bishop + King) |
| Rook (R/r) | 1 | Any orthogonal | +R / Dragon (Rook + King) |
| Lance (L/l) | 1 | Any number forward | +L (Gold movement) |
| Pawn (P/p) | 3 | 1 step forward | +P / Tokin (Gold movement) |

Total: 9 pieces per side, 18 on board.

**Hand piece types** (capturable, indices 1-6): Pawn, Silver, Gold, Bishop,
Rook, Lance.

#### ASCII Art Initial Position

```
  a  b  c  d  e  f
6 L  K  G  S  B  R   <- Gote (White)
5 .  .  p  p  p  .
4 .  .  .  .  .  .
3 .  .  .  .  .  .
2 .  P  P  P  .  .
1 r  b  s  g  k  l   <- Sente (Black)
```

Sente (Black): Rook(a1), Bishop(b1), Silver(c1), Gold(d1), King(e1),
Lance(f1), Pawns b2, c2, d2.

Gote (White): Lance(a6), King(b6), Gold(c6), Silver(d6), Bishop(e6),
Rook(f6), Pawns c5, d5, e5.

The arrangement is **180-degree rotationally symmetric**. Each side's back
rank has the same piece ordering: R-B-S-G-K-L (reading from Sente's
perspective). The 3 pawns are centered (files b-d for Sente, c-e for Gote).

#### Rules Summary

- Standard shogi rules: capture-and-reuse (drops), promotion by entering the
  promotion zone.
- Win by capturing the opponent's king.
- **Drop restrictions**:
  - No two unpromoted friendly pawns in the same file (nifu).
  - No pawn drop checkmate (uchifuzume).
  - Pawns cannot be dropped on the last rank.
  - Lance cannot be dropped on the last rank (no legal move).
- All captured pieces revert to unpromoted form when entering the hand.
- Draw on move 200 (MAX_STEP = 200) or by repetition (sennichite).

#### Promotion Rules

**Promotion zone**: Last **2 ranks** (ranks 5-6 for Sente, ranks 1-2 for
Gote).

Promotable pieces and their promoted forms:
- Pawn -> Tokin (+P): moves like Gold.
- Silver -> +S: moves like Gold.
- Lance -> +L: moves like Gold.
- Bishop -> Horse (+B): Bishop + King moves (diagonal ranging + 1 step orthogonal).
- Rook -> Dragon (+R): Rook + King moves (orthogonal ranging + 1 step diagonal).

Promotion is **optional** when entering, moving within, or leaving the
promotion zone, EXCEPT when a piece would have no legal move (pawn/lance on
the last rank must promote).

Gold and King do not promote.

#### Fairness Analysis

- **Rotational symmetry**: Perfect 180-degree rotational symmetry ensures no
  structural bias.
- **Centered pawns**: The 3 pawns occupy the center files, creating a
  symmetric center conflict. The open wing files (a-file and f-file for
  Sente's perspective) are balanced by the rotational symmetry.
- **Lance on the flank**: The lance starts on the wing (f1 for Sente, a6 for
  Gote), providing a long-range forward threat down the open file. Both sides
  have exactly the same lance positioning relative to their own king.
- **Drop mechanics**: The second player's inherent disadvantage (tempo) is
  partially offset by the drop mechanic, which allows defensive resources
  to be deployed instantly.
- **Expected first-player advantage**: Moderate. In shogi variants, sente
  advantage is typically 52-55%. With drops and a balanced position, Hayate
  should be around ~53%.

#### Complexity Estimate

| Metric | Estimate |
|---|---|
| Pieces on board (start) | 18 (9 per side) |
| Avg. branching factor | ~40 |
| Avg. game length | ~50 ply |
| State space (positions) | ~10^19 |
| Game tree complexity | ~10^40 |

Reasoning: Drops dramatically increase branching factor (~40 with drops vs.
~25 without). The lance adds another piece type that can be dropped and
captured, increasing the hand-piece combinations. 3 pawns per side means
more drop targets (nifu is less restrictive with fewer pawns). State space
is large because of hand-piece combinations multiplied by board positions.

#### Why This Is Good for Computer Chess

- **Richer than Judkins Shogi**: Adding the lance and increasing to 3 pawns
  creates more piece interactions and drop possibilities. The lance is a
  unique piece that requires special NNUE handling (forward-only ranging).
- **Drop complexity**: With 6 capturable piece types (vs. 5 in MiniShogi),
  the hand state space is richer. NNUE must learn the value of each piece
  in hand vs. on board.
- **3 pawns enable nifu dynamics**: With 3 pawns, file-based pawn management
  matters. NNUE must learn which files are "nifu-blocked" for drops and how
  that affects positional evaluation.
- **Promotion zone interactions**: The 2-rank promotion zone on a 6-rank
  board means 1/3 of the board is a promotion zone. This creates constant
  promotion threats that NNUE must evaluate.

#### Comparison to Existing Variants

- **vs. Judkins Shogi (6x6)**: Judkins has a knight but no lance, and only
  1 pawn. Hayate replaces the knight with a lance and uses 3 pawns. This
  creates a very different game: Hayate has more pawn structure play and
  forward-ranging lance attacks, while Judkins has knight forks and jumps.
- **vs. MiniShogi (5x5)**: MiniShogi has 1 pawn per side on a 5x5 board.
  Hayate's 6x6 board with 3 pawns creates a more strategically rich game
  with pawn structure considerations.
- **vs. Goro Goro Plus (5x6)**: Both have 3 pawns and include the lance,
  but Goro Goro lacks rook and bishop while starting with lance/knight in
  hand. Hayate has all major pieces on the board from the start.

---

### 5. Renmei Shogi (6x7)

#### Name

**Renmei Shogi** (renmei = "alliance/federation") -- a 6x7 shogi variant
with an expanded piece set including both lance and knight. The name reflects
the "alliance" of all major shogi piece types working together on the board.

#### Board Size

7 ranks x 6 files (6x7).

#### Piece Set

Each side has **11 pieces on board**:

| Piece  | Count | Movement | Promoted Form |
|--------|-------|----------|---------------|
| King (K/k) | 1 | 1 step any direction | -- |
| Gold (G/g) | 2 | 1 step any except diag-back | -- |
| Silver (S/s) | 1 | 1 step forward/diag | +S (Gold movement) |
| Bishop (B/b) | 1 | Any diag | +B / Horse (Bishop + King) |
| Rook (R/r) | 1 | Any orthogonal | +R / Dragon (Rook + King) |
| Knight (N/n) | 1 | Jump: 2 forward + 1 sideways | +N (Gold movement) |
| Lance (L/l) | 1 | Any number forward | +L (Gold movement) |
| Pawn (P/p) | 3 | 1 step forward | +P / Tokin (Gold movement) |

Total: 11 pieces per side, 22 on board.

**Hand piece types** (capturable, indices 1-7): Pawn, Silver, Gold, Bishop,
Rook, Knight, Lance.

#### ASCII Art Initial Position

```
  a  b  c  d  e  f
7 L  N  S  G  G  K   <- Gote (White)
6 .  R  .  .  B  .
5 p  p  p  .  .  .
4 .  .  .  .  .  .
3 .  .  .  P  P  P
2 .  b  .  .  r  .
1 k  g  g  s  n  l   <- Sente (Black)
```

Sente (Black): King(a1), Gold(b1), Gold(c1), Silver(d1), Knight(e1),
Lance(f1), Bishop(b2), Rook(e2), Pawns d3, e3, f3.

Gote (White): Lance(a7), Knight(b7), Silver(c7), Gold(d7), Gold(e7),
King(f7), Rook(b6), Bishop(e6), Pawns a5, b5, c5.

The position is **180-degree rotationally symmetric**. The major pieces
(Rook, Bishop) are on rank 2/6, slightly advanced, creating immediate
tension. The 3 pawns are on one wing for each side (files d-f for Sente,
files a-c for Gote), creating an asymmetric pawn structure that the
rotational symmetry balances.

#### Rules Summary

- Standard shogi rules with drops and promotion.
- Win by capturing the opponent's king.
- **Drop restrictions**:
  - No two unpromoted friendly pawns in the same file (nifu).
  - No pawn drop checkmate (uchifuzume).
  - Pawns and lances cannot be dropped on the last rank.
  - Knights cannot be dropped on the last 2 ranks (no legal move from there).
- Draw on move 200 (MAX_STEP = 200).

#### Promotion Rules

**Promotion zone**: Last **2 ranks** (ranks 6-7 for Sente, ranks 1-2 for
Gote).

Same promotion rules as standard shogi. Mandatory promotion when a piece
would have no legal move in its unpromoted form (pawn/lance on last rank,
knight on last 2 ranks).

#### Fairness Analysis

- **Rotational symmetry**: Perfect 180-degree rotational symmetry.
- **Asymmetric pawn wings**: Each side's pawns are on one wing (opposite
  wings). This creates inherent tension -- each side attacks on the wing
  where the opponent's pawns are absent. The rotational symmetry ensures
  this is balanced.
- **Advanced major pieces**: The rook and bishop start on rank 2/6, already
  partially developed. This reduces the impact of the first-move advantage
  because both sides have active pieces from the start.
- **Two golds**: Having 2 gold generals per side provides strong defensive
  resources, slowing the game down and reducing first-mover blitz potential.
- **7-rank depth**: The extra rank (vs. 6x6 Judkins) gives more maneuvering
  room, slightly favoring the defender and reducing tempo advantage.
- **Expected first-player advantage**: Low-moderate. ~52-53%.

#### Complexity Estimate

| Metric | Estimate |
|---|---|
| Pieces on board (start) | 22 (11 per side) |
| Avg. branching factor | ~50 |
| Avg. game length | ~60 ply |
| State space (positions) | ~10^23 |
| Game tree complexity | ~10^52 |

Reasoning: 22 pieces on 42 squares with drops creates a very large state
space. 7 hand piece types (pawn, silver, gold, bishop, rook, knight, lance)
dramatically increase drop possibilities. The knight's jump movement adds
fork-based tactical complexity. Two golds per side extend game length. This
variant approaches Tori Shogi in complexity.

#### Why This Is Good for Computer Chess

- **Complete piece set**: Renmei includes ALL standard shogi piece types
  (Pawn, Lance, Knight, Silver, Gold, Bishop, Rook, King). This is the only
  6-file shogi variant in this document to include both lance AND knight
  alongside major pieces. NNUE must learn the full range of shogi piece
  interactions.
- **7 hand piece types**: The hand state space is enormous. NNUE must learn
  the relative value of each piece in hand, which varies dramatically with
  board position.
- **Wing-based pawn asymmetry**: The asymmetric pawn placement (made fair by
  rotation) creates directional attacking/defending themes. NNUE must learn
  that piece values depend on which wing is under attack.
- **Knight on a 6-file board**: The knight's 2+1 jump is much more
  constrained on a 6-file board than on a 9-file board. NNUE must learn
  the reduced but still important knight value in this context.
- **Highest complexity**: Among the 6 variants in this document, Renmei has
  the highest estimated game tree complexity (~10^52), making it the most
  challenging for brute-force search and the most dependent on NNUE quality.

#### Comparison to Existing Variants

- **vs. Judkins Shogi (6x6)**: Judkins has knight but no lance, 1 gold, 1
  pawn. Renmei has both knight and lance, 2 golds, 3 pawns, and an extra
  rank. Renmei is substantially more complex.
- **vs. Tori Shogi (7x7)**: Both are 7-rank variants with drops. But Tori
  uses entirely unique bird-themed pieces, while Renmei uses standard shogi
  pieces. Tori has 16 pieces per side (8 swallows); Renmei has 11.
  Comparable complexity.
- **vs. Goro Goro Plus (5x6)**: Goro Goro has no rook or bishop on board
  (knight/lance in hand only). Renmei has all pieces on board. Renmei is
  wider (6 vs. 5 files) and deeper (7 vs. 6 ranks).
- **Unique aspect**: The combination of all standard shogi pieces on a 6x7
  board with wing-based asymmetric pawn placement is novel.

---

### 6. Tsurugi Shogi (6x6)

#### Name

**Tsurugi Shogi** (tsurugi = "sword") -- a sharp, aggressive 6x6 shogi
variant with minimal pawns and a unique 1-rank promotion zone that forces
decisive breakthroughs.

#### Board Size

6 ranks x 6 files (6x6).

#### Piece Set

Each side has **8 pieces on board**:

| Piece  | Count | Movement | Promoted Form |
|--------|-------|----------|---------------|
| King (K/k) | 1 | 1 step any direction | -- |
| Gold (G/g) | 1 | 1 step any except diag-back | -- |
| Silver (S/s) | 2 | 1 step forward/diag | +S (Gold movement) |
| Bishop (B/b) | 1 | Any diag | +B / Horse (Bishop + King) |
| Rook (R/r) | 1 | Any orthogonal | +R / Dragon (Rook + King) |
| Pawn (P/p) | 2 | 1 step forward | +P / Tokin (Gold movement) |

Total: 8 pieces per side, 16 on board.

**Hand piece types** (capturable, indices 1-4): Pawn, Silver, Gold, Bishop,
Rook.

No lance or knight -- this is a "pure" variant focused on the core shogi
pieces with doubled silvers.

#### ASCII Art Initial Position

```
  a  b  c  d  e  f
6 R  B  G  K  S  S   <- Gote (White)
5 .  p  .  .  p  .
4 .  .  .  .  .  .
3 .  .  .  .  .  .
2 .  P  .  .  P  .
1 s  s  k  g  b  r   <- Sente (Black)
```

Sente (Black): Silver(a1), Silver(b1), King(c1), Gold(d1), Bishop(e1),
Rook(f1), Pawns b2, e2.

Gote (White): Rook(a6), Bishop(b6), Gold(c6), King(d6), Silver(e6),
Silver(f6), Pawns b5, e5.

The position is **180-degree rotationally symmetric**. Each side has 2
silvers on the wing near the king and 2 pawns on the b-file and e-file
(symmetrically placed). The major pieces (rook, bishop) are on the opposite
wing from the king.

#### Rules Summary

- Standard shogi rules with drops and promotion.
- Win by capturing the opponent's king.
- **Drop restrictions**:
  - No two unpromoted friendly pawns in the same file (nifu).
  - No pawn drop checkmate (uchifuzume).
  - Pawns cannot be dropped on the last rank.
- **Special rule -- Sword Strike**: When a piece promotes, it gains a single
  "threat bonus" -- the promoted piece's first move after promotion cannot
  be blocked by drops. This is a thematic rule but optional for
  implementation simplicity. If omitted, standard promotion rules apply.
- Draw on move 200 (MAX_STEP = 200).

#### Promotion Rules

**Promotion zone**: Last **1 rank only** (rank 6 for Sente, rank 1 for
Gote).

This is a critical design choice. The single-rank promotion zone (like
MiniShogi) makes promotion harder to achieve, increasing the strategic
value of promotion and creating sharper, more decisive games. Pieces must
penetrate deep into enemy territory to promote.

Promotable pieces and their promoted forms:
- Pawn -> Tokin (+P): moves like Gold.
- Silver -> +S: moves like Gold.
- Bishop -> Horse (+B): Bishop + King moves.
- Rook -> Dragon (+R): Rook + King moves.

Promotion is optional when entering or moving within the promotion zone,
except Pawn on the last rank (mandatory).

Gold and King do not promote.

#### Fairness Analysis

- **Rotational symmetry**: Perfect 180-degree rotational symmetry.
- **2 pawns only**: The minimal pawn count creates a very open game. With
  only 2 pawns per side, nifu restricts only 2 files for pawn drops, leaving
  4 files open for pawn drops. This makes drops extremely powerful and
  partially offsets tempo advantage.
- **Doubled silvers**: Having 2 silvers per side provides flexible defense
  and attack options. Silvers are versatile pieces that work well both
  offensively and defensively.
- **1-rank promotion zone**: The narrow promotion zone means that promotion
  is a significant achievement, not an automatic consequence of advancing
  pieces. This adds strategic depth and reduces the first-player advantage
  (the first player cannot easily promote pieces before the second player
  can respond).
- **Expected first-player advantage**: Moderate. ~53-54%. The open board
  and powerful drops help the second player, but the first mover still has
  initiative.

#### Complexity Estimate

| Metric | Estimate |
|---|---|
| Pieces on board (start) | 16 (8 per side) |
| Avg. branching factor | ~35 |
| Avg. game length | ~45 ply |
| State space (positions) | ~10^17 |
| Game tree complexity | ~10^35 |

Reasoning: Fewer pieces (16 vs. 18 in Hayate) but the open board gives each
piece high mobility. Only 2 pawns means drop options are less restricted by
nifu, increasing branching factor for drop moves. The 1-rank promotion zone
means games tend to be slightly shorter (promotion is decisive when achieved).
5 hand piece types with the 2-silver doubling create interesting hand
combinations.

#### Why This Is Good for Computer Chess

- **Doubled silvers create unique patterns**: Standard shogi variants
  typically have 1 silver per side. Having 2 silvers changes the defensive
  and attacking dynamics in ways that NNUE must learn from scratch (no
  transfer from standard variants).
- **1-rank promotion zone**: The narrow promotion zone creates "all or
  nothing" breakthrough dynamics. NNUE must learn to evaluate positions where
  a piece is one rank away from promotion vs. safely distant.
- **2-pawn openness**: With only 2 pawns, almost every game reaches a unique
  middle-game position. This is excellent for NNUE training because the
  network sees diverse positions rather than repeated patterns.
- **Sharp tactics**: The combination of open board, powerful drops, and
  narrow promotion zone creates a game where tactics dominate. NNUE must
  learn to evaluate tactical complications accurately, which requires
  training on many diverse positions.

#### Comparison to Existing Variants

- **vs. MiniShogi (5x5)**: Both have a 1-rank promotion zone. But MiniShogi
  has 1 pawn per side on a 5x5 board with no doubled pieces. Tsurugi has 2
  pawns, 2 silvers, and a 6x6 board -- a substantially richer game.
- **vs. Judkins Shogi (6x6)**: Judkins has 7 piece types (including knight)
  but only 1 of each. Tsurugi has 5 piece types but doubles the silver. The
  1-rank promotion zone (vs. Judkins' 2-rank zone) creates a very different
  strategic character.
- **vs. Hayate Shogi (6x6, this document)**: Hayate has lance and 3 pawns
  with a 2-rank zone. Tsurugi has doubled silvers and 2 pawns with a 1-rank
  zone. Hayate is more positional; Tsurugi is more tactical.
- **Unique aspects**: The doubled silver and 1-rank promotion zone combination
  is not found in any published shogi variant.

---

## Comparison Table

| # | Name | Board | Type | Pieces/Side | Pawns | Drops | Promo Zone | Branching | Game Length | State Space | Tree Complexity |
|---|------|-------|------|-------------|-------|-------|------------|-----------|-------------|-------------|-----------------|
| 1 | Bastion Chess | 6x6 | Chess | 10 | 4 | No | Last rank | ~28 | ~50 ply | ~10^16 | ~10^36 |
| 2 | Corridor Chess | 6x7 | Chess | 11 | 5 | No | Last rank | ~30 | ~60 ply | ~10^19 | ~10^44 |
| 3 | Citadel Chess | 6x6 | Chess | 9 | 3 | No | Last rank* | ~32 | ~45 ply | ~10^15 | ~10^34 |
| 4 | Hayate Shogi | 6x6 | Shogi | 9 | 3 | Yes | Last 2 ranks | ~40 | ~50 ply | ~10^19 | ~10^40 |
| 5 | Renmei Shogi | 6x7 | Shogi | 11 | 3 | Yes | Last 2 ranks | ~50 | ~60 ply | ~10^23 | ~10^52 |
| 6 | Tsurugi Shogi | 6x6 | Shogi | 8 | 2 | Yes | Last 1 rank | ~35 | ~45 ply | ~10^17 | ~10^35 |

*Citadel Chess uses capture-based promotion (promote only to captured piece types).

### Key Observations from the Table

- **Shogi variants have higher complexity per square**: Drops dramatically
  amplify both state space and game tree complexity. Hayate Shogi on a 6x6
  board has comparable complexity to Corridor Chess on a 6x7 board, despite
  having fewer pieces.
- **Renmei Shogi is the most complex**: At ~10^52 game tree complexity, it
  approaches Tori Shogi (~10^50) and is far beyond brute-force solvability.
- **Citadel Chess is the simplest**: At ~10^34, it is comparable to Gardner
  MiniChess. However, the capture-based promotion rule adds evaluative
  complexity not captured by game tree size alone.
- **All variants exceed the solvability threshold**: Even the simplest
  (Citadel, ~10^34) is at the boundary of what has been weakly solved. None
  should be trivially solvable by modern engines.

---

## Recommendations

### Top Chess-type Recommendation: Corridor Chess (6x7)

**Justification:**

1. **Novel board shape**: The 6x7 board is unexplored territory for chess
   variants. The rectangular shape changes fundamental properties: bishop
   diagonals have different lengths, the center is shifted, and the pawn
   promotion journey is longer. This novelty means NNUE must learn genuinely
   new patterns.

2. **Highest chess-type complexity**: At ~10^44 game tree complexity, Corridor
   Chess is orders of magnitude more complex than Los Alamos chess (~10^33)
   or Gardner MiniChess (~10^34). This ensures NNUE training matters -- the
   game cannot be solved by depth alone.

3. **Strong fairness**: The 180-degree rotational symmetry and 3-rank buffer
   zone should produce excellent balance. The elongated board reduces
   first-mover advantage more than compact boards.

4. **Complete piece set**: All 6 chess piece types are present, creating the
   richest possible piece interaction space. Bishop diagonals on a
   rectangular board are particularly interesting for NNUE learning.

5. **Implementation simplicity**: The rules are standard chess rules on a
   new board size. No special rules (no capture-based promotion, no unusual
   piece types). This makes it the easiest to implement correctly (~500 lines
   of C++) and the least likely to have rule-ambiguity bugs.

### Top Shogi-type Recommendation: Renmei Shogi (6x7)

**Justification:**

1. **Complete standard shogi piece set**: Renmei is the only small-board shogi
   variant that includes ALL standard piece types (P, L, N, S, G, B, R, K)
   with major pieces on the board (not just in hand). This makes it the most
   faithful scaled-down shogi experience and the most interesting for NNUE
   because all piece interactions must be learned.

2. **Highest overall complexity**: At ~10^52 game tree complexity, Renmei is
   the most complex variant in this document and approaches the complexity
   of Tori Shogi. This ensures that NNUE quality is the primary determinant
   of playing strength, not search depth.

3. **Rich drop mechanics**: With 7 hand piece types, the drop dimension of
   the game is enormous. NNUE must learn not just board evaluation but also
   the value of each piece type in hand across diverse positions.

4. **Wing-based asymmetry**: The pawn placement on one wing (balanced by
   rotation) creates directional play themes. NNUE must learn that the value
   of a rook depends on whether it's attacking the pawn wing or the open
   wing -- a sophisticated positional concept.

5. **6x7 board**: Like Corridor Chess, the rectangular board is novel for
   shogi. The extra rank gives the knight more room to operate (the knight's
   2+1 jump is very constrained on a 6-rank board but workable on a 7-rank
   board).

6. **Balanced piece count**: 11 pieces per side is substantial enough for
   rich play but small enough for fast computation. Games complete in ~60
   ply, allowing rapid selfplay data generation for NNUE training.

---

## What Makes a Variant Good for NNUE Training

### Position Diversity

The most important property for NNUE training is a large, diverse set of
reachable positions. If many games follow similar patterns (as happens in
solved or near-solved variants), the NNUE network overfits to a small region
of the position space and fails to generalize.

**Design implications:**
- Open starting positions (fewer pawns) increase early-game diversity.
- Drops dramatically increase position diversity (pieces can appear on any
  empty square).
- Asymmetric features (wing-based pawns, offset back ranks) create
  directional variety.

### Complex Evaluation Landscape

NNUE is most valuable when the evaluation function is non-trivial -- when
simple material counting is insufficient and positional factors dominate.

**Design implications:**
- Promotion zones create "threshold effects" where a piece one rank away
  from promotion is worth more than the same piece two ranks away.
- Capture-based promotion (Citadel Chess) creates conditional values.
- Multiple piece types with different movement patterns create interaction
  effects that material counting cannot capture.
- King safety on a small board is a complex, non-linear evaluation factor.

### Not Easily Solvable

If a variant can be solved (or nearly solved) by brute-force search, NNUE
adds no value -- a sufficiently deep search finds the truth regardless of
evaluation quality. The target complexity range is:

- **Too simple** (< ~10^20 game tree): Engine can practically solve many
  positions. NNUE training adds marginal value. Examples: Kyoto Shogi,
  Micro Shogi.
- **Sweet spot** (~10^30 to ~10^55 game tree): Search cannot solve positions,
  so evaluation quality determines playing strength. NNUE training is
  essential. Examples: All 6 variants in this document.
- **Too complex** (> ~10^60 game tree): Training may require prohibitive
  selfplay data. Not a concern for our board sizes.

### Tactical Richness

NNUE learns best from positions where tactical complications exist --
positions where a small change (one move) can swing the evaluation
dramatically. Games that are purely positional (slow maneuvering, no
tactics) provide less training signal.

**Design implications:**
- Drops create constant tactical tension (every empty square is a potential
  drop threat).
- Open boards (few pawns) allow tactical piece play from early in the game.
- Promotion threats create tactical flashpoints.
- Piece diversity (many piece types) creates more fork/pin/skewer patterns.

### Game Length

Games should be long enough for NNUE to learn meaningful positional concepts
(>30 ply) but short enough for rapid selfplay data generation (<100 ply).
The sweet spot is ~40-70 ply.

**Design implications:**
- Draw limits (MAX_STEP) prevent infinite games.
- The number of pieces and pawns controls game length -- more pieces means
  longer games.
- Promotion zones affect game length -- narrow zones (1 rank) create
  shorter, sharper games; wide zones (2 ranks) create longer games.

### Feature Space Size

NNUE networks have a fixed input layer that encodes piece positions. The
feature space should be large enough to be interesting but small enough for
efficient training.

For a board with W files, H ranks, P piece types per side, and K hand piece
types:
- Board features: 2 (sides) x H x W x P
- Hand features: 2 (sides) x K x max_count
- Total feature space should be in the range of ~200-1000 for efficient
  halfkp-style architectures.

All 6 variants in this document fall within this range:
- Bastion Chess: 2 x 6 x 6 x 5 = 360 board features
- Corridor Chess: 2 x 7 x 6 x 5 = 420 board features
- Citadel Chess: 2 x 6 x 6 x 5 = 360 board features
- Hayate Shogi: 2 x 6 x 6 x 10 + 2 x 6 x max = ~720+ board+hand features
- Renmei Shogi: 2 x 7 x 6 x 10 + 2 x 7 x max = ~840+ board+hand features
- Tsurugi Shogi: 2 x 6 x 6 x 8 + 2 x 5 x max = ~576+ board+hand features

---

## Implementation Notes

All 6 variants are implementable within the existing `BaseState` interface.
Key implementation considerations:

### Chess-type Variants

- Reuse the existing `Board` class structure: `char board[2][BOARD_H][BOARD_W]`.
- Piece type encoding: 1=Pawn, 2=Rook, 3=Knight, 4=Bishop, 5=Queen, 6=King
  (same as existing MiniChess).
- Move generation: Adapt existing naive move generation (no bitboard needed
  for these board sizes; the overhead is minimal).
- Citadel Chess requires tracking captured pieces for promotion. Add a small
  array `bool captured[NUM_PIECE_TYPES]` to the Board class.

### Shogi-type Variants

- Reuse the existing MiniShogi `Board` class with hand pieces:
  `char hand[2][NUM_HAND_TYPES + 1]`.
- Add piece types for lance (and knight in Renmei). Promoted forms follow
  the same pattern as existing MiniShogi code.
- Drop move encoding: Use `DROP_ROW = BOARD_H` in the from-point, piece type
  in the from-column (same convention as existing MiniShogi).
- Renmei Shogi's knight drop restriction (cannot drop on last 2 ranks) is
  already handled in the existing MiniShogi codebase's `gen_drop_moves()`
  pattern and can be extended.

### Estimated Line Counts

| Variant | config.hpp | state.hpp | state.cpp | Total |
|---------|-----------|-----------|-----------|-------|
| Bastion Chess | ~30 | ~60 | ~400 | ~490 |
| Corridor Chess | ~30 | ~60 | ~400 | ~490 |
| Citadel Chess | ~35 | ~70 | ~500 | ~605 |
| Hayate Shogi | ~45 | ~70 | ~600 | ~715 |
| Renmei Shogi | ~50 | ~75 | ~650 | ~775 |
| Tsurugi Shogi | ~45 | ~70 | ~550 | ~665 |
