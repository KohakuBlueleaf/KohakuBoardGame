# MiniChess Algorithms

## Apply Move / State Representation

- Legal Move Generation
  - Naive (nested loop per piece type, direction tables)
  - Bitboard (30-bit uint32, precomputed attack tables, bit-scan iteration)
- Next State Construction
  - Board copy + piece move + capture removal
  - Pawn promotion (to Queen on back rank)
  - Game-over detection (king capture available)

## State Evaluation

- Material Only
  - Simple piece value sum (P=2, R=6, N=7, B=8, Q=20, K=100)
- KP Eval (King-Piece)
  - Material with 10x scale for positional granularity
  - Piece-Square Tables (PST)
    - Per-piece-type positional bonus per square
    - Mirrored vertically for black
  - King Tropism
    - Bonus for attacking pieces near enemy king
    - Distance-based weight per piece type
- Mobility Bonus
  - Count legal moves for both sides
  - Score += weight * (self_moves - opponent_moves)
- NNUE (Efficiently Updatable Neural Network)
  - Feature Extraction
    - PieceSquare (360-dim): color * piece_type * square
    - HalfKP (9000-dim): king_square * color * piece_type * square
  - Network Architecture
    - Sparse feature transformer (accumulator)
    - SCReLU activation (clamp(x,0,1)^2)
    - Perspective pairing (STM concat NSTM)
    - Two hidden layers + output (centipawn score)
  - Inference Optimization
    - Scalar (pure C++ float)
    - SIMD (AVX2 / NEON vectorized)
    - Quantized (int8/int16, Stockfish-style)
  - Training Pipeline
    - Self-play data generation (binary format, epsilon-jitter)
    - PyTorch training with WDL-blended loss
    - Binary weight export for C++ loading

## Search Algorithms

- MiniMax
  - Pure negamax (no pruning)
  - Exhaustive tree search to fixed depth
- AlphaBeta Pruning
  - Negamax with alpha-beta window
  - Prune branches that can't affect the result
- PVS (Principal Variation Search)
  - Null-window re-search framework
    - First move: full window
    - Remaining moves: zero-width window, re-search on fail-high
  - Iterative Deepening
    - Search depth 1, 2, 3, ... progressively
    - TT results from previous depth seed the next
    - Time management (stop when time runs out)
  - Move Ordering
    - TT best move searched first
    - MVV-LVA (Most Valuable Victim - Least Valuable Attacker) for captures
    - Killer Move Heuristic
      - Store quiet moves that caused beta cutoffs per ply
      - Rank below captures, above other quiet moves
  - Transposition Table
    - Zobrist Hashing (XOR of random keys per piece/square/side)
    - Probe: reuse results from same position via different move orders
    - Store: depth-based replacement (deeper always replaces)
    - PV Extraction: walk TT chain from root to reconstruct principal variation
  - Quiescence Search
    - At depth 0, continue searching capture moves only
    - Prevents horizon effect (evaluating mid-capture positions)
    - Stand-pat evaluation as lower bound
    - MVV-LVA sorted captures
  - Null Move Pruning
    - Skip own turn (pass) at reduced depth
    - If score still >= beta, the position is so good we can prune
    - Configurable reduction depth (R)
  - Late Move Reduction (LMR)
    - Moves ordered late are unlikely to be good
    - Search them at reduced depth first
    - Re-search at full depth only on fail-high
    - Skip reduction for captures and killer moves
  - Root Move Partial Results
    - Report current best move as each root move completes
    - Allows UI feedback during long searches
