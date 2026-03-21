# Custom Shogi Variants v2 -- Proper Pawn Density

Redesigned shogi variants for the MiniChess engine framework. These replace the
earlier designs (Hayate, Renmei, Tsurugi) which had fatally low pawn counts
(2-3 pawns on a 6-column board), breaking fundamental shogi dynamics.

---

## The Problem with v1 Designs

In standard 9x9 shogi, 9 pawns fill all 9 files. The pawn wall IS the game:

- **Pawn exchanges** create files for rook penetration.
- **Pawn chains** define the shape of the position and restrict piece movement.
- **Pawn drops** are the most common drop type, used for defense, tempo, and creating threats.
- **Nifu** (no two unpromoted pawns per file) is a real constraint that shapes drop strategy.
- **Lance** charges down files that have been opened by pawn exchanges.
- **Rook and Bishop** are blocked by the pawn wall until exchanges happen.

The v1 designs had 2-3 pawns on 6 files. This meant:

1. **Rook/Bishop dominate from move 1** -- no wall to impede ranging pieces.
2. **Drops are overpowered** -- dropping a Rook behind enemy lines with 3-4 open files is nearly decisive.
3. **No positional play** -- shogi strategy revolves around deciding WHICH pawn to exchange and WHERE to open a file. With 2-3 pawns, there are no choices to make.
4. **Lance is useless** -- it needs a file to charge down, but without pawn walls, it has no tactical niche.
5. **Nifu is irrelevant** -- with 3 pawns on 6 files, you can always find an open file for a pawn drop.

**Pawn density target**: 5-6 pawns on 6 files (83-100% coverage). This matches
real shogi's 9/9 = 100% and Corridor Chess's successful 5/7 = 71% approach.

---

## Design Principles

1. **5-6 pawns per side on a 6-column board** -- one pawn per file or close to it.
2. **Back rank has King + officers behind the pawn wall** -- not alongside it.
3. **Board size: 6x6 or 6x7** -- fits the engine framework.
4. **Full shogi rules** -- drops, promotions, capture-and-reuse.
5. **As fair as possible** -- 180-degree rotational symmetry preferred.
6. **Designed for computer play / NNUE training** -- sufficient complexity, diverse positions.

---

## Table of Contents

