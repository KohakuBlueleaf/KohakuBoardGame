# Next Game Variant: Analysis and Recommendation

A synthesis of variant game rules, complexity profiles, and NNUE training best
practices, aimed at selecting the best next variant to implement in the MiniChess
engine framework.

---

## Table of Contents

1. [Evaluation Criteria](#1-evaluation-criteria)
2. [Candidate Analysis](#2-candidate-analysis)
   - [Tori Shogi (7x7)](#21-tori-shogi-7x7)
   - [Judkins Shogi (6x6)](#22-judkins-shogi-6x6)
   - [Los Alamos Chess (6x6)](#23-los-alamos-chess-6x6)
   - [Kyoto Shogi (5x5)](#24-kyoto-shogi-5x5)
   - [Goro Goro Shogi (5x6)](#25-goro-goro-shogi-5x6)
   - [Micro Shogi (4x5)](#26-micro-shogi-4x5)
3. [Feature Space Calculations](#3-feature-space-calculations)
4. [Transition Path from Existing Codebase](#4-transition-path-from-existing-codebase)
5. [Top 3 Recommendations with Diagrams](#5-top-3-recommendations-with-diagrams)
6. [Final Ranked Recommendation](#6-final-ranked-recommendation)

---

## 1. Evaluation Criteria

Each variant is evaluated on five axes:

| Axis | What It Measures |
|------|-----------------|
| **NNUE Fit** | How naturally the variant maps to HalfKP features, hand-piece encoding, and the perspective network. Variants with a clear king (royal piece), standard piece-square structure, and optional hand pieces score highest. |
| **Implementation Effort** | How much new C++ code is needed for move generation, promotion, drops, and rule enforcement, relative to what already exists for MiniChess and MiniShogi. |
| **NNUE Value-Add** | Whether the variant is complex enough that an NNUE eval meaningfully outperforms a handcrafted eval. Practically solved games score low here. |
| **Training Feasibility** | Feature space size, data generation speed, and how many positions are needed to train a viable network. Smaller feature spaces need less data. |
| **Game Tree Complexity** | Deeper game trees mean slower datagen but richer strategic content. The sweet spot is large enough to be unsolved but small enough for fast self-play. |

---

## 2. Candidate Analysis

### 2.1 Tori Shogi (7x7)

**Board:** 7x7 | **Pieces per side:** 16 | **Drops:** Yes | **Promotion zone:** Last 2 ranks

#### NNUE Architecture Fit

Tori Shogi maps well to HalfKP with hand pieces. The Phoenix serves as the
royal piece (king-square axis). Piece types are: Phoenix, Falcon, Crane,
Pheasant, Left Quail, Right Quail, Swallow, plus promoted forms Goose and
Eagle -- 9 distinct piece types total (8 non-royal). Left Quail and Right
Quail are genuinely different pieces with asymmetric movement, which the NNUE
feature set handles naturally since each gets its own piece-type index.

Hand pieces include all capturable types (up to 7 types: Falcon, Crane,
Pheasant, Left Quail, Right Quail, Swallow, Goose). The existing hand-piece
feature extension in `features.py` appends `num_colors * num_hand_types`
features to the HalfKP vector, which generalizes directly.

The 180-degree rotational symmetry for black's perspective (standard in shogi
variants) is already implemented in the MiniShogi feature extractor.

**Fit score: Excellent.** The architecture maps with zero structural changes.

#### Implementation Effort

- **Piece movement:** 9 new movement patterns needed, including the complex
  Eagle (ranges diagonally forward + straight backward, steps 1 in all
  directions, up to 2 diagonally backward). The Pheasant's jump-2-forward
  (non-blocking leap) is a new movement class not present in MiniShogi.
  Left/Right Quail asymmetry requires directional range tables.
- **Promotion:** Only Swallow->Goose and Falcon->Eagle. Simpler than MiniShogi
  (which has 4 promoting piece types).
- **Drops:** Standard shogi drop rules with the "two-swallow rule" (no file may
  contain more than 2 friendly swallows) replacing the nifu rule. Swallow-drop
  checkmate is illegal (same as uchifuzume). These are minor modifications to
  the existing drop logic.
- **Board size:** 7x7 requires updating `BOARD_H`/`BOARD_W` constants. The
  existing code uses compile-time defines, so this is trivial.

**Effort: Medium-high.** The Eagle's compound movement and the Pheasant's jump
are the main new work. Roughly 60% of MiniShogi's move-generation logic can
be adapted; the rest is new.

#### NNUE Value-Add

With a game tree complexity of ~10^50 (between checkers and chess), Tori Shogi
is firmly unsolved and far too complex for tablebases or brute-force search.
The asymmetric quails, the Falcon-to-Eagle promotion timing, and the 8-swallow
pawn structure create rich positional concepts that a handcrafted eval will
struggle to capture. NNUE should provide substantial Elo gains.

**Value-add: High.** This is the strongest case for NNUE among all candidates.

#### Training Feasibility

The HalfKP feature space is large (see Section 3) at 125,440 features, but
with only ~30-35 active features per position, sparse mode (`EmbeddingBag`)
is highly effective. The network requires roughly 50-200M training positions
for a 128-accumulator architecture. At an estimated ~2,000-4,000 games/minute
on a modern CPU (slower than MiniShogi due to higher branching factor and
longer games), generating 100M positions takes approximately 8-16 hours.

**Feasibility: Good.** Larger feature space demands more data, but sparse
training keeps GPU costs manageable.

#### Datagen Speed

Average game length ~60 ply with branching factor ~35-45. Each game yields
~30 quiet training positions (after filtering checks and captures). Datagen
is roughly 3-5x slower per position than MiniShogi due to the larger board
and longer games.

---

### 2.2 Judkins Shogi (6x6)

**Board:** 6x6 | **Pieces per side:** 7 | **Drops:** Yes | **Promotion zone:** Last 2 ranks

#### NNUE Architecture Fit

Judkins Shogi is essentially standard shogi minus the Lance, played on 6x6.
It has the same piece types as MiniShogi plus Knight -- 7 base types (King,
Rook, Bishop, Gold, Silver, Knight, Pawn) with 4 promoted forms (+R, +B, +S,
+N, +P = Gold movement), yielding ~12 piece types total (11 non-royal). This
is almost identical to the MiniShogi configuration (11 piece types, 10
non-royal, 5 hand types) but with the Knight added, making it 13 types / 12
non-royal / 6 hand types.

The HalfKP + hand feature encoding works identically to MiniShogi. The
perspective flip uses 180-degree rotation as in all shogi variants.

**Fit score: Excellent.** Near-identical to MiniShogi's NNUE configuration.

#### Implementation Effort

- **Piece movement:** All piece types already exist in MiniShogi except the
  Knight. The shogi Knight (2 forward + 1 sideways, no backward) is simple
  to implement. Promoted Knight moves like Gold, which is already coded.
- **Promotion:** Same rules as MiniShogi, extended to Knight. The Knight
  cannot be dropped on the last 2 ranks (where it would have no legal move).
  This is a minor addition to the drop-restriction logic.
- **Drops:** Identical to MiniShogi. The nifu, uchifuzume, and rank
  restrictions generalize directly.
- **Board size:** 6x6 requires updating `BOARD_H=6`, `BOARD_W=6`.

**Effort: Low.** This is by far the easiest variant to implement. Roughly
85-90% of MiniShogi code can be reused directly; only the Knight piece type
and the 6x6 board constants need to be added.

#### NNUE Value-Add

Game tree complexity ~10^32 -- comparable to Los Alamos Chess and well above
the "practically solvable" threshold. With drops, the positional complexity
is high: piece interactions, promotion timing, drop tactics, and king safety
all benefit from learned evaluation. A handcrafted eval can cover material
and basic PSTs, but the knight's interaction with the promotion zone and
drop combinations are hard to hand-tune.

**Value-add: Medium-high.** Meaningful NNUE gains expected, though less
dramatic than Tori Shogi due to the smaller search space.

#### Training Feasibility

HalfKP feature space of 51,840 (see Section 3) is moderate. A 128-accumulator
network has ~6.6M parameters and needs 20-60M training positions. Datagen speed
is similar to MiniShogi (branching factor ~35, game length ~40 ply), yielding
~4,000-8,000 games/minute. Generating 50M positions takes roughly 2-4 hours.

**Feasibility: Excellent.** Fast datagen, moderate feature space.

#### Datagen Speed

Average game length ~40 ply, branching factor ~35. Each game produces ~20
quiet positions. Speed is comparable to MiniShogi -- roughly 1.5x slower due
to the extra rank/file.

---

### 2.3 Los Alamos Chess (6x6)

**Board:** 6x6 | **Pieces per side:** 12 | **Drops:** No | **Promotion:** Last rank (Q/R/N)

#### NNUE Architecture Fit

Los Alamos Chess is a pure chess variant with no drops and no hand pieces.
Piece types: King, Queen, Rook, Knight, Pawn -- only 5 types (4 non-royal).
No bishops. No promoted pieces beyond standard pawn promotion (the promoted
piece replaces the pawn with a new piece type, which is already one of the
existing types).

HalfKP works cleanly. The feature set is compact: 4 non-royal piece types
on a 36-square board with 36 king squares. No hand features needed. The
perspective flip is vertical mirroring (same as MiniChess).

**Fit score: Good.** Simple and clean mapping, but the lack of hand pieces
means the hand-feature extension goes unused.

#### Implementation Effort

- **Piece movement:** King, Queen, Rook, Knight, Pawn -- all already
  implemented in MiniChess. No bishop means one fewer piece, not one more.
- **Promotion:** Pawn promotes on rank 6 to Queen, Rook, or Knight. This is
  simpler than MiniChess promotion (which includes Bishop).
- **Special rules:** No castling, no en passant, no double pawn move. These
  are simplifications -- less code than MiniChess, not more.
- **Board size:** 6x6 requires `BOARD_H=6`, `BOARD_W=6`.

**Effort: Very low.** This is a strict subset of MiniChess functionality.
Nearly 95% of the MiniChess code applies directly; the only changes are
removing Bishop, removing castling/en-passant, removing pawn double-move,
and adjusting the board to 6x6.

#### NNUE Value-Add

Game tree complexity ~10^33. The game has been partially solved (after 1.e3,
Black wins in 21 moves). The absence of bishops makes the positional
landscape simpler -- no color complexes, no bishop pair dynamics. The
strategic themes (knight dominance, queen centrality, pawn structure) are
relatively straightforward to encode in a handcrafted eval with good PSTs.

**Value-add: Low-medium.** NNUE will help, but the marginal improvement over
a well-tuned handcrafted eval is smaller than for shogi variants with drops.

#### Training Feasibility

HalfKP feature space of only 10,368 (see Section 3) -- very compact. A
128-accumulator network has ~1.3M parameters and needs only 5-15M training
positions. No drops means faster move generation and shorter average game
length. Datagen at ~10,000+ games/minute. Generating 10M positions takes
under 1 hour.

**Feasibility: Excellent.** The fastest variant to train by a wide margin.

#### Datagen Speed

Average game length ~50 ply, branching factor ~22 (lowest of all candidates).
No drops means simpler and faster move generation. Each game yields ~25 quiet
positions. This is the fastest datagen of all candidates.

---

### 2.4 Kyoto Shogi (5x5)

**Board:** 5x5 | **Pieces per side:** 5 | **Drops:** Yes | **Unique:** Pieces flip identity every move

#### NNUE Architecture Fit

Kyoto Shogi's defining mechanic -- every piece (except King) flips between
two identities after each move -- creates an unusual NNUE modeling challenge.
The piece types are: King, Tokin/Lance, Silver/Bishop, Gold/Knight, Pawn/Rook.
Each non-royal piece is effectively two piece types that alternate. This can
be modeled as 9 distinct piece types (King + 8 faces), 8 non-royal, similar
to how MiniShogi handles promoted pieces.

However, the flip mechanic means that dropping a captured piece allows the
player to choose which face is up. This is different from standard shogi
drops (where pieces are always dropped unpromoted). The NNUE feature encoding
handles this naturally -- the piece on the board is whatever face is showing,
regardless of how it got there.

Hand pieces are the 4 non-royal tile types (each can be dropped as either
face), giving 4 hand types. But the drop-choice mechanic means the engine
must generate drop moves for both faces of each hand tile, doubling the
effective drop branching. The NNUE features only see the board state after
the drop, so no architectural change is needed.

**Fit score: Good.** The feature encoding works, but the flip mechanic's
strategic implications may be hard for a small network to learn.

#### Implementation Effort

- **Piece movement:** 9 distinct movement patterns, including Bishop and Rook
  (ranging pieces) and Knight (jumping piece). Many of these already exist in
  MiniShogi/MiniChess.
- **Flip mechanic:** This is entirely new. After every non-King move, the
  piece must be flipped. This requires a flip-table lookup in the move-apply
  function and changes the invariant that pieces on the board always have a
  fixed type until promotion.
- **Drops:** Captured pieces can be dropped with either face up. The drop
  move generator must enumerate both options for each hand tile. This is a
  moderate addition to the drop logic.
- **No promotion zone:** The standard promotion-zone logic is unused.
  Instead, the flip is automatic and unconditional.
- **Stuck pieces:** Unlike standard shogi, a piece can be moved to a square
  where it has no legal moves on the next turn (it can only be rescued by
  capture). This removes a validation check from move generation.

**Effort: Medium.** The flip mechanic and dual-face drops are conceptually
simple but touch many parts of the codebase (move generation, move application,
state display, SFEN parsing).

#### NNUE Value-Add

Game tree complexity is only ~10^20, and Kyoto Shogi is practically solvable
by Fairy-Stockfish with sufficient compute. Games are very short (~25 ply).
The "identity chaos" creates a volatile evaluation landscape that may
actually hurt NNUE training -- positions change character so rapidly that
learned positional patterns have short shelf lives within a game.

**Value-add: Low.** The game is too simple and volatile for NNUE to provide
large gains over a competent handcrafted eval. Alpha-beta search depth alone
can compensate.

#### Training Feasibility

HalfKP feature space of 20,000 (see Section 3) -- small. Training data
requirements are modest (5-10M positions). However, the volatile nature of
positions may require more data to learn stable patterns. Datagen is fast
(short games, small board).

**Feasibility: Good.** Easy to train, but the payoff is questionable.

---

### 2.5 Goro Goro Shogi (5x6)

**Board:** 5x6 | **Pieces per side:** 8 (+ 2 in hand for Plus variant) | **Drops:** Yes | **Promotion zone:** Last 2 ranks

#### NNUE Architecture Fit

Goro Goro Plus has piece types: King, Gold, Silver, Pawn, Lance, Knight,
plus promoted Silver and promoted Pawn (both move like Gold). That is 8 piece
types (7 non-royal) with 4 hand types (Silver, Pawn, Lance, Knight). No
long-range pieces (no Rook or Bishop) on the board.

The HalfKP encoding works directly. The board dimensions (5x6=30 squares) are
close to MiniShogi (5x5=25), and the hand-piece infrastructure from MiniShogi
applies with minor adjustments. The 180-degree rotational perspective flip is
standard.

**Fit score: Good.** Clean mapping, but the variant's simplicity limits the
NNUE architecture's utility.

#### Implementation Effort

- **Piece movement:** King, Gold, Silver, Pawn are already in MiniShogi.
  Lance and Knight are new but straightforward (Lance = forward range,
  Knight = 2-forward-1-sideways jump).
- **Promotion:** Silver, Pawn, Lance, Knight all promote to Gold movement.
  Same mechanic as MiniShogi.
- **Drops:** Standard shogi drop rules. Lance and Knight have rank
  restrictions (cannot drop where they would have no legal move). This is
  the same restriction logic as Judkins Shogi.
- **Board size:** 5x6 = `BOARD_H=6`, `BOARD_W=5`. Same width as MiniShogi,
  one extra rank.
- **Starting hand pieces:** The Plus variant starts with Lance + Knight in
  hand. This requires a small change to the initial-state setup.

**Effort: Low-medium.** Very similar to MiniShogi. The main new work is
Lance and Knight movement/promotion/drop-restriction, plus the 5x6 board.

#### NNUE Value-Add

Game tree complexity ~10^30 -- solidly unsolved. However, the lack of
long-range pieces (no Rook or Bishop on the board) makes positions more
tactical and local. Gold and Silver interactions, pawn structure with 3
pawns per side, and drop tactics provide meaningful complexity, but the
strategic depth is shallower than Judkins or Tori Shogi.

**Value-add: Medium.** NNUE will help, especially with drop evaluation and
promotion timing, but the positional landscape is relatively simple.

#### Training Feasibility

HalfKP feature space of 25,200 (see Section 3). A 128-accumulator network
has ~3.2M parameters and needs 10-30M training positions. Datagen speed is
similar to MiniShogi. Fast and feasible.

**Feasibility: Excellent.**

---

### 2.6 Micro Shogi (4x5)

**Board:** 4x5 | **Pieces per side:** 5 | **Drops:** Yes | **Unique:** Promotion on capture (not zone entry)

#### NNUE Architecture Fit

Micro Shogi has 5 base piece types (King, Gold, Silver, Bishop, Pawn) with
4 promoted forms (Rook, Lance, Tokin, Knight), yielding 9 piece types
(8 non-royal). The capture-based promotion mechanic (pieces flip when they
capture) does not affect NNUE feature encoding -- the board state is the
board state regardless of how pieces transformed.

The 4x5 board (20 squares) is very small. HalfKP features would be compact
but with only ~8 non-king pieces maximum on the board, the active feature
count is very low.

**Fit score: Good.** The encoding works, but the game is too small to
justify it.

#### Implementation Effort

- **Piece movement:** 9 movement patterns, most already in MiniShogi.
- **Capture-promotion:** Entirely new mechanic. The move-apply function
  must flip the capturing piece. This is simpler than zone-based promotion
  but conceptually different.
- **Board size:** 4x5 = `BOARD_H=5`, `BOARD_W=4`.

**Effort: Low-medium.** The capture-promotion mechanic is the main novelty.

#### NNUE Value-Add

Game tree complexity ~10^14 -- practically solvable by engine. Only ~10^10
legal positions. This is far too simple for NNUE to matter.

**Value-add: Very low.** Brute-force search solves it. NNUE is unnecessary.

---

## 3. Feature Space Calculations

### Formulas

```
num_squares       = board_h * board_w
num_piece_features = num_colors * num_pt_no_king * num_squares
                   = 2 * num_pt_no_king * num_squares

HalfKP size       = num_squares * num_piece_features
                   = num_squares * 2 * num_pt_no_king * num_squares
                   = 2 * num_pt_no_king * num_squares^2

Hand feature size  = num_colors * num_hand_types
                   = 2 * num_hand_types

Total input size   = HalfKP size + Hand feature size

Params (128 accum) ~ total_input_size * 128  (first layer dominates)
```

### Per-Variant Calculations

#### Tori Shogi (7x7)

| Parameter | Value |
|-----------|-------|
| `board_h` | 7 |
| `board_w` | 7 |
| `num_squares` | 49 |
| `num_piece_types` | 9 (Phoenix, Falcon, Crane, Pheasant, LQuail, RQuail, Swallow, Goose, Eagle) |
| `num_pt_no_king` | 8 |
| `num_hand_types` | 7 (Falcon, Crane, Pheasant, LQuail, RQuail, Swallow, Goose) |
| `num_piece_features` | 2 * 8 * 49 = 784 |
| **HalfKP size** | 49 * 784 = **38,416** |
| `hand_feature_size` | 2 * 7 = 14 |
| **Total input size** | **38,430** |
| **Params (128 accum)** | ~4.9M |
| **Max active features** | ~35 (up to 31 pieces on board + hand counts) |
| **EmbeddingBag sparse?** | Yes -- strongly recommended. 35 active out of 38K. |
| **Training data needed** | 50-200M positions |

> Note: If Goose (promoted Swallow) is not kept in hand and can only exist on
> the board, num_hand_types drops to 6 and hand_feature_size to 12. The
> standard Tori Shogi rules allow dropping captured Geese as Swallows (they
> revert), so the hand type is Swallow only. Revised: **num_hand_types = 6**
> (Falcon, Crane, Pheasant, LQuail, RQuail, Swallow), **hand_feature_size = 12**,
> **total = 38,428**.

#### Judkins Shogi (6x6)

| Parameter | Value |
|-----------|-------|
| `board_h` | 6 |
| `board_w` | 6 |
| `num_squares` | 36 |
| `num_piece_types` | 13 (King, Rook, Bishop, Gold, Silver, Knight, Pawn, +R, +B, +S, +N, +P) |
| `num_pt_no_king` | 12 |
| `num_hand_types` | 6 (Rook, Bishop, Gold, Silver, Knight, Pawn) |
| `num_piece_features` | 2 * 12 * 36 = 864 |
| **HalfKP size** | 36 * 864 = **31,104** |
| `hand_feature_size` | 2 * 6 = 12 |
| **Total input size** | **31,116** |
| **Params (128 accum)** | ~4.0M |
| **Max active features** | ~26 (up to 12 non-king pieces on board + hand counts) |
| **EmbeddingBag sparse?** | Yes -- recommended. 26 active out of 31K. |
| **Training data needed** | 20-60M positions |

#### Los Alamos Chess (6x6)

| Parameter | Value |
|-----------|-------|
| `board_h` | 6 |
| `board_w` | 6 |
| `num_squares` | 36 |
| `num_piece_types` | 5 (King, Queen, Rook, Knight, Pawn) |
| `num_pt_no_king` | 4 |
| `num_hand_types` | 0 |
| `num_piece_features` | 2 * 4 * 36 = 288 |
| **HalfKP size** | 36 * 288 = **10,368** |
| `hand_feature_size` | 0 |
| **Total input size** | **10,368** |
| **Params (128 accum)** | ~1.3M |
| **Max active features** | ~22 (up to 22 non-king pieces on board) |
| **EmbeddingBag sparse?** | Optional. 22 active out of 10K -- sparse helps but dense is also viable. |
| **Training data needed** | 5-15M positions |

#### Kyoto Shogi (5x5)

| Parameter | Value |
|-----------|-------|
| `board_h` | 5 |
| `board_w` | 5 |
| `num_squares` | 25 |
| `num_piece_types` | 9 (King, Tokin, Lance, Silver, Bishop, Gold, Knight, Pawn, Rook) |
| `num_pt_no_king` | 8 |
| `num_hand_types` | 4 (4 tile types, each droppable as either face) |
| `num_piece_features` | 2 * 8 * 25 = 400 |
| **HalfKP size** | 25 * 400 = **10,000** |
| `hand_feature_size` | 2 * 4 = 8 |
| **Total input size** | **10,008** |
| **Params (128 accum)** | ~1.3M |
| **Max active features** | ~16 (up to 8 non-king pieces + hand counts) |
| **EmbeddingBag sparse?** | Optional. Small enough for dense mode. |
| **Training data needed** | 5-10M positions |

#### Goro Goro Plus (5x6)

| Parameter | Value |
|-----------|-------|
| `board_h` | 6 |
| `board_w` | 5 |
| `num_squares` | 30 |
| `num_piece_types` | 8 (King, Gold, Silver, Pawn, Lance, Knight, +S, +P) |
| `num_pt_no_king` | 7 |
| `num_hand_types` | 4 (Silver, Pawn, Lance, Knight) |
| `num_piece_features` | 2 * 7 * 30 = 420 |
| **HalfKP size** | 30 * 420 = **12,600** |
| `hand_feature_size` | 2 * 4 = 8 |
| **Total input size** | **12,608** |
| **Params (128 accum)** | ~1.6M |
| **Max active features** | ~24 (up to 15 non-king pieces + hand counts) |
| **EmbeddingBag sparse?** | Optional. Dense mode is viable. |
| **Training data needed** | 10-30M positions |

#### Micro Shogi (4x5)

| Parameter | Value |
|-----------|-------|
| `board_h` | 5 |
| `board_w` | 4 |
| `num_squares` | 20 |
| `num_piece_types` | 9 (King, Gold, Silver, Bishop, Pawn, Rook, Lance, Tokin, Knight) |
| `num_pt_no_king` | 8 |
| `num_hand_types` | 4 |
| `num_piece_features` | 2 * 8 * 20 = 320 |
| **HalfKP size** | 20 * 320 = **6,400** |
| `hand_feature_size` | 2 * 4 = 8 |
| **Total input size** | **6,408** |
| **Params (128 accum)** | ~0.8M |
| **Max active features** | ~14 |
| **EmbeddingBag sparse?** | No. Dense mode is fine. |
| **Training data needed** | 3-8M positions |

### Summary Table

| Variant | Board | HalfKP Size | Hand Feat | Total Input | Params (128) | Data Needed |
|---------|-------|------------|-----------|-------------|-------------|-------------|
| Micro Shogi | 4x5 | 6,400 | 8 | 6,408 | 0.8M | 3-8M |
| Kyoto Shogi | 5x5 | 10,000 | 8 | 10,008 | 1.3M | 5-10M |
| Los Alamos | 6x6 | 10,368 | 0 | 10,368 | 1.3M | 5-15M |
| Goro Goro+ | 5x6 | 12,600 | 8 | 12,608 | 1.6M | 10-30M |
| Judkins | 6x6 | 31,104 | 12 | 31,116 | 4.0M | 20-60M |
| Tori Shogi | 7x7 | 38,416 | 12 | 38,428 | 4.9M | 50-200M |
| *(MiniShogi)* | *5x5* | *25,000* | *10* | *25,010* | *3.2M* | *15-50M* |
| *(MiniChess)* | *6x5* | *15,000* | *0* | *15,000* | *1.9M* | *10-30M* |

---

## 4. Transition Path from Existing Codebase

The MiniChess project currently supports two games: MiniChess (6x5, no drops)
and MiniShogi (5x5, with drops). The following analysis identifies what can be
reused and what must be written from scratch for each variant.

### 4.1 Code That Can Be Reused for Any Variant

These components are game-agnostic or parameterized:

| Component | Location | Reusability |
|-----------|----------|-------------|
| NNUE inference (`nnue.hpp`, `compute_quant.hpp`) | `src/nnue/` | 100% -- parameterized by feature size |
| NNUE training loop (`trainer.py`) | `nnue-train/` | 100% -- game-agnostic |
| Feature extraction (`features.py`) | `nnue-train/` | 100% -- driven by `game_config` dict |
| Game config system (`game_config.py`) | `nnue-train/` | 100% -- add a new dict entry |
| Dataset / data loader (`dataset.py`) | `nnue-train/` | 100% -- reads board+hand from binary |
| Datagen framework (`datagen.cpp`) | `src/` | 90% -- board serialization is generic |
| UBGI protocol (`ubgi.cpp`) | `src/ubgi/` | 95% -- move encoding may need extension |
| Search (alpha-beta, TT, etc.) | `src/search/` | 100% -- game-agnostic |
| GUI renderer | `gui/` | 80% -- board dimensions are configurable |
| Export / quantization (`export.py`) | `nnue-train/` | 100% -- architecture-agnostic |

### 4.2 Per-Variant New Code

#### For Judkins Shogi (Easiest)

| Task | Effort | Notes |
|------|--------|-------|
| `src/games/judkins/config.hpp` | Trivial | Copy MiniShogi config, set 6x6, add Knight |
| `src/games/judkins/state.hpp/cpp` | Low | Copy MiniShogi, add Knight movement + promotion |
| Knight move generation | Low | 2 forward + 1 sideways, no backward (shogi knight) |
| Knight drop restriction | Trivial | Cannot drop on last 2 ranks |
| Knight promotion to Gold | Trivial | Same mechanic as Silver/Pawn promotion |
| Initial position setup | Trivial | Set K-G-S-N-B-R arrangement |
| `game_config.py` entry | Trivial | Add "judkins" dict |
| Handcrafted eval PSTs | Low | Adjust existing MiniShogi PSTs for 6x6 |
| **Total new lines (est.)** | **~200-400** | |

#### For Tori Shogi (Moderate)

| Task | Effort | Notes |
|------|--------|-------|
| `src/games/tori/config.hpp` | Low | New piece type enum (9 types) |
| `src/games/tori/state.hpp/cpp` | Medium-high | All-new piece movements |
| Phoenix movement | Trivial | Same as King |
| Falcon movement | Low | All directions except straight back |
| Crane movement | Low | Forward, backward, diagonal (no sideways) |
| Pheasant movement | Medium | Jump-2-forward (new movement class) + 1-diag-back |
| Left/Right Quail movement | Medium | Asymmetric ranging + stepping |
| Swallow movement | Trivial | 1 step forward only |
| Goose movement | Medium | Jump-2-diag-forward, jump-2-straight-back |
| Eagle movement | High | Compound: range-diag-fwd, range-straight-back, step-all, 2-diag-back |
| Promotion logic | Low | Only Swallow->Goose, Falcon->Eagle |
| Two-swallow drop rule | Low | Check file count instead of nifu |
| Swallow checkmate restriction | Low | Same as uchifuzume with different piece |
| Initial position setup | Low | 7x7 with 16 pieces per side |
| `game_config.py` entry | Trivial | Add "tori" dict |
| Handcrafted eval | Medium | New PSTs for all 9 piece types |
| **Total new lines (est.)** | **~800-1200** | |

#### For Los Alamos Chess (Very Easy)

| Task | Effort | Notes |
|------|--------|-------|
| `src/games/losalamos/config.hpp` | Trivial | Copy MiniChess config, set 6x6, remove Bishop |
| `src/games/losalamos/state.hpp/cpp` | Low | Copy MiniChess, remove Bishop/castling/en-passant/double-move |
| Remove Bishop | Trivial | Delete from piece enum and move tables |
| Remove castling | Trivial | Delete castling code |
| Remove en passant | Trivial | Delete en passant code |
| Remove pawn double move | Trivial | Delete double-move code |
| Initial position setup | Trivial | R-N-Q-K-N-R arrangement |
| `game_config.py` entry | Trivial | Add "losalamos" dict |
| Handcrafted eval PSTs | Low | Adjust MiniChess PSTs for 6x6, no bishop |
| **Total new lines (est.)** | **~100-200** | |

---

## 5. Top 3 Recommendations with Diagrams

### Recommendation #1: Judkins Shogi (6x6)

The best balance of implementation effort, NNUE value, and strategic depth.

```
  a  b  c  d  e  f
6 K  G  S  N  B  R   <- Gote (White)
5 p  .  .  .  .  .
4 .  .  .  .  .  .
3 .  .  .  .  .  .
2 .  .  .  .  .  P
1 r  b  n  s  g  k   <- Sente (Black)
```

Piece types (with promoted forms):

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

**Why #1:** Judkins Shogi is the natural next step from MiniShogi. It uses the
same piece set plus Knight, on a moderately larger board. The implementation
effort is minimal (~200-400 lines of new code), the NNUE feature space (31K)
is large enough for meaningful learned evaluation, and the game tree complexity
(~10^32) ensures the variant is firmly unsolved. The drop mechanic exercises
the hand-piece feature code that already exists. The Knight piece type adds
genuine new strategic content (forks, promotion-zone threats) without
requiring any architectural changes to the NNUE pipeline.

---

### Recommendation #2: Tori Shogi (7x7)

The most ambitious choice -- highest strategic ceiling and NNUE payoff.

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
```

Unique pieces:

```
  PHOENIX (Royal)         FALCON                  CRANE
  . x x x .              . x x x .               . x . x .
  . x P x .              . x F x .               . x C x .
  . x x x .              . . . . .               . x . x .

  PHEASANT                LEFT QUAIL              RIGHT QUAIL
  . . J . .
  . . . . .              . . | . .               . . | . .
  . . H . .              . . | . .               . . | . .
  . x . x .              . . Q . .               . . Q . .
                           x . . . \               / . . . x
  J = jump-to square       . . . . .\             /. . . . .

  SWALLOW                 GOOSE (promoted Sw)     EAGLE (promoted Fa)
  . . x . .              J . . . J               \ . | . /
  . . S . .              . . . . .               .\.x./..
  . . . . .              . . G . .               x x E x x
                           . . . . .              .x.x.x..
                           . . J . .              x . x . x
```

**Why #2:** Tori Shogi offers the highest game tree complexity (~10^50) of all
candidates, ensuring NNUE provides maximal value over handcrafted evaluation.
The asymmetric quails, the 8-swallow structure, and the Falcon-to-Eagle
promotion create strategic depth unmatched by other small variants. The
implementation cost is higher (~800-1200 lines) due to the Eagle's compound
movement and the Pheasant's jump, but the codebase's modular game architecture
makes this manageable. The 7x7 board is a meaningful step up from 5x5/6x6
without being unwieldy. This is the right choice for a team willing to invest
more implementation time for a richer game.

---

### Recommendation #3: Los Alamos Chess (6x6)

The quick-win choice -- minimal effort with historical significance.

```
  a  b  c  d  e  f
6 r  n  q  k  n  r   <- Black
5 p  p  p  p  p  p
4 .  .  .  .  .  .
3 .  .  .  .  .  .
2 P  P  P  P  P  P
1 R  N  Q  K  N  R   <- White
```

Pieces (standard chess minus Bishop):

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
```

**Why #3:** Los Alamos Chess can be implemented in under 200 lines of new code,
almost entirely by removing features from MiniChess (no Bishop, no castling, no
en passant, no double pawn move). It provides a clean 6x6 chess variant for
testing the engine's scalability to different board sizes. The compact HalfKP
space (10K features) means NNUE training completes in under an hour. The
historical significance (first computer chess game, MANIAC I, 1956) adds
interest. The main weakness is that the game's strategic depth is limited --
no bishops means no color-complex play, and the NNUE improvement over
handcrafted eval will be modest.

---

## 6. Final Ranked Recommendation

| Rank | Variant | Score | Rationale |
|------|---------|-------|-----------|
| **1** | **Judkins Shogi** | **9.0/10** | Best overall balance. Lowest effort of any shogi variant, direct code reuse from MiniShogi, meaningful NNUE payoff, unsolved complexity. The natural evolutionary step. |
| 2 | Tori Shogi | 8.0/10 | Highest ceiling. Best NNUE value-add, richest strategic content, but 3-4x more implementation work than Judkins. Best second variant after Judkins is stable. |
| 3 | Los Alamos Chess | 7.0/10 | Quick win. Trivial implementation, fast training, but limited NNUE value-add and no drop mechanic. Good for testing infrastructure scalability. |
| 4 | Goro Goro Plus | 6.0/10 | Solid middle ground, but offers less strategic novelty than Judkins and less complexity than Tori. Teaching variant pedigree limits competitive interest. |
| 5 | Kyoto Shogi | 4.5/10 | Interesting flip mechanic, but practically solvable. Low NNUE value-add. The flip logic touches many code paths for minimal payoff. |
| 6 | Micro Shogi | 3.0/10 | Too small. Practically solved. NNUE is unnecessary. Only interesting as a toy/test variant. |

### The Winner: Judkins Shogi

**Judkins Shogi is the clear recommendation.** It maximizes the ratio of
strategic depth to implementation effort. The reasoning:

1. **Minimal new code.** The only genuinely new piece is the shogi Knight (a
   jumping piece with 2 target squares). Everything else -- King, Gold, Silver,
   Bishop, Rook, Pawn, all promoted forms, drop rules, promotion zones -- is
   directly inherited from MiniShogi. The 6x6 board is a constant change.

2. **Exercises the full NNUE pipeline.** With 31K HalfKP features + hand pieces,
   Judkins Shogi sits in the sweet spot where HalfKP provides measurable gains
   over PieceSquare features, and sparse training with `EmbeddingBag` is
   clearly beneficial. The 128-accumulator network (~4M params) needs 20-60M
   training positions -- substantial enough to validate the training pipeline at
   scale, but achievable in a few hours of datagen.

3. **Unsolved complexity.** At ~10^32 game tree complexity, no engine will
   brute-force this variant. NNUE-guided search will meaningfully outperform
   handcrafted evaluation, providing a clear demonstration of the NNUE
   infrastructure's value.

4. **Smooth transition path.** The game config system (`game_config.py`) already
   supports adding new games via a dictionary entry. The C++ side follows the
   pattern of `src/games/minishogi/` -- copy the directory, adjust the config
   header, add the Knight, and update the initial position. No architectural
   changes to the search, NNUE, datagen, or training code are needed.

5. **Community and tooling.** Judkins Shogi is supported by Fairy-Stockfish
   (for reference engine comparison), CuteChess (for automated testing), and
   has an established rule set with no ambiguities.

**Recommended implementation order:**

1. Implement Judkins Shogi (1-2 days)
2. Generate 30M training positions with handcrafted eval (~3 hours)
3. Train initial NNUE (128 accum, HalfKP+hand) (~2 hours on GPU)
4. Iterate: generate 50M positions with NNUE eval, retrain (~6 hours total)
5. Validate via self-play tournament against handcrafted eval
6. (Optional) Begin Tori Shogi implementation as the next variant

---

## References

- Variant rules and complexity: `docs/seed_variants.md`
- NNUE training practices: `docs/seed_nnue_training.md`
- Existing game configs: `nnue-train/game_config.py`
- Existing feature extraction: `nnue-train/features.py`
- MiniShogi C++ config: `src/games/minishogi/config.hpp`
- MiniChess C++ config: `src/games/minichess/config.hpp`
- Fairy-Stockfish (reference engine): https://github.com/fairy-stockfish/Fairy-Stockfish
