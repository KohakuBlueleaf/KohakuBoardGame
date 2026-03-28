# Hand-Crafted Evaluation (HCE) Design for Chess & Shogi

Comprehensive reference for improving evaluation functions in our engine.
Covers standard chess (8x8), chess variants (5x6, 6x6), and shogi variants.

---

## Table of Contents

1. [Architecture: Tapered Eval](#1-architecture-tapered-eval)
2. [Material Values](#2-material-values)
3. [Piece-Square Tables](#3-piece-square-tables)
4. [Passed Pawns](#4-passed-pawns)
5. [Pawn Structure](#5-pawn-structure)
6. [King Safety](#6-king-safety)
7. [Piece Mobility](#7-piece-mobility)
8. [Bishop Pair](#8-bishop-pair)
9. [Rook on Open File](#9-rook-on-open-file)
10. [Outposts](#10-outposts)
11. [Threats](#11-threats)
12. [Endgame Knowledge](#12-endgame-knowledge)
13. [Shogi-Specific Eval](#13-shogi-specific-eval)
14. [Elo Impact Estimates](#14-elo-impact-estimates)
15. [Our Current State & Upgrade Plan](#15-our-current-state--upgrade-plan)

---

## 1. Architecture: Tapered Eval

The most important architectural decision for HCE. Every strong classical engine
(Stockfish, Fruit, Crafty) uses this.

### Concept

Every eval term produces **two scores**: middlegame (MG) and endgame (EG).
A game-phase value interpolates between them:

```
phase = remaining_piece_material / max_material   // 256 = opening, 0 = endgame
final = (mg * phase + eg * (256 - phase)) / 256
```

### Phase Weights (Stockfish)

| Piece  | Phase Weight |
|--------|-------------|
| Pawn   | 0           |
| Knight | 1           |
| Bishop | 1           |
| Rook   | 2           |
| Queen  | 4           |

Total starting phase = 4 knights + 4 bishops + 4 rooks + 2 queens = 24.
Normalize to 0-256 range for interpolation.

### Packed Score Trick (Fruit/Stockfish)

Pack MG and EG into a single 32-bit int. Addition/subtraction propagate
both scores simultaneously. Only unpack at the end:

```c
typedef int Score;
#define S(mg, eg) ((int)((unsigned)(mg) << 16) + (eg))
#define mg_value(s) ((int16_t)((uint16_t)((s + 0x8000) >> 16)))
#define eg_value(s) ((int16_t)((uint16_t)(s & 0xFFFF)))

// All eval terms just add Score values:
score += S(10, 5);  // adds 10 to MG, 5 to EG simultaneously
```

**Cost: zero.** Same number of additions, one division at the end.

### Why This Matters for Us

Our current eval uses a single score with no phase distinction. The king PST
encourages the king to hide (good for middlegame) but doesn't centralize in
endgame. Passed pawn bonuses should be much larger in endgame. Rook mobility
matters more in endgame. All of this requires tapered eval.

---

## 2. Material Values

### Chess (Stockfish Internal Units / Approximate Centipawns)

| Piece  | MG (cp) | EG (cp) | Our Current |
|--------|---------|---------|-------------|
| Pawn   | 100     | 130     | 100         |
| Knight | 310-325 | 320-340 | 320         |
| Bishop | 330-340 | 340-360 | 330         |
| Rook   | 490-510 | 530-560 | 500         |
| Queen  | 950-1000| 1020-1060| 900        |

Key: rook and queen gain value in endgame (open board), knight slightly loses.

### PeSTO Tuned Values (widely used baseline)

MG: P=82, N=337, B=365, R=477, Q=1025
EG: P=94, N=281, B=297, R=512, Q=936

Note bishop > knight by ~30cp consistently.

### Shogi (Traditional / Bonanza-Style)

| Piece       | Board Value | Promoted | Hand Multiplier |
|-------------|------------|----------|-----------------|
| Pawn        | 100        | 420 (Tokin) | 1.2x         |
| Lance       | 250-300    | 400      | 1.15x           |
| Knight      | 350-400    | 420      | 1.15x           |
| Silver      | 500-550    | 520      | 1.1x            |
| Gold        | 550-600    | N/A      | 1.1x            |
| Bishop      | 800-900    | 1050 (Horse) | 1.15x       |
| Rook        | 1000-1100  | 1250 (Dragon) | 1.15x      |

**Critical**: pieces in hand are worth MORE than on board (drop flexibility).

---

## 3. Piece-Square Tables

### Design Principles

- Separate MG and EG tables for each piece (tapered)
- White perspective (row 0 = rank 8); mirror for Black via `7 - row`
- Updated incrementally on make/unmake: `score -= pst[piece][old_sq]; score += pst[piece][new_sq]`

### Key Guidelines (centipawns)

**Pawns:** Center control (d4/e4: +10-20), advancement (+5 per rank),
edge penalty (-5 to -10). EG table strongly rewards advancement (rank 7: +50-100).

**Knights:** Strong center preference (+15-25 on d4/e5), severe edge/corner
penalty (-20 to -50). "A knight on the rim is dim."

**Bishops:** Slight center preference (+5-10), less extreme than knights.

**Rooks:** 7th rank bonus (+10-20), otherwise relatively flat.

**King MG:** Castled positions +20-30, center -30 to -50. Safety is paramount.

**King EG:** CENTER +20-30, corner -20. Complete reversal from MG.
This single change (different king PST for MG vs EG) is one of the highest-impact
improvements from tapered eval.

---

## 4. Passed Pawns

A pawn with no enemy pawn on the same file or adjacent files ahead of it.
One of the highest-value eval terms after material+PST.

### Detection (Bitboard)

```c
// White passed pawn at (row, col):
// Check files (col-1, col, col+1) from row-1 up to row 0 for black pawns
uint64_t pass_mask = file_forward_mask[WHITE][sq] |
                     file_forward_mask[WHITE][sq-1] |
                     file_forward_mask[WHITE][sq+1];
bool passed = !(pass_mask & black_pawns);
```

Cost: O(1) per pawn with precomputed masks.

### Bonuses by Rank (approximate centipawns)

| Rank   | MG    | EG     |
|--------|-------|--------|
| 4th    | 10-15 | 15-25  |
| 5th    | 20-30 | 40-55  |
| 6th    | 40-60 | 80-110 |
| 7th    | 80-130| 150-200|

Stockfish sf_10 values (internal units, S(mg, eg)):
```
Rank 2: S(5,18)    Rank 3: S(12,23)   Rank 4: S(10,31)
Rank 5: S(57,62)   Rank 6: S(163,167) Rank 7: S(271,250)
```

### Modifiers

- **Connected passers**: 1.5-2x multiplier when two passers on adjacent files
- **Protected passer** (defended by pawn): +10-30 additional
- **Blocked passer** (piece in front): reduce bonus by 50%
- **King proximity** (endgame): bonus if own king is close, penalty if enemy king close
- **Rook behind passer** (Tarrasch rule): +15-30 cp
- **Unstoppable passer**: if no enemy piece can catch it, near-winning bonus

### Elo Impact: +50-119 Elo

---

## 5. Pawn Structure

### Isolated Pawns (no friendly pawn on adjacent files)

- Penalty: MG -5 to -20, EG -15 to -30
- Worse on semi-open file (enemy can pile up)
- Stockfish: S(5, 15) per isolated pawn

### Doubled Pawns (two same-color pawns on same file)

- Penalty: MG -10 to -20, EG -20 to -56
- Stockfish: S(11, 56) — much worse in endgame

### Backward Pawns (can't advance safely, no adjacent support)

- Penalty: MG -5 to -15, EG -10 to -25
- Stockfish: S(9, 24)

### Connected / Phalanx Pawns

Bonuses by rank (seeds from Stockfish):
```
Rank 2: 13    Rank 3: 24    Rank 4: 18
Rank 5: 65    Rank 6: 100   Rank 7: 175
```
Formula: `seed * (2 + phalanx + supported) * multiplier`

### Pawn Hash Table

All pawn structure terms depend only on pawn positions. Cache them in a small
hash table (16K-256K entries) keyed by pawn Zobrist. Hit rate >95% because
pawns rarely move. Amortizes the cost of passed pawn detection + structure
analysis to nearly zero.

### Elo Impact: +20-50 Elo (but poorly tuned can LOSE Elo)

---

## 6. King Safety

The most complex and impactful middlegame eval term.

### Pawn Shield (cheap, high impact)

For each of the 3 files around the king:
- Pawn on rank 2 (right in front): +25-35 cp
- Pawn on rank 3: +10-20 cp
- Pawn missing entirely: -20 to -30 cp
- Pawn on rank 4+: -10 to -20 cp (overextended)

Cost: 3 bitboard lookups, O(1).

### Pawn Storm (enemy pawns advancing toward our king)

For each of the 3 files around the king:
- Enemy pawn on rank 5: +5 danger
- Enemy pawn on rank 4: +15 danger
- Enemy pawn on rank 3: +30 danger
- No enemy pawn: moderate danger (open file)

### Attack Units (Stockfish-style, non-linear)

This is the key insight: accumulate "attack units" and convert via an S-curve table.

```
danger = 0
for each enemy piece attacking king zone:
    danger += attack_weight[piece_type] * squares_attacked_in_zone

// Attack weights:
//   Knight: 77    Bishop: 55    Rook: 44    Queen: 10

// Scale by number of attackers (non-linear!):
// 2 attackers is much worse than 2x one attacker

// Safe check bonuses (very large):
//   Knight safe check: 790    Rook safe check: 880
//   Bishop safe check: 435    Queen safe check: 780

// Convert via quadratic/table:
king_penalty = safety_table[min(danger, 99)]
```

Safety table (Stockfish, 100 entries, capped at 500 internal units ≈ 240cp):
```
0, 0, 1, 2, 3, 5, 7, 9, 12, 15, 18, 22, 26, 30, 35, 39,
44, 50, 56, 62, 68, 75, 82, 85, 89, 97, 105, ...
```

The S-curve means: scattered attacks barely register, coordinated multi-piece
attacks produce massive penalties.

### King Zone Definition

The 8 squares surrounding the king plus 3 forward-facing squares (toward the
enemy). Total ~9-12 squares depending on king position.

### Elo Impact: +30-80 Elo

---

## 7. Piece Mobility

Count pseudo-legal squares each piece can move to. Correlates strongly with
piece activity. Use attack bitboards (computed for movegen anyway) + popcount.

### Stockfish MobilityBonus (selected values, S(mg, eg))

**Knight** (0-8 squares):
```
0 sq: S(-62,-81)   4 sq: S(3,8)   8 sq: S(33,33)
```

**Bishop** (0-13 squares):
```
0 sq: S(-48,-59)   7 sq: S(63,57)   13 sq: S(98,97)
```

**Rook** (0-14 squares):
```
0 sq: S(-58,-76)   7 sq: S(16,118)  14 sq: S(58,171)
```
Rook mobility matters enormously in endgame: 14 squares = +82cp EG.

**Queen** (0-27 squares):
```
0 sq: S(-39,-36)   14 sq: S(67,123)  27 sq: S(116,212)
```

### Simpler Linear Formula (CPW-Engine)

```
Knight: 4 * (mobility - 4)        // baseline 4 squares
Bishop: 3 * (mobility - 7)        // baseline 7 squares
Rook:   2 * (mobility - 7) MG; 4 * (mobility - 7) EG
Queen:  1 * (mobility - 14) MG; 2 * (mobility - 14) EG
```

### Implementation

```c
// Reuse attack bitboards from move generation
uint64_t attacks = knight_attacks[sq];
uint64_t safe = attacks & ~own_pieces & ~enemy_pawn_attacks;
int mobility = popcount(safe);
score += mobility_bonus[KNIGHT][mobility];
```

Exclude squares attacked by enemy pawns (not truly "mobile").

### Elo Impact: +45-62 Elo

---

## 8. Bishop Pair

Having two bishops vs one (or none) provides a significant advantage,
especially in open positions and endgames.

- **MG bonus**: +30 to +45 cp
- **EG bonus**: +45 to +60 cp
- Kaufman's research (300K master games): consistently +50 cp
- Scale by pawn count: fewer pawns = stronger bishop pair
  `bonus = base + (16 - total_pawns) * 3`

Detection: O(1) — check if piece count for bishops >= 2.

Stockfish imbalance table coefficient: 1438 / 16 ≈ 90 internal units ≈ 43cp.

---

## 9. Rook on Open File

**Open file** (no pawns of either color): +20-40 cp MG, +10-20 cp EG
**Semi-open file** (no own pawn): +10-20 cp MG, +5-10 cp EG

Stockfish sf_10: Semi-open S(18,7), Open S(44,20).

Additional:
- **Rook on 7th rank**: +15-30 cp
- **Doubled rooks on open file**: +10-20 cp extra

Detection: two bitboard ANDs per rook against file masks, O(1).

---

## 10. Outposts

A square on rank 4/5/6 that cannot be attacked by enemy pawns and is
defended by own pawn.

- **Knight on outpost**: +15-40 cp (very strong for short-range piece)
- **Bishop on outpost**: +5-15 cp

Stockfish sf_10: Knight outpost S(22,6) to S(36,12); Bishop outpost S(9,2) to S(15,5).

Detection: same "pass mask" concept as passed pawns, O(1) with bitboards.

---

## 11. Threats

Lower-value pieces attacking higher-value pieces.

Stockfish ThreatByMinor (attacking piece type → bonus):
```
Pawn: S(0,31)   Knight: S(39,42)   Bishop: S(57,44)
Rook: S(68,112)  Queen: S(62,120)
```

ThreatByRook:
```
Pawn: S(0,24)   Knight: S(38,71)   Bishop: S(38,61)
Rook: S(0,38)   Queen: S(51,38)
```

Also: ThreatByPawnPush S(48,42), hanging pieces penalty (-10 to -20cp).

---

## 12. Endgame Knowledge

### Scaling Factors

Applied as multipliers to the eval to avoid false wins:

- **Opposite-colored bishops**: scale eval down 50%+ (especially with few pawns)
- **KvK, KNvK, KBvK**: drawn — return 0
- **KBPvK (wrong rook pawn)**: bishop doesn't control promotion square → draw

Detection: O(1) piece count checks.

### Mop-up Eval

When one side has decisive advantage, help the engine deliver checkmate:
```
bonus = 10 * (7 - manhattan_distance(winning_king, losing_king))
      + 5 * center_distance(losing_king)
```

### King Centralization

Handled via tapered eval: EG king PST strongly rewards center (+20-30 cp)
and penalizes corners (-20 cp).

---

## 13. Shogi-Specific Eval

### Pieces in Hand

Pieces in hand are worth 10-30% MORE than on the board due to drop flexibility.
Our current shogi engines already implement this (+2 to +10 bonus per hand piece).

### Castle Pattern Recognition

Evaluate known castle formations via bitboard pattern matching:
- **Mino castle**: gold/silver/king arrangement on ranks 1-2, files 1-3 → +100-200 cp
- **Yagura**: similar, ranks 1-3 → +100-200 cp
- **Anaguma**: king in corner with full coverage → +200-300 cp

Implementation: precompute bitboard patterns, match against current position, O(1).

### Drop Threats Near King

Count squares near enemy king where you could legally drop a piece.
Weight by piece type (gold/silver drops near king are devastating).
This enhances the king safety evaluation for shogi.

### Promoted Piece Bonuses

Beyond raw material difference, a tokin (promoted pawn) near the enemy king
deserves extra bonus (+50-80 cp) because of the mating threats it creates.

---

## 14. Elo Impact Estimates

From various engine development logs:

| Feature                        | Elo Gain    |
|--------------------------------|-------------|
| Material only                  | baseline (~1200-1400) |
| + Piece-square tables          | +200-400    |
| + Tapered eval / tuned PST     | +250-300    |
| + Piece mobility               | +45-62      |
| + Passed pawn evaluation       | +50-119     |
| + King safety                  | +30-80      |
| + Pawn structure               | +20-50      |
| + Bishop pair                  | +10-20      |
| + Rook on open file            | +10-20      |
| + Threats                      | +10-30      |
| + Outposts                     | +5-15       |
| + Space                        | +5-15       |
| **Total HCE engine**           | **~2200-2500 Elo** |
| + NNUE                         | +200-400 additional |

**Warning**: poorly tuned features LOSE Elo. One developer found blindly guessing
pawn penalties cost -100 Elo vs material+PST alone. Texel tuning is essential
for non-trivial terms.

---

## 15. Our Current State & Upgrade Plan

### Current Eval (Chess 8x8)

- Material (fixed values, no MG/EG split)
- PST (single table per piece, no taper)
- King tropism (Manhattan distance, simple linear weights)
- No passed pawn detection
- No pawn structure analysis
- No king safety (pawn shield/attack units)
- No mobility (disabled — was counting legal moves, too expensive)
- No bishop pair bonus
- No rook on open file bonus
- Eval recomputed from scratch every call (no incremental update)
- ~2M nps, depth 9-11 in 5 seconds, game rating ~2400

### Current Eval (Shogi Variants)

- Material with hand piece premiums (already good)
- PST per piece type
- King tropism (Chebyshev distance)
- Mobility (legal move count difference * 2 — expensive)
- No castle pattern recognition
- No drop threat analysis

### Upgrade Plan — Priority Order

#### Phase 1: Tapered Eval + King EG PST (highest impact, zero cost)

1. Implement packed Score type `S(mg, eg)`
2. Split all PST tables into MG and EG versions
3. **King EG PST**: centralization bonus (+20-30) instead of hiding bonus
4. Compute game phase from remaining material
5. Single interpolation at the end of eval

Expected: **+100-200 Elo** (king EG alone is massive)

#### Phase 2: Passed Pawns + Bishop Pair + Rook Open File (high impact, cheap)

6. Precompute file masks (8 bitboards for files A-H)
7. Passed pawn detection via forward file masks, O(1) per pawn
8. Rank-based bonus table (escalating dramatically for ranks 6-7)
9. Bishop pair: one `if` statement, +45 MG / +60 EG
10. Rook on open/semi-open file: two bitboard ANDs per rook

Expected: **+50-100 Elo**

#### Phase 3: Pawn Structure + King Safety (medium impact, moderate cost)

11. Isolated pawn detection (no friendly pawn on adjacent files)
12. Doubled pawn detection (two pawns on same file)
13. Pawn shield evaluation (3 squares in front of castled king)
14. Basic attack count near king zone (reuse bitboard infrastructure)
15. Optional: pawn hash table to cache pawn eval

Expected: **+30-60 Elo**

#### Phase 4: Mobility (moderate impact, needs care)

16. Use attack bitboards from existing magic infrastructure
17. Compute mobility as popcount of attack squares minus own pieces
18. Exclude squares attacked by enemy pawns
19. Non-linear bonus tables per piece type

Expected: **+40-60 Elo**, but ~5-15% NPS cost

#### Phase 5: Shogi Enhancements

20. Castle pattern recognition (bitboard pattern match)
21. Drop threat evaluation near enemy king
22. Enhanced promoted piece PST bonuses
23. Scale hand piece values by game phase

### Architecture Notes

- All new terms produce `Score` (packed MG+EG), accumulated into one total
- Bitboard infrastructure already exists (magic rook/bishop, leaper tables)
- Keep eval under ~500ns per call to maintain >1.5M nps
- Test each addition via selfplay (SPRT or fixed-game match)
- Consider Texel tuning once we have 10+ parameters

---

## References

- Stockfish sf_10 evaluate.cpp, pawns.cpp, material.cpp
- Stockfish Evaluation Guide (hxim.github.io)
- Chess Programming Wiki (chessprogramming.org): Evaluation, Tapered Eval,
  King Safety, Passed Pawn, Mobility, PeSTO
- Kaufman: Material Imbalances (bishop pair = +50cp)
- PeSTO's Evaluation Function (Texel-tuned PSTs)
- Simplified Evaluation Function (Michniewski)
- Bonanza/KPPT shogi evaluation
- MadChess: Piece Mobility (+62 Elo)
- Rustic Chess: Playing Strength progression
