# Next Variant Deep Dive: Judkins Shogi & Tori Shogi

A visual reference guide for implementing the top two recommended next variants
in the MiniChess engine. Based on analysis from `merged_variant_recommendation.md`
and rules from `seed_variants.md`.

---

## Table of Contents

1. [Judkins Shogi (6x6)](#1-judkins-shogi-6x6)
   - [Rules at a Glance](#11-rules-at-a-glance)
   - [Board Diagram](#12-board-diagram--initial-position)
   - [Piece Movement Reference](#13-piece-movement-reference)
   - [Sample Middle Game](#14-sample-middle-game)
   - [Implementation Plan](#15-implementation-plan)
2. [Tori Shogi (7x7)](#2-tori-shogi-7x7)
   - [Rules at a Glance](#21-rules-at-a-glance)
   - [Board Diagram](#22-board-diagram--initial-position)
   - [Piece Movement Reference](#23-piece-movement-reference)
   - [Sample Middle Game](#24-sample-middle-game)
   - [Implementation Plan](#25-implementation-plan)
3. [Comparison Table](#3-comparison-table--judkins-vs-tori)

---

## 1. Judkins Shogi (6x6)

**Recommendation rank: #1 (Score 9.0/10)**
Standard shogi on 6x6, minus the Lance. The natural evolutionary step from MiniShogi.

### 1.1 Rules at a Glance

| Rule | Detail |
|------|--------|
| **Board** | 6 ranks x 6 files |
| **Pieces per side** | 7 (King, Rook, Bishop, Gold, Silver, Knight, Pawn) |
| **Drops** | Yes -- standard shogi drop rules |
| **Promotion zone** | Last 2 ranks (ranks 5-6 for Sente, ranks 1-2 for Gote) |
| **Promotions** | Rook -> Dragon King, Bishop -> Dragon Horse, Silver/Knight/Pawn -> Gold movement |
| **Drop restrictions** | Nifu (no two unpromoted friendly pawns in same file), uchifuzume (no pawn-drop checkmate), Knight cannot drop on last 2 ranks |
| **Win condition** | Capture the opponent's King |
| **Repetition** | Three-fold repetition handled per standard shogi rules |
| **Avg. game length** | ~40 ply |
| **Branching factor** | ~35 |
| **Game tree complexity** | ~10^32 (unsolved) |

### 1.2 Board Diagram -- Initial Position

```
     a   b   c   d   e   f
  +---+---+---+---+---+---+
6 | K | G | S | N | B | R |  <- Gote (White)
  +---+---+---+---+---+---+
5 | p | . | . | . | . | . |
  +---+---+---+---+---+---+
4 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
3 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
2 | . | . | . | . | . | P |
  +---+---+---+---+---+---+
1 | r | b | n | s | g | k |  <- Sente (Black)
  +---+---+---+---+---+---+

Sente (Black, moves first):
  Rook(a1) Bishop(b1) Knight(c1) Silver(d1) Gold(e1) King(f1)
  Pawn(f2)

Gote (White):
  King(a6) Gold(b6) Silver(c6) Knight(d6) Bishop(e6) Rook(f6)
  Pawn(a5)

Back rank arrangement: K-G-S-N-B-R
Single pawn placed in the file of the King.
```

### 1.3 Piece Movement Reference

All pieces move identically to their standard shogi counterparts.

#### Base Pieces

```
  KING (K/k)                GOLD GENERAL (G/g)         SILVER GENERAL (S/s)
  All 8 directions, 1 sq.   Fwd + sides + diag-fwd     Diag all + fwd

  . . . . .                 . . . . .                  . . . . .
  . x x x .                 . x x x .                  . x . x .
  . x K x .                 . x G x .                  . x S x .
  . x x x .                 . . x . .                  . x . x .
  . . . . .                 . . . . .                  . . . . .


  KNIGHT (N/n)              BISHOP (B/b)               ROOK (R/r)
  Jumps 2-fwd + 1-side      Ranges diagonally          Ranges orthogonally
  (no backward)

  . x . x .                 x . . . x                  . . x . .
  . . . . .                 . x . x .                  . . x . .
  . . N . .                 . . B . .                  x x R x x
  . . . . .                 . x . x .                  . . x . .
  . . . . .                 x . . . x                  . . x . .


  PAWN (P/p)
  1 step forward only

  . . x . .
  . . P . .
  . . . . .
```

#### Promoted Pieces

```
  DRAGON KING (+R)                   DRAGON HORSE (+B)
  Rook + 1-sq diagonal               Bishop + 1-sq orthogonal

  x . x . x                          . . x . .
  . x x x .                          . x x x .
  . x+R x .                          x x+B x x
  . x x x .                          . x x x .
  x . x . x                          . . x . .


  PROMOTED SILVER (+S)   PROMOTED KNIGHT (+N)   PROMOTED PAWN (+P / Tokin)
  All three move like Gold General:

  . x x x .
  . x + x .
  . . x . .
```

#### Promotion Zone Map (Sente perspective)

```
     a   b   c   d   e   f
  +---+---+---+---+---+---+
6 |###|###|###|###|###|###|  <- PROMOTION ZONE (Sente)
  +---+---+---+---+---+---+
5 |###|###|###|###|###|###|  <- PROMOTION ZONE (Sente)
  +---+---+---+---+---+---+
4 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
3 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
2 |###|###|###|###|###|###|  <- PROMOTION ZONE (Gote)
  +---+---+---+---+---+---+
1 |###|###|###|###|###|###|  <- PROMOTION ZONE (Gote)
  +---+---+---+---+---+---+
```

### 1.4 Sample Middle Game

```
     a   b   c   d   e   f       Hands:
  +---+---+---+---+---+---+     Gote: P
6 | K | G | . | . | . | . |
  +---+---+---+---+---+---+     Sente: n, b
5 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
4 | . | . | . | s | . | . |     Sente promoted Bishop (+B)
  +---+---+---+---+---+---+     controls the center from c3.
3 | . | . |+B | . | . | . |     Gote's King is exposed on a6.
  +---+---+---+---+---+---+     Sente holds knight and bishop
2 | . | . | . | . | . | . |     in hand for drop attacks.
  +---+---+---+---+---+---+
1 | . | . | . | . | g | k |
  +---+---+---+---+---+---+

Key themes:
 - Dragon Horse (+B) on c3 dominates the board diagonally + 1-sq orthogonal
 - Sente can drop knight (n) to fork King and Gold
 - Gote has a pawn in hand for defensive drops
 - Silver (s) on d4 probes the promotion zone
```

### 1.5 Implementation Plan

#### 1.5.1 New `config.hpp` Values

```
src/games/judkins/config.hpp

  #define BOARD_H  6
  #define BOARD_W  6

  #define EMPTY     0
  #define PAWN      1
  #define SILVER    2
  #define GOLD      3
  #define BISHOP    4
  #define ROOK      5
  #define KING      6
  #define KNIGHT    7        // NEW -- not in MiniShogi

  #define P_PAWN    8        // promoted pawn   -> Gold movement
  #define P_SILVER  9        // promoted silver -> Gold movement
  #define P_BISHOP  10       // dragon horse    -> Bishop + King
  #define P_ROOK    11       // dragon king     -> Rook + King
  #define P_KNIGHT  12       // promoted knight -> Gold movement   // NEW

  #define NUM_PIECE_TYPES 13  // 0-12 (was 11 in MiniShogi)
  #define NUM_PT_NO_KING  12  // all except king
  #define KING_ID          6
  #define NUM_HAND_TYPES   6  // pawn, silver, gold, bishop, rook, knight (was 5)
```

#### 1.5.2 Piece Movement Generation

| Piece | Status | Notes |
|-------|--------|-------|
| King | **Reuse** | Identical to MiniShogi King |
| Gold | **Reuse** | Identical to MiniShogi Gold |
| Silver | **Reuse** | Identical to MiniShogi Silver |
| Bishop | **Reuse** | Identical to MiniShogi Bishop (ranging diagonal) |
| Rook | **Reuse** | Identical to MiniShogi Rook (ranging orthogonal) |
| Pawn | **Reuse** | Identical to MiniShogi Pawn (1-step forward) |
| Dragon Horse (+B) | **Reuse** | Identical to MiniShogi promoted Bishop |
| Dragon King (+R) | **Reuse** | Identical to MiniShogi promoted Rook |
| Promoted Pawn (+P) | **Reuse** | Gold movement, same as MiniShogi |
| Promoted Silver (+S) | **Reuse** | Gold movement, same as MiniShogi |
| **Knight (N)** | **NEW** | Jump: 2 forward + 1 sideways (2 target squares only, no backward) |
| **Promoted Knight (+N)** | **NEW** | Gold movement (trivial -- same pattern as +P, +S) |

**Summary:** 10 of 12 non-king movement patterns are directly reusable from MiniShogi.
Only the Knight needs a genuinely new move generator (2 target squares per position).
Promoted Knight reuses the Gold movement table.

Knight move generation (pseudocode):
```
// Shogi knight: jumps to (row+2, col+/-1) for Sente
//               jumps to (row-2, col+/-1) for Gote
int knight_targets[2] = { {+2, -1}, {+2, +1} };  // Sente forward
// Flip for Gote: { {-2, -1}, {-2, +1} }
```

#### 1.5.3 Promotion Rules

- Same mechanic as MiniShogi: entering, moving within, or leaving the promotion
  zone allows (or forces) promotion.
- Pawn, Silver, Knight promote to Gold movement. Bishop -> Dragon Horse. Rook -> Dragon King.
- **Forced promotion:** Pawn on last rank must promote. Knight on last 2 ranks must promote
  (a shogi knight on rank 5 or 6 has no legal forward move).

#### 1.5.4 Drop Rules

- Identical to MiniShogi drop rules, extended with Knight:
  - **Nifu:** No two unpromoted friendly Pawns in the same file.
  - **Uchifuzume:** No Pawn drop that delivers immediate checkmate.
  - **Rank restriction (Pawn):** Cannot drop Pawn on the last rank.
  - **Rank restriction (Knight):** Cannot drop Knight on the last 2 ranks (NEW).
- Captured promoted pieces revert to unpromoted form in hand.

#### 1.5.5 NNUE Feature Config

```python
# game_config.py -- add "judkins" entry
"judkins": {
    "board_h": 6,
    "board_w": 6,
    "num_piece_types": 13,      # 0..12
    "num_pt_no_king": 12,
    "king_id": 6,
    "num_hand_types": 6,        # P, S, G, B, R, N
    "hand_piece_ids": [1,2,3,4,5,7],
    "has_drops": True,
    "perspective": "rotate_180",
}

# HalfKP feature space:
#   num_squares       = 6 * 6 = 36
#   num_piece_features = 2 * 12 * 36 = 864
#   HalfKP size       = 36 * 864 = 31,104
#   hand_feature_size = 2 * 6 = 12
#   total_input_size  = 31,116
#   params (128 accum) ~ 4.0M
#   training data needed: 20-60M positions
```

---

## 2. Tori Shogi (7x7)

**Recommendation rank: #2 (Score 8.0/10)**
Bird Shogi -- invented 1799 by Toyota Genryu. Highest strategic ceiling of all candidates.

### 2.1 Rules at a Glance

| Rule | Detail |
|------|--------|
| **Board** | 7 ranks x 7 files |
| **Pieces per side** | 16 (1 Phoenix, 1 Falcon, 2 Cranes, 2 Pheasants, 2 Quails, 8 Swallows) |
| **Royal piece** | Phoenix (equivalent to King) |
| **Drops** | Yes -- with two-swallow rule (max 2 friendly swallows per file) |
| **Promotion zone** | Last 2 ranks |
| **Promotions** | Only 2 types: Swallow -> Goose, Falcon -> Eagle |
| **Drop restrictions** | Two-swallow rule (replaces nifu), no swallow-drop checkmate (like uchifuzume), no swallow drop on last rank |
| **Win condition** | Capture the opponent's Phoenix |
| **Repetition** | Initiator of repeating sequence loses |
| **Avg. game length** | ~60 ply |
| **Branching factor** | ~35-45 |
| **Game tree complexity** | ~10^50 (between checkers and chess -- firmly unsolved) |

### 2.2 Board Diagram -- Initial Position

```
     a   b   c   d   e   f   g
  +----+----+----+----+----+----+----+
7 | RQ | Pt | Cr | Ph | Cr | Pt | LQ |  <- Gote (White)
  +----+----+----+----+----+----+----+
6 |  . |  . |  . | Fa |  . |  . |  . |
  +----+----+----+----+----+----+----+
5 | Sw | Sw | Sw | Sw | Sw | Sw | Sw |
  +----+----+----+----+----+----+----+
4 |  . |  . | sw |  . |  . |  . |  . |
  +----+----+----+----+----+----+----+
3 | sw | sw | sw | sw | sw | sw | sw |
  +----+----+----+----+----+----+----+
2 |  . |  . |  . | fa |  . |  . |  . |
  +----+----+----+----+----+----+----+
1 | lq | pt | cr | ph | cr | pt | rq |  <- Sente (Black)
  +----+----+----+----+----+----+----+

Key:
  ph/Ph = Phoenix (Royal)     fa/Fa = Falcon
  cr/Cr = Crane               pt/Pt = Pheasant
  lq/LQ = Left Quail          rq/RQ = Right Quail
  sw/Sw = Swallow
  lowercase = Sente (Black)   UPPERCASE = Gote (White)

Sente: lq(a1) pt(b1) cr(c1) ph(d1) cr(e1) pt(f1) rq(g1)
       fa(d2)
       sw(a3-g3), sw(c4)  -- 8 swallows total

Gote:  RQ(a7) Pt(b7) Cr(c7) Ph(d7) Cr(e7) Pt(f7) LQ(g7)
       Fa(d6)
       Sw(a5-g5)           -- 7 swallows on rank 5 + implicit 8th
```

### 2.3 Piece Movement Reference

#### Base Pieces

```
  PHOENIX (Royal)                     FALCON
  1 step in any direction             1 step in any direction
  (identical to King)                 EXCEPT straight backward

  . . . . .                           . . . . .
  . x x x .                           . x x x .
  . x P x .                           . x F x .
  . x x x .                           . x . x .
  . . . . .                           . . . . .


  CRANE                               SWALLOW
  Forward, backward, all 4            1 step forward only
  diagonals. No sideways.             (like a Pawn)

  . . . . .                           . . . . .
  . x . x .                           . . x . .
  . x C x .                           . . S . .
  . x . x .                           . . . . .
  . . . . .                           . . . . .
```

```
  PHEASANT
  Jumps exactly 2 squares forward (leap -- cannot be blocked),
  OR steps 1 square diagonally backward.

  . . J . .        J = jump target (2 squares forward, non-blocking leap)
  . . . . .        The square between is jumped over.
  . . H . .
  . x . x .        x = 1-step diagonal backward
  . . . . .
```

```
  LEFT QUAIL                          RIGHT QUAIL
  Ranges forward (straight),          Ranges forward (straight),
  ranges diag. backward-right,        ranges diag. backward-left,
  steps 1 diag. backward-left.        steps 1 diag. backward-right.

  . . | . .                           . . | . .
  . . | . .                           . . | . .
  . . Q . .                           . . Q . .
  x . . . \                           / . . . x
  . . . . .\                         /. . . . .

  | = ranges any number               | = ranges any number
  \ = ranges any number               / = ranges any number
  x = 1-step only                     x = 1-step only

  (mirrors of each other)             (mirrors of each other)
```

#### Promoted Pieces

```
  GOOSE (promoted Swallow)
  Jumps exactly 2 squares diagonally forward (both directions),
  OR jumps exactly 2 squares straight backward.
  All are non-blocking leaps.

  J . . . J        J = jump-to squares (2 diag-forward)
  . . . . .
  . . G . .
  . . . . .
  . . J . .        J = jump-to square (2 straight backward)
```

```
  EAGLE (promoted Falcon)
  The most powerful piece in Tori Shogi. Compound movement:
  1) Ranges any number of squares diagonally forward (both directions)
  2) Ranges any number of squares straight backward
  3) Steps 1 square in any of the 8 directions (like a King)
  4) Steps up to 2 squares diagonally backward (not a jump -- blockable)

  \ . | . /        \ / = ranges diagonally forward (any distance)
  .\.x./.            | = 1-step forward (king-like)
  x x E x x         x = 1-step sideways (king-like)
  .x.x.x.         .x. = 1-step diag-backward + potential 2nd step
  x . x . x         x at corners = 2-step diagonal backward (blockable)
                     | below = ranges straight backward (any distance)
                     (continued downward)

  Full movement map (7x7 view, Eagle at center):

         col: -3  -2  -1   0  +1  +2  +3
  row +3:      .    .    \   |   /    .   .     <- ranges diag-fwd & fwd
  row +2:      .    .    .\  |  /.    .   .
  row +1:      .    .    .\ x|x /.    .   .     <- 1-step fwd + diag-fwd range
  row  0:      .    .    x x E x x    .   .     <- 1-step sideways
  row -1:      .    .    x  x|x  x    .   .     <- 1-step + 2-step diag-back
  row -2:      .    .   x    |    x   .   .     <- 2-step diag-back (blockable)
  row -3:      .    .    .   |   .    .   .     <- ranges straight backward
```

#### All 9 Piece Types at a Glance

```
  +----------+----+----+----+----+----+----+----+----+----+
  |          | Ph | Fa | Cr | Pt | LQ | RQ | Sw | Go | Ea |
  +----------+----+----+----+----+----+----+----+----+----+
  | Fwd      |  1 |  1 |  1 | J2 |  R |  R |  1 |  . |  1 |
  | Fwd-L    |  1 |  1 |  1 |  . |  . |  . |  . | J2 |  R |
  | Fwd-R    |  1 |  1 |  1 |  . |  . |  . |  . | J2 |  R |
  | Left     |  1 |  1 |  . |  . |  . |  . |  . |  . |  1 |
  | Right    |  1 |  1 |  . |  . |  . |  . |  . |  . |  1 |
  | Back     |  1 |  . |  1 |  . |  . |  . |  . | J2 |  R |
  | Back-L   |  1 |  1 |  1 |  1 |  1 |  R |  . |  . |  2 |
  | Back-R   |  1 |  1 |  1 |  1 |  R |  1 |  . |  . |  2 |
  +----------+----+----+----+----+----+----+----+----+----+

  Legend:
    1  = 1-step        2  = up to 2 steps (blockable)
    R  = ranges (any)  J2 = jump exactly 2 (non-blocking leap)
    .  = cannot move
```

### 2.4 Sample Middle Game

```
     a   b   c   d   e   f   g       Hands:
  +----+----+----+----+----+----+----+
7 |  . |  . | Cr | Ph |  . | Pt | LQ |  Gote in hand: sw sw
  +----+----+----+----+----+----+----+
6 |  . |  . |  . |  . |  . |  . |  . |
  +----+----+----+----+----+----+----+
5 |  . | Sw |  . | Sw | Sw |  . |  . |
  +----+----+----+----+----+----+----+
4 |  . |  . |  . | sw |  . | Go |  . |  Go = Goose (promoted Swallow)
  +----+----+----+----+----+----+----+
3 | sw | sw |  . |  . | sw |  . |  . |
  +----+----+----+----+----+----+----+
2 |  . |  . |  . | fa |  . |  . |  . |
  +----+----+----+----+----+----+----+
1 | lq | pt | cr | ph |  . |  . | rq |  Sente in hand: Sw Pt
  +----+----+----+----+----+----+----+

Key themes:
 - Falcon (fa) on d2 is Sente's key attacking piece -- promoting it to
   Eagle would be decisive. Sente aims to advance it into ranks 6-7.
 - Goose (Go) on f4 controls jump squares f6, d6, and f2 --
   restricting both the Gote Falcon and Sente's back rank.
 - Gote holds 2 swallows for drops to reinforce the swallow wall
   or create defensive barriers.
 - Sente holds a Swallow and Pheasant for drop attacks against
   the exposed Gote Phoenix on d7.
 - The asymmetric quails (lq on a1, LQ on g7) create opposite-side
   pressure along diagonals and files.
```

### 2.5 Implementation Plan

#### 2.5.1 New `config.hpp` Values

```
src/games/tori/config.hpp

  #define BOARD_H  7
  #define BOARD_W  7

  #define EMPTY       0
  #define SWALLOW     1     // Pawn equivalent
  #define CRANE       2
  #define PHEASANT    3     // Jumper -- new movement class
  #define LEFT_QUAIL  4     // Asymmetric ranger -- new
  #define RIGHT_QUAIL 5     // Asymmetric ranger -- new
  #define FALCON      6
  #define PHOENIX     7     // Royal piece (= King)

  #define GOOSE       8     // Promoted Swallow -- jumper
  #define EAGLE       9     // Promoted Falcon -- compound ranger

  #define NUM_PIECE_TYPES 10   // 0-9
  #define NUM_PT_NO_KING   8   // all except Phoenix
  #define KING_ID          7   // Phoenix is the royal piece
  #define NUM_HAND_TYPES   6   // Swallow, Crane, Pheasant, LQ, RQ, Falcon
                               // (Goose reverts to Swallow when captured;
                               //  Eagle reverts to Falcon when captured)
```

#### 2.5.2 Piece Movement Generation

| Piece | Status | Notes |
|-------|--------|-------|
| Phoenix | **Reuse** | Same as King (1-step all 8 directions) |
| Swallow | **Reuse** | Same as Pawn (1-step forward) |
| Crane | **Adapt** | Subset of King -- fwd, back, all 4 diagonals (no sideways). Minor table edit. |
| Falcon | **Adapt** | Subset of King -- all directions except straight back. Minor table edit. |
| Pheasant | **NEW** | Jump-2-forward (non-blocking leap, new class) + 1-step diag-backward. Two distinct movement components. |
| Left Quail | **NEW** | Range-forward + range-diag-back-right + 1-step-diag-back-left. Asymmetric ranging with mixed step/range. |
| Right Quail | **NEW** | Mirror of Left Quail: range-forward + range-diag-back-left + 1-step-diag-back-right. |
| Goose | **NEW** | Jump-2-diag-forward (both) + jump-2-straight-back. All non-blocking leaps. New movement class. |
| Eagle | **NEW** | Compound: range-diag-fwd + range-straight-back + 1-step-all-8 + up-to-2-diag-back (blockable). Most complex piece. |

**Summary:** 2 pieces directly reusable (Phoenix, Swallow), 2 adaptable with minor
table changes (Crane, Falcon), 5 require genuinely new movement generators.

New movement classes needed:
```
1. JUMP_2_FORWARD       -- Pheasant (non-blocking leap over 1 square)
2. ASYMMETRIC_RANGE     -- Left/Right Quail (directional range + step mix)
3. JUMP_2_DIAGONAL_FWD  -- Goose (non-blocking diagonal leap)
4. JUMP_2_BACKWARD      -- Goose (non-blocking straight backward leap)
5. COMPOUND_EAGLE       -- Eagle (range + step + limited-range combined)
```

#### 2.5.3 Promotion Rules

Only 2 promotions exist (simpler than MiniShogi):

| Piece | Promotes To | Condition |
|-------|-------------|-----------|
| Swallow | Goose | Mandatory when entering/within last 2 ranks |
| Falcon | Eagle | Mandatory when entering/within last 2 ranks |

- All other pieces (Crane, Pheasant, Left Quail, Right Quail) never promote.
- Captured promoted pieces (Goose, Eagle) revert to unpromoted form (Swallow, Falcon) in hand.

#### 2.5.4 Drop Rules

| Rule | Detail |
|------|--------|
| **Two-Swallow Rule** | A file may contain at most 2 friendly unpromoted Swallows. (Replaces the nifu one-pawn rule. More permissive.) |
| **Swallow-drop checkmate** | Dropping a Swallow to deliver immediate checkmate is illegal (same logic as uchifuzume). |
| **Rank restriction** | Swallow cannot be dropped on the last rank (it would have no legal move). |
| **Reversion on capture** | Goose -> Swallow, Eagle -> Falcon when captured. Dropped in unpromoted form. |
| **Droppable types** | Swallow, Crane, Pheasant, Left Quail, Right Quail, Falcon (6 types). |

Implementation notes:
- The existing nifu check (`count pawns in file == 1`) becomes `count swallows in file >= 2`.
- The uchifuzume check generalizes directly (swap "pawn" for "swallow").
- Left Quail and Right Quail maintain their identity when captured -- they are distinct piece types.

#### 2.5.5 NNUE Feature Config

```python
# game_config.py -- add "tori" entry
"tori": {
    "board_h": 7,
    "board_w": 7,
    "num_piece_types": 10,      # 0..9
    "num_pt_no_king": 8,
    "king_id": 7,               # Phoenix
    "num_hand_types": 6,        # Sw, Cr, Pt, LQ, RQ, Fa
    "hand_piece_ids": [1,2,3,4,5,6],
    "has_drops": True,
    "perspective": "rotate_180",
}

# HalfKP feature space:
#   num_squares        = 7 * 7 = 49
#   num_piece_features = 2 * 8 * 49 = 784
#   HalfKP size        = 49 * 784 = 38,416
#   hand_feature_size  = 2 * 6 = 12
#   total_input_size   = 38,428
#   params (128 accum) ~ 4.9M
#   max active features ~ 35
#   sparse EmbeddingBag: strongly recommended
#   training data needed: 50-200M positions
```

---

## 3. Comparison Table -- Judkins vs Tori

| Dimension | Judkins Shogi (6x6) | Tori Shogi (7x7) |
|-----------|--------------------|--------------------|
| **Board size** | 6x6 (36 squares) | 7x7 (49 squares) |
| **Pieces per side** | 7 | 16 |
| **Piece types (total)** | 13 (incl. promoted) | 10 (incl. promoted) |
| **Royal piece** | King | Phoenix |
| **Drops** | Yes | Yes |
| **Promotion zone** | Last 2 ranks | Last 2 ranks |
| **Promoting pieces** | 5 (P, S, N, B, R) | 2 (Swallow, Falcon) |
| **Drop restrictions** | Nifu + uchifuzume + rank | Two-swallow + sw-checkmate + rank |
| **New piece types to code** | 1 (Knight) | 5 (Pheasant, LQ, RQ, Goose, Eagle) |
| **New movement classes** | 0 (Knight jump exists in chess) | 4 (jump-2-fwd, asym-range, jump-2-diag, compound) |
| **Code reuse from MiniShogi** | ~85-90% | ~40-60% |
| **Estimated new lines** | ~200-400 | ~800-1200 |
| **Implementation time** | 1-2 days | 4-7 days |
| | | |
| **HalfKP input size** | 31,116 | 38,428 |
| **NNUE params (128 accum)** | ~4.0M | ~4.9M |
| **Training data needed** | 20-60M positions | 50-200M positions |
| **Datagen speed (vs MiniShogi)** | ~1.5x slower | ~3-5x slower |
| **Max active features** | ~26 | ~35 |
| | | |
| **Game tree complexity** | ~10^32 | ~10^50 |
| **Avg. branching factor** | ~35 | ~35-45 |
| **Avg. game length** | ~40 ply | ~60 ply |
| **Status** | Unsolved | Firmly unsolved |
| | | |
| **NNUE fit** | Excellent | Excellent |
| **NNUE value-add** | Medium-high | High (best of all candidates) |
| **Training feasibility** | Excellent | Good |
| **Overall score** | **9.0 / 10** | **8.0 / 10** |
| | | |
| **Best for** | Fastest path to a working NNUE shogi variant. Natural MiniShogi successor. | Maximum strategic depth and NNUE payoff. Ideal second variant after Judkins is stable. |
| **Fairy-Stockfish** | Built-in variant | Built-in variant |

### Recommended Sequence

```
Phase 1:  Implement Judkins Shogi          (~1-2 days)
          Generate 30M training positions   (~3 hours)
          Train NNUE (128 accum)            (~2 hours GPU)
          Validate vs handcrafted eval      (self-play tournament)

Phase 2:  Implement Tori Shogi             (~4-7 days)
          Generate 100M training positions  (~8-16 hours)
          Train NNUE (128 accum)            (~4 hours GPU)
          Validate vs handcrafted eval      (self-play tournament)
```
