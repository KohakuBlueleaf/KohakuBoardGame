# MiniChess Project Requirements

## Apply Move / State Representation

- Legal Move Generation
  - Naive (nested loop per piece type, direction tables)
    - Required
  - Bitboard (30-bit uint32, precomputed attack tables, bit-scan iteration)
    - Bonus and small diff, actually not very important
- Next State Construction
  - Board copy + piece move + capture removal
    - We will keep this as part of framework
  - Pawn promotion (to Queen on back rank)
    - part of framework
  - Game-over detection (king capture available)
    - part of framework

## State Evaluation

- Material Only
  - Simple piece value sum (P=2, R=6, N=7, B=8, Q=20, K=100)
    - required, we ask student to compare with better eval
- KP Eval (King-Piece)
  - Piece-Square Tables (PST)
    - required
  - King Tropism
    - bonus
- Mobility Bonus
  - bonus
- NNUE (Efficiently Updatable Neural Network)
  - bonus
  - part of bonus baseline

## Search Algorithms

- MiniMax
  - required
- AlphaBeta Pruning
  - required
- PVS (Principal Variation Search)
  - Required
  - Quiescence Search
    - Required
  - Move Ordering (MVV-LVA/Killer Move, or more)
    - Bonus
  - Transposition Table
    - Bonus
  - Null Move Pruning
    - Bonus
  - Late Move Reduction (LMR)
    - Bonus
  - Move ordering/TT/Null Move Pruning/LMR, should be implemented few for beat baseline 4
- Root Move Partial Results
  - Bonus and recommended

## Baseline Setup

1. Minimax + material
2. AlphaBeta + material
3. AlphaBeta + KP
4. PVS (Quiescence Search + naive PVS only) + KP
5. Bonus1: Full algo PVS + KP
6. Bonus2: Full algo PVS + NNUE
