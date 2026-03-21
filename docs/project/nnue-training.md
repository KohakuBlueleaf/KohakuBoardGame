# NNUE Training Pipeline

Comprehensive documentation for the NNUE (Efficiently Updatable Neural Network) training
system used by the MiniChess engine family. Covers data generation, feature extraction,
model architecture, training, and binary export for C++ inference.

---

## Table of Contents

1. [Pipeline Overview](#1-pipeline-overview)
2. [Data Generation (datagen.cpp)](#2-data-generation)
3. [Data Loading (MmapDataSource)](#3-data-loading)
4. [Feature Extraction (PS and HalfKP)](#4-feature-extraction)
5. [Model Architecture (GameNNUE)](#5-model-architecture)
6. [Loss Functions](#6-loss-functions)
7. [Training Loop (NNUETrainer)](#7-training-loop)
8. [Binary Export](#8-binary-export)
9. [CLI Reference](#9-cli-reference)
10. [Known Issues and Fixes](#10-known-issues-and-fixes)

---

## 1. Pipeline Overview

The NNUE system follows a four-stage pipeline: generate labeled positions via self-play,
train a neural network on those positions, export the weights to a compact binary format,
and load them into the C++ engine for real-time evaluation.

```
+==================+     +===============+     +=============+     +==============+
|   DATA GENERATION |     |    TRAINING    |     |    EXPORT    |     |   INFERENCE   |
|                  |     |               |     |             |     |              |
| datagen.cpp      |     | nnue-train/   |     | export.py   |     | C++ engine   |
| (self-play PVS)  |---->| (PyTorch)     |---->| (float/     |---->| (SIMD int8/  |
|                  |     |               |     |  quantized) |     |  int16 eval) |
| Output: .bin     |     | Output: .pt   |     | Output: .bin|     |              |
| (v5 format)      |     | (checkpoint)  |     | (weights)   |     |              |
+==================+     +===============+     +=============+     +==============+
        |                        ^
        |     +-----------+      |
        +---->| .bin files |------+
              | (mmap'd)  |
              +-----------+
```

### Iterative Improvement Loop

Each generation of the network produces better training data for the next:

```
  Handcrafted eval (v0)
        |
        v
  datagen (depth=6, epsilon=0.10) --> 20M positions
        |
        v
  Train NNUE v1 (from scratch, lr=1e-3, 400 epochs)
        |
        v
  datagen with NNUE v1 eval --> 30-50M positions
        |
        v
  Train NNUE v2 (fine-tune v1, lr=5e-4, 200 epochs)
        |
        v
  ... repeat until Elo gain < 5 per iteration ...
```

**Stop rule:** Two consecutive iterations gaining less than 5 Elo indicates a plateau.
At that point, upgrade the architecture or increase search depth.

### File Locations

| Component | Path |
|-----------|------|
| C++ data generator | `src/datagen.cpp` |
| Shell parallelizer | `scripts/gen_data.sh` |
| Python training package | `nnue-train/` |
| CLI entry point | `nnue-train/__main__.py` |
| Game configurations | `nnue-train/game_config.py` |
| Data I/O (mmap) | `nnue-train/data.py` |
| Dataset (PyTorch) | `nnue-train/dataset.py` |
| Feature extraction | `nnue-train/features.py` |
| Model definition | `nnue-train/model.py` |
| Loss functions | `nnue-train/loss.py` |
| Binary export | `nnue-train/export.py` |
| Training loop | `nnue-train/trainer.py` |
| Lightning module (reference) | `nnue-train/lit_module.py` |
| C++ quantized compute | `src/nnue/compute_quant.hpp` |

---

## 2. Data Generation

### 2.1 How datagen.cpp Works

The data generator plays self-play games using Principal Variation Search (PVS) and
records every non-terminal position with its search score and eventual game result.

**Self-play loop for one game:**

```
  1. Initialize board to starting position
  2. For each ply:
     a. With probability epsilon: pick a random legal move (jitter)
        - Still run PVS to get an accurate score for the position
     b. Otherwise: run PVS at depth D to get best move + score
     c. Execute the chosen move
     d. If the resulting position is not terminal:
        - Record the board state, side-to-move, negated score, ply, best move
        - Score is negated because search_score is from the pre-move player's
          perspective, but the recorded position belongs to the post-move player
     e. Repeat until terminal or MAX_STEP reached
  3. Backfill game result (+1 win, 0 draw, -1 loss) for all recorded positions
```

**Key design decisions:**

- **Jitter (epsilon):** A fraction of moves are random to diversify the training set.
  Even when a random move is chosen, PVS still runs to provide an accurate score label.
  Recommended values: 0.10--0.30 with ply-dependent decay.

- **Score perspective:** The search score is always from the side-to-move perspective
  of the *recorded* position (post-move). The code negates the pre-move PVS score to
  achieve this.

- **Terminal filtering:** Positions where the game is already won are not recorded, since
  those positions have trivial evaluations.

- **Parallelism:** For large-scale generation, run multiple instances with different seeds
  and output files. The `scripts/gen_data.sh` wrapper handles this automatically.

### 2.2 Binary Format (v5)

All integers are little-endian. The file consists of a fixed-size header followed by
a flat array of fixed-size records.

```
+------------------------------------------------------------------+
|                         FILE LAYOUT                               |
+------------------------------------------------------------------+
| Offset 0:  DataHeader (36 bytes)                                 |
| Offset 36: DataRecord[0]                                         |
| Offset 36 + record_size: DataRecord[1]                           |
| ...                                                              |
| Offset 36 + (count-1)*record_size: DataRecord[count-1]           |
+------------------------------------------------------------------+
```

#### Header Structure (36 bytes)

```
Offset  Size  Type      Field        Description
------  ----  --------  -----------  ------------------------------------
 0       4    char[4]   magic        "BGDT" (Board Game Data Training)
 4       4    int32     version      Format version (currently 5)
 8       4    int32     count        Number of records (updated at EOF)
12       2    int16     board_h      Board height (e.g., 6 for minichess)
14       2    int16     board_w      Board width (e.g., 5 for minichess)
16       2    int16     num_hand     Hand piece types per player (0 if none)
18       2    int16     reserved     Padding (always 0)
20      16    char[16]  game_name    Null-terminated ASCII game name
```

Header versions:
- **v1--v3:** 12-byte minimal header (`magic + version + count`)
- **v4:** 32-byte extended header (adds `board_h`, `board_w`, `game_name`)
- **v5:** 36-byte full header (adds `num_hand`, `reserved`)

#### Record Structure (variable size by game)

```
Offset  Size               Type         Field       Description
------  -----------------  ----------   ----------  ---------------------------
 0      2 * H * W          int8[2][H][W] board      Board state, per player
 ...    2 * max(HAND,1)    int8[2][HAND] hand       Hand pieces (0 if unused)
 ...    1                  int8          player      Side to move (0 or 1)
 ...    2                  int16         score       PVS score (STM perspective)
 ...    1                  int8          result      Game outcome: +1/0/-1
 ...    2                  uint16        ply         Ply counter from game start
 ...    2                  uint16        best_move   Encoded move (from*N+to, 0xFFFF=none)
```

**Record sizes by game:**

| Game | Board Cells | Hand Cells | Metadata | Total Record Size |
|------|------------|------------|----------|-------------------|
| MiniChess (6x5) | 60 | 2 | 8 | 70 bytes |
| MiniShogi (5x5) | 50 | 10 | 8 | 68 bytes |
| Gomoku (9x9) | 162 | 2 | 8 | 172 bytes |

**Move encoding:** `best_move = from_square * NUM_SQUARES + to_square`, where
`square = row * board_width + col`. The sentinel value `0xFFFF` means no move.

### 2.3 Data Generation Script (gen_data.sh)

The shell script parallelizes data generation across multiple CPU cores:

```bash
# Generate 30,000 games of minichess at depth 6 with 64 workers
bash scripts/gen_data.sh -g minichess -n 30000 -w 64 -d 6 -e 0.15 -o data

# Generate with NNUE eval (for iterative improvement)
bash scripts/gen_data.sh -g minichess -n 1000000 -w 64 -d 6 -e 0.10 \
  -m models/nnue_v1.bin -o data_v2
```

| Flag | Default | Description |
|------|---------|-------------|
| `-g` | minichess | Game type: minichess, minishogi, gomoku |
| `-n` | 30000 | Total games to generate |
| `-w` | 64 | Number of parallel worker processes |
| `-d` | 6 | Search depth |
| `-e` | 0.15 | Jitter probability (epsilon) |
| `-m` | (none) | NNUE model file for eval |
| `-o` | data | Output directory |

Each worker writes to `{output_dir}/train_{i}.bin` with a unique seed. The script polls
file sizes to display a progress estimate with ETA.

---

## 3. Data Loading

### 3.1 MmapDataSource Design

**File:** `nnue-train/data.py`

`MmapDataSource` is a multi-file, memory-mapped data reader designed for efficient
random access into large training datasets without loading everything into RAM.

```
                    MmapDataSource
                    ==============
  +---------------------------------------------+
  | file_idx[]  (int32, length = total_valid)    |  <-- which file
  | rec_idx[]   (int32, length = total_valid)    |  <-- which record in file
  +---------------------------------------------+
         |
         v  get_record(global_idx)
  +------+------+------+
  | File 0      | File 1      | File 2      |
  | train_0.bin | train_1.bin | train_2.bin |
  | (mmap'd)    | (mmap'd)    | (mmap'd)    |
  +-------------+-------------+-------------+
```

**Key properties:**

1. **Lazy mmap handles:** Mmap file handles are opened on first access and cached in a
   per-process dictionary (`_mmaps`). This is critical because mmap handles cannot be
   pickled -- they would break when passed to DataLoader worker processes.

2. **Pickle safety:** The `__getstate__` method drops the mmap cache before pickling.
   Each DataLoader worker rebuilds its own mmap handles on first access.

3. **Filtering at index time:** During construction, a temporary mmap is opened for each
   file to pre-filter records. Records with `|score| > 10000` are excluded (mate scores,
   extreme outliers). An optional `min_ply` filter skips early-game positions. Only the
   indices of valid records are stored in memory, not the records themselves.

4. **Memory footprint:** O(N * 8 bytes) for the index arrays, where N is the number of
   valid records. The actual position data stays on disk and is read on demand via mmap.

### 3.2 Record Dtype Construction

The `make_record_dtype()` function builds a NumPy structured dtype matching the binary
layout for a given game and format version:

```python
# v5 record for minichess (6x5):
dtype([
    ('board', 'i1', (60,)),
    ('hand',  'i1', (2,)),     # 2*max(HAND_SIZE,1)
    ('player','i1'),
    ('score', '<i2'),
    ('result','i1'),
    ('ply',   '<u2'),
    ('best_move', '<u2'),
])
```

### 3.3 NNUEDataset

**File:** `nnue-train/dataset.py`

`NNUEDataset` is a PyTorch `Dataset` that wraps `MmapDataSource` and performs on-the-fly
feature extraction in `__getitem__`:

```
  DataLoader worker
  =================
  __getitem__(idx)
      |
      v
  source.get_record(global_idx)       # read raw bytes via mmap
      |
      v
  extract_halfkp_sparse(board, ...)   # convert to feature indices
      |
      v
  return (white_idx, black_idx,       # sparse int32 arrays (~80 bytes)
          stm, score, result)         # scalar tensors
```

For HalfKP features, the dataset returns **sparse index arrays** (int32) rather than dense
float32 tensors. This is a deliberate design choice to avoid exhausting shared memory when
DataLoader workers queue up prefetched batches (see Section 10 for details).

---

## 4. Feature Extraction

**File:** `nnue-train/features.py`

The training system supports two feature encoding schemes: PieceSquare (PS) and HalfKP.
Both produce separate feature vectors for the white and black perspectives.

### 4.1 PieceSquare (PS) Features

PS features encode what piece is on what square, without king-relative indexing.

```
Feature index = color * (num_piece_types * num_squares) + piece_type * num_squares + square
```

**Dimensions by game:**

| Game | Formula | PS Size |
|------|---------|---------|
| MiniChess | 2 * 6 * 30 | 360 |
| MiniShogi | 2 * 11 * 25 | 550 (+10 hand) |
| Gomoku | 2 * 2 * 81 | 324 |

PS features are returned as **dense float32 tensors** since they are small enough that
shared memory is not a concern.

**Perspective mirroring:** The black perspective mirrors the board vertically
(row -> board_h - 1 - row) and swaps colors (color -> 1 - color), so that both
perspectives see "their own" pieces in the same orientation.

### 4.2 HalfKP Features

HalfKP (Half King-Piece) features encode each non-king piece's position relative to
the friendly king's position:

```
Feature index = king_square * num_piece_features
              + color * (num_pt_no_king * num_squares)
              + piece_type * num_squares
              + square
```

**Dimensions by game:**

| Game | King Squares | Piece Features | HalfKP Size | With Hand |
|------|-------------|----------------|-------------|-----------|
| MiniChess | 30 | 5*30*2 = 300 | 9,000 | 9,000 |
| MiniShogi | 25 | 10*25*2 = 500 | 12,500 | 12,510 |
| Gomoku | n/a (no king) | 2*81*2 = 324 | 26,244 | 26,244 |

For games with hand pieces (MiniShogi), hand features are appended after the board
features: `base + color * num_hand_types + piece_type`. Hand feature counts are
additive (a piece held twice contributes twice).

### 4.3 Sparse Mode (450x Memory Reduction)

The key optimization: instead of returning a dense float32 tensor of size 9,000+
(~36 KB per sample), the sparse extractor returns an **int32 index array** of the
~20 active features (~80 bytes per sample).

```
Dense mode:  [0, 0, 0, 1, 0, 0, ..., 0, 1, 0, ...]   9,000 floats = 36,000 bytes
Sparse mode: [3, 127, 4502, ..., PAD, PAD, PAD]       max_active ints = ~80 bytes
                                                       ~450x smaller
```

**Padding:** Sparse index arrays are fixed-length (`max_active`, typically 20--40),
padded with `feature_size` (an out-of-range sentinel). The `sparse_to_dense` function
on GPU uses `scatter_add_` with masking to ignore padding values.

**Why this matters:** PyTorch DataLoader workers on Windows use shared memory to pass
tensors to the main process. With 4 workers, batch_size=8192, and 2 prefetch batches,
the dense approach needs `4 * 8192 * 2 * 2 * 36KB = ~4.5 GB` of shared memory. The
sparse approach needs only `4 * 8192 * 2 * 2 * 80 = ~10 MB`.

### 4.4 Sparse-to-Dense Expansion

The `sparse_to_dense()` utility converts sparse index tensors back to dense on GPU:

```python
def sparse_to_dense(indices, feature_size):
    # indices: (B, max_active), padding value = feature_size
    dense = torch.zeros(B, feature_size, device=indices.device)
    valid = indices < feature_size
    clamped = indices.clamp(max=feature_size - 1).long()
    dense.scatter_add_(1, clamped, valid.float())
    return dense
```

This runs on GPU and is negligible compared to the forward pass.

---

## 5. Model Architecture

**File:** `nnue-train/model.py`

### 5.1 GameNNUE Architecture

```
+-----------------------------------------------------------------------+
|                          GameNNUE                                     |
|                                                                       |
|  WHITE FEATURES ----+                                                 |
|                     |    +------------------+                         |
|                     +--->| Feature Transform |---> SCReLU --> W_accum  |
|                          | (shared weights) |                         |
|  BLACK FEATURES ----+--->| EmbeddingBag or  |---> SCReLU --> B_accum  |
|                          | Linear           |                         |
|                          +------------------+                         |
|                                                                       |
|  STM flag selects ordering:                                           |
|    STM_accum  = W_accum if white-to-move, else B_accum                |
|    NSTM_accum = the other one                                         |
|                                                                       |
|  +---------------------+                                              |
|  | [STM_accum | NSTM_accum]  (2 * accum_size)                        |
|  +---------------------+                                              |
|           |                                                           |
|           v                                                           |
|  +------------------+     +------------------+     +-------------+    |
|  | Linear(2*A, L1)  |---->| Linear(L1, L2)   |---->| Linear(L2,1)|    |
|  | + SCReLU         |     | + SCReLU         |     | (value out) |    |
|  +------------------+     +------------------+     +-------------+    |
|                                                                       |
|  Optional policy head (branched from concatenated accumulators):      |
|  [STM | NSTM] --> Linear(2*A, 128) --> ReLU --> Linear(128, N*N)      |
+-----------------------------------------------------------------------+
```

### 5.2 Feature Transform: Dense vs. Sparse Mode

The feature transform (FT) layer has two implementations controlled by the `sparse` flag:

| Mode | Layer | Input | Weight Shape | Notes |
|------|-------|-------|-------------|-------|
| Dense | `nn.Linear` | `(B, feature_size)` float32 | `(accum, feature)` | Standard matmul |
| Sparse | `nn.EmbeddingBag` | `(B, max_active)` int32 | `(feature, accum)` | Sum of active rows |

**Sparse FT mechanics:** `EmbeddingBag` with `mode="sum"` sums only the embedding rows
corresponding to active feature indices. For ~20 active features out of 9,000, this is
~450x less computation than a full matrix multiply. A separate `ft_bias` parameter is
added since `EmbeddingBag` does not have a built-in bias.

**Padding handling in sparse mode:** Padding indices (= `feature_size`, out of range) are
clamped to `feature_size - 1` and multiplied by a `per_sample_weights` mask of 0.0,
effectively zeroing their contribution.

**Weight export compatibility:** `get_linear_ft_state()` transposes `EmbeddingBag` weights
from `(feature, accum)` to `(accum, feature)` format for export, matching the `nn.Linear`
convention.

### 5.3 SCReLU Activation

Squared Clipped ReLU: `SCReLU(x) = clamp(x, 0, 1)^2`

This activation function was adopted from Stockfish NNUE. The squaring operation provides
stronger gradients near the boundaries compared to standard ReLU, and the clamp ensures
bounded activations that are amenable to quantization.

### 5.4 Architecture Tiers

| Tier | accum_size | l1_size | l2_size | ~Params (MiniChess HalfKP) | Use |
|------|-----------|---------|---------|---------------------------|-----|
| Small | 32 | 32 | 32 | ~290K | v1--v2 |
| Medium | 64 | 32 | 32 | ~580K | v3--v4 |
| Large | 128 | 32 | 32 | ~1.16M | v5+ |

The majority of parameters are in the feature transform layer
(feature_size x accum_size). The dense layers are tiny by comparison.

---

## 6. Loss Functions

**File:** `nnue-train/loss.py`

### 6.1 Sigmoid MSE with WDL Blending (nnue_loss)

The primary loss function operates in sigmoid-scaled space:

```
SCORE_SCALE = 400.0

pred_sigmoid  = sigmoid(predicted / SCORE_SCALE)
score_sigmoid = sigmoid(search_score / SCORE_SCALE)
wdl           = (game_result + 1) / 2          # maps {-1, 0, +1} to {0.0, 0.5, 1.0}

target = (1 - wdl_weight) * score_sigmoid + wdl_weight * wdl
loss   = mean((pred_sigmoid - target)^2)
```

**Why sigmoid space?** Raw centipawn scores have unbounded range. Mapping to [0, 1] via
sigmoid normalizes the scale and makes the loss well-behaved for both small and large
evaluation differences.

**SCORE_SCALE = 400:** This maps a 100 centipawn advantage (1 pawn) to
`sigmoid(100/400) = sigmoid(0.25) = 0.562`, i.e., ~56% win probability. This constant
must match between training and C++ inference.

**WDL blending:** The `wdl_weight` parameter controls how much the loss trusts the
game outcome vs. the search score:

| wdl_weight | Behavior |
|------------|----------|
| 0.0 | Pure score distillation (train only on PVS scores) |
| 0.5 | Equal blend (recommended default) |
| 1.0 | Pure result prediction (ignore search scores) |

Low values (0.0--0.3) are better for early iterations when the search is weak.
Higher values (0.5--0.85) help later when game results are more meaningful.

### 6.2 Dual Loss (dual_loss)

When the policy head is enabled, the loss combines value and policy:

```
total_loss = value_loss + policy_weight * policy_loss
```

Where `policy_loss` is cross-entropy between the predicted move probabilities and the
best move from search. Only positions with a valid best move (`!= 0xFFFF`) contribute
to the policy loss. Default `policy_weight = 0.1`.

---

## 7. Training Loop

**File:** `nnue-train/trainer.py`

### 7.1 NNUETrainer Class

The training loop is a custom implementation (not PyTorch Lightning) optimized for
throughput on small models where Lightning overhead is 30--40% of wall time.

```
NNUETrainer
===========
  __init__:
    - model.to(device)
    - Adam optimizer
    - AnySchedule (cosine + warmup)
    - EMA (exponential moving average of weights)

  fit(epochs):
    for each epoch:
      for each batch:
        1. Forward pass + loss computation
        2. Backward pass + optimizer step
        3. LR scheduler step
        4. EMA update
        5. Every val_every_n_steps: run validation with EMA weights
        6. Log to wandb (every 50 steps)
      Save epoch checkpoint

    Final validation + export
```

### 7.2 Exponential Moving Average (EMA)

The EMA class maintains a shadow copy of all model parameters:

```
theta_ema = decay * theta_ema + (1 - decay) * theta_current
```

Default decay = 0.999. EMA weights are used for:
- All validation runs (original weights are swapped back after)
- Final model export (both float and quantized)
- Best-model checkpointing

### 7.3 Learning Rate Schedule

Uses `AnySchedule` with cosine decay and linear warmup:

```
LR
 ^
 |        /--...
 |       /      \
 |      /        \
 |     /          \
 |    /            \
 |   /              \
 |  /                \_____ min_value (1% of peak)
 | /
 +--+----+----+----+----+----> step
    0   warmup        total_steps
```

- **Warmup:** Linear ramp from 0 to `lr` over `warmup_steps` (default: auto 5% of total, max 2000)
- **Cosine decay:** From `lr` to `0.01 * lr` over remaining steps

### 7.4 Validation

Validation runs at configurable step intervals (`val_every_n_steps`, default: auto ~4x per epoch).

**Metrics computed:**
- `loss`: Same loss function as training (sigmoid MSE with WDL blending)
- `mae_cp`: Mean Absolute Error in centipawns
- `winner_acc`: Accuracy of predicting game winner (on decisive games only)

**Best model tracking:** If validation loss improves, EMA weights are saved to
`{output}_best.pt`.

### 7.5 Checkpointing

| Checkpoint Type | When | Contents | Path |
|-----------------|------|----------|------|
| Best model | Val loss improves | EMA state_dict | `models/nnue_v1_best.pt` |
| Epoch checkpoint | End of each epoch | Full state (model, optimizer, scheduler, step, loss) | `models/nnue_v1_epochN.pt` |
| Final model | End of training | EMA state_dict | `models/nnue_v1.pt` |

### 7.6 Lightning Module (Reference)

`nnue-train/lit_module.py` contains `NNUELitModule`, a PyTorch Lightning wrapper around
the same model and loss functions. It is kept as a reference implementation but is not
used by the CLI trainer due to Lightning's overhead on small models.

---

## 8. Binary Export

**File:** `nnue-train/export.py`

Two export formats are supported: float32 (for debugging and float C++ inference) and
quantized int16/int8 (for SIMD-optimized C++ inference).

### 8.1 Float Export

```
+-------------------------------------------------------+
| HEADER                                                |
|  "MCNN" magic (4 bytes)                               |
|  version (int32): 1 = PS, 2 = HalfKP                 |
|  feature_size (int32)                                 |
|  accum_size (int32)                                   |
|  l1_size (int32)                                      |
|  l2_size (int32)                                      |
+-------------------------------------------------------+
| WEIGHTS (all float32, little-endian)                  |
|  ft.weight  (feature_size x accum_size)  [row-major]  |
|  ft.bias    (accum_size)                              |
|  l1.weight  (accum_size*2 x l1_size)                  |
|  l1.bias    (l1_size)                                 |
|  l2.weight  (l1_size x l2_size)                       |
|  l2.bias    (l2_size)                                 |
|  out.weight (l2_size x 1)                             |
|  out.bias   (1)                                       |
+-------------------------------------------------------+
```

**FT weight layout:** The feature transform weight is transposed from PyTorch's
`(accum, feature)` format to `(feature, accum)` row-major for C++ consumption. The
`get_linear_ft_state()` method handles the EmbeddingBag-to-Linear transpose when the
model uses sparse mode.

### 8.2 Quantized Export

Version = float_version + 10 (11 for PS, 12 for HalfKP). Same header structure.

**Quantization constants (must match `src/nnue/compute_quant.hpp`):**

| Constant | Value | Type | Purpose |
|----------|-------|------|---------|
| QA | 255 | int16 | FT weight/bias scale |
| QA_HIDDEN | 127 | uint8 | Hidden activation scale |
| QB | 64 | int8 | Dense weight scale |
| QAH_QB | 8128 (= 127 * 64) | int32 | Dense bias scale |

**Quantization scheme:**

```
Layer             Float -> Quantized             Type
================  ============================  ===========
FT weight         round(w * 255)                int16
FT bias           round(b * 255)                int16
Dense weight      round(w * 64)                 int8
Dense bias        round(b * 8128)               int32
```

**C++ SCReLU with dequantization:**

```
FT SCReLU:    output = min(127, clamp(x, 0, 255)^2 >> 9)     int16 -> uint8
Dense SCReLU: output = min(127, clamp(x, 0, 8128)^2 >> 19)   int32 -> uint8
Final output: centipawns = raw_int32 / 8128
```

The bit shifts (>> 9, >> 19) cancel the accumulated scale factors from the quantization,
keeping everything in integer arithmetic with no floating-point operations at inference time.

**Export diagnostics:** The export function prints weight ranges and clipping counts to help
detect quantization-related accuracy loss.

**Policy head note:** Policy head weights are NOT exported to binary format; C++ support
for the policy head is pending.

---

## 9. CLI Reference

```
python -m nnue-train [OPTIONS]
```

### Data and Game Options

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--game` | str | auto-detect | Game type: `minichess`, `minishogi`, `gomoku` |
| `--data` | str | `data/train_*.bin` | Glob pattern for binary data files |
| `--features` | str | `halfkp` | Feature type: `ps` or `halfkp` |
| `--min-ply` | int | 0 | Skip positions with ply below this value |
| `--policy` | flag | false | Enable policy head (requires v3+ data with best_move) |

### Training Hyperparameters

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--epochs` | int | 100 | Number of training epochs |
| `--batch-size` | int | 8192 | Batch size |
| `--lr` | float | 1e-3 | Peak learning rate (Adam) |
| `--accum-size` | int | 128 | Accumulator width (FT output dimension) |
| `--wdl-weight` | float | 0.5 | WDL blending: 0.0 = pure score, 1.0 = pure result |
| `--policy-weight` | float | 0.1 | Weight of policy loss relative to value loss |

### Validation and Schedule

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--val-size` | int | 0 | Fixed number of validation samples (0 = use fraction) |
| `--val-split` | float | 0.05 | Fraction of data for validation (mutually exclusive with --val-size) |
| `--val-every-n-steps` | int | 0 (auto) | Validation interval in steps (0 = auto ~4x/epoch) |
| `--warmup-steps` | int | -1 (auto) | LR warmup steps (-1 = auto 5% of total, max 2000) |
| `--ema-decay` | float | 0.999 | EMA decay rate for model weights |

### Infrastructure

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--num-workers` | int | 0 | DataLoader worker processes |
| `--device` | str | `auto` | Compute device: `auto`, `cpu`, `cuda`, `cuda:0` |
| `--output` | str | `models/nnue_v1.pt` | Path to save PyTorch model |
| `--export` | str | `models/nnue_v1.bin` | Path to export binary weights |

### Weights & Biases (wandb)

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--wandb` | flag | false | Enable wandb logging |
| `--wandb-project` | str | `NNUE` | wandb project name |
| `--wandb-name` | str | auto | wandb run name (auto-generated from config) |

### Example Commands

```bash
# Basic training (minichess, HalfKP, 100 epochs)
python -m nnue-train --data "data/train_*.bin" --features halfkp --epochs 100

# MiniShogi with PS features
python -m nnue-train --game minishogi --data "data/shogi_*.bin" --features ps

# Large-scale run with fixed val size, step-based val, more workers
python -m nnue-train --data "data/*.bin" --val-size 1000000 \
    --val-every-n-steps 2000 --num-workers 4 --epochs 10

# Full production run with wandb
python -m nnue-train \
    --game minichess --data "data_v1/train_*.bin" --features halfkp \
    --accum-size 128 --batch-size 8192 --lr 1e-3 --wdl-weight 0.5 \
    --ema-decay 0.999 --warmup-steps 1000 --epochs 100 \
    --val-size 100000 --val-every-n-steps 2000 --num-workers 2 \
    --device auto --output models/nnue_v1.pt --export models/nnue_v1.bin \
    --wandb --wandb-project NNUE
```

---

## 10. Known Issues and Fixes

### 10.1 Datagen Raw-Eval Bug

**Issue:** An earlier version of `datagen.cpp` recorded the raw static evaluation instead
of the PVS search score. Static eval and search score can differ significantly, especially
in tactical positions. Training on raw eval produces a network that is weaker at tactics.

**Fix:** The current code always records the PVS search score. When a jitter (random) move
is chosen, PVS still runs to obtain an accurate score for the position:

```cpp
if(jitter){
    int idx = rng_int((int)game->legal_actions.size());
    chosen_move = game->legal_actions[idx];
    // Still run a search to get a proper score for this position
    SearchContext score_ctx;
    search_score = PVS::search(game, cfg.depth, score_ctx).score;
}
```

**Score type rule:** The data header summary states: "Score type: **Search score (PVS)** --
never raw eval." This should be verified whenever modifying the datagen code.

**Score perspective:** The search score is from the pre-move player's perspective. Since
the recorded position is post-move, the score is negated: `int score = -search_score`.
Getting this sign wrong produces a network that thinks losing positions are winning.

### 10.2 Windows Shared Memory Exhaustion

**Issue:** PyTorch DataLoader workers on Windows use shared memory (`/dev/shm` equivalent)
to pass tensors from workers to the main process. With HalfKP dense features (~36 KB per
sample), the prefetch queue can exhaust shared memory:

```
4 workers * 8192 batch_size * 2 perspectives * 36 KB = ~2.3 GB per prefetch round
```

This causes `RuntimeError: DataLoader worker exited unexpectedly` or silent hangs.

**Fix:** The sparse feature encoding reduces per-sample transfer size from ~36 KB to ~80
bytes (a 450x reduction). Sparse index arrays are passed through shared memory and
expanded to dense tensors on GPU via `scatter_add_`:

```python
# In features.py: extract_halfkp_sparse returns int32 indices
# In training loop: sparse_to_dense(indices, feature_size) expands on GPU
```

The `NNUEDataset` automatically uses sparse mode for HalfKP features and dense mode for
PS features.

### 10.3 wandb Compatibility

**Issue:** wandb logging is optional and guarded behind a flag. If wandb is not installed,
training works normally without it. However, wandb can introduce overhead on very fast
training loops (logging every step).

**Mitigation:** Train-step logging is throttled to every 50 steps
(`self.global_step % 50 == 0`). Validation metrics are logged at the configured
`val_every_n_steps` interval. The run name is auto-generated from the config if not
specified.

### 10.4 Perspective Flip Bug

**Symptom:** Network plays well as white but poorly as black (or vice versa).

**Cause:** Mismatch between how Python training mirrors the board for the black perspective
and how C++ inference does it. The black perspective must mirror vertically
(`row -> board_h - 1 - row`) and swap colors (`color -> 1 - color`).

**Verification:** Compare feature indices produced by `extract_halfkp_sparse` in Python
against the C++ feature extraction for the same position. They must match exactly.

### 10.5 Quantization Accuracy Loss

**Symptom:** Float eval is strong, but quantized eval plays poorly.

**Cause:** Weights outside the representable range are clipped during quantization:
- FT weights clipped to [-128.5, +128.5] (int16 / QA=255)
- Dense weights clipped to [-2.0, +2.0] (int8 / QB=64)

**Mitigation:** The export function prints weight ranges and clipping counts. If significant
clipping occurs, consider:
- Adding weight decay or gradient clipping during training
- Increasing quantization constants (requires matching C++ changes)
- Using `SCORE_SCALE` adjustment to reduce weight magnitudes

**Critical:** The quantization constants `QA=255`, `QA_HIDDEN=127`, `QB=64` must match
exactly between `nnue-train/export.py` and `src/nnue/compute_quant.hpp`.

### 10.6 Mmap Handle Leaks

**Issue:** If `MmapDataSource` is not properly garbage collected, mmap file handles may
remain open. On Windows, this can prevent the data files from being deleted or overwritten.

**Mitigation:** The `__getstate__` method ensures mmap handles are not carried across
process boundaries. The `del mmap, data` call after indexing releases the temporary mmap
used during construction. For long-running sessions, explicitly delete the data source
or use a context manager.
