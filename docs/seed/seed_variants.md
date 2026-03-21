# Small Chess & Shogi Variants (5x5 to 7x7)

A detailed reference of small-board chess and shogi variants suitable for engine
development, AI research, and game design. Each entry includes rules, starting
positions, piece movement diagrams, strategic themes, complexity estimates, and
engine support.

---

## Table of Contents

1. [Minishogi (5x5)](#1-minishogi-5x5) -- baseline
2. [Gardner Minichess (5x5)](#2-gardner-minichess-5x5) -- solved, reference
3. [Kyoto Shogi (5x5)](#3-kyoto-shogi-5x5) -- flip identity
4. [Goro Goro Shogi (5x6)](#4-goro-goro-shogi-5x6) -- pieces in hand
5. [Los Alamos Chess (6x6)](#5-los-alamos-chess-6x6) -- no bishops
6. [Judkins Shogi (6x6)](#6-judkins-shogi-6x6) -- standard shogi on 6x6
7. [Tori Shogi (7x7)](#7-tori-shogi-7x7) -- bird shogi
8. [Micro Shogi (4x5)](#8-micro-shogi-4x5) -- bonus variant
9. [Complexity Comparison Table](#complexity-comparison-table)
10. [Engine Support Matrix](#engine-support-matrix)

---

## 1. Minishogi (5x5)

**Also known as:** 5-Five Shogi / Go-Go Shogi
**Invented:** c. 1970 by Shigenobu Kusumoto (Osaka, Japan)
**Board:** 5 ranks x 5 files
**Pieces per side:** 6 (King, Gold, Silver, Bishop, Rook, Pawn)
**Drops:** Yes (standard shogi drop rules)
**Promotion zone:** Last rank only (rank 5 for Sente, rank 1 for Gote)

### 1.1 Rules Summary

- Identical to standard shogi rules except for the reduced board and piece set.
- Each player has: 1 King (K), 1 Gold General (G), 1 Silver General (S),
  1 Bishop (B), 1 Rook (R), 1 Pawn (P).
- Promotion zone is only the single furthest rank.
- Rook promotes to Dragon King (R+King moves).
  Bishop promotes to Dragon Horse (B+King moves).
  Silver, Pawn promote to Gold-movement.
- Drop restrictions: no two unpromoted friendly pawns in the same file (nifu),
  no pawn drop checkmate (uchifuzume), no drops onto the last rank for pawn.

### 1.2 Initial Position

```
  a  b  c  d  e
5 K  G  S  B  R   <- Gote (White)
4 .  .  .  .  p
3 .  .  .  .  .
2 P  .  .  .  .
1 r  b  s  g  k   <- Sente (Black)
```

Sente (Black, moves first): King on e1, Gold on d1, Silver on c1, Bishop on b1,
Rook on a1, Pawn on a2.

Gote (White): King on a5, Gold on b5, Silver on c5, Bishop on d5, Rook on e5,
Pawn on e4.

**SFEN:** `rbsgk/4p/5/P4/KGSBR w - 1`

### 1.3 Piece Movement Diagrams

```
  King (K/k)         Gold General (G/g)    Silver General (S/s)
  . x x x .          . x x x .             . x . x .
  . x K x .          . x G x .             . x S x .
  . x x x .          . . x . .             . x . x .

  Bishop (B/b)        Rook (R/r)            Pawn (P/p)
  x . . . x          . . x . .             . . x . .
  . x . x .          . . x . .             . . P . .
  . . B . .          x x R x x             . . . . .
  . x . x .          . . x . .
  x . . . x          . . x . .

  Dragon Horse (+B)   Dragon King (+R)
  . . x . .          x . x . x
  . x x x .          . x x x .
  x x+B x x          . x+R x .
  . x x x .          . x x x .
  . . x . .          x . x . x
```

### 1.4 Typical Middle-Game Position

```
  a  b  c  d  e        Gote in hand: S
5 .  G  K  .  .
4 .  .  .  .  .
3 .  .  +B .  P
2 .  .  p  .  .
1 .  .  g  k  R        Sente in hand: b
```

Themes: Sente has promoted the bishop to Dragon Horse on c3, creating a
powerful central piece. Both sides have captured material available for drops.

### 1.5 Strategic Themes

- **Pawn breaks** are critical despite having only one pawn per side.
- **Drops** create constant tactical tension; the board is never "quiet."
- **Promoted bishop/rook** dominate the small board with enormous range.
- **King safety** is paramount -- the small board means attacks develop fast.
- Typical game length: ~40 half-moves (20 move pairs).

### 1.6 Game Tree Complexity Estimate

| Metric | Estimate |
|---|---|
| Reachable positions | ~2.38 x 10^18 |
| Avg. branching factor | ~40 (with drops) |
| Avg. game length | ~40 ply |
| Game tree complexity | ~10^38 (estimated) |
| Comparison | Similar to checkers in state space |

### 1.7 Engine Support

- **Fairy-Stockfish**: Full support (built-in variant). 3x UEC Cup Minishogi
  champion. Strongest available engine for this variant.
- **GNU Shogi**: Supports minishogi.
- **Lishogi**: Playable online at lishogi.org.
- **PyChess**: Playable online at pychess.org.

---

## 2. Gardner Minichess (5x5)

**Invented:** 1969 by Martin Gardner (Scientific American column)
**Board:** 5 ranks x 5 files
**Pieces per side:** 8 (King, Queen, Rook, Bishop, Knight, 3 Pawns)
**Drops:** No
**Promotion:** Pawns promote on the last rank (no bishop promotion)
**Status:** WEAKLY SOLVED -- draw with best play (Mhalla & Prost, 2013)

### 2.1 Rules Summary

- Standard chess rules with these modifications:
  - No pawn double-move (no two-square advance).
  - No en passant.
  - No castling.
  - Pawns promote on the last rank to Q, R, or N (not B, since bishops are
    already present).
- All standard chess pieces are present, just reduced in number.

### 2.2 Initial Position

```
  a  b  c  d  e
5 r  n  b  q  k   <- Black
4 p  p  p  p  p
3 .  .  .  .  .
2 P  P  P  P  P
1 R  N  B  Q  K   <- White
```

White: Rook a1, Knight b1, Bishop c1, Queen d1, King e1, Pawns a2-e2.
Black: Rook a5, Knight b5, Bishop c5, Queen d5, King e5, Pawns a4-e4.

Note: Each side has 5 pawns (one per file) and a full set of piece types.

### 2.3 Piece Movement Diagrams

Standard chess movements apply. All pieces move as in regular chess.

```
  Knight (N)          Bishop (B)           Rook (R)
  . x . x .          x . . . x            . . x . .
  x . . . x          . x . x .            . . x . .
  . . N . .          . . B . .            x x R x x
  x . . . x          . x . x .            . . x . .
  . x . x .          x . . . x            . . x . .

  Queen (Q)           King (K)
  x . x . x          . . . . .
  . x x x .          . x x x .
  x x Q x x          . x K x .
  . x x x .          . x x x .
  x . x . x          . . . . .
```

### 2.4 Typical Middle-Game Position

```
  a  b  c  d  e
5 r  .  .  .  k
4 .  .  p  .  p
3 .  .  P  .  .
2 P  P  .  .  .
1 R  .  .  .  K
```

In Gardner chess, pawns are typically exchanged or blocked early. The game
quickly transitions to piece play on an extremely cramped board.

### 2.5 Strategic Themes

- **Pawns block immediately** -- most games see early pawn exchanges or frozen
  pawn structures since there is no double-move.
- **Piece development** is severely constrained; almost all free squares are
  controlled by opposing pawns.
- **The bishop** is less powerful on a 5x5 board (limited diagonals).
- **Endgame theory** is critical; the game was weakly solved by constructing
  drawing strategies for both sides.
- **Tempo** is extremely important with so few squares.

### 2.6 Game Tree Complexity Estimate

| Metric | Estimate |
|---|---|
| Legal positions | ~9 x 10^18 |
| Avg. branching factor | ~25 |
| Avg. game length | ~30 ply |
| Game tree complexity | ~10^34 (estimated) |
| Status | Weakly solved (draw) |

### 2.7 Engine Support

- **Fairy-Stockfish**: Supported as built-in variant.
- **Mini Chess Resolution project** (Mhalla & Prost): Provides complete oracles
  for drawing play from both sides.
- **Custom engines**: Multiple implementations on GitHub (e.g., mdhiebert/minichess).

---

## 3. Kyoto Shogi (5x5)

**Invented:** c. 1976 by Tamiya Katsuya
**Board:** 5 ranks x 5 files
**Pieces per side:** 5 (King, Tokin/Lance, Silver/Bishop, Gold/Knight, Pawn/Rook)
**Drops:** Yes
**Unique mechanic:** Every piece (except King) FLIPS after each move

### 3.1 Rules Summary

- There is NO promotion zone. Instead, every piece (except the King) alternates
  between its two identities every time it moves. After moving, the piece is
  flipped over to reveal its other side.
- Each piece is a two-sided tile with different movement on each side:
  - **Tokin** (moves like Gold) <-> **Lance** (moves any number forward)
  - **Silver General** <-> **Bishop** (moves any number diagonally)
  - **Gold General** <-> **Knight** (jumps 2 forward + 1 sideways)
  - **Pawn** (1 step forward) <-> **Rook** (moves any number orthogonally)
  - **King**: Does not flip. Moves 1 step in any direction.
- A piece may be moved into a position where it cannot move on a subsequent
  turn (unlike standard shogi). It can only be rescued by being captured.
- Captured pieces can be dropped with EITHER side face-up (player chooses).
- Three-fold repetition = draw.

### 3.2 Initial Position

```
  a  b  c  d  e
5 to si Ki go pa    <- Gote (White)
4 .  .  .  .  .
3 .  .  .  .  .
2 .  .  .  .  .
1 PA GO KI SI TO    <- Sente (Black)

Key: to/TO = Tokin, si/SI = Silver, Ki/KI = King,
     go/GO = Gold, pa/PA = Pawn
```

Sente (Black): Pawn(a1), Gold(b1), King(c1), Silver(d1), Tokin(e1).
Gote (White): Tokin(a5), Silver(b5), King(c5), Gold(d5), Pawn(e5).

The arrangement is symmetric/mirrored: what is Tokin on one side corresponds
to Pawn on the other.

### 3.3 Piece Movement Diagrams (Both Sides)

```
  Tokin (= Gold move)       Lance (flip side)
  . x x x .                 . . x . .
  . x T x .                 . . x . .
  . . x . .                 . . L . .
                             . . . . .
                             . . . . .

  Silver General             Bishop (flip side)
  . x . x .                 x . . . x
  . x S x .                 . x . x .
  . x . x .                 . . B . .
                             . x . x .
                             x . . . x

  Gold General               Knight (flip side)
  . x x x .                 . x . x .
  . x G x .                 . . . . .
  . . x . .                 . . N . .
                             . . . . .
                             . . . . .

  Pawn                       Rook (flip side)
  . . x . .                 . . x . .
  . . P . .                 . . x . .
  . . . . .                 x x R x x
                             . . x . .
                             . . x . .

  King (does not flip)
  . x x x .
  . x K x .
  . x x x .
```

### 3.4 Typical Middle-Game Position

```
  a  b  c  d  e        Gote in hand: la(nce)
5 .  .  Ki .  .
4 .  .  .  BI .        (BI = Bishop, flipped from Silver)
3 .  .  .  .  .
2 .  RO .  .  .        (RO = Rook, flipped from Pawn)
1 .  .  KI .  TO       Sente in hand: kn(ight)
```

After just a few moves, piece identities have changed dramatically. A pawn
that moved forward becomes a rook; a silver that captured becomes a bishop.

### 3.5 Strategic Themes

- **Identity chaos**: Every move changes a piece's power. A lowly pawn becomes
  a rook after moving, fundamentally altering board control.
- **Drop flexibility**: Choosing which side to drop a piece on adds a layer of
  strategy absent from other shogi variants.
- **Traps and tactics**: The knight (flip side of gold) can create surprising
  fork threats. The lance (flip side of tokin) can deliver back-rank threats.
- **Short, sharp games**: Most games end in under 30 moves due to the volatile
  nature of piece transformations.
- **Practically solved**: Fairy-Stockfish can practically solve this variant
  with sufficient compute.

### 3.6 Game Tree Complexity Estimate

| Metric | Estimate |
|---|---|
| Legal positions | ~10^12 (rough estimate) |
| Avg. branching factor | ~30 (with drops + flip choices) |
| Avg. game length | ~25 ply |
| Game tree complexity | ~10^20 (estimated) |
| Status | Practically solvable by engine |

### 3.7 Engine Support

- **Fairy-Stockfish**: Full support. Can practically solve the variant.
- **Lishogi**: Playable online at lishogi.org/variant/kyotoshogi.
- **PyChess**: Playable online at pychess.org/variants/kyotoshogi.

---

## 4. Goro Goro Shogi (5x6)

**Also known as:** Goro Goro Dobutsu Shogi (animal version)
**Invented:** 2012 (teaching variant for Japanese children)
**Board:** 5 files x 6 ranks
**Pieces per side (on board):** 8 (1 King, 2 Gold, 2 Silver, 3 Pawn)
**Pieces in hand (Goro Goro Plus):** 1 Lance + 1 Knight per side
**Drops:** Yes (standard shogi rules)
**Promotion zone:** Last 2 ranks

### 4.1 Rules Summary

- Standard shogi rules on a 5x6 board.
- No long-range pieces (no Rook or Bishop) on the board at start.
- Each player starts with: 1 King, 2 Gold Generals, 2 Silver Generals, 3 Pawns.
- **Goro Goro Plus** variant: each player additionally starts with 1 Lance and
  1 Knight in hand, available for drops from the first move.
- Promotion zone is the 2 furthest ranks from the player.
- Pawn, Silver promote to Gold-movement. Lance and Knight (in Plus variant)
  promote to Gold-movement.
- Standard drop restrictions apply (nifu, no pawn-drop checkmate, etc).

### 4.2 Initial Position (Standard Goro Goro)

```
  a  b  c  d  e
6 s  g  k  g  s   <- Gote
5 .  .  .  .  .
4 .  p  p  p  .
3 .  P  P  P  .
2 .  .  .  .  .
1 S  G  K  G  S   <- Sente
```

**SFEN (Goro Goro Plus):** `sgkgs/5/1ppp1/1PPP1/5/SGKGS[LNln] w 0 1`

In Goro Goro Plus, each player additionally holds: 1 Lance (L/l) and
1 Knight (N/n) in hand at game start.

### 4.3 Piece Movement Diagrams

```
  King (K)            Gold General (G)      Silver General (S)
  . x x x .          . x x x .             . x . x .
  . x K x .          . x G x .             . x S x .
  . x x x .          . . x . .             . x . x .

  Pawn (P)            Lance (L) [in hand]   Knight (N) [in hand]
  . . x . .           . . x . .             . x . x .
  . . P . .           . . x . .             . . . . .
  . . . . .           . . L . .             . . N . .
                       . . . . .             . . . . .
```

All pieces except King and Gold can promote. Promoted pieces move like Gold.

### 4.4 Typical Middle-Game Position (Goro Goro Plus)

```
  a  b  c  d  e        Gote in hand: P, N
6 .  g  k  .  .
5 .  .  .  .  s
4 .  .  P  p  .
3 .  .  +S .  .        (+S = promoted Silver, moves like Gold)
2 L  .  .  .  .        (L = dropped Lance)
1 S  G  K  .  .        Sente in hand: g
```

### 4.5 Strategic Themes

- **Three pawns per side** make this much closer to standard shogi than
  minishogi. Pawn structure management matters.
- **No ranged pieces on board** means the game is initially slow and
  positional. Knights and lances in hand (Plus) add surprise attack potential.
- **Teaching variant**: Designed to teach shogi fundamentals to children.
  Good for learning pawn play and general interactions.
- **Gold/Silver interplay**: With 2 of each general, castling-like king
  defense structures are possible even on the small board.

### 4.6 Game Tree Complexity Estimate

| Metric | Estimate |
|---|---|
| Legal positions | ~10^15 (estimated) |
| Avg. branching factor | ~25-35 (with drops) |
| Avg. game length | ~40 ply |
| Game tree complexity | ~10^30 (estimated) |

### 4.7 Engine Support

- **Fairy-Stockfish**: Goro Goro Plus is a built-in variant.
- **PyChess**: Playable online at pychess.org/variants/gorogoroplus.

---

## 5. Los Alamos Chess (6x6)

**Invented:** 1956 by Paul Stein and Mark Wells (Los Alamos National Lab)
**Board:** 6 ranks x 6 files
**Pieces per side:** 12 (King, Queen, 2 Rooks, 2 Knights, 6 Pawns)
**Drops:** No
**Historical significance:** First chess variant played by a computer (MANIAC I)

### 5.1 Rules Summary

- Standard chess rules with these differences:
  - **No bishops** -- removed entirely from the game.
  - **No castling**.
  - **No pawn double-move** (pawns advance one square only).
  - **No en passant** (consequence of no double-move).
  - Pawns promote on the last rank to Queen, Rook, or Knight (not Bishop).
- The game is sometimes called "anti-bishop chess" or "MANIAC chess."

### 5.2 Initial Position

```
  a  b  c  d  e  f
6 r  n  q  k  n  r   <- Black
5 p  p  p  p  p  p
4 .  .  .  .  .  .
3 .  .  .  .  .  .
2 P  P  P  P  P  P
1 R  N  Q  K  N  R   <- White
```

White: R(a1), N(b1), Q(c1), K(d1), N(e1), R(f1), Pawns a2-f2.
Black: R(a6), N(b6), Q(c6), K(d6), N(e6), R(f6), Pawns a5-f5.

### 5.3 Piece Movement Diagrams

All pieces move as in standard chess (no bishop available):

```
  Knight (N)          Rook (R)             Queen (Q)
  . x . x .          . . x . .            x . x . x
  x . . . x          . . x . .            . x x x .
  . . N . .          x x R x x            x x Q x x
  x . . . x          . . x . .            . x x x .
  . x . x .          . . x . .            x . x . x

  King (K)            Pawn (P)
  . x x x .          . . x . .
  . x K x .          . . P . .
  . x x x .          . . . . .
                      (captures diagonally forward as normal)
```

### 5.4 Typical Middle-Game Position

```
  a  b  c  d  e  f
6 r  .  .  k  .  r
5 p  .  p  .  p  .
4 .  .  n  p  .  .
3 .  P  .  .  N  .
2 P  .  P  .  P  P
1 R  .  .  K  .  R
```

The MANIAC I computer played the first computer chess game in history using
this variant. A human "weak player" lost to the computer in 23 moves.

### 5.5 Strategic Themes

- **No bishops** radically changes the game. Diagonal control comes only from
  the queen, pawns, and king. Color complexes do not exist.
- **Knights are stronger** relative to other pieces because bishops are absent
  and the small board suits the knight's short-range jumps.
- **Queen is dominant** as the only piece with diagonal range.
- **Pawn structure** is critical since pawns can only advance one square.
  Pawn chains form differently without bishop pressure.
- **Endgame**: Rook + Knight vs. King is a common endgame pattern.
- **Partially solved**: After 1.e3, the game has been solved -- Black wins in
  21 moves (Sayle, 2024). The overall game-theoretic value is unknown.

### 5.6 Game Tree Complexity Estimate

| Metric | Estimate |
|---|---|
| Legal positions | ~4 x 10^17 |
| Avg. branching factor | ~22 |
| Avg. game length | ~50 ply |
| Game tree complexity | ~10^33 (estimated) |
| Comparison | Branching factor ~2/3 of standard chess |

### 5.7 Engine Support

- **Fairy-Stockfish**: Supported as built-in variant.
- **Green Chess**: Playable online at greenchess.net.
- **Jocly**: Playable online with 3D visualization.
- **MANIAC I** (historical): The original 1956 implementation.

---

## 6. Judkins Shogi (6x6)

**Invented:** Prior to April 1998 by Paul Judkins (Norwich, UK)
**Board:** 6 ranks x 6 files
**Pieces per side:** 7 (King, Rook, Bishop, Gold, Silver, Knight, Pawn)
**Drops:** Yes (standard shogi drop rules)
**Promotion zone:** Last 2 ranks

### 6.1 Rules Summary

- Identical to standard shogi rules on a reduced 6x6 board.
- Each player has all the piece types of standard shogi except Lance: King (K),
  Rook (R), Bishop (B), Gold General (G), Silver General (S), Knight (N),
  and Pawn (P). Only one of each piece.
- Promotion zone is the furthest 2 ranks.
- Rook promotes to Dragon King, Bishop promotes to Dragon Horse.
- Silver, Knight, Pawn promote to Gold-movement.
- Standard drop restrictions apply. Knight cannot be dropped onto the last 2
  ranks (where it would have no legal move).

### 6.2 Initial Position

```
  a  b  c  d  e  f
6 K  G  S  N  B  R   <- Gote (White)
5 p  .  .  .  .  .
4 .  .  .  .  .  .
3 .  .  .  .  .  .
2 .  .  .  .  .  P
1 r  b  n  s  g  k   <- Sente (Black)
```

Sente (Black): Rook(a1), Bishop(b1), Knight(c1), Silver(d1), Gold(e1),
King(f1), Pawn(f2).

Gote (White): King(a6), Gold(b6), Silver(c6), Knight(d6), Bishop(e6),
Rook(f6), Pawn(a5).

The back rank arrangement is: K-G-S-N-B-R, with the single pawn placed in
the file of the king.

### 6.3 Piece Movement Diagrams

Same as standard shogi pieces:

```
  King (K)            Gold General (G)      Silver General (S)
  . x x x .          . x x x .             . x . x .
  . x K x .          . x G x .             . x S x .
  . x x x .          . . x . .             . x . x .

  Knight (N)          Bishop (B)            Rook (R)
  . x . x .          x . . . x             . . x . .
  . . . . .          . x . x .             . . x . .
  . . N . .          . . B . .             x x R x x
  . . . . .          . x . x .             . . x . .
                      x . . . x             . . x . .

  Pawn (P)            Dragon King (+R)      Dragon Horse (+B)
  . . x . .          x . x . x             . . x . .
  . . P . .          . x x x .             . x x x .
  . . . . .          . x+R x .             x x+B x x
                      . x x x .             . x x x .
                      x . x . x             . . x . .
```

### 6.4 Typical Middle-Game Position

```
  a  b  c  d  e  f        Gote in hand: P
6 K  G  .  .  .  .
5 .  .  .  .  .  .
4 .  .  .  s  .  .
3 .  .  +B .  .  .        (+B = Dragon Horse)
2 .  .  .  .  .  .
1 .  .  .  .  g  k        Sente in hand: n, b
```

### 6.5 Strategic Themes

- **Full shogi experience** on a smaller board. All standard shogi piece types
  except lance are present.
- **Knight** is more restricted on a 6x6 board -- fewer safe landing squares.
- **Bishop and Rook** promotion to Dragon Horse / Dragon King remains
  game-defining, as these promoted pieces dominate the small board.
- **Faster games** than standard shogi; typical games last 30-50 moves.
- **Good training variant** for players learning standard shogi.

### 6.6 Game Tree Complexity Estimate

| Metric | Estimate |
|---|---|
| Legal positions | ~10^16 (estimated) |
| Avg. branching factor | ~35 (with drops) |
| Avg. game length | ~40 ply |
| Game tree complexity | ~10^32 (estimated) |

### 6.7 Engine Support

- **Fairy-Stockfish**: Supported as built-in variant.
- **CuteChess**: Judkins Shogi support via pull request #545.
- **PyChess**: Not currently available as a variant.

---

## 7. Tori Shogi (7x7)

**Also known as:** Bird Shogi (Tori = Bird)
**Invented:** 1799 by Toyota Genryu
**Board:** 7 ranks x 7 files
**Pieces per side:** 16 (1 Phoenix, 1 Falcon, 2 Cranes, 2 Pheasants,
2 Quails (L+R), 8 Swallows)
**Drops:** Yes
**Promotion zone:** Last 2 ranks
**Historical note:** One of the oldest shogi variants with the drop rule

### 7.1 Rules Summary

- Objective: Capture the opponent's **Phoenix** (the royal piece, equivalent to
  the King in other shogi variants).
- All pieces are named after birds.
- Only two pieces promote:
  - **Swallow** -> **Goose** (mandatory on reaching last 2 ranks)
  - **Falcon** -> **Eagle** (mandatory on reaching last 2 ranks)
- **Left Quail** and **Right Quail** are DIFFERENT pieces with asymmetric
  movement (mirror images of each other).
- Drop rule: Like standard shogi, but with the **two-swallow rule** -- you
  cannot drop a swallow into a file that already contains two friendly swallows.
- Dropping a swallow for immediate checkmate (capturing the Phoenix) loses the
  game (similar to uchifuzume in shogi).
- Three-fold repetition: the player who initiated the repeating sequence loses.
- A swallow may not be dropped on the furthest rank.

### 7.2 Initial Position

```
  a  b  c  d  e  f  g
7 RQ Pt Cr Ph Cr Pt LQ   <- Gote (White)
6 .  .  .  Fa .  .  .
5 Sw Sw Sw Sw Sw Sw Sw
4 .  .  sw .  .  .  .
3 sw sw sw sw sw sw sw
2 .  .  .  fa .  .  .
1 lq pt cr ph cr pt rq   <- Sente (Black)

Key: ph/PH = Phoenix, fa/FA = Falcon, cr/CR = Crane
     pt/PT = Pheasant, lq/LQ = Left Quail, rq/RQ = Right Quail
     sw/SW = Swallow
     (lowercase = Sente/Black, UPPERCASE = Gote/White)
```

Rank 1 (Sente back): LQ(a1), Pt(b1), Cr(c1), Ph(d1), Cr(e1), Pt(f1), RQ(g1)
Rank 2 (Sente):      Falcon on d2
Rank 3 (Sente):      Swallows on a3, b3, c3, d3, e3, f3, g3
Rank 4:              Sente swallow on c4 (note: 8th swallow)
Rank 5 (Gote):       Swallows on a5, b5, c5, d5, e5, f5, g5
Rank 6 (Gote):       Falcon on d6
Rank 7 (Gote back):  RQ(a7), Pt(b7), Cr(c7), Ph(d7), Cr(e7), Pt(f7), LQ(g7)

Note: Each side has 8 swallows. 7 fill rank 3/5 and the 8th is on c4/e4.

### 7.3 Piece Movement Diagrams

```
  PHOENIX (Royal)         FALCON                  CRANE
  Moves 1 step any dir.   Moves 1 step any dir.   Moves 1 step forward,
                           EXCEPT straight back.   backward, or diagonally.
                                                   Cannot move sideways.
  . x x x .              . x x x .               . x . x .
  . x P x .              . x F x .               . x C x .
  . x x x .              . . . . .               . x . x .


  PHEASANT                LEFT QUAIL              RIGHT QUAIL
  Jumps 2 forward, or     Ranges forward (any),   Ranges forward (any),
  steps 1 diag. backward  ranges diag. back-right ranges diag. back-left
                           steps 1 diag. back-left steps 1 diag. back-right
  . . J . .
  . . . . .              . . | . .               . . | . .
  . . H . .              . . | . .               . . | . .
  . x . x .              . . Q . .               . . Q . .
                           x . . . \               / . . . x
                           . . . . .\             /. . . . .
  J = jump-to square
  H = can be occupied        (ranges down-right)    (ranges down-left)
      (jumped over)


  SWALLOW                 GOOSE (promoted Sw)     EAGLE (promoted Fa)
  Moves 1 step forward    Jumps 2 diag-forward    Ranges diag-fwd (any),
  only.                   or 2 straight backward. ranges straight back,
                                                   steps 1 any direction,
  . . x . .              J . . . J               1-2 diag-backward.
  . . S . .              . . . . .
  . . . . .              . . G . .              \ . | . /
                           . . . . .             .\.x./..
                           . . J . .             x x E x x
                                                 .x.x.x..
  J = jump-to square                             x . x . x (up to 2)
  (Goose jumps -- cannot
   be blocked)
```

#### Detailed Eagle Movement

The Eagle (promoted Falcon) is the most powerful piece in Tori Shogi. It has
three movement components:

1. **Ranging**: Any number of squares diagonally forward (both directions) or
   straight backward.
2. **Stepping**: One square in any of the 8 directions (like a King).
3. **Short diagonal backward**: Up to 2 squares diagonally backward (this is
   NOT a jump -- it can be blocked by intervening pieces).

### 7.4 Typical Middle-Game Position

```
  a  b  c  d  e  f  g        Gote in hand: sw sw
7 .  .  Cr Ph .  Pt LQ
6 .  .  .  .  .  .  .
5 .  Sw .  Sw Sw .  .
4 .  .  .  sw .  Go .        (Go = Goose, promoted swallow)
3 sw sw .  .  sw .  .
2 .  .  .  fa .  .  .
1 lq pt cr ph .  .  rq       Sente in hand: Sw Pt
```

The Falcon (fa) on d2 is a key attacking piece. Both sides have captured
swallows available for drops. The promoted Goose on f4 controls jump squares.

### 7.5 Strategic Themes

- **Asymmetric quails**: The left and right quails create asymmetric attack
  and defense patterns. Planning which side to attack with which quail is a
  core strategic decision.
- **Swallow walls**: 8 swallows per side form pawn-like walls. Managing
  swallow exchanges and drops is critical.
- **Falcon/Eagle promotion**: The falcon must be advanced carefully. Once
  promoted to eagle, it becomes overwhelmingly powerful.
- **Phoenix safety**: The phoenix (royal piece) is much more exposed on a 7x7
  board than a king on a 9x9 board.
- **Pheasant jumps**: The pheasant's jump-2-forward is unique and can create
  surprise attacks.
- **Historical depth**: Invented in 1799, this is one of the most carefully
  designed shogi variants with rich strategic theory.

### 7.6 Game Tree Complexity Estimate

| Metric | Estimate |
|---|---|
| Legal positions | ~10^25 (estimated) |
| Avg. branching factor | ~35-45 (with drops) |
| Avg. game length | ~60 ply |
| Game tree complexity | ~10^50 (estimated) |
| Comparison | Between checkers and chess |

### 7.7 Engine Support

- **Fairy-Stockfish**: Full support as built-in variant.
- **PyChess**: Playable online at pychess.org/variants/torishogi.
- **Tabletopia**: Playable online with graphical board.

---

## 8. Micro Shogi (4x5)

**Also known as:** Gofun Maka Shogi
**Invented:** c. 1980s, attributed to Oyama Yasuharu
**Board:** 4 files x 5 ranks
**Pieces per side:** 5 (King, Gold, Silver, Bishop, Pawn)
**Drops:** Yes
**Unique mechanic:** Pieces promote/demote on CAPTURE (not on zone entry)

### 8.1 Rules Summary

- There is NO promotion zone. Instead, a piece promotes when it captures,
  and promotion is mandatory.
- Each piece has a different identity on its reverse side:
  - **King** (blank reverse -- does not promote)
  - **Silver** <-> **Lance**
  - **Gold** <-> **Rook**
  - **Bishop** <-> **Tokin** (Gold-movement)
  - **Pawn** <-> **Knight**
- When a promoted piece (Lance, Rook, Tokin, or Knight) captures, it flips
  back to its unpromoted form.
- Pieces flip back and forth as they make captures throughout the game.
- Standard shogi drop rules apply.

### 8.2 Initial Position

```
  a  b  c  d
5 K  G  S  B   <- Gote (White)
4 .  .  .  p
3 .  .  .  .
2 P  .  .  .
1 b  s  g  k   <- Sente (Black)
```

Sente: Bishop(a1), Silver(b1), Gold(c1), King(d1), Pawn(a2).
Gote: King(a5), Gold(b5), Silver(c5), Bishop(d5), Pawn(d4).

### 8.3 Piece Movement (Both Sides of Each Tile)

```
  King (no flip)      Gold / Rook           Silver / Lance
  . x x x .          . x x x .  / . x .    . x . x .  / . x .
  . x K x .          . x G x .  / x R x    . x S x .  / . x .
  . x x x .          . . x . .  / . x .    . x . x .  / . L .
                                                        / . . .

  Bishop / Tokin      Pawn / Knight
  x . . x  / . x x   . x .  / x . x
  . x x .  / . T .   . P .  / . . .
  . B . .  / . x .   . . .  / . N .
  . x x .
  x . . x
```

### 8.4 Strategic Themes

- **Capture-based promotion** creates fascinating tactical puzzles. Capturing
  with the wrong piece can weaken your position.
- **Oscillating identity**: A silver captures -> becomes lance -> captures again
  -> becomes silver. This creates unique rhythmic patterns.
- **Extremely small board**: At only 20 squares, games are very short and
  tactical.
- Practically solved by Fairy-Stockfish.

### 8.5 Game Tree Complexity Estimate

| Metric | Estimate |
|---|---|
| Legal positions | ~10^10 (estimated) |
| Avg. branching factor | ~15 |
| Avg. game length | ~20 ply |
| Game tree complexity | ~10^14 (estimated) |
| Status | Practically solvable by engine |

### 8.6 Engine Support

- **Fairy-Stockfish**: Full support. Practically solved.

---

## Complexity Comparison Table

| Variant | Board | Pieces | Drops | Positions (est.) | Tree (est.) | Status |
|---|---|---|---|---|---|---|
| Micro Shogi | 4x5 | 5+5 | Yes | 10^10 | 10^14 | Practically solved |
| Kyoto Shogi | 5x5 | 5+5 | Yes | 10^12 | 10^20 | Practically solved |
| Gardner Minichess | 5x5 | 8+8 | No | 9x10^18 | 10^34 | Weakly solved (draw) |
| Minishogi | 5x5 | 6+6 | Yes | 2.38x10^18 | 10^38 | Unsolved |
| Goro Goro Shogi | 5x6 | 8+8 | Yes | 10^15 | 10^30 | Unsolved |
| Los Alamos Chess | 6x6 | 12+12 | No | 4x10^17 | 10^33 | Partially solved |
| Judkins Shogi | 6x6 | 7+7 | Yes | 10^16 | 10^32 | Unsolved |
| Tori Shogi | 7x7 | 16+16 | Yes | 10^25 | 10^50 | Unsolved |
| *(Standard Chess)* | *8x8* | *16+16* | *No* | *10^46* | *10^123* | *Unsolved* |
| *(Standard Shogi)* | *9x9* | *20+20* | *Yes* | *10^64* | *10^226* | *Unsolved* |

Notes:
- Drops dramatically increase game tree complexity relative to position count.
- Minishogi (with drops) has comparable state space to Gardner (without drops)
  but much higher game tree complexity.
- The "practically solved" status means an engine can play perfect or
  near-perfect play with sufficient compute, not that a full game table exists.

---

## Engine Support Matrix

| Variant | Fairy-Stockfish | Lishogi | PyChess | CuteChess | Other |
|---|---|---|---|---|---|
| Minishogi | Yes (champion) | Yes | Yes | Yes | GNU Shogi |
| Gardner Minichess | Yes | -- | -- | -- | Oracles available |
| Kyoto Shogi | Yes (solved) | Yes | Yes | -- | -- |
| Goro Goro Plus | Yes | -- | Yes | -- | -- |
| Los Alamos Chess | Yes | -- | -- | -- | Green Chess, Jocly |
| Judkins Shogi | Yes | -- | -- | Yes | -- |
| Tori Shogi | Yes | -- | Yes | -- | Tabletopia |
| Micro Shogi | Yes (solved) | -- | -- | -- | -- |

**Fairy-Stockfish** is the universal engine for all these variants. It is open
source and available at: https://github.com/fairy-stockfish/Fairy-Stockfish

For NNUE training and variant-specific neural networks:
https://github.com/fairy-stockfish/variant-nnue-tools

---

## Additional Small Variants of Note

### Petty Chess (5x6)

Invented by B. Walker Watson in 1930. Each side has a King, Queen, Rook,
Bishop, Knight, and 5 Pawns. No pawn double-move. Castling is allowed.

```
  a  b  c  d  e
6 r  n  b  q  k   <- Black
5 p  p  p  p  p
4 .  .  .  .  .
3 .  .  .  .  .
2 P  P  P  P  P
1 R  N  B  Q  K   <- White
```

### Speed Chess (5x6)

Invented by Mr. den Oude in 1988. Similar to Petty Chess but with a
different piece arrangement. Pawns have no double-move.

### Diana Chess (6x6)

Suggested by Hopwood in 1870. No queens on the board. Pawns cannot promote
to queen. No pawn double-move.

```
  a  b  c  d  e  f
6 r  n  b  k  n  r   <- Black (note: no queen)
5 p  p  p  p  p  p
4 .  .  .  .  .  .
3 .  .  .  .  .  .
2 P  P  P  P  P  P
1 R  N  B  K  N  R   <- White
```

### EuroShogi (5x5)

A European variant of minishogi designed for Western players. Supported by
Fairy-Stockfish. Uses standard shogi rules on a 5x5 board with a different
piece set than minishogi.

---

## References and Sources

- Tori Shogi: [PyChess](https://www.pychess.org/variants/torishogi),
  [Chess Variants](https://www.chessvariants.com/shogivariants.dir/tori.html),
  [Gambiter](https://gambiter.com/shogi/variants/Tori_shogi.html),
  [torishogi.com](https://torishogi.com/learn/what-is-tori-shogi/)
- Kyoto Shogi: [PyChess](https://www.pychess.org/variants/kyotoshogi),
  [Lishogi](https://lishogi.org/variant/kyotoshogi),
  [Gambiter](https://gambiter.com/shogi/variants/Kyoto_shogi.html)
- Los Alamos Chess: [Grokipedia](https://grokipedia.com/page/Los_Alamos_chess),
  [Chess Variants](https://www.chessvariants.com/small.dir/losalamos.html),
  [Green Chess](https://greenchess.net/rules.php?v=los-alamos)
- Judkins Shogi: [Chess Variants](https://www.chessvariants.com/shogivariants.dir/judkin.html),
  [Chess Variant Wiki](http://www.eglebbk.dds.nl/program/cvwiki/index.php?title=Judkins_Shogi)
- Goro Goro Shogi: [PyChess](https://www.pychess.org/variants/gorogoroplus),
  [Gambiter](https://gambiter.com/shogi/variants/Goro_goro_shogi.html),
  [Dr Eric Silverman](https://drericsilverman.com/tag/goro-goro-shogi/)
- Minishogi: [PyChess](https://www.pychess.org/variants/minishogi),
  [Lishogi](https://lishogi.org/variant/minishogi),
  [Gambiter](https://gambiter.com/shogi/variants/Minishogi.html)
- Gardner Minichess: [Mhalla & Prost (2013)](https://arxiv.org/abs/1307.7118),
  [Mini Chess Resolution](https://lig-membres.imag.fr/prost/MiniChessResolution/)
- Micro Shogi: [Gambiter](https://gambiter.com/shogi/variants/Micro_shogi.html)
- Minishogi position estimate: [Arxiv (2024)](https://arxiv.org/html/2409.00129v2)
- Game complexity: [Los Alamos solved line (Sayle 2024)](https://journals.sagepub.com/doi/10.3233/ICG-240247)
- Fairy-Stockfish: [GitHub](https://github.com/fairy-stockfish/Fairy-Stockfish),
  [Variants](https://fairy-stockfish.github.io/variants/)
