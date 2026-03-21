# Kohaku Shogi (琥珀将棋) --- Design Document

A custom shogi variant for the MiniChess engine framework, designed for
computer play, NNUE training, and rich positional depth on a compact board.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Initial Position](#2-initial-position)
3. [Design Philosophy: Why This Exact Position](#3-design-philosophy-why-this-exact-position)
4. [Complete Rules](#4-complete-rules)
5. [Design Decisions](#5-design-decisions)
6. [Emergent Strategy](#6-emergent-strategy)
7. [Fairness Analysis](#7-fairness-analysis)
8. [Game Complexity](#8-game-complexity)
9. [AI/NNUE Feasibility](#9-ainnue-feasibility)
10. [Comparison to Existing Variants](#10-comparison-to-existing-variants)
11. [Fun Factor](#11-fun-factor)

---

## 1. Overview

### Name

**Kohaku** (琥珀) means **amber** in Japanese. Amber is fossilized tree resin
that preserves insects in a golden, translucent shell --- frozen in time,
encased in protection. The name reflects the variant's central philosophy:
the King begins the game already **encased** in a protective formation of
Pawns, Gold, Silver, and Knight, like an insect preserved in amber. Where
standard shogi requires 10-15 moves of castling to achieve a defensive
formation, Kohaku Shogi starts with the King pre-sheltered, allowing play to
focus immediately on the strategic middle game.

The amber metaphor extends further: the game itself is a distilled, preserved
essence of full 9x9 shogi --- all eight standard piece types, the complete
drop mechanic, pawn walls, promotion --- compressed into 42 squares of golden,
concentrated strategy.

### Vital Statistics

| Property | Value |
|----------|-------|
| Board | 6 files x 7 ranks (42 squares) |
| Pieces per side | 14 (28 total on board) |
| Piece types | All 8 standard shogi types (P, S, G, L, N, B, R, K) |
| Pawn density | 6 pawns on 6 files = 100% |
| Board density | 28/42 = 67% |
| Promotion zone | Last 2 ranks |
| Symmetry | 180-degree rotational |
| Win condition | Capture the opponent's King |
| Max game length | 300 moves |

### Design Goals

1. **Full shogi experience** on a small board --- all piece types, all rules.
2. **Pre-castled King** --- skip the tedious opening castling phase.
3. **Dense pawn wall** --- preserve the file-opening strategy that defines shogi.
4. **Sufficient complexity** for meaningful NNUE training (~10^25-30 state space).
5. **Computer-friendly** --- fast move generation, tractable datagen depth.
6. **Deliberate gating** --- major pieces (Rook, Bishop) require development
   effort to activate, preventing trivial opening tactics.

---

## 2. Initial Position

```
     a   b   c   d   e   f
  +---+---+---+---+---+---+
7 | r | s | l | b | n | k |  <- Gote (White, moves second)
  +---+---+---+---+---+---+
6 | p | p | p | p | s | g |
  +---+---+---+---+---+---+
5 | . | . | . | . | p | p |
  +---+---+---+---+---+---+
4 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
3 | P | P | . | . | . | . |
  +---+---+---+---+---+---+
2 | G | S | P | P | P | P |
  +---+---+---+---+---+---+
1 | K | N | B | L | S | R |  <- Sente (Black, moves first)
  +---+---+---+---+---+---+
     a   b   c   d   e   f
```

### Sente (Black, moves first)

| Piece | Square(s) |
|-------|-----------|
| King (K) | a1 |
| Gold (G) | a2 |
| Silver (S) | b2 (defensive), e1 (back rank) |
| Knight (N) | b1 |
| Bishop (B) | c1 |
| Lance (L) | d1 |
| Rook (R) | f1 |
| Pawns (P) | a3, b3, c2, d2, e2, f2 |

### Gote (White, moves second)

| Piece | Square(s) |
|-------|-----------|
| King (k) | f7 |
| Gold (g) | f6 |
| Silver (s) | e6 (defensive), b7 (back rank) |
| Knight (n) | e7 |
| Bishop (b) | d7 |
| Lance (l) | c7 |
| Rook (r) | a7 |
| Pawns (p) | a6, b6, c6, d6, e5, f5 |

### Symmetry Verification

The position has **perfect 180-degree rotational symmetry** about the board
center. Every piece Sente has at square (file, rank), Gote has the
corresponding piece at (7-file, 8-rank). For example:

- Sente King at a1 <-> Gote King at f7
- Sente Gold at a2 <-> Gote Gold at f6
- Sente Knight at b1 <-> Gote Knight at e7
- Sente Bishop at c1 <-> Gote Bishop at d7
- Sente Rook at f1 <-> Gote Rook at a7
- Sente advanced Pawn at a3 <-> Gote advanced Pawn at f5
- Sente advanced Pawn at b3 <-> Gote advanced Pawn at e5
- Sente defensive Silver at b2 <-> Gote defensive Silver at e6

This ensures perfect structural fairness.

---

## 3. Design Philosophy: Why This Exact Position

The initial position is not arbitrary. Every piece placement was chosen to
create a specific strategic texture --- one where major pieces are deliberately
**locked** behind their own army, forcing complex development before any real
attack can begin. This section explains the reasoning behind the key
placement decisions.

### 3.1 The Locked Rook (f1)

**The Rook at f1 is deliberately gated.** This is the single most important
design decision in the position.

The Rook's file (f) is blocked by its own Pawn at f2. Its rank (rank 1) is
occupied by S(e1), L(d1), B(c1), and N(b1), all sitting between the Rook and
any open squares to the left. The Rook literally cannot move without first
relocating multiple other pieces.

This prevents the trivial "push pawn, trade, open Rook file" opening that
plagues many small shogi variants. In MiniShogi and Judkins Shogi, the Rook
can activate within 1-2 moves, and the game immediately devolves into a
Rook-dominated tactical slugfest. In Kohaku Shogi, the Rook is a sleeping
giant --- enormously powerful once awake, but requiring real strategic effort
to deploy.

The player must choose: push the f-pawn to give the Rook vertical access?
Move the back-rank pieces out of the way for horizontal mobility? Swing the
Rook to a different file entirely? Each path commits the position in a
different direction, creating genuine opening strategy.

### 3.2 The f-File Fortress (Gote's King Defense)

Gote's King at f7 sits behind a **layered fortress** on the f-file. This
is the defensive counterpart to Sente's locked Rook --- even if Sente manages
to activate the Rook on the f-file, breaking through requires dismantling
multiple layers of defense:

- **Gold at f6**: Directly blocks the f-file one square in front of the King.
  Covers f5, f7 (the King itself), e6, and both e7/g7 diagonals (g7 is off-
  board, but the principle holds). The Gold is the premier defensive piece,
  and it sits exactly where it needs to be.

- **Silver at e6**: Covers f7 (the King) via its back-diagonal, and also
  covers f5 and d5. If the Gold is captured, the Silver provides backup
  coverage of the critical squares.

- **Knight at e7**: Controls d5 and f5 via its jump squares. This means f5
  is defended by the Knight even from two ranks back, making pawn-push
  approaches on f5 extremely costly.

- **Bishop at d7**: Covers the d7-e6-f5 diagonal. Even if the Silver moves
  from e6 to contest f5, the Bishop takes over diagonal coverage. The Bishop
  also provides long-range defensive vision down the a4 diagonal.

The critical square **f5 is quadruple-defended** (Gold from f6, Silver from
e6, Knight from e7, Bishop from d7). The Rook's most direct route to the
enemy King --- straight up the f-file --- runs into an absolute fortress.
Sente cannot simply push f2-f3-f4-f5 and crash through; this is by design.

The fortress forces the attacker to either:
1. Dismantle the fortress through piece exchanges (earning drops in the
   process), or
2. Attack from a different direction entirely (flank attack on the a/b side),
   or
3. Build an overwhelming positional advantage before attempting the break.

All three paths lead to complex, strategically rich games.

### 3.3 The Blind Bishop (c1)

**The Bishop at c1 has no immediate targets.** Both of its diagonals are
blocked by friendly pieces and pawns:

- The b2-a3 diagonal: blocked by the Silver at b2.
- The d2-e3 diagonal: blocked by the Pawn at d2.

The Bishop cannot snipe anything from its starting square. There is no
"Bishop takes pawn on move 2" tactic, no early diagonal threat to worry
about. This prevents the degenerate "Bishop dominates the opening" pattern
seen in some small variants.

Like the Rook, the Bishop requires development --- moving the d2 Pawn or
repositioning the b2 Silver --- before it contributes to the attack. This
creates additional opening decisions and prevents the game from being solved
by a single aggressive piece.

### 3.4 Summary: Deliberate Piece Gating

The overall design philosophy is **deliberate constraint**:

| Piece | Starting square | How it is gated |
|-------|----------------|-----------------|
| Rook | f1 | f2 Pawn blocks file; 4 pieces block rank |
| Bishop | c1 | Both diagonals blocked by own pieces/pawns |
| Lance | d1 | d2 Pawn directly in front |
| Knight | b1 | Needs b3 pawn to advance, then can jump to a3 or c3 |

This gating means the opening phase is about **development** --- maneuvering
pieces into active positions --- rather than about immediate tactical threats.
This mirrors the structure of real 9x9 shogi, where the opening is about
piece deployment, not piece activation. The pre-castled King means this
development phase focuses on offense, not defense, creating positive strategic
tension from move 1.

---

## 4. Complete Rules

### 4.1 Piece Movement

Kohaku Shogi uses all 8 standard shogi piece types. Movement is identical to
9x9 shogi.

#### King (K/k) --- Gyoku/Ou

```
  . x .        Moves one square in any
  x K x        of the 8 directions.
  . x .        Cannot move into check.
```

Full diagram:
```
  x x x
  x K x
  x x x
```

The King moves exactly one square in any direction: forward, backward, left,
right, and all four diagonals (8 directions total). The King cannot be
dropped (it is never captured --- the game ends when a King is taken).

#### Gold General (G/g) --- Kin

```
  x x x        Moves one square in 6
  x G x        directions: forward,
  . x .        diag-forward, sideways,
                and backward.
```

Full diagram:
```
  x x x
  x G x
  . x .
```

The Gold moves one square forward, diagonally forward-left, diagonally
forward-right, left, right, or backward (6 directions). It cannot move
diagonally backward. The Gold is the premier defensive piece: its movement
pattern covers the squares most commonly attacked around the King. Gold
**cannot promote**.

#### Silver General (S/s) --- Gin

```
  x x x        Moves one square in 5
  . S .        directions: forward and
  x . x        all four diagonals.
```

Full diagram:
```
  x x x
  . S .
  x . x
```

The Silver moves one square forward, diagonally forward-left, diagonally
forward-right, diagonally backward-left, or diagonally backward-right (5
directions). It cannot move sideways or straight backward. The Silver is a
versatile piece: strong on attack (3 forward directions) but able to retreat
diagonally. It complements the Gold's sideways coverage.

**Promoted Silver (+S)** moves like a Gold:
```
  x x x
  x +S x
  . x .
```

#### Knight (N/n) --- Keima

```
  x . x        Jumps to one of 2 squares:
  . . .        2 ranks forward and 1 file
  . N .        to either side. Leaps over
                intervening pieces.
```

Full diagram:
```
  x . x
  . . .
  . N .
```

The shogi Knight is more restricted than its chess counterpart: it can only
jump **forward** (2 ranks forward + 1 file sideways), giving it exactly 2
target squares. Unlike other pieces, the Knight **leaps** over intervening
pieces. It cannot jump backward or sideways. This makes it a powerful
offensive weapon (it can strike behind pawn walls) but unable to retreat.

**Promoted Knight (+N)** moves like a Gold:
```
  x x x
  x +N x
  . x .
```

#### Lance (L/l) --- Kyousha

```
  x              Moves any number of squares
  x              straight forward. Cannot
  x              move backward, sideways,
  L              or diagonally. Blocked by
                  the first piece in its path.
```

Full diagram (on open board):
```
  x
  x
  x
  x
  x
  L
```

The Lance is a forward-only ranging piece. It moves any number of squares
straight forward, stopping when it hits the board edge or another piece
(capturing enemy pieces, blocked by friendly pieces). It cannot move in any
other direction. The Lance excels at charging down open files created by pawn
exchanges.

**Promoted Lance (+L)** moves like a Gold:
```
  x x x
  x +L x
  . x .
```

#### Bishop (B/b) --- Kaku

```
  x . . . x      Moves any number of squares
  . x . x .      diagonally in any of the 4
  . . B . .      diagonal directions. Blocked
  . x . x .      by the first piece in path.
  x . . . x
```

The Bishop is a major piece (alongside the Rook). It slides any number of
squares along diagonal lines. It covers only squares of one color on its
starting diagonal, but shogi's drop mechanic means a captured Bishop can be
placed on any color --- making it effectively omnipresent.

**Promoted Bishop / Horse (+B)** --- Bishop + 1-step orthogonal:
```
  x . . . x
  . x . x .
  . x +B x .
  . x . x .
  x . . . x
```

The Horse retains full diagonal sliding movement and gains the ability to
step one square orthogonally (forward, backward, left, right). This makes
it one of the most powerful pieces on the board, covering both diagonals and
the four cardinal directions adjacent to it.

#### Rook (R/r) --- Hisha

```
  . . x . .      Moves any number of squares
  . . x . .      orthogonally in any of the 4
  x x R x x      cardinal directions. Blocked
  . . x . .      by the first piece in path.
  . . x . .
```

The Rook is the strongest unpromoted piece. It slides any number of squares
along ranks and files. In shogi, the Rook's power is gated by the pawn wall
--- it cannot activate until files are opened through pawn exchanges. This
creates the fundamental "which file to open" strategic decision.

**Promoted Rook / Dragon (+R)** --- Rook + 1-step diagonal:
```
  . x x x .
  . . x . .
  x x +R x x
  . . x . .
  . x x x .
```

The Dragon retains full orthogonal sliding movement and gains the ability to
step one square diagonally. Combined with its orthogonal range, the Dragon
is the single most powerful piece in the game.

#### Pawn (P/p) --- Fu

```
  x              Moves one square straight
  P              forward only. Cannot move
                  backward, sideways, or
                  diagonally.
```

The Pawn moves and captures one square straight forward. Unlike chess pawns,
shogi pawns capture in the same direction they move (straight ahead). Pawns
are the soul of shogi: the 6-pawn wall in Kohaku Shogi defines the entire
opening and middle game. Which pawn to push, which to exchange, and where to
drop captured pawns are the most frequent and consequential decisions.

**Promoted Pawn / Tokin (+P)** moves like a Gold:
```
  x x x
  x +P x
  . x .
```

The Tokin is deceptively powerful. Created from the lowly Pawn, it gains full
Gold movement. Since Pawns are the most commonly captured piece, Tokin appear
frequently and can dominate the endgame.

### 4.2 Promotion Rules

#### Promotion Zone

The promotion zone is the **last 2 ranks** of the board:

- **Sente (Black)**: Ranks 6 and 7
- **Gote (White)**: Ranks 1 and 2

A piece may promote when it **enters**, **moves within**, or **leaves** the
promotion zone. Promotion is always optional unless the piece would have no
legal move in its unpromoted form (see forced promotion below).

#### Promotion Table

| Piece | Promotes To | Movement After Promotion | Mandatory? |
|-------|-------------|--------------------------|------------|
| Pawn (P) | Tokin (+P) | Gold movement | Yes, on last rank |
| Silver (S) | +S | Gold movement | No |
| Knight (N) | +N | Gold movement | Yes, on last 2 ranks |
| Lance (L) | +L | Gold movement | Yes, on last rank |
| Bishop (B) | Horse (+B) | Bishop + 1-step orthogonal | No |
| Rook (R) | Dragon (+R) | Rook + 1-step diagonal | No |
| Gold (G) | --- | Cannot promote | N/A |
| King (K) | --- | Cannot promote | N/A |

#### Forced (Must-Promote) Rules

Certain pieces **must** promote when they reach squares from which they would
have no legal unpromoted move:

- **Pawn on the last rank**: A Pawn on rank 7 (Sente) or rank 1 (Gote)
  cannot move forward --- there is no rank beyond. It must promote to Tokin.
- **Lance on the last rank**: Same logic as Pawn. A Lance on the last rank
  has no forward square and must promote.
- **Knight on the last 2 ranks**: A Sente Knight on rank 6 would jump to
  rank 8 (nonexistent); on rank 7, it would jump to rank 9 (nonexistent).
  Neither rank allows a legal Knight move. Therefore, Knights on ranks 6-7
  (Sente) or ranks 1-2 (Gote) must promote. This matches the standard shogi
  rule scaled from a 9-rank board (where Knights on ranks 8-9 must promote)
  to a 7-rank board.

#### Promotion Is Irreversible

Once a piece promotes, it remains promoted for the rest of its life on the
board. If a promoted piece is captured, it **reverts to its unpromoted form**
when placed in the captor's hand. When dropped back onto the board, it arrives
unpromoted and may promote again by entering the promotion zone.

### 4.3 Capture and Drop Mechanic

Kohaku Shogi uses the full shogi **capture-and-reuse** system. This is the
defining mechanic that separates shogi from chess: captured pieces switch
allegiance and can be parachuted back onto the board.

#### Capture

When a piece moves to a square occupied by an enemy piece, the enemy piece is
**captured**: it is removed from the board, reverts to its unpromoted form,
and is placed in the capturing player's **hand** (a reserve of pieces
available for dropping).

#### Drop

Instead of moving a piece on the board, a player may **drop** a piece from
their hand onto any empty square on the board, subject to restrictions.
Dropped pieces always arrive **unpromoted**, regardless of where they are
placed (even in the promotion zone --- a piece must make a board move into,
within, or out of the promotion zone to promote).

#### Drop Restrictions

1. **Nifu (二歩)**: A player may not drop a Pawn onto a file that already
   contains one of that player's unpromoted Pawns. Promoted Pawns (Tokin) do
   not count --- only unpromoted Pawns trigger nifu. This is the most
   important drop restriction in shogi. In Kohaku Shogi's initial position,
   all 6 files contain Pawns, so Pawn drops are **impossible until a Pawn is
   exchanged** (captured by the opponent). This "earn your drops" dynamic is
   the heart of shogi's opening strategy.

2. **Last-rank restrictions**: Pieces cannot be dropped onto squares where
   they would have no legal move:
   - **Pawn**: Cannot be dropped on the last rank (rank 7 for Sente, rank 1
     for Gote).
   - **Lance**: Cannot be dropped on the last rank.
   - **Knight**: Cannot be dropped on the last 2 ranks (ranks 6-7 for Sente,
     ranks 1-2 for Gote).

3. **Uchifuzume (打ち歩詰め)**: A Pawn drop that delivers **immediate
   checkmate** is illegal. This prevents the degenerate case where a Pawn
   drop in front of the enemy King creates an unstoppable mate. Other pieces
   may deliver checkmate via drop; only Pawn drops are restricted. Note that
   a Pawn drop that delivers **check** (but not checkmate) is legal.

### 4.4 Win Condition and Game End

- **Win**: Capture the opponent's King. (The MiniChess engine uses king-capture
  rather than checkmate detection. A position where the King is in check and
  cannot escape is lost on the next move when the King is taken.)
- **Draw by move limit**: The game is drawn if 300 moves (MAX_STEP = 300) are
  played without a King capture.
- **Repetition (Sennichite)**: If the same position (board + hands + side to
  move) occurs 4 times, the game is drawn. In tournament shogi, the player
  perpetuating the repetition loses, but for engine play, a draw simplifies
  implementation.

### 4.5 Movement Summary Table

| Piece | Directions | Range | Promotes To | Notes |
|-------|-----------|-------|-------------|-------|
| K | All 8 | 1 | --- | Cannot be dropped |
| G | F, FL, FR, L, R, B | 1 | --- | Premier defender |
| S | F, FL, FR, BL, BR | 1 | +S (Gold) | Versatile attacker |
| N | 2F+1L, 2F+1R | Jump | +N (Gold) | Leaps over pieces |
| L | F | Slide | +L (Gold) | Forward-only ranger |
| B | FL, FR, BL, BR | Slide | +B (Horse) | Diagonal slider |
| R | F, B, L, R | Slide | +R (Dragon) | Orthogonal slider |
| P | F | 1 | +P (Tokin/Gold) | Soul of the game |

Legend: F=forward, B=backward, L=left, R=right, FL=forward-left, etc.

---

## 5. Design Decisions

Each element of Kohaku Shogi's design was a deliberate choice. This section
explains the reasoning behind every decision.

### 5.1 Why 6x7?

The board dimensions were chosen through the intersection of several
constraints:

**6 columns** are necessary for meaningful pawn density. With 6 files and 6
pawns per side, every file is occupied (100% pawn density). This matches
standard shogi's 9 pawns on 9 files and creates the fundamental shogi dynamic:
the pawn wall must be breached through deliberate pawn exchanges, each exchange
opening a file for piece infiltration and creating a piece in hand for dropping.
Fewer columns (5, as in MiniShogi) make pawn walls too thin to support real
positional play. More columns (7+) would require more pieces and a larger board
than the engine framework targets.

**7 rows** solve two critical problems that 6-row boards face:

1. **Knight functionality**: The shogi Knight jumps 2 ranks forward. On a 6-rank
   board, a Knight starting on rank 1 can only reach ranks 3 and 4 before
   running into forced-promotion territory (ranks 5-6). This gives the Knight
   an effective operating range of just 2 usable destination ranks. With 7
   ranks, the Knight has 3 usable ranks (3, 4, and 5) before forced promotion
   kicks in on ranks 6-7. This 50% increase in operating space makes the Knight
   a genuinely useful tactical piece rather than a one-shot projectile.

2. **Development room**: The extra rank creates a full empty rank (rank 4)
   between the pawn lines, giving both sides room to maneuver pieces before
   contact. On a 6-rank board with pawns on ranks 2 and 5, the pawn lines are
   separated by only 2 ranks (3-4). With 7 ranks, the advanced pawns (on ranks
   3 and 5) still leave rank 4 as a buffer, while the main pawn line and back
   rank have space for piece deployment behind the wall. This prevents the game
   from degenerating into immediate tactical exchanges.

### 5.2 Why Corner King?

In standard 9x9 shogi, the first 10-15 moves are typically spent **castling**:
shuffling the King from the center to a fortified corner position (Yagura,
Mino, Anaguma, etc.). This is rich strategic content on a 9x9 board where the
journey itself involves meaningful decisions. On a 6x7 board, this castling
phase would consume a disproportionate fraction of the game and reduce to a
near-forced sequence --- there simply are not enough squares for multiple castle
structures to exist as viable alternatives.

Kohaku Shogi solves this by **starting the King in the corner** (a1 for Sente,
f7 for Gote). The King begins already sheltered, surrounded by Gold, Silver,
Knight, and Pawns. This is the **amber philosophy**: the King is encased from
the start, preserved within its protective shell. Play begins immediately at
the strategic middle game --- deciding which pawns to push, which files to open,
and how to activate the Rook and Bishop.

The corner placement also creates natural asymmetric tension: the King-side
(files a-b for Sente) is defensive territory, while the opposite wing (files
e-f) houses the major pieces (Rook and Silver on the back rank) ready for
development. This King-side vs. attack-side dichotomy mirrors the structure
of real shogi positions post-castling.

### 5.3 Why Gold at a2 (Adjacent to King)?

The Gold General sits at a2, immediately above the King at a1. This mirrors
the most fundamental defensive principle in shogi: the Gold belongs next to
the King. In every major castle formation in standard shogi (Yagura, Mino,
Anaguma, Bear-in-the-Hole), at least one Gold is directly beside the King.

The Gold's movement pattern (forward, diagonal-forward, sideways, backward)
perfectly complements corner defense: it covers the squares most likely to be
attacked around a cornered King while also blocking diagonal infiltration from
Bishops. Placing the Gold adjacent from move 1 means the King's most critical
defender is already in position --- no tempo wasted on setup.

In this position, the Gold at a2 covers a1 (the King), a3, b2, and b3 ---
creating a tight defensive cluster with the Silver at b2. The Gold also
blocks the a-file above the King, preventing Lance or Rook infiltration from
the front.

### 5.4 Why 2 Silvers?

Kohaku Shogi includes **two Silver Generals** per side --- one on the second
rank (b2) and one on the back rank (e1). This dual-Silver design serves two
distinct roles:

1. **Defensive Silver (b2)**: Positioned next to the King and Gold, this Silver
   forms the inner wall of the "amber shell." Its diagonal movement covers the
   squares that the Gold does not (backward diagonals), creating a complementary
   defensive duo. In real shogi, the Silver beside the King in Yagura or
   Anaguma castle is the backbone of the defense.

2. **Offensive Silver (e1)**: Starting on the back rank on the Rook's wing,
   this Silver is available for forward deployment. The Silver's 3-forward-
   direction movement makes it an excellent piece for supporting pawn pushes
   and invading the promotion zone. Having a dedicated offensive Silver means
   the defending Silver never has to choose between guarding the King and
   joining the attack.

Standard 9x9 shogi has 2 Silvers per side for exactly this reason: one for
defense, one for offense. Kohaku Shogi preserves this fundamental piece
balance. In contrast, variants with only 1 Silver force it into an impossible
dual role, weakening both defense and attack.

### 5.5 Why Include the Knight?

The Knight is the piece that MiniShogi (5x5) and several small shogi variants
omit, and its absence fundamentally impoverishes the game:

- **Tactical depth**: The Knight is the only piece in shogi that leaps over
  others. It creates threats that the pawn wall cannot block --- a Knight drop
  behind the pawn line can fork the King and a Gold, and no amount of pawn
  structure prevents this. This forces both sides to account for aerial threats,
  adding an entire dimension of tactical calculation.

- **Fork motifs**: Knight forks (attacking two pieces simultaneously) are among
  the most important tactical patterns in shogi. Without the Knight, these
  patterns simply do not exist, and the tactical vocabulary of the game is
  severely diminished.

- **NNUE learning**: Knight tactics are notoriously difficult for evaluation
  functions to handle. A position may look safe until a Knight drop creates an
  unstoppable fork. Teaching NNUE to recognize Knight-drop threats is one of
  the most valuable training objectives, and it requires the Knight to exist
  in the game.

The Knight is placed at b1 (Sente) / e7 (Gote), on the back rank adjacent
to the King-side. This placement contributes to the overall piece-gating
philosophy: the Knight needs the b3 Pawn to advance before it can develop
forward, and it also blocks the Rook's horizontal path, adding to the Rook's
deliberate constraint.

### 5.6 Why 6 Pawns with 2 Advanced?

Each side has **6 Pawns covering all 6 files**, achieving 100% pawn density.
This matches standard shogi's 9/9 pawn coverage and is the single most
important design feature:

- **Pawn wall IS the game**: With all files occupied, the opening revolves
  around choosing WHICH pawn to push and WHERE to open a file. Every pawn
  exchange is a strategic commitment: it opens a file for the Rook, creates a
  piece in hand, and changes the nifu constraints for future drops.

- **Nifu is a real constraint**: With 6 unpromoted Pawns on 6 files, Pawn
  drops are completely impossible until an exchange occurs. This is exactly
  like real shogi. After one Pawn exchange, the captured Pawn can only be
  dropped on the newly opened file (or any file where the player no longer
  has an unpromoted Pawn). This creates a cascading strategic sequence: each
  exchange opens more drop possibilities.

- **Rook/Bishop gated by wall**: The major pieces start behind a complete pawn
  wall and cannot activate until files/diagonals are opened. This prevents the
  degenerate "Rook dominates from move 1" problem that plagues low-pawn-count
  variants.

**Why 2 advanced Pawns?** The Pawns at a3 and b3 (Sente) / e5 and f5 (Gote)
are pushed one rank forward from the main pawn line. This serves two purposes:

1. **King-wing protection**: The advanced Pawns are on the King-side (files
   a-b for Sente), providing an extra rank of buffer in front of the
   King's defensive formation. They act as an outer wall: an attacker must
   break through the advanced Pawns before reaching the inner defenses.

2. **Immediate strategic tension**: The advanced Pawns are closer to contact
   with the opponent's pieces, creating early decision points. Should you push
   them further to exchange? Hold them to maintain the wall? The main pawn
   line (c2-f2) is more conservative, keeping the center and attack wing
   intact until the player is ready to open those files.

### 5.7 Why 180-Degree Rotational Symmetry?

The initial position has perfect 180-degree rotational symmetry: rotating the
board 180 degrees about its center produces the identical position with colors
swapped. This is the strongest form of positional fairness available:

- **No structural bias**: Every feature that benefits Sente has an identical
  mirror benefiting Gote. The King-side, the pawn structure, the piece
  placement, the open diagonals --- all perfectly balanced.

- **Historical precedent**: Standard 9x9 shogi uses 180-degree rotational
  symmetry. MiniShogi, Judkins Shogi, and all well-designed shogi variants
  follow this convention. It is the natural symmetry type for shogi because
  the board is rectangular and the two sides face opposite directions.

- **Not mirror symmetry**: Left-right mirror symmetry would place both Kings
  on the same file, creating a symmetrical but strategically degenerate
  position. Rotational symmetry places the Kings on opposite corners, creating
  rich asymmetric attack/defense geometry while maintaining perfect fairness.

### 5.8 Why ALL Standard Piece Types?

Kohaku Shogi includes all 8 standard shogi piece types (King, Gold, Silver,
Knight, Lance, Bishop, Rook, Pawn). No other small shogi variant achieves
this:

| Variant | K | G | S | N | L | B | R | P | Missing |
|---------|---|---|---|---|---|---|---|---|---------|
| MiniShogi (5x5) | 1 | 1 | 1 | 0 | 0 | 1 | 1 | 1 | N, L |
| Judkins Shogi (6x6) | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | L |
| Tori Shogi (7x7) | --- | --- | --- | --- | --- | --- | --- | --- | Uses non-standard pieces |
| **Kohaku Shogi (6x7)** | **1** | **1** | **2** | **1** | **1** | **1** | **1** | **6** | **None** |
| Standard Shogi (9x9) | 1 | 2 | 2 | 2 | 2 | 1 | 1 | 9 | None |

Including all piece types means:

- **Full drop vocabulary**: All 7 hand piece types (P, S, G, N, L, B, R) are
  available. Each has unique drop value and strategic considerations. Knight
  drops create forks. Lance drops create skewers. Pawn drops create walls.
  Bishop and Rook drops create devastating infiltrators. This is the complete
  shogi drop experience.

- **Full promotion table**: All 6 promotable pieces (P, S, N, L, B, R)
  exist, producing 6 promoted forms. NNUE must learn to evaluate all of them.

- **Transferable knowledge**: Patterns learned in Kohaku Shogi transfer
  directly to 9x9 shogi study and vice versa. A player who understands
  Knight-drop forks, Lance file charges, Silver-Gold defensive coordination,
  and Bishop vs. Rook piece trades in Kohaku Shogi understands these same
  concepts in full shogi.

---

## 6. Emergent Strategy

Through self-play testing, three main strategic approaches have emerged from
the initial position. These are not prescriptive --- they arise naturally from
the position's structure.

### 6.1 Strategy A: "Trade and Drop"

Fight in the center, exchange pieces to build a hand, then drop behind enemy
lines. This is the classic shogi approach.

The idea: push central pawns (c, d files) to initiate exchanges. Each
exchange puts a piece in hand. Once the hand is loaded with 2-3 pieces,
drop them behind the enemy pawn wall --- a Knight fork on the King, a Rook
on an open file, a Pawn to create a Tokin threat. The defender must juggle
multiple infiltration points simultaneously.

This strategy leverages the full shogi drop mechanic and rewards accurate
tactical calculation. It is the default strategy when both sides develop
symmetrically.

### 6.2 Strategy B: "Edge Attack"

Move pieces to the a/b file side (from Sente's perspective, the enemy's
King-side) where the fortress is thinner.

While the f-file fortress (Gold + Silver + Knight + Bishop defending f5) is
nearly impregnable, the a/b side of the board is defended only by advanced
pawns and no major piece coverage. An attack on the a-file or b-file with
Silver, Lance, and Rook support can overwhelm the defenders on that wing.

The risk: shifting pieces to the a/b wing weakens the attacker's own
position on the e/f wing, potentially allowing a counter-attack.

### 6.3 Strategy C: "Rolling Fortress" (Yagura-style)

Push the entire defensive formation forward like a wall. Advance pawns as a
unified front, with Gold and Silver following behind. This creates an
advancing fortress that forces the opponent to either:

1. **Counter-attack** --- risky, as the advancing wall provides cover for
   the pieces behind it.
2. **Retreat** --- concedes territory, allowing the attacker to push deeper.

This mirrors the Yagura strategy from real 9x9 shogi, where both sides build
massive castles and then slowly advance the entire structure. On the smaller
6x7 board, the rolling fortress reaches the enemy faster, making it a viable
aggressive strategy.

### 6.4 The Three Strategies Interact

The three strategies form a rock-paper-scissors dynamic:

- **Trade and Drop** beats **Rolling Fortress**: the fortress is slow, and
  piece exchanges generate drops that can infiltrate behind the advancing wall.
- **Rolling Fortress** beats **Edge Attack**: the advancing wall covers the
  flank and overwhelms the edge attackers with central pressure.
- **Edge Attack** beats **Trade and Drop**: the flank attack creates threats
  before the center trader has accumulated enough drops.

This dynamic ensures that no single strategy dominates, and the game rewards
strategic flexibility and reading the opponent's intentions.

---

## 7. Fairness Analysis

### 7.1 Rotational Symmetry

As detailed in Section 5.7, the position has perfect 180-degree rotational
symmetry. This guarantees that no positional or structural advantage exists
for either side. The only asymmetry is the **tempo advantage** of moving
first.

### 7.2 Time vs. Depth Asymmetry

A fascinating property discovered during engine testing reveals genuine
strategic balance:

- **With DEPTH limit** (same search depth for both sides), **Sente wins** ---
  the tempo advantage of moving first matters when both sides see equally deep.
  The first mover can set the pace and force the second mover to react.

- **With TIME limit** (same clock for both sides), **Gote wins** --- defensive
  positions allow deeper search. Gote's positions tend to have fewer critical
  forcing moves to consider, which means better alpha-beta pruning and
  effectively deeper search within the same time budget.

This is a remarkable property. It means the game has **genuine strategic
balance**: Sente's first-mover tempo advantage is countered by Gote's
positional stability and search efficiency. Neither side is structurally
favored --- the advantage depends on the playing conditions.

For practical purposes (engine vs. engine with time controls), this suggests
the game is very well balanced, as real games are always played under time
constraints.

### 7.3 First-Mover Advantage (General Analysis)

In shogi variants, the first-mover advantage is generally **smaller** than in
chess variants, for several reasons:

1. **Drops neutralize tempo**: The second player can deploy captured pieces
   instantly via drops, partially compensating for the first-move advantage.
   A single well-timed drop can negate several moves of positional buildup.

2. **Dense pawn wall**: With 100% pawn density, the first player cannot
   immediately exploit the tempo advantage --- the pawn wall must be breached
   first, which requires multiple moves and gives the second player time to
   respond.

3. **Pre-castled position**: Both Kings start already defended. The first
   player cannot exploit the tempo by castling faster --- both sides are
   already castled. The tempo advantage must be used for the strategic middle
   game, where it is less decisive.

4. **Shogi's historical balance**: In professional 9x9 shogi, Gote (second
   player) wins approximately 48% of games. The game is remarkably balanced
   despite the first-move advantage. Smaller boards tend to amplify tempo
   advantages somewhat, but the dense pawn wall and drops should keep Kohaku
   Shogi reasonably balanced.

**Expected first-mover advantage**: Sente wins ~52-54% of games under equal
depth conditions, but this is offset under time conditions. This is within the
acceptable range for a competitive variant. For comparison:

| Variant | First-player win rate | Notes |
|---------|----------------------|-------|
| Standard Shogi (9x9) | ~52% | Extremely well-balanced |
| MiniShogi (5x5) | ~53-55% | Fewer pawns = more tempo impact |
| Judkins Shogi (6x6) | ~54-56% | Very open board = tempo matters |
| Chess | ~55% | No drops to compensate |
| **Kohaku Shogi (6x7)** | **~52-54%** | Dense wall + drops + pre-castled |

### 7.4 Draw Frequency

Shogi variants have very low draw rates compared to chess, because:

- Captured pieces return to the board, so material is never permanently lost.
  Games cannot peter out into drawn endgames from material depletion.
- The drop mechanic provides constant fuel for attacks. Even when the board
  is nearly empty, hand pieces create ongoing threats.
- Perpetual check is handled by repetition rules (the checking side must
  change the position).

**Expected draw rate**: < 5%. The 300-move limit (MAX_STEP = 300) provides a
generous ceiling. Most games should conclude well within this limit, given
the aggressive nature of piece drops and the relatively compact board.

### 7.5 Game Length

**Observed game length**: Self-play at equal depth produces games of
approximately **~100 moves** (200 ply).

This is longer than the initial theoretical estimate of 50-80 moves and
indicates deep, complex games with real strategic phases:

1. **Opening** (~moves 1-25): Piece maneuvering, choosing attack direction.
   Developing the Rook and Bishop from their gated starting positions.
   Deciding which pawns to push and which to hold.

2. **Middle game** (~moves 25-50): Fighting for center control, initiating
   pawn exchanges, piece trading. The first captures create pieces in hand,
   unlocking the drop dimension.

3. **Drop phase** (~moves 50-75): Infiltrating with captured pieces. Knight
   forks, Rook drops on open files, Pawn drops to create Tokin threats. This
   is where the game's shogi character shines brightest.

4. **Endgame** (~moves 75-100): Breaking the fortress with accumulated drops.
   The defender's amber shell is cracked, and the attacker combines board
   pieces with hand drops to construct a mating net.

The ~100-move game length is a strong indicator of strategic depth. For
comparison, standard 9x9 shogi averages ~115 moves, and Kohaku Shogi achieves
87% of that depth on half the board. Games are long enough for genuine strategy
but short enough for efficient engine training.

---

## 8. Game Complexity

### 8.1 Basic Metrics

| Metric | Value | Reasoning |
|--------|-------|-----------|
| Board squares | 42 | 6 x 7 |
| Pieces per side | 14 | K, G, 2S, N, L, B, R, 6P |
| Total pieces at start | 28 | 14 x 2 |
| Board density | 67% | 28 / 42 |
| Piece types (base) | 8 | K, G, S, N, L, B, R, P |
| Piece types (with promoted) | 15 | 8 base + 6 promoted + empty |
| Hand piece types | 7 | P, S, G, N, L, B, R |

### 8.2 Branching Factor

**Estimated average branching factor**: ~30-40 legal moves per position.

Breakdown:

- **Board moves**: ~15-20. In the opening, most pieces are blocked by the pawn
  wall. Each Pawn has 0-1 moves (forward if not blocked). Officers behind the
  wall have limited mobility. As files open, piece mobility increases, but
  the board also becomes less populated.

- **Drop moves**: ~15-25. Drop moves multiply with each capture. Initially,
  no drops are available (empty hands). After the first pawn exchange, 1 piece
  can be dropped on ~5-10 legal squares (restricted by nifu, last-rank rules).
  As more pieces enter the hand, drop options proliferate. In the middle game,
  a player might have 3-5 pieces in hand with 5-15 legal drop squares each.

- **Nifu constraint on pawn drops**: With 6 files initially occupied by pawns,
  pawn drops are impossible until exchanges occur. After N pawn exchanges, N
  files become available for pawn drops. This gradual unlocking of drop options
  is a key complexity driver.

### 8.3 State Space

**Estimated state space**: ~10^25-30 distinct legal positions.

Contributing factors:

- **Board configurations**: 42 squares, each can hold one of ~29 piece states
  (empty, or one of 14 piece types for either color). The theoretical upper
  bound is 29^42, but piece count constraints, pawn file restrictions, and
  piece conservation laws dramatically reduce this.

- **Hand configurations**: Each of 7 hand piece types can appear 0-N times in
  each player's hand. The total pieces of each type are conserved (board +
  both hands = constant). For example, there are 12 total Pawns (6 per side),
  each of which can be on the board (as Pawn or Tokin, for either player) or
  in either hand. The number of Pawn distributions is bounded by the
  multinomial coefficient C(12+3, 3) for 4 states per pawn, but piece
  placement correlations reduce the actual count.

- **Adjusted estimate**: Accounting for piece conservation, promotion status,
  nifu constraints, and King uniqueness, the effective state space is
  approximately 10^25 to 10^30 positions. This is roughly 5-10 orders of
  magnitude larger than MiniShogi (~10^20) and 20-30 orders of magnitude
  smaller than standard shogi (~10^71).

### 8.4 Game Tree Complexity

**Estimated game tree complexity**: ~10^50-60.

Calculation: branching_factor ^ (game_length / 2) = 35^55 ~ 10^85. However,
this is the naive upper bound. Adjusting for:

- Transpositions (same position reached via different move orders).
- Early terminations (games ending before average length).
- Forced sequences (many positions have only 1-3 reasonable moves).

The adjusted game tree complexity is approximately 10^50 to 10^60. This places
Kohaku Shogi comfortably beyond solvability while remaining tractable for
NNUE-based engine play.

### 8.5 Comparison to Other Variants

| Metric | MiniShogi (5x5) | Judkins (6x6) | Kohaku (6x7) | Standard (9x9) |
|--------|----------------|---------------|--------------|----------------|
| Board squares | 25 | 36 | 42 | 81 |
| Pieces/side | 6 | 7 | 14 | 20 |
| Pawns/side | 1 | 1 | 6 | 9 |
| Pawn density | 20% | 17% | 100% | 100% |
| Piece types | 5 | 6 | 8 | 8 |
| Hand types | 5 | 6 | 7 | 7 |
| Has Knight? | No | Yes | Yes | Yes |
| Has Lance? | No | No | Yes | Yes |
| Branching factor | ~25 | ~30 | ~35 | ~80 |
| Game length (moves) | ~20 | ~23 | ~100 | ~115 |
| State space | ~10^20 | ~10^22 | ~10^25-30 | ~10^71 |
| Game tree | ~10^30 | ~10^32 | ~10^50-60 | ~10^226 |

Kohaku Shogi occupies a unique niche: it has the piece-type completeness of
standard shogi, the pawn density of standard shogi, but the board size and
game length of a small variant. It is substantially more complex than MiniShogi
or Judkins Shogi while remaining far more tractable than 9x9 shogi.

---

## 9. AI/NNUE Feasibility

### 9.1 HalfKP Feature Size

The HalfKP (Half-King-Piece) feature encoding maps each (King_square,
piece_type, piece_square) triple to a unique feature index. For Kohaku Shogi:

**Board features (pieces on the board)**:

- King squares: 42 (the friendly King can be on any square)
- Piece types (excluding King): 13 types x 2 colors = 26
  - The 13 types are: P, S, G, L, N, B, R, +P, +S, +L, +N, +B, +R
  - Note: King is excluded from the piece list (it IS the indexing dimension)
- Piece squares: 42

Board feature count per perspective = 42 (king squares) x 26 (piece-color
combinations) x 42 (piece squares) = **45,864**

**Hand features (pieces in hand)**:

- 7 hand piece types (P, S, G, N, L, B, R) per color = 14
- Each with binary "at least 1 in hand" encoding, or count-based encoding

With simple count-based encoding (max count per type):
- Pawn: up to 6 in hand -> 6 features per perspective
- Silver: up to 2 -> 2
- Gold: up to 1 -> 1
- Knight: up to 1 -> 1
- Lance: up to 1 -> 1
- Bishop: up to 1 -> 1
- Rook: up to 1 -> 1
- Total per color: 13 features
- Both colors: 26

But with per-king-square indexing for hand features:
Hand feature count = 42 (king squares) x 7 (hand types) x 2 (colors) = **588**

This can also be simplified. With a flat hand feature encoding (no king-square
indexing for hand):
Hand feature count = 7 hand types x 2 colors = **14**

**Total HalfKP feature size** (with king-indexed hand features):

45,864 (board) + 588 (hand) = **46,452**

Alternatively, using the formula from the user's specification:
42 (king_sq) x 2 (colors) x 13 (piece_types_no_king) x 42 (piece_sq) + 2 x 7 (hand_types)
= 42 x 2 x 13 x 42 + 14 = 45,864 + 14 = **45,878**

This is a very manageable feature size. For comparison:
- MiniShogi HalfKP: 25 x 2 x 9 x 25 + 10 = 11,260
- Standard Shogi HalfKP: 81 x 2 x 13 x 81 + 14 = 170,586
- Kohaku Shogi HalfKP: **45,878**

The feature space is roughly 4x MiniShogi and 0.27x standard shogi --- large
enough to capture complex piece relationships but small enough for efficient
training and inference.

### 9.2 Why NNUE Matters for This Variant

Kohaku Shogi is **too complex for handcrafted evaluation** to play well:

1. **Drop combinatorics**: With 7 hand piece types and 42 squares, the
   interaction between board state and hand composition creates explosive
   tactical complexity. A handcrafted eval cannot enumerate Knight-fork threats,
   Lance-file dangers, and Bishop-drop infiltrations simultaneously.

2. **Pawn structure evaluation**: The 6-pawn wall creates 2^6 = 64 possible
   file-opening patterns (each file open or closed), and the value of each
   pattern depends on the full context (piece placement, hand composition,
   King safety). NNUE learns these contextual valuations from data.

3. **Promotion timing**: When to promote vs. maintain unpromoted form (e.g.,
   keeping a Silver unpromoted for its diagonal retreat capability vs.
   promoting for Gold movement) requires subtle positional judgment that
   emerges naturally from NNUE training.

4. **King safety**: Evaluating the safety of a cornered King surrounded by
   various defender configurations, with potential drop threats on empty
   squares nearby, is precisely the kind of pattern recognition that neural
   networks excel at.

### 9.3 Datagen Considerations

**Search depth for datagen**: Depth 6 is the recommended starting point.

- On a 42-square board with ~35 branching factor, depth 6 search examines
  on the order of 35^3 = ~43,000 nodes (with alpha-beta pruning cutting the
  effective depth roughly in half). This is fast enough for high-throughput
  self-play.

- The tactical horizon at depth 6 captures most single-move tactics (forks,
  skewers, pin exploitations) and many 2-move combinations. Knight-drop forks
  are typically visible at depth 3-4.

- Quiescence search extends the tactical horizon for captures and checks,
  effectively adding 2-4 ply of tactical depth.

**Depth 6 vs. Depth 9 trade-off**: A key hypothesis is that many fast shallow
iterations at depth 6 compound knowledge more effectively than fewer deep
iterations at depth 9. The reasoning:

- Depth 6 datagen is roughly 35^3 / 35^4.5 = ~100x faster than depth 9.
- Each NNUE iteration effectively adds 2-3 plies of "knowledge depth" ---
  the network learns patterns that previously required deeper search to find.
- The iterative loop: handcrafted eval at depth 6 generates data for NNUE v1;
  v1 at depth 6 generates data for NNUE v2; each iteration compounds.
- After 3-4 iterations, NNUE v4 at depth 6 may play stronger than the
  handcrafted eval at depth 12, because the accumulated pattern knowledge
  substitutes for raw search depth.

This makes depth 6 the sweet spot for rapid iteration cycles during
development. Deeper datagen (depth 8-9) can be reserved for final training
runs when the NNUE architecture has stabilized.

**Self-play game generation rate**: With depth 6 search and a simple evaluation
function (material + piece-square tables as bootstrap), expect ~50-200 games
per second per CPU core, depending on average game length and move generation
speed.

### 9.4 Training Data Requirements

**Estimated requirement**: ~20-50 million positions.

Reasoning:

- **Feature space**: With ~46,000 HalfKP features, the network has ~46,000 x
  accumulator_size parameters in the first layer alone. For a 256-wide
  accumulator, this is ~12 million parameters. Adequate training requires
  roughly 2-5x the parameter count in training positions.

- **Position diversity**: The ~10^25-30 state space means 50M positions sample
  a vanishingly small fraction of possible positions. However, NNUE learning
  generalizes through shared features: a position with a Knight threatening
  a fork teaches the network about ALL similar positions with Knights in
  similar configurations.

- **Comparison to standard shogi NNUE**: Stockfish's NNUE for chess (~10^44
  state space) trains on ~1-2 billion positions. Scaling proportionally by
  state space: (10^28 / 10^44) x 10^9 ~ 10^-7 --- suggesting even 1M
  positions might suffice. However, the drop mechanic creates more tactical
  diversity per state space size, so 20-50M is a reasonable target.

- **Iterative improvement**: Start with 5M positions from random self-play,
  train an initial NNUE, then generate 20M+ positions using NNUE-guided
  search for the next iteration. The recommended loop:
  1. hc-d6 (handcrafted eval, depth 6) -> generate data -> train NNUE v1
  2. v1-d6 -> generate data -> train NNUE v2
  3. v2-d6 -> generate data -> train NNUE v3
  4. Each iteration effectively adds 2-3 plies of evaluation quality
  5. After 3-5 iterations, the NNUE should play at a level comparable to
     much deeper search with the handcrafted evaluation.

---

## 10. Comparison to Existing Variants

### 10.1 Feature Comparison Table

| Feature | MiniShogi | Judkins | Tori Shogi | **Kohaku** | Std Shogi |
|---------|-----------|---------|------------|------------|-----------|
| **Board** | 5x5 (25) | 6x6 (36) | 7x7 (49) | **6x7 (42)** | 9x9 (81) |
| **Pieces/side** | 6 | 7 | 8 | **14** | 20 |
| **Pawns/side** | 1 | 1 | 4 | **6** | 9 |
| **Pawn density** | 20% | 17% | 57% | **100%** | 100% |
| **Uses std pieces?** | Yes (subset) | Yes (subset) | No (unique) | **Yes (all)** | Yes (all) |
| **Has Knight?** | No | Yes | No | **Yes** | Yes |
| **Has Lance?** | No | No | No | **Yes** | Yes |
| **Has Gold?** | Yes (1) | Yes (1) | No | **Yes (1)** | Yes (2) |
| **Has Silver?** | Yes (1) | Yes (1) | No | **Yes (2)** | Yes (2) |
| **Hand types** | 5 | 6 | 4 | **7** | 7 |
| **Piece types (total)** | 10 | 12 | 12 | **15** | 15 |
| **Promotion zone** | 1 rank | 2 ranks | 2 ranks | **2 ranks** | 3 ranks |
| **Pre-castled?** | No | No | N/A | **Yes** | No |
| **Pawn wall?** | No | No | Partial | **Yes (full)** | Yes (full) |
| **Pieces gated?** | No | No | Partial | **Yes** | Yes (by pawns) |
| **Branching factor** | ~25 | ~30 | ~35 | **~35** | ~80 |
| **Game length (moves)** | ~20 | ~23 | ~35 | **~100** | ~115 |
| **State space** | ~10^20 | ~10^22 | ~10^25 | **~10^25-30** | ~10^71 |
| **Game tree** | ~10^30 | ~10^32 | ~10^50 | **~10^50-60** | ~10^226 |
| **Feels like shogi?** | Barely | Somewhat | Different game | **Yes** | Canonical |

### 10.2 Detailed Comparisons

#### vs. MiniShogi (5x5)

MiniShogi is the most widely known small shogi variant, but it barely resembles
real shogi. With only 1 Pawn per side on a 5x5 board:

- There is no pawn wall and no file-opening strategy.
- The Rook and Bishop dominate from move 1 with open lanes.
- Drops are the entire game --- particularly Rook drops behind enemy lines.
- No Knight and no Lance means no fork/skewer tactics.
- Nifu is nearly irrelevant (1 pawn blocks only 1 of 5 files).
- Games are short (~40 ply) and almost purely tactical.

MiniShogi is a fine abstract strategy game, but it teaches nothing about
real shogi strategy. Kohaku Shogi preserves everything MiniShogi discards:
pawn walls, file-opening decisions, Knight tactics, Lance charges, and the
full range of drop types.

#### vs. Judkins Shogi (6x6)

Judkins Shogi adds a Knight (and a 6th file) to MiniShogi's piece set but
retains the fatal 1-Pawn-per-side design:

- Still no pawn wall (1 pawn on 6 files = 17% coverage).
- The Knight exists but has minimal interaction with pawn structure (there
  is no structure to interact with).
- No Lance, so the "charge down an open file" tactic is absent.
- 5 of 6 files are open from the start --- Rook drops are devastating.
- Games are short and tactically chaotic.

Judkins Shogi is Kohaku Shogi minus the pawn wall, the Lance, the extra
Silver, and the pre-castled position. Removing these elements strips away
most of what makes shogi strategically deep.

#### vs. Tori Shogi (7x7)

Tori Shogi (Bird Shogi) is an interesting alternative that uses completely
non-standard piece types (Phoenix, Falcon, Crane, Pheasant, Swallow, Quail).
While it achieves meaningful complexity on a 7x7 board, its pieces have no
relationship to standard shogi:

- Knowledge does not transfer to or from 9x9 shogi.
- The piece movements are unique to Tori Shogi and must be learned from
  scratch.
- There is no equivalent of the Knight, Lance, Silver, or Gold.

Tori Shogi is a well-designed standalone game, but it exists in its own
universe. Kohaku Shogi deliberately uses standard shogi pieces so that
concepts transfer between the variant and the full game.

#### vs. Standard Shogi (9x9)

Standard 9x9 shogi is the canonical form. Kohaku Shogi is a deliberate
compression of the same game:

| Element | Standard | Kohaku | Ratio |
|---------|----------|--------|-------|
| Board squares | 81 | 42 | 0.52x |
| Pieces per side | 20 | 14 | 0.70x |
| Pawns per side | 9 | 6 | 0.67x |
| Piece types | 8 | 8 | 1.00x |
| Hand types | 7 | 7 | 1.00x |
| Game length | ~115 | ~100 | 0.87x |

The compression is remarkably proportional: the board shrinks to 52% of its
original size, pieces shrink to 70%, pawns shrink to 67%, but piece type
diversity and hand type diversity are preserved at 100%. Game length preserves
87% of standard shogi's depth. This means Kohaku Shogi sacrifices scale but
not vocabulary --- the same strategic language applies, spoken in shorter
sentences.

What Kohaku Shogi trades away:
- The second Gold, the second Knight, and the second Lance.
- 3 Pawns (9 -> 6).
- The elaborate castling phase (replaced by pre-castled start).
- The deep positional maneuvering of the 9x9 board.

What Kohaku Shogi preserves:
- The complete pawn wall and file-opening strategy.
- All 8 piece types and all 7 hand types.
- Knight forks, Lance charges, Silver-Gold defense, Bishop/Rook activation.
- The drop-and-promote lifecycle of pieces.
- The "earn your drops" opening dynamic.
- Genuine game length (~100 moves) with 4 distinct strategic phases.

---

## 11. Fun Factor

### 11.1 What Makes Kohaku Shogi Fun to PLAY

**Immediate action**: The pre-castled start means no tedious setup phase. From
move 1, every move is a real strategic decision: push a pawn to probe? Start
developing pieces from the gated back rank? Swing the Rook to a different
file? The game starts at the interesting part.

**The development puzzle**: Unlike most small shogi variants where pieces are
immediately active, Kohaku Shogi's deliberately gated Rook and Bishop create
a genuine development puzzle. How do you get the Rook out from behind 4 pieces
and a pawn? Do you move the pawn first, or rearrange the back rank? This
development phase mirrors real shogi's opening and adds strategic depth that
other small variants lack.

**The pawn wall dance**: With 6 pawns covering all files, the opening is a
delicate negotiation of pawn pushes and exchanges. Pushing the a-file Pawn
opens a lane toward the enemy King but also invites counter-play. Pushing the
f-file Pawn begins to free the Rook but weakens the attack wing. Every pawn
push is a commitment with consequences --- this is the essence of shogi
strategy.

**Knight-drop terror**: Nothing in small shogi variants matches the thrill
(or terror) of a Knight drop that forks the King and a Gold. In MiniShogi,
this cannot happen --- no Knight exists. In Judkins Shogi, Knight forks are
common but not meaningful because the King is already exposed. In Kohaku Shogi,
the King starts safely encased, and a Knight fork that cracks the shell open
is a genuinely dramatic event.

**Endgame depth**: Because captured pieces return to the board, endgames in
Kohaku Shogi are not the quiet affairs of chess. Even with few pieces on the
board, both players have hand pieces to drop. A Tokin (promoted Pawn) near
the enemy King supported by a Rook drop can create unstoppable mating threats.
The endgame is as exciting as the middle game.

**Deep but not interminable**: Observed game length of ~100 moves means a game
takes 10-20 minutes at human speed. Long enough for real strategy with 4
distinct phases, short enough to play multiple games in a session. This makes
it excellent for casual play, tournament events, and especially for AI training
where millions of games must be played.

### 11.2 What Makes Kohaku Shogi Interesting for AI RESEARCH

**Full shogi drop mechanic on a tractable board**: The drop mechanic is what
makes shogi uniquely challenging for AI. Pieces never leave the game --- they
change hands and return. This creates a fundamentally different search and
evaluation problem from chess, where material monotonically decreases. Kohaku
Shogi provides this challenge on a board small enough for deep search and
rapid datagen.

**NNUE feature learning**: With 7 hand piece types, 15 total piece types, and
42 squares, the NNUE feature space (~46K HalfKP features) is large enough to
require genuine pattern learning but small enough to train in hours rather
than weeks. This makes it an ideal testbed for NNUE architecture experiments.

**Iterative NNUE training**: The depth-6 iterative training loop (hc -> v1 ->
v2 -> v3) is a novel approach that can be tested and validated on Kohaku Shogi
before applying to larger games. If shallow-but-iterated training outperforms
deep-but-single-pass training, this has implications for NNUE training
methodology across all board games.

**Opening theory exploration**: The pre-castled, symmetric start position with
deliberately gated pieces creates a well-defined opening theory problem. Which
pawn breaks are optimal? Should the Rook be freed vertically (push f-pawn) or
horizontally (clear the back rank)? Does the Knight develop early or stay back
as a defender? Do you attack the fortress head-on or go around the edge? These
questions have answers that NNUE-guided search can discover, and the answers
should be nontrivial given the three emergent strategies.

**The time-vs-depth balance property**: The discovery that Sente wins under
depth limits but Gote wins under time limits provides a natural benchmark
for search algorithm efficiency. An improved search algorithm should narrow
this gap by making better use of available time for both sides.

**Benchmark for search algorithms**: At branching factor ~35 and game length
~100 moves, Kohaku Shogi occupies the sweet spot for comparing search
algorithms (alpha-beta, MCTS, hybrid approaches). It is complex enough that
naive search fails but tractable enough that algorithmic improvements produce
measurable Elo gains.

**Comparison point for shogi research**: Results on Kohaku Shogi can be
meaningfully compared to MiniShogi and Judkins Shogi research. If an NNUE
architecture improvement helps on Kohaku Shogi but not MiniShogi, this tells
us something about the role of pawn structure in NNUE learning. Such
comparative insights are valuable for the broader shogi AI community.

### 11.3 The Amber Aesthetic

The name **Kohaku** (琥珀, amber) is not merely decorative. It encodes the
variant's design philosophy:

- **Preservation**: Just as amber preserves the complete form of an ancient
  insect, Kohaku Shogi preserves the complete form of shogi --- all 8 piece
  types, the full drop mechanic, the pawn wall --- in a smaller, crystallized
  form.

- **Protection**: The King begins encased in its shell of defenders, like an
  insect in amber. Cracking open the amber (breaching the defensive formation)
  is the attacker's challenge; maintaining the amber's integrity is the
  defender's goal.

- **Constraint**: Amber traps what is inside. The Rook and Bishop begin
  trapped behind their own army, encased in amber alongside the King. Freeing
  them is part of the game's strategic challenge --- you must crack your own
  amber to release your attacking power, while keeping the enemy's amber
  intact.

- **Warmth**: Amber has a warm, golden color. It is organic, not cold like
  crystal. Kohaku Shogi aims to feel warm and natural --- like real shogi, not
  like an artificial puzzle. The pre-castled start, the full pawn wall, the
  complete piece set all contribute to a game that feels like a natural
  miniature of the real thing.

- **Timelessness**: Amber endures for millions of years. A well-designed
  shogi variant, with proper complexity and balance, can endure as a lasting
  contribution to the world of abstract strategy games.

### 11.4 Opening Theory Speculation

The initial position suggests several natural opening strategies, shaped by
the deliberately gated piece placement:

**Rook liberation via f-pawn push**: Push f2-f3 to give the Rook vertical
mobility on the f-file. This is the most direct approach but runs straight
into Gote's f-file fortress (Gold + Silver + Knight + Bishop all defending
f5). The Rook gains movement but lacks breakthrough potential without
additional preparation.

**Rook swing via back-rank clearing**: Move pieces off the first rank (N b1
to c3, B c1 to d2, etc.) to give the Rook horizontal access. The Rook can
then swing to a central file (c or d) where the pawn wall is the only
obstacle. This is slower but positions the Rook for a more productive break.

**Silver charge (bougin)**: The offensive Silver at e1 advances through
e2 (after the Pawn moves) toward the center. The classic "climbing Silver"
strategy from 9x9 shogi translates directly. The Silver supports pawn pushes
and can invade the promotion zone.

**Edge attack preparation**: Push the a3 and b3 Pawns further forward to
challenge the enemy's e5/f5 advanced Pawns (which are the opponent's King-
side defenders). An edge attack bypasses the f-file fortress entirely.

**Bishop exchange line**: Develop the Bishop from c1 by pushing d2 forward.
If both Bishops can be exchanged, the resulting Bishop-in-hand creates
powerful drop threats. A Bishop dropped behind enemy lines can threaten the
King directly. The decision of whether to exchange Bishops or maintain the
Bishop on the board is a fundamental strategic choice.

These opening themes mirror real shogi theory in compressed form. The
pre-castled position and gated pieces mean the opening phase focuses on
choosing a development plan and committing to a strategic direction ---
exactly the kind of content that rewards deep understanding and punishes
aimless play.

---

## Appendix: Quick Reference Card

```
KOHAKU SHOGI (琥珀将棋) --- Quick Reference

Board:  6x7 (42 squares)
Pieces: K G S S N L B R P P P P P P  (14 per side, 28 total)
Win:    Capture the enemy King
Draw:   Move 300 or 4-fold repetition

PROMOTION ZONE: Last 2 ranks
  Sente promotes on ranks 6-7
  Gote promotes on ranks 1-2

MUST PROMOTE:
  Pawn/Lance on last rank
  Knight on last 2 ranks

DROPS: Captured pieces (unpromoted) go to hand.
  Drop onto any empty square, with restrictions:
  - Nifu: no 2 unpromoted friendly Pawns per file
  - No Pawn/Lance on last rank
  - No Knight on last 2 ranks
  - No Pawn-drop checkmate (uchifuzume)

START POSITION:

     a   b   c   d   e   f
  +---+---+---+---+---+---+
7 | r | s | l | b | n | k |  Gote
  +---+---+---+---+---+---+
6 | p | p | p | p | s | g |
  +---+---+---+---+---+---+
5 | . | . | . | . | p | p |
  +---+---+---+---+---+---+
4 | . | . | . | . | . | . |
  +---+---+---+---+---+---+
3 | P | P | . | . | . | . |
  +---+---+---+---+---+---+
2 | G | S | P | P | P | P |
  +---+---+---+---+---+---+
1 | K | N | B | L | S | R |  Sente
  +---+---+---+---+---+---+
     a   b   c   d   e   f

KEY DESIGN FEATURES:
  - Rook at f1 is deliberately locked (pawn + 4 pieces block it)
  - Bishop at c1 has no immediate diagonal targets
  - f-file fortress: f5 is quadruple-defended (G+S+N+B)
  - Three strategies: Trade & Drop, Edge Attack, Rolling Fortress
  - Time vs depth asymmetry: Sente wins at equal depth, Gote at equal time
  - ~100 move games with 4 distinct phases
```

---

*Document version: 2.0*
*Variant design for the MiniChess engine framework*
*Kohaku Shogi --- where the King rests in amber.*