1. [Variant A: Compact Shogi (6x6)](#variant-a-compact-shogi-6x6)
2. [Variant B: Full Shogi 6x7 (6x7)](#variant-b-full-shogi-6x7-6x7)
3. [Variant C: Knight Shogi (6x6)](#variant-c-knight-shogi-6x6)
4. [Variant D: Fortress Shogi (6x6)](#variant-d-fortress-shogi-6x6)
5. [Comparison Table](#comparison-table)
6. [Comparison to MiniShogi and Judkins Shogi](#comparison-to-minishogi-and-judkins-shogi)

---

## Variant A: Compact Shogi (6x6)

### Name and Board Size

**Compact Shogi** -- the smallest variant that preserves the pawn-wall feel of
real shogi. 6 ranks x 6 files (6x6). Like real shogi minus Lance and Knight,
with a near-full pawn front.

### Complete Piece Set

Each side has **10 pieces on board**:

| Piece | Count | Movement | Promoted Form |
|-------|-------|----------|---------------|
| King (K/k) | 1 | 1 step any direction | -- |
| Rook (R/r) | 1 | Any orthogonal | +R / Dragon (Rook + 1-step diagonal) |
| Bishop (B/b) | 1 | Any diagonal | +B / Horse (Bishop + 1-step orthogonal) |
| Gold (G/g) | 1 | 1 step: fwd, diag-fwd, sideways, back | -- |
| Silver (S/s) | 1 | 1 step: fwd, all 4 diags | +S (Gold movement) |
| Pawn (P/p) | 5 | 1 step forward | +P / Tokin (Gold movement) |

Total: 10 pieces per side, 20 on board.

**Hand piece types** (5): Pawn, Silver, Gold, Bishop, Rook.

### ASCII Art Initial Position

```
     a   b   c   d   e   f
  +---+---+---+---+---+---+
6 | R | B | S | G | K | . |  <- Gote (White)
  +---+---+---+---+---+---+
5 | p | p | p | p | p | . |
  +---+---+---+---+---+---+
4 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
3 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
2 | . | P | P | P | P | P |
  +---+---+---+---+---+---+
1 | . | K | G | S | B | R |  <- Sente (Black)
  +---+---+---+---+---+---+

Sente (Black, moves first):
  King(b1), Gold(c1), Silver(d1), Bishop(e1), Rook(f1)
  Pawns: b2, c2, d2, e2, f2

Gote (White):
  Rook(a6), Bishop(b6), Silver(c6), Gold(d6), King(e6)
  Pawns: a5, b5, c5, d5, e5
```

**180-degree rotational symmetry.** Sente occupies files b-f (ranks 1-2), Gote
occupies files a-e (ranks 5-6). Each side has 5 pawns covering 5 of 6 files,
with one open file on their own wing (a-file for Sente, f-file for Gote). The
open files are on opposite sides of the board, creating directional tension.

### Rules Summary

- Standard shogi rules: capture-and-reuse (drops), promotion.
- Win by capturing the opponent's king.
- **Drop restrictions**:
  - **Nifu**: No two unpromoted friendly pawns in the same file.
  - **Uchifuzume**: No pawn drop that delivers immediate checkmate.
  - Pawns cannot be dropped on the last rank (no legal move).
- All captured pieces revert to unpromoted form when entering the hand.
- Draw on move 200 (MAX_STEP = 200) or by repetition (sennichite -- the player
  perpetuating a repeated position loses, or draw if both equally responsible).

### Promotion Rules and Zone

**Promotion zone**: Last **2 ranks** (ranks 5-6 for Sente, ranks 1-2 for Gote).

| Piece | Promotes To | Mandatory? |
|-------|-------------|------------|
| Pawn | Tokin (+P) -- Gold movement | Yes, on last rank |
| Silver | +S -- Gold movement | No |
| Bishop | Horse (+B) -- Bishop + 1-step orthogonal | No |
| Rook | Dragon (+R) -- Rook + 1-step diagonal | No |
| Gold | -- | Cannot promote |
| King | -- | Cannot promote |

Promotion is optional when entering, moving within, or leaving the promotion
zone, except when a piece would have no legal move in its current form.

### Fairness Analysis

- **Rotational symmetry**: Perfect 180-degree rotational symmetry ensures no
  structural bias. Every positional feature White has, Black has the mirror.
- **5 pawns on 6 files**: Each side has a dense pawn wall covering 5 of 6 files.
  The single open file is on each side's own wing (a-file for Sente, f-file for
  Gote), creating directional asymmetry that enriches play without favoring either
  side.
- **2-rank buffer zone**: With 6 ranks, pieces on ranks 1-2 and 5-6, there are
  exactly 2 empty ranks (3-4) between the pawn lines. This is tight -- like
  real shogi's 3-rank gap scaled down. Contact happens quickly but not
  immediately.
- **Drop mechanics offset tempo**: The second player can deploy captured pieces
  instantly, partially compensating for the first-move advantage.
- **Expected first-player advantage**: Moderate. ~52-54%. The dense pawn wall
  slows the tempo advantage compared to open-board variants.

### Complexity Estimates

| Metric | Estimate | Reasoning |
|--------|----------|-----------|
| Pieces on board (start) | 20 (10 per side) | 5 officers + 5 pawns each |
| Avg. branching factor | ~38 | 5 pawns = more nifu-constrained drops, but more board moves |
| Avg. game length | ~55 ply | Dense pawns slow the game; pawn exchanges create middle-game structure |
| State space (positions) | ~10^18 | 36 squares, 5 hand types, pawn permutations |
| Game tree complexity | ~10^42 | b^(d/2) = 38^27.5 ~ 10^43, adjusted for draws/termination |

**Branching factor breakdown**: ~15 board moves (5 pawns with 1 move each,
plus officers) + ~23 drop moves (5 hand types x ~4.6 legal squares average,
restricted by nifu) = ~38 total. With 5 pawns, nifu blocks 5 files for pawn
drops, leaving only 1 file open -- pawn drops are genuinely scarce, forcing
players to use other pieces for drops. This is a key strategic feature.

### Why It Works for NNUE Training

- **Pawn structure matters**: With 5 pawns, the network must learn pawn-chain
  dynamics: which pawn to advance, which to exchange, and how file-opening
  affects piece mobility. This is the core of shogi strategy.
- **Nifu is a real constraint**: 5 pawns on 6 files means only 1 file is
  initially open for pawn drops. NNUE must learn the value of opening files
  (via pawn exchange) for both piece infiltration and drop opportunities.
- **Controlled piece activity**: Rook and Bishop start behind the pawn wall
  and must find ways to activate. This creates the development-vs-attack tension
  that produces diverse training positions.
- **Compact but not trivial**: 10^42 game tree complexity is well beyond
  solvability. The 6x6 board keeps inference fast for self-play datagen.

### Comparison to MiniShogi (5x5) and Judkins Shogi (6x6)

- **vs. MiniShogi (5x5)**: MiniShogi has 1 pawn per side on a 5x5 board -- no
  pawn structure exists. Compact Shogi's 5 pawns create a genuine pawn wall that
  dominates the opening and shapes the middle game. MiniShogi is essentially a
  drop-tactics game; Compact Shogi is a pawn-structure + drops game.
- **vs. Judkins Shogi (6x6)**: Judkins has 1 pawn per side, a Knight, and a
  1-pawn-in-king-file arrangement. It plays more like "drop chess with shogi
  pieces" than like shogi. Compact Shogi sacrifices the Knight to gain 5 pawns,
  which fundamentally changes the game's character to feel like real shogi.
  Judkins has ~10^32 complexity; Compact Shogi has ~10^42 -- a 10-billion-fold
  increase in game tree size, largely driven by the richer pawn interactions.

---

## Variant B: Full Shogi 6x7 (6x7)

### Name and Board Size

**Full Shogi 6x7** -- the variant that feels closest to real 9x9 shogi. Includes
ALL standard shogi piece types (King, Rook, Bishop, 2 Gold, 2 Silver, Knight,
Lance, 6 Pawns) on a 6x7 board. The 7 rows give room for the pawn wall, piece
development, and Knight jumping.

### Complete Piece Set

Each side has **14 pieces on board**:

| Piece | Count | Movement | Promoted Form |
|-------|-------|----------|---------------|
| King (K/k) | 1 | 1 step any direction | -- |
| Rook (R/r) | 1 | Any orthogonal | +R / Dragon (Rook + 1-step diagonal) |
| Bishop (B/b) | 1 | Any diagonal | +B / Horse (Bishop + 1-step orthogonal) |
| Gold (G/g) | 2 | 1 step: fwd, diag-fwd, sideways, back | -- |
| Silver (S/s) | 2 | 1 step: fwd, all 4 diags | +S (Gold movement) |
| Knight (N/n) | 1 | Jump: 2 forward + 1 sideways | +N (Gold movement) |
| Lance (L/l) | 1 | Any number forward only | +L (Gold movement) |
| Pawn (P/p) | 6 | 1 step forward | +P / Tokin (Gold movement) |

Total: 14 pieces per side (reduced from real shogi's 20), 28 on board.

In real 9x9 shogi: K, R, B, 2G, 2S, 2N, 2L, 9P = 20 pieces. Full Shogi 6x7
cuts one Knight, one Lance, and 3 Pawns -- proportional to the board shrinkage
from 81 to 42 squares (52% reduction in area, 30% reduction in pieces).

**Hand piece types** (7): Pawn, Silver, Gold, Bishop, Rook, Knight, Lance.

### ASCII Art Initial Position

```
     a   b   c   d   e   f
  +---+---+---+---+---+---+
7 | L | N | S | G | K | . |  <- Gote (White)
  +---+---+---+---+---+---+
6 | . | R | . | . | B | . |
  +---+---+---+---+---+---+
5 | p | p | p | p | p | p |
  +---+---+---+---+---+---+
4 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
3 | P | P | P | P | P | P |
  +---+---+---+---+---+---+
2 | . | b | . | . | r | . |
  +---+---+---+---+---+---+
1 | . | K | G | S | N | L |  <- Sente (Black)
  +---+---+---+---+---+---+

Sente (Black, moves first):
  Back rank (rank 1): King(b1), Gold(c1), Silver(d1), Knight(e1), Lance(f1)
  Rank 2: Bishop(b2), Rook(e2)
  Pawns (rank 3): a3, b3, c3, d3, e3, f3

Gote (White):
  Back rank (rank 7): Lance(a7), Knight(b7), Silver(c7), Gold(d7), King(e7)
  Rank 6: Rook(b6), Bishop(e6)
  Pawns (rank 5): a5, b5, c5, d5, e5, f5
```

**180-degree rotational symmetry.** Sente's King is on b1, Gote's King is on
e7 -- rotationally symmetric. The Rook and Bishop are on rank 2/6, one square
advanced from the back rank, allowing them to support the pawn wall while being
ready to activate once files open.

**Design rationale for piece placement**:
- **6 pawns fill ALL 6 files** -- a complete pawn wall, exactly like real shogi's
  9 pawns on 9 files. This is the most important design feature.
- **Rook and Bishop on rank 2/6** -- in real shogi, the Rook starts behind the
  pawn wall on rank 2 and the Bishop on rank 2. Here we replicate this: they sit
  one rank behind the pawn wall, ready to activate through pawn exchanges.
- **Second Gold is placed on the back rank** -- providing king safety (a "Gold
  fortress" pattern from real shogi).
- **Knight and Lance are on the wing** -- the Lance on the edge file can charge
  down that file once the pawn exchanges open it.

### Rules Summary

- Full standard shogi rules: capture-and-reuse (drops), promotion.
- Win by capturing the opponent's king.
- **Drop restrictions**:
  - **Nifu**: No two unpromoted friendly pawns in the same file.
  - **Uchifuzume**: No pawn drop that delivers immediate checkmate.
  - Pawns and Lances cannot be dropped on the last rank.
  - Knights cannot be dropped on the last 2 ranks (no legal forward jump from there).
- Draw on move 256 (MAX_STEP = 256) or by repetition.

### Promotion Rules and Zone

**Promotion zone**: Last **2 ranks** (ranks 6-7 for Sente, ranks 1-2 for Gote).

| Piece | Promotes To | Mandatory? |
|-------|-------------|------------|
| Pawn | Tokin (+P) -- Gold movement | Yes, on last rank |
| Silver | +S -- Gold movement | No |
| Knight | +N -- Gold movement | Yes, on last 2 ranks |
| Lance | +L -- Gold movement | Yes, on last rank |
| Bishop | Horse (+B) -- Bishop + 1-step orthogonal | No |
| Rook | Dragon (+R) -- Rook + 1-step diagonal | No |
| Gold | -- | Cannot promote |
| King | -- | Cannot promote |

**Forced promotion reasoning**: On a 7-rank board, a Knight on rank 6 can still
jump to rank 7+1 = out of bounds (since the board only goes to rank 7). Actually,
a Knight on rank 6 jumps forward 2 to rank 8 -- which does not exist. A Knight
on rank 7 would jump to rank 9 -- also nonexistent. So Knights on the last 2
ranks have no legal forward jump and must promote. This matches the standard
rule scaled to 7 ranks: on a 9-rank board, Knights on ranks 8-9 must promote;
here, Knights on ranks 6-7 must promote.

### Fairness Analysis

- **Rotational symmetry**: Perfect 180-degree rotational symmetry.
- **Complete pawn wall**: 6 pawns on 6 files means every file is occupied. The
  opening phase consists of choosing WHICH pawn to advance and exchange -- exactly
  like real shogi. This is the single most important fairness and gameplay feature.
- **3-rank buffer (ranks 3-5)**: Wait -- actually the pawn lines are on ranks 3
  and 5, so only rank 4 is between them. This means pawns are separated by only
  1 rank. This is deliberate: it mirrors real shogi where pawns on rank 3 and
  rank 7 are separated by 3 ranks on a 9-rank board. Proportionally,
  1 rank / 7 total = 14% vs. 3 ranks / 9 total = 33%. The tighter spacing means
  pawn contact happens faster, which is appropriate for a smaller board where
  games should resolve sooner. A 6x7 board cannot afford 20+ moves of quiet
  development like a 9x9 board.
- **Rook/Bishop behind the wall**: The major pieces start behind the pawn wall
  (rank 2 for Sente, rank 6 for Gote), not on the front line. They must wait
  for pawn exchanges to activate -- exactly as in real shogi.
- **Two Golds for king safety**: Having 2 Golds allows the classic "Gold-Silver
  fortress" castle formation around the King.
- **Expected first-player advantage**: Low-moderate. ~52-53%. The dense pawn wall
  and deep board reduce tempo advantage. The second player has defensive resources
  via drops and a fully populated pawn wall.

### Complexity Estimates

| Metric | Estimate | Reasoning |
|--------|----------|-----------|
| Pieces on board (start) | 28 (14 per side) | Highest density of all variants |
| Avg. branching factor | ~55 | 6 pawns + 7 hand types + Knight/Lance specials |
| Avg. game length | ~70 ply | Dense pawn wall + deep board = longer games |
| State space (positions) | ~10^26 | 42 squares, 7 hand types, massive pawn permutations |
| Game tree complexity | ~10^60 | b^(d/2) = 55^35 ~ 10^61, adjusted |

**Branching factor breakdown**: ~20 board moves (6 pawns + 8 officers) + ~35
drop moves (7 hand types, but nifu blocks 6 files for pawn drops initially,
leaving 0 open -- pawn drops are IMPOSSIBLE until a pawn is exchanged, just
like real shogi). After the first pawn exchange, the captured pawn can be
dropped on the now-open file (or any file where the player has no pawn). This
"earn your drops" dynamic is the heart of shogi.

### Why It Works for NNUE Training

- **Closest to real shogi**: NNUE patterns learned here transfer most naturally
  to/from real shogi knowledge. Pawn-push timing, file-opening strategy, castle
  formation, and piece coordination all mirror 9x9 shogi at a compressed scale.
- **7 hand piece types**: The largest hand-state space of all variants. NNUE must
  learn nuanced piece-in-hand valuations that depend on board structure.
- **Complete piece set**: All standard shogi piece types appear. The network
  learns Knight forks, Lance skewers, Silver-Gold defense coordination, and
  Rook-Bishop major piece interplay.
- **Game length**: ~70 ply provides long, complex games with many training
  positions per game. The middle-game is where NNUE evaluation matters most, and
  this variant has a substantial middle-game phase.
- **Diversity**: The complete pawn wall can be opened in 2^6 = 64 different
  file-opening combinations (each file can be open or closed), creating enormous
  positional diversity for training data.

### Comparison to MiniShogi (5x5) and Judkins Shogi (6x6)

- **vs. MiniShogi (5x5)**: MiniShogi has 1 pawn, no Knight, no Lance, no doubled
  Golds/Silvers. It is a speed-tactics game. Full Shogi 6x7 has 6 pawns, a
  Knight, a Lance, 2 Golds, 2 Silvers -- it is a genuine shogi game with
  opening theory, middle-game strategy, and endgame technique. The complexity
  jump is enormous: ~10^60 vs. MiniShogi's ~10^20.
- **vs. Judkins Shogi (6x6)**: Judkins has 1 pawn, 1 Gold, 1 Silver, 1 Knight,
  no Lance. Full Shogi 6x7 has 6x the pawns, 2x the Golds, 2x the Silvers,
  adds a Lance, and uses a deeper 7-rank board. Judkins feels like a "shogi
  puzzle"; Full Shogi 6x7 feels like a real game. Complexity: ~10^60 vs. ~10^32.
- **vs. Renmei Shogi (6x7, v1)**: Renmei had 3 pawns on 6 files -- half the
  files were open from the start. Full Shogi 6x7 has 6 pawns covering all files.
  This single change transforms the game from an open-board tactics fest into a
  proper positional shogi game. Renmei also placed the Rook and Bishop on rank
  2/6 but with only 3 pawns shielding them, they were immediately active.

---

## Variant C: Knight Shogi (6x6)

### Name and Board Size

**Knight Shogi** -- like Compact Shogi but adds the Knight, the piece that
MiniShogi and standard Compact Shogi lack. The Knight's 2-forward-1-sideways
jump adds tactical forks and requires the pawn wall to account for jump-over
threats. 6 ranks x 6 files (6x6).

### Complete Piece Set

Each side has **11 pieces on board**:

| Piece | Count | Movement | Promoted Form |
|-------|-------|----------|---------------|
| King (K/k) | 1 | 1 step any direction | -- |
| Rook (R/r) | 1 | Any orthogonal | +R / Dragon (Rook + 1-step diagonal) |
| Bishop (B/b) | 1 | Any diagonal | +B / Horse (Bishop + 1-step orthogonal) |
| Gold (G/g) | 1 | 1 step: fwd, diag-fwd, sideways, back | -- |
| Silver (S/s) | 1 | 1 step: fwd, all 4 diags | +S (Gold movement) |
| Knight (N/n) | 1 | Jump: 2 forward + 1 sideways | +N (Gold movement) |
| Pawn (P/p) | 5 | 1 step forward | +P / Tokin (Gold movement) |

Total: 11 pieces per side, 22 on board.

**Hand piece types** (6): Pawn, Silver, Gold, Bishop, Rook, Knight.

### ASCII Art Initial Position

```
     a   b   c   d   e   f
  +---+---+---+---+---+---+
6 | R | B | N | G | K | . |  <- Gote (White)
  +---+---+---+---+---+---+
5 | p | p | p | p | p | . |
  +---+---+---+---+---+---+
4 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
3 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
2 | . | P | P | P | P | P |
  +---+---+---+---+---+---+
1 | . | K | G | N | B | R |  <- Sente (Black)
  +---+---+---+---+---+---+

Sente (Black, moves first):
  King(b1), Gold(c1), Knight(d1), Bishop(e1), Rook(f1)
  Pawns: b2, c2, d2, e2, f2

Gote (White):
  Rook(a6), Bishop(b6), Knight(c6), Gold(d6), King(e6)
  Pawns: a5, b5, c5, d5, e5
```

**180-degree rotational symmetry.** Identical structure to Compact Shogi but with
the Silver replaced by a Knight. The Knight sits on d1/c6, in the interior of
the back rank, where it can jump forward over the pawn wall to reach d3+c2/e2
or d3+e2/c2 targets (Sente perspective: from d1, the Knight jumps to c3 or e3
on its first move).

**Knight placement rationale**: The Knight is placed in the center of the back
rank rather than on the wing. On a 6-file board, a wing-placed Knight has fewer
jump targets. Centralized, it threatens both flanks. The 5-pawn wall in front of
it gives the Knight time to develop -- it can jump over the pawns (Shogi knights
leap, they are not blocked by pieces on the intermediate square).

### Rules Summary

- Standard shogi rules with drops and promotion.
- Win by capturing the opponent's king.
- **Drop restrictions**:
  - **Nifu**: No two unpromoted friendly pawns in the same file.
  - **Uchifuzume**: No pawn drop that delivers immediate checkmate.
  - Pawns cannot be dropped on the last rank.
  - Knights cannot be dropped on the last 2 ranks (a Knight on ranks 5-6 for
    Sente or ranks 1-2 for Gote has no legal forward jump on a 6-rank board).
- Draw on move 200 (MAX_STEP = 200) or by repetition.

**Knight on a 6-rank board**: A Sente Knight jumps forward 2 ranks. From rank 4,
it jumps to rank 6 (the last rank) -- this is legal. From rank 5, it would jump
to rank 7, which does not exist. So Knights on rank 5 or rank 6 have no legal
move and cannot be dropped there. This means Knights can only be dropped on
ranks 1-4 (for Sente) or ranks 3-6 (for Gote).

### Promotion Rules and Zone

**Promotion zone**: Last **2 ranks** (ranks 5-6 for Sente, ranks 1-2 for Gote).

| Piece | Promotes To | Mandatory? |
|-------|-------------|------------|
| Pawn | Tokin (+P) -- Gold movement | Yes, on last rank |
| Silver | +S -- Gold movement | No (N/A -- no Silver in this variant) |
| Knight | +N -- Gold movement | Yes, on last 2 ranks |
| Bishop | Horse (+B) -- Bishop + 1-step orthogonal | No |
| Rook | Dragon (+R) -- Rook + 1-step diagonal | No |
| Gold | -- | Cannot promote |
| King | -- | Cannot promote |

Note: This variant has no Silver piece. The Knight replaces the Silver from
Compact Shogi. This is a deliberate tradeoff: Silver provides defensive
flexibility (all 4 diagonals + forward), while Knight provides offensive
jump-fork threats. Knight Shogi is therefore more tactically sharp than
Compact Shogi.

### Fairness Analysis

- **Rotational symmetry**: Perfect 180-degree rotational symmetry.
- **5 pawns on 6 files**: Same dense pawn wall as Compact Shogi.
- **Knight dynamics**: The Knight jumps over the pawn wall, creating early
  tactical threats that both sides face equally (rotational symmetry). The Knight
  is a double-edged piece: powerful for offense but weak for defense (it cannot
  retreat in shogi). This creates exciting, aggressive games.
- **No Silver, more tactical**: Without the Silver's flexible defensive
  coverage, the King is more exposed to diagonal attacks. This increases the
  importance of the Gold for king safety and makes the game sharper.
- **Expected first-player advantage**: Moderate. ~53-55%. The Knight gives the
  first player more offensive options, but the pawn wall limits how quickly
  these can be exploited.

### Complexity Estimates

| Metric | Estimate | Reasoning |
|--------|----------|-----------|
| Pieces on board (start) | 22 (11 per side) | 6 officers + 5 pawns + Knight |
| Avg. branching factor | ~42 | Knight adds jump targets; 6 hand types |
| Avg. game length | ~50 ply | Knight forks can accelerate resolution |
| State space (positions) | ~10^19 | 36 squares, 6 hand types |
| Game tree complexity | ~10^40 | b^(d/2) = 42^25 ~ 10^40 |

**Knight impact on branching**: The Knight adds 2 target squares per position
(jump forward-left and forward-right). More importantly, Knight drops add a
new tactical dimension: dropping a Knight to create a fork on the King and a
Gold is a classic shogi tactic. With 6 hand types instead of 5, drop-move
generation produces ~10% more moves.

### Why It Works for NNUE Training

- **Knight tactics require deep evaluation**: Knight forks and drop-fork threats
  are notoriously hard for evaluation functions. NNUE must learn "this position
  looks safe but a Knight drop on d4 forks the King and Rook." This is exactly
  the kind of pattern that makes NNUE valuable over handcrafted evaluation.
- **Pawn wall + Knight interaction**: The Knight jumps over the pawn wall, so
  NNUE must learn that pawns do NOT protect against Knight threats the way they
  protect against Rook/Bishop/Lance. This creates a rich interaction between
  piece types that rewards deep training.
- **No Silver = different defense patterns**: Without the Silver's diagonal
  defense, the King relies on Gold and pawn drops for protection. NNUE must
  learn defensive patterns that do not exist in other variants.
- **Sharp games generate diverse positions**: The Knight's tactical nature means
  games diverge quickly from the opening, producing high positional diversity
  for training.

### Comparison to MiniShogi (5x5) and Judkins Shogi (6x6)

- **vs. MiniShogi (5x5)**: MiniShogi has no Knight, 1 pawn, and plays as a
  pure drop-tactics game. Knight Shogi has a Knight AND 5 pawns, combining
  jump-fork tactics with pawn-structure strategy.
- **vs. Judkins Shogi (6x6)**: Judkins has a Knight but only 1 pawn. This means
  the Knight has no pawn wall to jump over -- it just attacks freely in open
  space. Knight Shogi gives the Knight a wall to interact with, making the
  Knight's role more nuanced: it threatens to bypass the wall, forcing the
  opponent to create countermeasures. Judkins' Knight is strong because
  everything is open; Knight Shogi's Knight is interesting because it creates
  asymmetric threats through a structured position.
- **vs. Compact Shogi (this document, Variant A)**: Same structure but Silver
  replaced with Knight. Compact Shogi is more positional (Silver is a flexible
  defender); Knight Shogi is more tactical (Knight is a rigid attacker).

---

## Variant D: Fortress Shogi (6x6)

### Name and Board Size

**Fortress Shogi** -- a creative 6x6 variant that doubles the Silver generals
instead of including Gold. The idea: two Silvers provide flexible diagonal
coverage but lack the Gold's straight-backward retreat capability, creating
a "fortress" that is strong on attack but has specific defensive weaknesses.
6 ranks x 6 files (6x6).

This variant explores what happens when you change the piece composition
while keeping pawn density high. Real shogi has Gold and Silver as complementary
pieces (Gold covers straight directions; Silver covers diagonals). What if you
had only Silvers? The defense becomes porous against straight-line attacks but
very strong against diagonal infiltration.

### Complete Piece Set

Each side has **11 pieces on board**:

| Piece | Count | Movement | Promoted Form |
|-------|-------|----------|---------------|
| King (K/k) | 1 | 1 step any direction | -- |
| Rook (R/r) | 1 | Any orthogonal | +R / Dragon (Rook + 1-step diagonal) |
| Bishop (B/b) | 1 | Any diagonal | +B / Horse (Bishop + 1-step orthogonal) |
| Silver (S/s) | 2 | 1 step: fwd, all 4 diags | +S (Gold movement) |
| Lance (L/l) | 1 | Any number forward only | +L (Gold movement) |
| Pawn (P/p) | 5 | 1 step forward | +P / Tokin (Gold movement) |

Total: 11 pieces per side, 22 on board.

**Hand piece types** (5): Pawn, Silver, Bishop, Rook, Lance.

**Key design decisions**:
- **No Gold general**: Replaced by a second Silver. This means promoted pieces
  (+S, +L, +P) gain Gold movement -- becoming the ONLY pieces with Gold-pattern
  movement on the board. Promotion is therefore more strategically significant
  than in any other variant: it is the only way to obtain a Gold-movement piece.
- **Lance included**: The Lance provides a forward-only ranging piece that works
  perfectly with the dense pawn wall. It charges down files opened by pawn
  exchanges.
- **2 Silvers**: Both Silvers can advance aggressively (their forward+diagonal
  movement makes them natural attacking pieces) but cannot retreat sideways or
  straight backward. This creates a "commit or die" dynamic: once a Silver
  advances, it cannot easily retreat.

### ASCII Art Initial Position

```
     a   b   c   d   e   f
  +---+---+---+---+---+---+
6 | L | S | B | S | K | . |  <- Gote (White)
  +---+---+---+---+---+---+
5 | p | p | p | p | p | . |
  +---+---+---+---+---+---+
4 | . | R | . | . | . | . |
  +---+---+---+---+---+---+
3 | . | . | . | . | r | . |
  +---+---+---+---+---+---+
2 | . | P | P | P | P | P |
  +---+---+---+---+---+---+
1 | . | K | S | B | S | L |  <- Sente (Black)
  +---+---+---+---+---+---+

Sente (Black, moves first):
  King(b1), Silver(c1), Bishop(d1), Silver(e1), Lance(f1)
  Rook(e3) -- advanced to rank 3
  Pawns: b2, c2, d2, e2, f2

Gote (White):
  Lance(a6), Silver(b6), Bishop(c6), Silver(d6), King(e6)
  Rook(b4) -- advanced to rank 4
  Pawns: a5, b5, c5, d5, e5
```

**180-degree rotational symmetry.** The Rooks start on rank 3/4 -- advanced in
front of the back rank but behind the pawn wall. This is a deliberate design
choice: it mirrors the "ranging Rook" (furibisha) opening strategy from real
shogi where the Rook moves to the center or opposite wing to support a pawn
push. Starting the Rook pre-deployed creates immediate tension and shortens
the opening phase for a smaller board.

**Why the Rook is advanced**: On a 6x6 board with 5 pawns, the back rank has
6 squares occupied by K + 2S + B + L = 5 pieces with an open square on the
wing. The Rook does not fit on the back rank without creating a cramped position.
Placing it on rank 3 (behind the pawn wall but in front of the back rank)
gives it room to operate and creates an interesting opening dynamic.

### Rules Summary

- Standard shogi rules with drops and promotion.
- Win by capturing the opponent's king.
- **Drop restrictions**:
  - **Nifu**: No two unpromoted friendly pawns in the same file.
  - **Uchifuzume**: No pawn drop that delivers immediate checkmate.
  - Pawns cannot be dropped on the last rank.
  - Lance cannot be dropped on the last rank.
- Draw on move 200 (MAX_STEP = 200) or by repetition.

### Promotion Rules and Zone

**Promotion zone**: Last **2 ranks** (ranks 5-6 for Sente, ranks 1-2 for Gote).

| Piece | Promotes To | Mandatory? |
|-------|-------------|------------|
| Pawn | Tokin (+P) -- Gold movement | Yes, on last rank |
| Silver | +S -- Gold movement | No |
| Lance | +L -- Gold movement | Yes, on last rank |
| Bishop | Horse (+B) -- Bishop + 1-step orthogonal | No |
| Rook | Dragon (+R) -- Rook + 1-step diagonal | No |
| King | -- | Cannot promote |

**Promotion is extra valuable in this variant**: Since there are no Gold generals
on the board, the only way to get Gold movement is through promotion. A promoted
Silver, promoted Lance, or promoted Pawn (Tokin) all gain the Gold's powerful
6-directional step movement. This makes the promotion zone a critical strategic
objective.

### Fairness Analysis

- **Rotational symmetry**: Perfect 180-degree rotational symmetry.
- **5 pawns on 6 files**: Dense pawn wall, same as Compact Shogi.
- **No Gold = promotion-focused strategy**: Both sides equally lack Gold generals.
  The race to promote pieces first is a symmetric objective that does not
  inherently favor the first player.
- **Advanced Rooks**: Both Rooks start in front of the back rank (rank 3 for
  Sente, rank 4 for Gote). The first player's Rook on rank 3 is one rank closer
  to the center than Gote's Rook on rank 4. However, the Rook on rank 4 is also
  useful -- it is immediately adjacent to the neutral zone. This slight
  positional tension enriches the opening without creating a decisive advantage.
- **Lance on the wing**: The Lance is on the edge file (f1 for Sente, a6 for
  Gote), ready to charge down the open file once the pawn is exchanged. Both
  sides have this resource.
- **Expected first-player advantage**: Moderate. ~53-55%. The Rook placement
  creates slight first-mover tension, but the pawn wall and lack of Gold
  (making defense harder for BOTH sides) keep the game dynamic.

### Complexity Estimates

| Metric | Estimate | Reasoning |
|--------|----------|-----------|
| Pieces on board (start) | 22 (11 per side) | Dense board with advanced Rooks |
| Avg. branching factor | ~40 | Lance adds ranging moves; 5 hand types |
| Avg. game length | ~50 ply | No Gold = less defensive; games resolve faster |
| State space (positions) | ~10^19 | 36 squares, 5 hand types, 2 Silver permutations |
| Game tree complexity | ~10^40 | b^(d/2) = 40^25 ~ 10^40 |

**Unique complexity driver**: The absence of Gold creates a tactical asymmetry
in the piece set: no piece on the initial board has the Gold's movement pattern
(forward, diag-forward, sideways, backward but not diag-backward). This means
positions are inherently more vulnerable to straight-line backward attacks
(which Gold normally defends against). NNUE must learn this unusual defensive
gap.

### Why It Works for NNUE Training

- **Novel piece composition**: No published shogi variant has 2 Silvers, no Gold,
  and a Lance on a 6x6 board. NNUE cannot rely on patterns learned from other
  variants -- it must learn from scratch.
- **Promotion creates Gold**: The "earn your Gold" mechanic means NNUE must learn
  to value promotion much more highly than in variants where Gold already exists
  on the board. A promoted Pawn (Tokin) becomes the most defensively important
  piece on the board.
- **Lance + pawn wall synergy**: The Lance is genuinely useful here (unlike in
  v1 designs where open boards made it redundant). NNUE must learn the Lance's
  value in relation to the pawn structure: on a closed file, the Lance is
  blocked by its own pawn; once the file opens (via pawn exchange), the Lance
  becomes a devastating attacker.
- **Advanced Rook creates opening diversity**: The Rook on rank 3/4 can swing
  left or right to support different pawn pushes. This creates branching opening
  strategies that produce diverse training positions.
- **Defensive learning**: Without Gold, NNUE must learn entirely new defensive
  patterns based on Silver positioning and pawn drops. This is the kind of
  novel evaluation challenge that makes NNUE training valuable.

### Comparison to MiniShogi (5x5) and Judkins Shogi (6x6)

- **vs. MiniShogi (5x5)**: MiniShogi has Gold, Silver, 1 pawn, and no Lance.
  Fortress Shogi has no Gold, 2 Silvers, 5 pawns, and a Lance. Completely
  different strategic character.
- **vs. Judkins Shogi (6x6)**: Judkins has Gold, Silver, Knight, and 1 pawn.
  Fortress Shogi has no Gold, 2 Silvers, Lance, and 5 pawns. Judkins is a
  Knight-tactics game on an open board; Fortress Shogi is a Lance-and-Silver
  game behind a pawn wall. Fortress Shogi should feel much more like real shogi.
- **vs. Tsurugi Shogi (v1)**: Tsurugi also had 2 Silvers but only 2 pawns and
  a 1-rank promotion zone. Fortress Shogi has 5 pawns (2.5x more), a 2-rank
  promotion zone, and adds a Lance. The higher pawn count transforms the game
  from open-board chaos into structured positional play.

---

## Comparison Table

| Dimension | A: Compact | B: Full 6x7 | C: Knight | D: Fortress |
|-----------|-----------|-------------|-----------|-------------|
| **Board** | 6x6 (36 sq) | 6x7 (42 sq) | 6x6 (36 sq) | 6x6 (36 sq) |
| **Pieces/side** | 10 | 14 | 11 | 11 |
| **Pawns/side** | 5 | 6 | 5 | 5 |
| **Pawn density** | 5/6 = 83% | 6/6 = 100% | 5/6 = 83% | 5/6 = 83% |
| **Piece types (base)** | 5 | 8 | 6 | 6 |
| **Piece types (total incl. promoted)** | 10 | 15 | 12 | 11 |
| **Hand types** | 5 | 7 | 6 | 5 |
| **Has Knight?** | No | Yes | Yes | No |
| **Has Lance?** | No | Yes | No | Yes |
| **Has Gold?** | Yes | Yes (x2) | Yes | No |
| **Promotion zone** | 2 ranks | 2 ranks | 2 ranks | 2 ranks |
| **Branching factor** | ~38 | ~55 | ~42 | ~40 |
| **Game length** | ~55 ply | ~70 ply | ~50 ply | ~50 ply |
| **State space** | ~10^18 | ~10^26 | ~10^19 | ~10^19 |
| **Game tree** | ~10^42 | ~10^60 | ~10^40 | ~10^40 |
| **1st player advantage** | ~52-54% | ~52-53% | ~53-55% | ~53-55% |
| **Code reuse from MiniShogi** | ~95% | ~85% | ~90% | ~85% |
| **New piece code needed** | None | Knight + Lance | Knight | Lance |
| **Implementation effort** | 1-2 days | 3-5 days | 2-3 days | 2-3 days |

### Pawn Density Comparison with v1 Designs

| Variant | Pawns | Files | Density | Open files at start |
|---------|-------|-------|---------|---------------------|
| MiniShogi (5x5) | 1 | 5 | 20% | 4 |
| Judkins Shogi (6x6) | 1 | 6 | 17% | 5 |
| Hayate v1 (6x6) | 3 | 6 | 50% | 3 |
| Renmei v1 (6x7) | 3 | 6 | 50% | 3 |
| Tsurugi v1 (6x6) | 2 | 6 | 33% | 4 |
| **Compact Shogi v2** | **5** | **6** | **83%** | **1** |
| **Full 6x7 v2** | **6** | **6** | **100%** | **0** |
| **Knight Shogi v2** | **5** | **6** | **83%** | **1** |
| **Fortress Shogi v2** | **5** | **6** | **83%** | **1** |
| Real Shogi (9x9) | 9 | 9 | 100% | 0 |

The v2 designs achieve 83-100% pawn density, comparable to real shogi's 100%.
The v1 designs were at 17-50%, which is fundamentally insufficient for shogi
gameplay.

---

## Comparison to MiniShogi and Judkins Shogi

### MiniShogi (5x5)

MiniShogi is the standard small shogi variant, played on a 5x5 board:

```
     a   b   c   d   e
  +---+---+---+---+---+
5 | K | G | S | B | R |  <- Gote
  +---+---+---+---+---+
4 | . | . | . | . | p |
  +---+---+---+---+---+
3 | . | . | . | . | . |
  +---+---+---+---+---+
2 | P | . | . | . | . |
  +---+---+---+---+---+
1 | r | b | s | g | k |  <- Sente
  +---+---+---+---+---+
```

**1 pawn per side.** This means:
- No pawn wall, no pawn structure, no file-opening strategy.
- Rook and Bishop have full range from move 1.
- Drops dominate the game (especially Rook drops behind enemy lines).
- The game is almost purely tactical, with very little positional depth.
- Nifu is rarely relevant (only 1 pawn means only 1 file is blocked).

MiniShogi is a well-designed game for what it is -- a fast, tactical drop game.
But it does not feel like shogi. It feels like a unique abstract strategy game
that happens to use shogi pieces.

### Judkins Shogi (6x6)

Judkins Shogi is the standard 6x6 shogi variant:

```
     a   b   c   d   e   f
  +---+---+---+---+---+---+
6 | K | G | S | N | B | R |  <- Gote
  +---+---+---+---+---+---+
5 | p | . | . | . | . | . |
  +---+---+---+---+---+---+
4 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
3 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
2 | . | . | . | . | . | P |
  +---+---+---+---+---+---+
1 | r | b | n | s | g | k |  <- Sente
  +---+---+---+---+---+---+
```

**1 pawn per side on a 6x6 board.** All the same problems as MiniShogi, amplified:
- 5 open files (out of 6) from move 1.
- The Rook has nearly the entire board to range across.
- The Knight, while adding tactical interest, operates on a completely open board
  where its forks are devastating but also somewhat random (no structure to
  create patterns).
- The single pawn is almost a curiosity rather than a strategic element.

Judkins has a Knight, which MiniShogi lacks, and this adds genuine tactical
complexity. But the fundamental problem remains: without a pawn wall, the game
does not play like shogi.

### How the v2 Variants Fix These Problems

All four v2 variants address the core issues:

| Problem | MiniShogi/Judkins | v2 Solution |
|---------|-------------------|-------------|
| Open board from move 1 | 4-5 open files | 0-1 open files |
| Rook/Bishop dominate | Full range immediately | Blocked by pawn wall |
| Drops overpowered | Drop Rook anywhere | Must earn open files first |
| No positional play | Pure tactics | Pawn structure decisions |
| Nifu irrelevant | 1 file blocked | 5-6 files blocked |
| Lance useless | No files to charge | Opens files via pawn exchange |
| No opening theory | Few meaningful first moves | Which pawn to push? Which file to open? |
| Short, random games | ~30-40 ply, high variance | ~50-70 ply, structured |

The single most important change is pawn density. Everything else follows from it.

---

## Implementation Recommendations

### Recommended Implementation Order

```
Priority 1:  Compact Shogi (Variant A)
             - Simplest: no new piece types needed
             - 100% code reuse from MiniShogi engine
             - Fast datagen for NNUE training validation
             - Proves the "dense pawn wall" concept works

Priority 2:  Full Shogi 6x7 (Variant B)
             - Requires Knight + Lance implementation
             - Highest complexity and closest to real shogi
             - Best long-term NNUE training target
             - Needs the most training data (~100M+ positions)

Priority 3:  Knight Shogi (Variant C) or Fortress Shogi (Variant D)
             - Choose based on which piece is already implemented:
               * If Knight exists from Judkins: do Knight Shogi
               * If Lance exists from Hayate: do Fortress Shogi
             - Both are interesting tactical variants of Compact Shogi
```

### NNUE Feature Configurations

```python
# Compact Shogi (Variant A)
"compact_shogi": {
    "board_h": 6,
    "board_w": 6,
    "num_piece_types": 10,     # Empty, P, S, G, B, R, K, +P, +S, +B, +R
    "num_pt_no_king": 9,
    "king_id": 6,
    "num_hand_types": 5,       # P, S, G, B, R
    "hand_piece_ids": [1, 2, 3, 4, 5],
    "has_drops": True,
    "perspective": "rotate_180",
}
# HalfKP: 36 * (2 * 9 * 36) = 36 * 648 = 23,328
# + hand features: 2 * 5 * max_count = ~50
# Total: ~23,378 input features
# Params (128 accum): ~3.0M
# Training data needed: 15-40M positions

# Full Shogi 6x7 (Variant B)
"full_shogi_6x7": {
    "board_h": 7,
    "board_w": 6,
    "num_piece_types": 16,     # Empty, P, S, G, B, R, K, N, L, +P, +S, +N, +L, +B, +R
    "num_pt_no_king": 14,
    "king_id": 6,
    "num_hand_types": 7,       # P, S, G, B, R, N, L
    "hand_piece_ids": [1, 2, 3, 4, 5, 7, 8],
    "has_drops": True,
    "perspective": "rotate_180",
}
# HalfKP: 42 * (2 * 14 * 42) = 42 * 1176 = 49,392
# + hand features: 2 * 7 * max_count = ~70
# Total: ~49,462 input features
# Params (128 accum): ~6.3M
# Training data needed: 50-200M positions

# Knight Shogi (Variant C)
"knight_shogi": {
    "board_h": 6,
    "board_w": 6,
    "num_piece_types": 12,     # Empty, P, G, B, R, K, N, +P, +N, +B, +R
    "num_pt_no_king": 10,
    "king_id": 5,
    "num_hand_types": 6,       # P, G, B, R, N (no Silver)
    "hand_piece_ids": [1, 2, 3, 4, 6],
    "has_drops": True,
    "perspective": "rotate_180",
}
# HalfKP: 36 * (2 * 10 * 36) = 36 * 720 = 25,920
# + hand features: 2 * 5 * max_count = ~50  (5 distinct types excluding King)
# Total: ~25,970 input features
# Params (128 accum): ~3.3M
# Training data needed: 20-50M positions

# Fortress Shogi (Variant D)
"fortress_shogi": {
    "board_h": 6,
    "board_w": 6,
    "num_piece_types": 12,     # Empty, P, S, B, R, K, L, +P, +S, +L, +B, +R
    "num_pt_no_king": 10,
    "king_id": 5,
    "num_hand_types": 5,       # P, S, B, R, L (no Gold)
    "hand_piece_ids": [1, 2, 3, 4, 6],
    "has_drops": True,
    "perspective": "rotate_180",
}
# HalfKP: 36 * (2 * 10 * 36) = 36 * 720 = 25,920
# + hand features: 2 * 5 * max_count = ~50
# Total: ~25,970 input features
# Params (128 accum): ~3.3M
# Training data needed: 20-50M positions
```

### Key Insight Preserved

The Corridor Chess design works because it has 5 pawns on 7 files -- dense enough
for structure (71% coverage), with 2 open files for piece play. The same
philosophy applies here:

- **Compact/Knight/Fortress (6x6)**: 5 pawns on 6 files = 83% coverage, 1 open
  file per side. Dense enough for pawn-wall strategy, with just enough opening
  for piece activity. The single open file is on opposite sides for each player
  (rotational symmetry), creating directional tension.
- **Full 6x7**: 6 pawns on 6 files = 100% coverage, 0 open files. Maximum pawn
  density, exactly like real shogi. Players must earn every open file through
  pawn exchanges. This produces the richest strategic play but slower games.

The pawn wall is not a constraint on the game -- it IS the game.
