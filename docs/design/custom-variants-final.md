# Custom Variants Specification: Corridor Chess & Compact Shogi

Two custom game variants designed for the MiniChess engine framework. Each
variant is specified to the level of detail required for a complete, correct
implementation within the existing `BaseState` interface.

---

## Table of Contents

1. [Variant 1: Corridor Chess (6x7)](#variant-1-corridor-chess-6x7)
2. [Variant 2: Compact Shogi (6x6)](#variant-2-compact-shogi-6x6)
3. [Comparison Table](#comparison-table)
4. [NNUE Training Considerations](#nnue-training-considerations)
5. [Implementation Effort Estimate](#implementation-effort-estimate)

---

## Variant 1: Corridor Chess (6x7)

### Overview

**Corridor Chess** is a chess variant played on a 6-file, 7-rank rectangular
board. The elongated "corridor" shape creates a deeper battlefield where
pawns must traverse 5 ranks to promote and the 3-rank buffer zone between
armies reduces first-mover advantage. All six standard chess piece types are
present. Rules are simplified: no castling, no en passant, no pawn
double-move.

### Board Dimensions

- **Files**: 6 (a through f)
- **Ranks**: 7 (1 through 7)
- **Total squares**: 42

### Piece Set

Each side has **11 pieces**:

| Piece  | Count | Piece ID | Value (MVV-LVA) |
|--------|-------|----------|------------------|
| Pawn   | 5     | 1        | 2                |
| Rook   | 1     | 2        | 6                |
| Knight | 1     | 3        | 7                |
| Bishop | 1     | 4        | 8                |
| Queen  | 1     | 5        | 20               |
| King   | 1     | 6        | 100              |

**Total**: 22 pieces on the board at the start.

### Initial Position

```
     a   b   c   d   e   f
  +---+---+---+---+---+---+
7 | r | n | b | q | k | . |  <- Black
  +---+---+---+---+---+---+
6 | p | p | p | p | p | . |
  +---+---+---+---+---+---+
5 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
4 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
3 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
2 | . | P | P | P | P | P |
  +---+---+---+---+---+---+
1 | . | K | Q | B | N | R |  <- White
  +---+---+---+---+---+---+
     a   b   c   d   e   f
```

**White pieces**: King(b1), Queen(c1), Bishop(d1), Knight(e1), Rook(f1),
Pawns on b2, c2, d2, e2, f2.

**Black pieces**: Rook(a7), Knight(b7), Bishop(c7), Queen(d7), King(e7),
Pawns on a6, b6, c6, d6, e6.

**Symmetry**: The position has **180-degree rotational symmetry** about the
board center (between d3 and c5). White occupies files b-f on ranks 1-2;
Black occupies files a-e on ranks 6-7. Every structural advantage White has
on one side, Black has on the opposite side.

### Complete Rules

#### Piece Movement (Standard Chess)

| Piece  | Movement |
|--------|----------|
| King   | One square in any direction (8 directions). |
| Queen  | Any number of squares orthogonally or diagonally. |
| Rook   | Any number of squares orthogonally. |
| Bishop | Any number of squares diagonally. |
| Knight | L-shape: 2 squares in one direction + 1 square perpendicular. Jumps over pieces. |
| Pawn   | Moves: one square forward. Captures: one square diagonally forward. |

All sliding pieces (Queen, Rook, Bishop) are blocked by the first piece in
their path (standard chess sliding rules).

#### Capturing

A piece captures by moving to a square occupied by an opponent's piece.
The captured piece is removed from the game permanently.

#### Pawn Rules

- Pawns move **one square forward only** (no double-move from starting rank).
- Pawns capture **one square diagonally forward** (standard chess).
- **No en passant**.

#### Promotion

When a pawn reaches the **last rank** (rank 7 for White, rank 1 for Black),
it **must** promote. The player chooses one of:

- Queen
- Rook
- Bishop
- Knight

Promotion is unrestricted: any piece type is always available regardless
of what pieces remain on the board.

#### Castling

**No castling**. The king has no castling rights.

#### Win Condition

Win by **capturing the opponent's king**. This is consistent with the
MiniChess engine's existing win-condition model (no checkmate detection
required; a player who leaves their king in capture is simply lost on the
next move).

Note: The engine should detect checkmate (no legal moves while in check)
as an immediate loss for the side in check, since the king capture would
happen on the very next move.

#### Draw Conditions

- **Move limit**: The game is drawn after 120 ply (MAX_STEP = 120). The
  longer board justifies a higher limit than the 100-ply limit used for
  6x6 chess variants.
- No stalemate rule is needed under the king-capture model (a player with
  no legal moves simply loses because they cannot escape capture).

### Implementation Notes

#### config.hpp Values

```cpp
#define BOARD_H 7
#define BOARD_W 6
#define MAX_STEP 120
#define USE_BITBOARD          // optional, 42 squares fits in uint64_t

#define NUM_PIECE_TYPES 6     // EMPTY=0, PAWN=1, ROOK=2, KNIGHT=3,
                              // BISHOP=4, QUEEN=5, KING=6
#define NUM_PT_NO_KING  5
#define KING_ID         6

#define NUM_PIECE_VALS 7
static const int PIECE_VAL[NUM_PIECE_VALS] = {
    /* EMPTY */ 0, /* PAWN */ 2, /* ROOK */ 6, /* KNIGHT */ 7,
    /* BISHOP */ 8, /* QUEEN */ 20, /* KING */ 100,
};
```

#### Piece Counts (for Board Initialization)

| Piece    | White position          | Black position          |
|----------|-------------------------|-------------------------|
| King     | b1                      | e7                      |
| Queen    | c1                      | d7                      |
| Bishop   | d1                      | c7                      |
| Knight   | e1                      | b7                      |
| Rook     | f1                      | a7                      |
| Pawn x5  | b2, c2, d2, e2, f2     | a6, b6, c6, d6, e6     |

Initial board array (player 0 = White, stored with rank 0 = rank 1):

```cpp
// Player 0 (White)
{0,0,0,0,0,0},  // rank 1: .  K  Q  B  N  R  (indices shifted: col 0=a)
{0,1,1,1,1,1},  // rank 2: .  P  P  P  P  P
{0,0,0,0,0,0},  // rank 3
{0,0,0,0,0,0},  // rank 4
{0,0,0,0,0,0},  // rank 5
{0,0,0,0,0,0},  // rank 6
{0,0,0,0,0,0},  // rank 7

// But the back rank pieces are:
// board[0][0] = {0, KING, QUEEN, BISHOP, KNIGHT, ROOK}
// board[0][1] = {0, PAWN, PAWN, PAWN, PAWN, PAWN}
```

Player 1 (Black) is stored as a 180-degree rotation:

```cpp
// board[1][0] = {ROOK, KNIGHT, BISHOP, QUEEN, KING, 0}
// board[1][1] = {PAWN, PAWN, PAWN, PAWN, PAWN, 0}
```

#### HalfKP Feature Size

Using the formula from `game_config.py`:

```
num_squares       = 7 * 6 = 42
num_piece_features = 2 * NUM_PT_NO_KING * num_squares
                   = 2 * 5 * 42 = 420
halfkp_size       = num_squares * num_piece_features
                   = 42 * 420 = 17,640
hand_feature_size = 0          (no drops)
total_feature_size = 17,640
```

#### game_config.py Entry

```python
"corridor_chess": {
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

### Complexity Estimate

| Metric                   | Estimate   |
|--------------------------|------------|
| Pieces on board (start)  | 22 (11 per side) |
| Average branching factor | ~30        |
| Average game length      | ~60 ply    |
| State space (positions)  | ~10^19     |
| Game tree complexity     | ~10^44     |

**Reasoning**: 42 squares with 22 pieces provides substantially more
positions than 6x6 boards (36 squares). The 5 pawns per side create
meaningful pawn structure. The extra rank increases average game length to
~60 ply (vs. ~50 for 6x6 variants), and the branching factor of ~30
reflects full chess piece mobility on a mid-sized board. The 3-rank buffer
zone between armies lengthens the opening phase.

---

## Variant 2: Compact Shogi (6x6)

### Overview

**Compact Shogi** is a 6x6 shogi variant with full drop mechanics,
6 piece types (plus promoted forms), and a complete pawn wall. It is
designed as a balanced, strategically rich shogi experience that is larger
than MiniShogi (5x5) but maintains fast game completion for efficient
selfplay data generation. The addition of the **Lance** piece and a full
6-pawn front distinguishes it from existing 6x6 shogi variants like
Judkins Shogi.

### Board Dimensions

- **Files**: 6 (a through f)
- **Ranks**: 6 (1 through 6)
- **Total squares**: 36

### Piece Set

Each side has **12 pieces on board**:

| Piece   | Count | Base ID | Promoted Form     | Promoted ID |
|---------|-------|---------|-------------------|-------------|
| King    | 1     | 7       | -- (no promotion) | --          |
| Gold    | 1     | 3       | -- (no promotion) | --          |
| Silver  | 1     | 2       | Promoted Silver   | 9           |
| Lance   | 1     | 4       | Promoted Lance    | 10          |
| Rook    | 1     | 6       | Dragon            | 12          |
| Bishop  | 1     | 5       | Horse             | 11          |
| Pawn    | 6     | 1       | Tokin             | 8           |

**Total**: 24 pieces on the board at the start (12 per side).

**Full piece type ID table**:

| ID | Piece           | Moves like                    |
|----|-----------------|-------------------------------|
| 0  | EMPTY           | --                            |
| 1  | PAWN            | One step forward              |
| 2  | SILVER          | Forward + diagonals (5 dirs)  |
| 3  | GOLD            | All except diagonal-back (6 dirs) |
| 4  | LANCE           | Any distance forward (forward-Rook) |
| 5  | BISHOP          | Any distance diagonally       |
| 6  | ROOK            | Any distance orthogonally     |
| 7  | KING            | One step any direction (8 dirs) |
| 8  | P_PAWN (Tokin)  | Moves like Gold               |
| 9  | P_SILVER        | Moves like Gold               |
| 10 | P_LANCE         | Moves like Gold               |
| 11 | P_BISHOP (Horse)| Bishop + one step orthogonally |
| 12 | P_ROOK (Dragon) | Rook + one step diagonally    |

### Initial Position

**Sente (Black, moves first) perspective -- standard display**:

```
     a   b   c   d   e   f
  +---+---+---+---+---+---+
6 | b | r | l | s | g | k |  <- Gote (White)
  +---+---+---+---+---+---+
5 | p | p | p | p | p | p |
  +---+---+---+---+---+---+
4 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
3 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
2 | P | P | P | P | P | P |
  +---+---+---+---+---+---+
1 | K | G | S | L | R | B |  <- Sente (Black)
  +---+---+---+---+---+---+
     a   b   c   d   e   f
```

**Compact notation**:

```
  a b c d e f
6 b r l s g k   <- Gote
5 p p p p p p
4 . . . . . .
3 . . . . . .
2 P P P P P P
1 K G S L R B   <- Sente
```

  a b c d e f
7 r b n . q k
6 p p p p . b
5 . . . . p p
4 . . . . . .
3 P P . . . .
2 B . P P P P
1 K Q . N B R

**Sente (Black)**: King(a1), Gold(b1), Silver(c1), Lance(d1), Rook(e1),
Bishop(f1), Pawns a2 through f2.

**Gote (White)**: Bishop(a6), Rook(b6), Lance(c6), Silver(d6), Gold(e6),
King(f6), Pawns a5 through f5.

**Symmetry**: 180-degree rotational symmetry about the board center. Every
piece placement for Sente on square (r, c) has a matching Gote piece on
square (7-r, 7-c) using 1-indexed coordinates.

### Design Rationale

- **King in corner (a1/f6)**: Shogi-style "pre-castled" position. The king
  is naturally protected on two sides by the board edge.
- **Gold adjacent to king**: Provides immediate defensive coverage. The
  Gold on b1 shields the King on a1.
- **Rook far from king**: The Rook on e1 is on the opposite wing, creating
  an attacking formation. This mirrors shogi strategy where the rook-side
  attacks and the king-side defends.
- **Full pawn wall (6 pawns on 6 files)**: Creates a genuine shogi feel
  with pawn structure play. Every file is contested. The nifu rule becomes
  meaningful because all 6 files start occupied.
- **Lance included**: The Lance is a distinctive shogi piece not found in
  Judkins Shogi. Its forward-only ranging movement creates asymmetric
  attack patterns and interesting drop decisions.

### Complete Rules

#### Piece Movement

**Base pieces**:

```
PAWN (P):               SILVER (S):            GOLD (G):
  . X .                   X . X                  X X X
  . P .                   . S .                  X G X
  . . .                   X . X                  . X .

  Moves one step         Moves one step         Moves one step in
  straight forward.      forward, or one step   all directions except
                         diagonally (any).      diagonally backward.
                         (5 directions)         (6 directions)
```

```
LANCE (L):              KING (K):
  . | .                   X X X
  . | .                   X K X
  . L .                   X X X
  . . .
                          Moves one step in
  Moves any number of     any of 8 directions.
  squares straight
  forward (like a
  forward-only Rook).
  Blocked by first
  piece in path.
```

```
BISHOP (B):             ROOK (R):
  \ . /                   . | .
  . B .                   - R -
  / . \                   . | .

  Any number of           Any number of squares
  squares diagonally.     orthogonally. Blocked
  Blocked by first        by first piece in
  piece in path.          path.
```

**Promoted pieces**:

```
TOKIN (+P):             PROMOTED SILVER (+S):   PROMOTED LANCE (+L):
  X X X                   X X X                   X X X
  X +P X                  X +S X                  X +L X
  . X .                   . X .                   . X .

  All three promoted pieces move exactly like Gold.
```

```
HORSE (+B):                    DRAGON (+R):
  \ . . . /                      . . | . .
  . \ o / .                      . o | o .
  . o +B o .                     - - +R - -
  . / o \ .                      . o | o .
  / . . . \                      . . | . .

  Diagonal slides (\/)            Orthogonal slides (| -)
  + one step orthogonal (o).      + one step diagonal (o).
```

#### Capturing and Drops (Shogi Rules)

1. **Capture**: When a piece moves to a square occupied by an opponent's
   piece, the opponent's piece is captured. It is **removed from the board**,
   **reverts to its unpromoted form**, and is placed in the capturing
   player's **hand**.

2. **Drop**: Instead of moving a piece on the board, a player may place
   (drop) a piece from their hand onto any empty square, subject to
   restrictions (see below). Dropped pieces are always in unpromoted form.

3. A player may choose to either move a board piece or drop a hand piece
   on each turn (not both).

#### Promotion Zone

```
     a   b   c   d   e   f
  +---+---+---+---+---+---+
6 |###|###|###|###|###|###|  <- Sente's promotion zone (ranks 5-6)
  +---+---+---+---+---+---+
5 |###|###|###|###|###|###|
  +---+---+---+---+---+---+
4 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
3 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
2 |###|###|###|###|###|###|  <- Gote's promotion zone (ranks 1-2)
  +---+---+---+---+---+---+
1 |###|###|###|###|###|###|
  +---+---+---+---+---+---+
```

- **Sente's promotion zone**: ranks 5 and 6 (last 2 ranks).
- **Gote's promotion zone**: ranks 1 and 2 (last 2 ranks).

A piece may promote when:
- It **enters** the promotion zone (moves from outside to inside).
- It **moves within** the promotion zone (both origin and destination are
  inside).
- It **leaves** the promotion zone (moves from inside to outside).

Promotion is **optional** in all these cases, EXCEPT:
- **Pawn on the last rank**: must promote (no legal forward move otherwise).
- **Lance on the last rank**: must promote (no legal forward move otherwise).

#### Promotion Table

| Base Piece | Promoted Form    | Promoted Movement |
|------------|------------------|-------------------|
| Pawn       | Tokin (+P)       | Gold              |
| Silver     | Prom. Silver (+S)| Gold              |
| Lance      | Prom. Lance (+L) | Gold              |
| Bishop     | Horse (+B)       | Bishop + 1-step orthogonal |
| Rook       | Dragon (+R)      | Rook + 1-step diagonal |
| Gold       | -- (cannot)      | --                |
| King       | -- (cannot)      | --                |

#### Drop Restrictions

| Rule | Description |
|------|-------------|
| **Nifu** (two-pawn) | Cannot drop an unpromoted Pawn on a file that already contains a friendly unpromoted Pawn. |
| **Last-rank Pawn** | Cannot drop a Pawn on the last rank (rank 6 for Sente, rank 1 for Gote) because it would have no legal move. |
| **Last-rank Lance** | Cannot drop a Lance on the last rank for the same reason. |
| **Pawn-drop checkmate** | Cannot drop a Pawn to deliver immediate checkmate (uchifuzume). A Pawn drop that gives check is legal only if the opponent has a legal response. |
| **Empty square** | Drops are only on empty squares. |

**Hand piece types** (6 droppable types):

| Index | Piece  |
|-------|--------|
| 1     | Pawn   |
| 2     | Silver |
| 3     | Gold   |
| 4     | Lance  |
| 5     | Bishop |
| 6     | Rook   |

When a promoted piece is captured, it reverts to its base type before
entering the captor's hand. For example, a captured Horse (+B) becomes a
Bishop in the captor's hand.

#### Win Condition

Win by **capturing the opponent's King**. Consistent with the engine's
existing model. A player who leaves their king in a position where it can
be captured loses on the opponent's next move.

#### Draw Conditions

- **Move limit**: Draw after 200 ply (MAX_STEP = 200).
- **Repetition (sennichite)**: A position that occurs 4 times with the
  same side to move is a draw. Hand contents and board position must both
  match for repetition detection.

### Piece Movement Diagrams (All Types)

The diagrams below use the following legend:
- Capital letter = the piece itself
- `X` = squares the piece can move to (one step)
- `|`, `-`, `\`, `/` = ranging movement (slides until blocked)
- `.` = square the piece cannot reach

#### Pawn

```
. X .
. P .
. . .
```

Forward one step only. Captures the same way it moves (unlike chess).

#### Silver

```
X . X
. S .
X . X
```

Wait -- to be precise, Silver moves to 5 squares:

```
X X X
. S .
X . X
```

One step to: forward-left, forward, forward-right, back-left, back-right.
(All diagonals plus straight forward.)

#### Gold

```
X X X
X G X
. X .
```

One step to: forward-left, forward, forward-right, left, right, back.
(All directions except diagonal-backward.)

#### Lance

```
. | .
. | .
. | .
. L .
. . .
```

Slides any number of squares straight forward. Cannot move backward,
sideways, or diagonally. Blocked by the first piece in its path (captures
it if enemy, stops before it if friendly).

#### Bishop

```
\ . . . /
. \ . / .
. . B . .
. / . \ .
/ . . . \
```

Slides any number of squares along any diagonal. Blocked by first piece
in each direction.

#### Rook

```
. . | . .
. . | . .
- - R - -
. . | . .
. . | . .
```

Slides any number of squares along any orthogonal (row or column). Blocked
by first piece in each direction.

#### King

```
X X X
X K X
X X X
```

One step in any of the 8 directions. The King cannot move into a square
attacked by an opponent's piece.

#### Tokin (+P), Promoted Silver (+S), Promoted Lance (+L)

All three move identically to Gold:

```
X X X
X * X
. X .
```

#### Horse (+B) -- Promoted Bishop

```
\ . . . /
. \ o / .
. o +B o .
. / o \ .
/ . . . \
```

Diagonal slides (`\ /`) + one step orthogonal (`o`).

#### Dragon (+R) -- Promoted Rook

```
. . | . .
. o | o .
- - +R - -
. o | o .
. . | . .
```

Orthogonal slides (`| -`) + one step diagonal (`o`).

### Implementation Notes

#### config.hpp Values

```cpp
#pragma once
#include "../../config.hpp"

#ifndef BOARD_H
#define BOARD_H 6
#endif
#ifndef BOARD_W
#define BOARD_W 6
#endif

#define MAX_STEP 200

/* Base piece types */
#define EMPTY    0
#define PAWN     1
#define SILVER   2
#define GOLD     3
#define LANCE    4
#define BISHOP   5
#define ROOK     6
#define KING     7

/* Promoted pieces */
#define P_PAWN    8   /* Tokin: moves like Gold */
#define P_SILVER  9   /* Promoted Silver: moves like Gold */
#define P_LANCE  10   /* Promoted Lance: moves like Gold */
#define P_BISHOP 11   /* Horse: Bishop + 1-step orthogonal */
#define P_ROOK   12   /* Dragon: Rook + 1-step diagonal */

#define NUM_PIECE_TYPES 13  /* 0-12 inclusive */
#define NUM_PT_NO_KING  12  /* all types except KING (0 excluded, 7=KING excluded) */
#define KING_ID          7
#define NUM_HAND_TYPES   6  /* Pawn, Silver, Gold, Lance, Bishop, Rook (indices 1-6) */

#define NNUE_FILE "models/nnue.bin"

/* Drop moves use sentinel row = BOARD_H in the from-point */
#define DROP_ROW BOARD_H

/* Piece display */
#define PIECE_STR_LEN 3
const char PIECE_TABLE[2][NUM_PIECE_TYPES][4] = {
    {"  "," P"," S"," G"," L"," B"," R"," K","+P","+S","+L","+B","+R"},
    {"  "," p"," s"," g"," l"," b"," r"," k","+p","+s","+l","+b","+r"},
};
```

Note: NUM_PT_NO_KING = 12 counts all piece type IDs (1-6 base, 8-12
promoted) that are not King, used as the non-king piece count for NNUE
feature indexing. The gap at index 0 (EMPTY) and 7 (KING) are excluded.

#### Board Initialization (state.hpp)

```cpp
// Player 0 = Sente (Black, moves first)
// Row 0 = rank 1 (bottom of board display)
char board[2][BOARD_H][BOARD_W] = {{
    // Sente's pieces
    {KING, GOLD, SILVER, LANCE, ROOK, BISHOP},  // rank 1: K G S L R B
    {PAWN, PAWN, PAWN,   PAWN,  PAWN, PAWN},    // rank 2: P P P P P P
    {0, 0, 0, 0, 0, 0},                          // rank 3
    {0, 0, 0, 0, 0, 0},                          // rank 4
    {0, 0, 0, 0, 0, 0},                          // rank 5
    {0, 0, 0, 0, 0, 0},                          // rank 6
}, {
    // Gote's pieces (stored as 180-degree rotation)
    {0, 0, 0, 0, 0, 0},                          // rank 1
    {0, 0, 0, 0, 0, 0},                          // rank 2
    {0, 0, 0, 0, 0, 0},                          // rank 3
    {0, 0, 0, 0, 0, 0},                          // rank 4
    {PAWN, PAWN, PAWN,   PAWN,  PAWN, PAWN},    // rank 5
    {BISHOP, ROOK, LANCE, SILVER, GOLD, KING},   // rank 6
}};
char hand[2][NUM_HAND_TYPES + 1] = {};  // hand[player][piece_type] = count
```

#### Promotion and Demotion Mapping

```cpp
// promote(piece) -> promoted form
int promote(int piece) {
    switch(piece) {
        case PAWN:   return P_PAWN;
        case SILVER: return P_SILVER;
        case LANCE:  return P_LANCE;
        case BISHOP: return P_BISHOP;
        case ROOK:   return P_ROOK;
        default:     return piece;  // Gold, King: no promotion
    }
}

// demote(piece) -> base form (for hand placement after capture)
int demote(int piece) {
    switch(piece) {
        case P_PAWN:   return PAWN;
        case P_SILVER: return SILVER;
        case P_LANCE:  return LANCE;
        case P_BISHOP: return BISHOP;
        case P_ROOK:   return ROOK;
        default:       return piece;  // already base form
    }
}

// unpromoted_type(piece) -> hand index (1-6)
// Maps any piece (promoted or not) to its hand index for storage.
int unpromoted_type(int piece) {
    int base = demote(piece);
    // Hand indices: PAWN=1, SILVER=2, GOLD=3, LANCE=4, BISHOP=5, ROOK=6
    return base;  // base piece IDs already match hand indices
}
```

#### Promotion Zone Logic

```cpp
bool is_promotion_zone(int row, int player) {
    // Sente: ranks 5-6 (rows 4-5 in 0-indexed)
    // Gote:  ranks 1-2 (rows 0-1 in 0-indexed)
    if (player == 0) return row >= BOARD_H - 2;  // row 4 or 5
    else             return row <= 1;              // row 0 or 1
}

bool must_promote(int piece, int row, int player) {
    // Pawn or Lance on the very last rank
    int last_rank = (player == 0) ? BOARD_H - 1 : 0;
    if (row == last_rank && (piece == PAWN || piece == LANCE))
        return true;
    return false;
}
```

#### HalfKP Feature Size

```
num_squares        = 6 * 6 = 36
num_pt_no_king     = 12
num_piece_features = 2 * 12 * 36 = 864
halfkp_size        = 36 * 864 = 31,104
hand_feature_size  = 2 * 6 = 12
total_feature_size = 31,104 + 12 = 31,116
```

This is larger than MiniShogi's HalfKP (25 * 200 = 5,000) because of the
additional piece types (12 vs. 10 non-king) and larger board (36 vs. 25
squares). A PS (Piece-Square) architecture may be more practical for
initial training:

```
ps_size            = 2 * 13 * 36 = 936
ps_size_with_hand  = 936 + 12 = 948
```

#### game_config.py Entry

```python
"compact_shogi": {
    "board_h": 6,
    "board_w": 6,
    "num_piece_types": 13,   # 0=empty, 1-7 base, 8-12 promoted
    "num_pt_no_king": 12,
    "king_id": 7,
    "piece_names": [
        ".", "P", "S", "G", "L", "B", "R", "K",
        "+P", "+S", "+L", "+B", "+R",
    ],
    "has_hand": True,
    "num_hand_types": 6,
},
```

#### Move Encoding

Board moves use the standard `(from_row, from_col, to_row, to_col)` format.
Drop moves encode the piece type in `from_col` and use `from_row = DROP_ROW`
(= BOARD_H = 6):

```
Move(DROP_ROW, piece_type, to_row, to_col)
```

Where `piece_type` is the hand index (1-6).

#### Policy Size

```
board_moves = 36 * 36 = 1,296   (from-square * to-square)
drop_moves  = 6 * 36  = 216     (6 piece types * 36 target squares)
policy_size = 1,296 + 216 = 1,512
```

Or, using the sentinel encoding where DROP_ROW=6:

```
policy_size = (BOARD_H + 1) * BOARD_W * BOARD_H * BOARD_W
            = 7 * 6 * 6 * 6 = 1,512
```

### Complexity Estimate

| Metric                   | Estimate   |
|--------------------------|------------|
| Pieces on board (start)  | 24 (12 per side) |
| Average branching factor | ~45        |
| Average game length      | ~55 ply    |
| State space (positions)  | ~10^20     |
| Game tree complexity     | ~10^45     |

**Reasoning**: 24 pieces on 36 squares with full drop mechanics. The 6
pawns per side create substantial pawn structure, and the nifu rule is
highly relevant since all 6 files start occupied. Drops increase the
branching factor significantly (~45 with drops vs. ~25 without). The
6 hand piece types create a large hand-state space. The full pawn wall
means more captures must occur before drop targets open up, slightly
increasing game length. State space accounts for board positions multiplied
by hand-piece combinations (each of 6 piece types can have 0-2+ in hand
for each player).

### Comparison to Existing Small Shogi Variants

| Property        | MiniShogi (5x5) | Judkins Shogi (6x6) | Compact Shogi (6x6) |
|-----------------|-----------------|----------------------|----------------------|
| Board           | 5x5 (25 sq)    | 6x6 (36 sq)         | 6x6 (36 sq)         |
| Pieces/side     | 6               | 7                    | 12                   |
| Pawns/side      | 1               | 1                    | 6                    |
| Piece types     | K,G,S,B,R,P     | K,G,S,B,R,N,P       | K,G,S,L,B,R,P       |
| Has Knight      | No              | Yes                  | No                   |
| Has Lance       | No              | No                   | Yes                  |
| Hand types      | 5               | 6                    | 6                    |
| Promotion zone  | 1 rank          | 2 ranks              | 2 ranks              |
| Pawn structure  | Minimal         | Minimal              | Full wall            |
| Nifu relevance  | Very low (1 pawn)| Very low (1 pawn)  | High (6 pawns)       |
| State space     | ~10^14          | ~10^16               | ~10^20               |
| Game tree       | ~10^30          | ~10^33               | ~10^45               |

**Key differentiators of Compact Shogi**:

- **Full pawn wall**: The 6-pawn front is unique among small shogi variants
  and creates genuine pawn structure play, file control, and meaningful
  nifu constraints. This is the most shogi-like pawn experience possible
  on a small board.
- **Lance instead of Knight**: The Lance's forward-only ranging attack is
  a distinctive shogi piece absent from both MiniShogi and Judkins Shogi.
  It creates different tactical and drop patterns than the Knight's jump.
- **12 pieces per side**: The highest piece density of any small shogi
  variant, creating a richer opening and middle game.
- **Corner king with Gold shield**: The starting position mimics real shogi
  castle formations, unlike Judkins/MiniShogi which use centered back-rank
  positions.

---

## Comparison Table

| Property                 | Corridor Chess (6x7)    | Compact Shogi (6x6)      |
|--------------------------|-------------------------|---------------------------|
| **Type**                 | Chess                   | Shogi                     |
| **Board**                | 6x7 (42 squares)       | 6x6 (36 squares)          |
| **Pieces per side**      | 11                      | 12                        |
| **Total pieces**         | 22                      | 24                        |
| **Piece types (base)**   | 6 (P,R,N,B,Q,K)        | 7 (P,S,G,L,B,R,K)        |
| **Piece types (total)**  | 6                       | 12 (+ 5 promoted forms)   |
| **Pawns per side**       | 5                       | 6                         |
| **Drops**                | No                      | Yes (6 hand types)        |
| **Promotion zone**       | Last rank only          | Last 2 ranks              |
| **Promotion choices**    | Q, R, B, or N           | Fixed promoted form       |
| **Special rules**        | None (simplified chess)  | Nifu, uchifuzume, mandatory promo |
| **Win condition**        | King capture             | King capture              |
| **MAX_STEP**             | 120                     | 200                       |
| **Symmetry**             | 180-degree rotational   | 180-degree rotational     |
| **Branching factor**     | ~30                     | ~45                       |
| **Game length**          | ~60 ply                 | ~55 ply                   |
| **State space**          | ~10^19                  | ~10^20                    |
| **Game tree**            | ~10^44                  | ~10^45                    |
| **HalfKP features**      | 17,640                  | 31,116                    |
| **PS features**          | 504                     | 948                       |
| **Policy size**          | 1,764 (42*42)           | 1,512 (36*36 + 6*36)     |

---

## NNUE Training Considerations

### Corridor Chess

- **All 6 chess piece types**: The network must learn interactions between
  all piece types, including bishop-knight imbalances and queen-vs-two-piece
  trades. No standard chess piece is missing.
- **Rectangular board**: The 6x7 board creates unique bishop diagonal
  patterns. The bishop covers different diagonal lengths in each direction,
  changing its relative value compared to square boards. NNUE must learn
  these novel geometric patterns from scratch.
- **Open f-file asymmetry**: White has an open f-file; Black has an open
  a-file. NNUE must learn directional rook activity patterns.
- **Long pawn promotion journey**: Pawns cross 5 ranks to promote,
  creating a rich evaluation gradient. NNUE must assess when a pawn advance
  is strategically justified versus premature.
- **Moderate feature space**: 17,640 HalfKP features is manageable for
  training. A 256-hidden-unit architecture (standard for the engine) should
  work well.
- **Position diversity**: The 3-rank buffer zone and 180-degree rotational
  symmetry create many distinct opening configurations. The open file on
  opposite sides for each player enriches position variety.

### Compact Shogi

- **Drop mechanics dominate training**: Drops create positions where any
  empty square can receive a piece. NNUE must learn the value of pieces in
  hand versus on board, and how hand composition changes positional
  evaluation. This is fundamentally different from chess NNUE training.
- **Pawn structure + nifu**: With 6 pawns per side, the nifu rule creates
  complex constraints on pawn drops. NNUE must learn which files are
  "locked" for drops and how this affects attack/defense. This pawn
  structure play is absent from MiniShogi and Judkins Shogi.
- **Lance as a unique piece**: The forward-only ranging piece creates
  asymmetric board patterns. NNUE must learn that a Lance is powerful
  on the attacking wing but limited on defense. Lance drops are
  particularly dangerous on open files.
- **Promotion zone as evaluation factor**: The 2-rank zone means 1/3 of
  the board is a promotion zone. NNUE must constantly evaluate promotion
  threats and defensive responses.
- **Larger feature space**: 31,116 HalfKP features is substantial. A PS
  architecture (948 features) may be more practical for initial experiments,
  with HalfKP used for stronger models.
- **Training data density**: Each game produces ~55 positions with high
  diversity due to drops. Fewer selfplay games are needed per NNUE
  iteration compared to chess variants.

### What Makes Each Interesting

| Aspect | Corridor Chess | Compact Shogi |
|--------|---------------|---------------|
| Novel geometry | Rectangular board changes piece values | Corner-king fortress |
| Tactical variety | Open-file play, pawn breaks | Drops, promotion threats |
| Strategic depth | Pawn structure, piece coordination | Nifu management, hand evaluation |
| NNUE challenge | Bishop value on rectangular board | Hand-piece valuation |
| Training efficiency | ~60 ply games, no drops | ~55 ply games, drops add diversity |
| Transfer learning | Some patterns transfer from standard chess | Minimal transfer from any existing variant |

---

## Implementation Effort Estimate

### Corridor Chess

| Component      | Lines (est.) | Notes |
|----------------|-------------|-------|
| `config.hpp`   | ~30         | Piece types, MVV-LVA values, display table |
| `state.hpp`    | ~60         | Board class, State class (reuse MiniChess pattern) |
| `state.cpp`    | ~400        | Move gen, eval, hash, encode/decode, NNUE features |
| **Total**      | **~490**    | |

**Reuse from existing MiniChess**: ~80% of `state.cpp` can be adapted
directly. The move generation for all 6 piece types already exists. Main
changes:

- Board dimensions (6x7 instead of 6x5)
- Initial position
- Remove any castling/en passant code (if present)
- Update NNUE feature extraction for new board size
- Adjust promotion rank

**New code needed**: Minimal. The piece movement logic is identical to
standard chess. Only the board geometry changes.

### Compact Shogi

| Component      | Lines (est.) | Notes |
|----------------|-------------|-------|
| `config.hpp`   | ~50         | 13 piece types, hand types, display table |
| `state.hpp`    | ~75         | Board class with hand, State class |
| `state.cpp`    | ~650        | Move gen (board + drops), promotion, nifu, eval, hash |
| **Total**      | **~775**    | |

**Reuse from existing MiniShogi**: ~70% of `state.cpp` can be adapted.
The drop system, promotion system, hand management, and capture logic
all follow the same patterns. Main changes:

- Board dimensions (6x6 instead of 5x5)
- Add Lance piece type (ID 4) and its promoted form (ID 10)
- Add Lance movement generation (forward-only slide)
- Add Lance drop restriction (cannot drop on last rank)
- Update piece type IDs (KING moves from 6 to 7; add LANCE at 4)
- Update promotion/demotion tables
- Update NNUE feature extraction for new dimensions
- Initial position with 12 pieces per side

**New code needed**: Lance movement generation (~30 lines), updated
promotion tables, adjusted nifu logic for 6 files. The rest is structural
adaptation of the existing MiniShogi codebase.

### Summary

| Variant        | Est. Total Lines | Effort | Primary Dependency |
|----------------|-----------------|--------|--------------------|
| Corridor Chess | ~490            | Low    | Adapt MiniChess    |
| Compact Shogi  | ~775            | Medium | Adapt MiniShogi    |

Both variants can be implemented by an experienced developer in the
codebase within 1-2 days each. Corridor Chess is simpler (no drops, no
promotion types, no hand state). Compact Shogi requires more careful
implementation due to the drop system, 13 piece types, and nifu/uchifuzume
rules, but the existing MiniShogi code provides a solid template.

---

## Appendix: Quick Reference

### Corridor Chess Setup (Algebraic)

```
White: Kb1, Qc1, Bd1, Ne1, Rf1, Pb2 Pc2 Pd2 Pe2 Pf2
Black: Ra7, Nb7, Bc7, Qd7, Ke7, Pa6 Pb6 Pc6 Pd6 Pe6
```

### Compact Shogi Setup (Algebraic)

```
Sente: Ka1, Gb1, Sc1, Ld1, Re1, Bf1, Pa2 Pb2 Pc2 Pd2 Pe2 Pf2
Gote:  Ba6, Rb6, Lc6, Sd6, Ge6, Kf6, Pa5 Pb5 Pc5 Pd5 Pe5 Pf5
```

### Piece Type ID Quick Reference

**Corridor Chess**: EMPTY=0, P=1, R=2, N=3, B=4, Q=5, K=6

**Compact Shogi**: EMPTY=0, P=1, S=2, G=3, L=4, B=5, R=6, K=7,
+P=8, +S=9, +L=10, +B=11, +R=12
