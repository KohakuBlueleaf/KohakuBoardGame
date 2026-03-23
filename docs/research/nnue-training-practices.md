# NNUE Training Best Practices

A comprehensive guide to training NNUE (Efficiently Updatable Neural Network) evaluation
networks for chess and chess variants. This document synthesizes knowledge from the
Stockfish project, nnue-pytorch, academic research, and the engine development community.

---

## Table of Contents

1. [Network Architecture Choices](#1-network-architecture-choices)
2. [Loss Function Design](#2-loss-function-design)
3. [Training Hyperparameters](#3-training-hyperparameters)
4. [EMA vs Raw Weights for Inference](#4-ema-vs-raw-weights-for-inference)
5. [Quantization Strategies](#5-quantization-strategies)
6. [Fine-Tuning vs Training from Scratch](#6-fine-tuning-vs-training-from-scratch)
7. [Data Requirements](#7-data-requirements)
8. [Common Pitfalls and Failure Modes](#8-common-pitfalls-and-failure-modes)

---

## 1. Network Architecture Choices

### 1.1 Feature Sets

NNUE architectures differ primarily in how they encode the board as input features.
The choice of feature set determines the first layer size and directly impacts model
capacity, training data requirements, and inference speed.

#### PieceSquare (PS)

The simplest encoding. Each feature is a `(piece_type, piece_color, square)` tuple.
For standard chess: `2 colors * 6 piece_types * 64 squares = 768` features.

- **Pros**: Compact, fast, low memory.
- **Cons**: No king-relative information; the network cannot learn that a pawn on e4
  matters differently depending on where the king stands.
- **Best for**: Small variants (e.g., 5x5 minichess) where the king's position has
  less strategic variation, or as a baseline to compare against.

#### HalfKP

Each feature is `(own_king_square, piece_square, piece_type, piece_color)` -- excluding
kings from the piece set. For standard chess:
`64 king_squares * 64 piece_squares * 5 piece_types * 2 colors = 40,960` features.

- **Pros**: Sweet spot of size vs. expressiveness. Only ~30 features are active per
  position, so despite the large input dimension, updates are sparse and fast. Most
  network capacity resides in the first layer, which is the cheapest to evaluate
  incrementally.
- **Cons**: Does not include king-as-piece features. Slightly less expressive than
  HalfKA variants.
- **History**: The original Shogi NNUE feature set. Used by Stockfish through SF13.

#### HalfKA / HalfKAv2

Like HalfKP but includes the king as a piece type (12 piece types instead of 10 for
standard chess). HalfKAv2 is an optimized variant that removes redundant king-own
features (you already know where your own king is from the king-square axis):
`11 * 64 * 64 = 45,056` inputs per side.

HalfKAv2 additionally includes:
- **PSQT outputs from the feature transformer**: 8 piece-square-table buckets fed
  directly to the output, allowing the network to learn material-imbalance patterns
  without routing them through the narrow hidden layers.
- **Output buckets**: The game phase is divided into 8 buckets based on
  `(piece_count - 1) / 4`, each with its own sub-network (layer stack). This lets
  the network specialize evaluation for opening, middlegame, and endgame.

- **Pros**: Most expressive standard feature set. The PSQT outputs provide a strong
  baseline that the hidden layers refine.
- **Cons**: Largest input dimension. Requires more training data to fully utilize.
- **Used by**: Stockfish 14+ (SFNNv4 and later).

#### Choosing for Variants

For a variant like minishogi (5x5 board, 6 piece types, hand pieces):

| Feature Set | Input Dimension | Notes |
|-------------|----------------|-------|
| PS          | ~360           | Compact; good starting point |
| HalfKP      | ~9,000         | King-relative; needs sparse input handling |
| HalfKP+Hand | ~9,030         | Adds hand-piece features for drops |

The smaller the board, the less critical king-relative features become, because every
piece is already "near" the king. PS features may suffice. However, HalfKP still
provides measurable gains even on 5x5 because it lets the network distinguish
same-side vs. cross-board piece placement relative to the king.

### 1.2 Layer Sizes

The canonical NNUE architecture is:

```
Feature Transformer (sparse first layer)
  -> SCReLU
  -> Concatenate [STM perspective, NSTM perspective]
  -> Dense L1 -> SCReLU
  -> Dense L2 -> SCReLU
  -> Output (1 neuron, scalar eval)
```

#### Feature Transformer (Accumulator)

This is by far the largest layer and contains most of the parameters.

| Accumulator Size | Parameters (HalfKP 40K) | Parameters (PS 768) | Notes |
|-----------------|------------------------|---------------------|-------|
| 128             | ~5.2M                  | ~100K               | Minimum viable for variants |
| 256             | ~10.5M                 | ~200K               | Good balance for standard chess |
| 512             | ~21M                   | ~400K               | Used by some SF architectures |
| 768             | ~31M                   | ~600K               | SFNNv9 (2024) |
| 1024+           | ~41M+                  | ~800K+              | Diminishing returns without massive data |

**Rule of thumb**: For small variants, 64-128 accumulator neurons are sufficient.
For standard chess with HalfKP/HalfKAv2, 256-1024 is the productive range.

#### Hidden Layers

Typically 1-2 small dense layers after the perspective concatenation:

- **Stockfish classic**: `256x2 -> 32 -> 32 -> 1` (two hidden layers of 32)
- **Stockfish SFNNv4+**: `512x2 -> 16 -> 32 -> 1` (first hidden layer shrinks)
- **Common variant config**: `128x2 -> 32 -> 32 -> 1`

Larger hidden layers (64, 128) are possible but provide diminishing returns relative
to their inference cost, because the feature transformer already encodes most of the
positional knowledge.

### 1.3 Activation Functions

#### Clipped ReLU (CReLU)

`CReLU(x) = clamp(x, 0, 1)` -- the original NNUE activation.

After quantization, the activation range becomes `[0, 127]` (uint8), enabling
efficient SIMD computation.

#### Squared Clipped ReLU (SCReLU)

`SCReLU(x) = clamp(x, 0, 1)^2` -- a strictly superior activation for NNUE.

Benefits over CReLU:
- Provides additional nonlinearity that lets shallow architectures capture more
  complex patterns.
- At equivalent neuron counts, SCReLU achieves the same loss as a CReLU network
  with 50% more neurons.
- Many engines report double-digit Elo gains from switching CReLU to SCReLU.
- The squaring operation adds negligible cost in both float and quantized inference.

**Recommendation**: Always use SCReLU unless you have a specific reason not to.

### 1.4 Perspective Network

NNUE computes features from both sides' perspectives:

1. **White accumulator**: Features indexed by white's king position.
2. **Black accumulator**: Features indexed by black's (mirrored) king position.

At evaluation time, these are concatenated as `[STM_accumulator, NSTM_accumulator]`,
where STM = side to move. This lets the network learn that "having the move" changes
the evaluation in a structured way.

For black's perspective in chess, the board is flipped vertically (A1 becomes A8) and
colors are swapped. For shogi variants with rotational symmetry, a 180-degree rotation
is used instead.

---

## 2. Loss Function Design

### 2.1 Sigmoid-Space MSE

The standard NNUE loss operates in "WDL space" (Win-Draw-Loss probability space)
rather than raw centipawn space. This is accomplished by applying a sigmoid transform:

```python
SCORE_SCALE = 400.0  # engine-dependent; Stockfish uses ~410

pred_wdl  = sigmoid(predicted_eval / SCORE_SCALE)
target_wdl = sigmoid(target_score / SCORE_SCALE)

loss = mean((pred_wdl - target_wdl) ** 2)
```

**Why WDL space?**
- Large evaluations (e.g., +1500 cp vs +2000 cp) are compressed together, reflecting
  that both are "winning" and precision there matters less.
- Small differences near 0 cp are expanded, giving the network more incentive to be
  precise in balanced positions where accuracy matters most.
- Prevents large gradients from extreme evaluations dominating training.
- Enables blending with game results (which are naturally in WDL space).

### 2.2 Score Scaling Factor

The `SCORE_SCALE` parameter (often called `nnue_pawn_value_eg` or simply the scaling
constant) controls the sigmoid's steepness:

- **Lower values** (e.g., 200): Steeper sigmoid, more compression. Extreme evals
  produce nearly identical WDL values. Risk: near-equal positions get too little
  gradient.
- **Higher values** (e.g., 600): Gentler sigmoid, less compression. The network
  tries harder to distinguish large advantages. Risk: training becomes dominated by
  extreme-eval positions.
- **Typical range**: 361-410 for Stockfish-generated data. The value should match the
  engine that produced the training scores. Using the wrong scale factor is a common
  source of training failure.

### 2.3 WDL Blending (Lambda)

The key innovation in modern NNUE training: blend the engine's score target with the
actual game result:

```python
wdl_eval = sigmoid(target_score / SCORE_SCALE)   # what the engine thought
wdl_result = (game_result + 1) / 2               # -1->0, 0->0.5, 1->1.0

target = (1 - lambda) * wdl_eval + lambda * wdl_result

loss = mean((pred_wdl - target) ** 2)
```

- **lambda = 0.0**: Train purely on engine scores. The network learns to replicate the
  search evaluation.
- **lambda = 1.0**: Train purely on game outcomes. The network learns to predict who
  wins.
- **lambda = 0.3-0.5**: Typical sweet spot. The engine score provides a stable signal
  (low variance, possibly biased), while the game result provides ground truth (high
  variance, unbiased). Blending gives the best of both.

#### Lambda Scheduling

Some training pipelines schedule lambda over training:

- **Start with lambda=1.0** (score-heavy): Let the network quickly learn piece values
  and basic positional concepts from the deterministic score signal.
- **Anneal toward lambda=0.5**: Gradually incorporate game outcomes to correct biases
  in the engine's evaluation.
- **Alternative**: Use fixed lambda=0.5 throughout (simpler, often equally effective).

### 2.4 Loss Exponent

The MSE exponent can be tuned beyond the standard 2.0:

```python
loss = mean(|pred_wdl - target| ** exponent)
```

- **Exponent 2.0**: Standard MSE. Equal weight to all errors.
- **Exponent 2.6**: Used by some Stockfish networks. Increases weight on larger errors,
  pushing the network to get outlier positions right at the cost of micro-precision on
  well-learned positions.
- **Exponent 3.0+**: Aggressive outlier focusing. Risk of instability.

**Recommendation**: Start with 2.0. Experiment with 2.4-2.6 once training is stable.

### 2.5 Dual Loss (Value + Policy)

If training a combined value-policy network:

```python
total_loss = value_loss + policy_weight * cross_entropy(policy_logits, best_move)
```

Typical `policy_weight` is 0.1-0.3. The policy head can improve move ordering in
search but should not dominate the value head's learning.

---

## 3. Training Hyperparameters

### 3.1 Optimizer

| Optimizer | Pros | Cons | Recommendation |
|-----------|------|------|----------------|
| **Adam**  | Adaptive LR per parameter; works well out of the box | Can overfit; weight decay behavior differs from SGD | Default choice for NNUE |
| **Ranger** (RAdam + Lookahead) | Stable early training; less sensitive to LR | Slightly more complex; two sets of hyperparameters | Good alternative; used by some SF trainers |
| **SGD + Momentum** | Better generalization with proper LR schedule | Requires careful LR tuning; slower convergence | Viable with cosine schedule but more finicky |

**Recommendation**: Use Adam with a cosine LR schedule. It is the most robust choice
and the default in nnue-pytorch.

### 3.2 Learning Rate

- **Initial LR**: `8.75e-4` to `1e-3` for Adam with batch size 16384.
- **Schedule**: Cosine annealing to ~1% of initial LR over the total training steps.
- **Warmup**: 1000-2000 steps of linear warmup. Prevents early instability,
  especially with large batch sizes.

LR and batch size are coupled. If you halve the batch size, consider halving the LR
(linear scaling rule). However, NNUE training is less sensitive to this than ImageNet-
scale tasks.

### 3.3 Batch Size

- **Recommended**: 16384 (the nnue-pytorch default).
- **Range**: 8192-32768 works well. Smaller batches see more diverse data per epoch
  but train slower per wall-clock time. Larger batches are more GPU-efficient but may
  need LR adjustment.
- **GPU memory**: For HalfKP features with sparse input, batch size is rarely the
  memory bottleneck. For dense PS features, 16384 easily fits even on modest GPUs.

### 3.4 Epochs and Duration

- **Maturation**: Networks typically mature after ~400 epochs on large datasets, but
  can be competitive after only ~100 epochs.
- **Diminishing returns**: After ~400 epochs, improvements flatten. The nnue-pytorch
  default `max_epochs` is 800, providing ample runway.
- **Step-based training**: An alternative to epoch-based training is to set a total
  step count (e.g., 100,000-500,000 steps). This decouples training duration from
  dataset size.
- **Early stopping**: Monitor validation loss. If it stops decreasing for 50-100
  epochs, further training is unlikely to help.

### 3.5 Threads and Workers

- **PyTorch threads** (`--threads`): 4 is generally sufficient. Benchmark between 1-8
  on your hardware.
- **Data loader workers** (`--num-workers`): At least 2-3. More workers help if data
  loading is the bottleneck (large datasets, HDD storage). On NVMe, 2-4 workers
  typically saturate the pipeline.

### 3.6 WDL Weight (Lambda)

- **Typical**: 0.3-0.5 for game data with engine scores.
- **Score-only data** (no game results): Use lambda=0.0 (all score, no WDL blending).
- **Result-only data**: Use lambda=1.0.

### 3.7 Summary of Recommended Defaults

| Parameter | Value | Notes |
|-----------|-------|-------|
| Optimizer | Adam | |
| LR | 1e-3 | With cosine schedule |
| Batch size | 16384 | Adjust LR if changed |
| Warmup | 1000 steps | Linear |
| LR schedule | Cosine to 1% | |
| WDL weight | 0.5 | Blend score and result equally |
| Loss exponent | 2.0 | Start here; try 2.6 later |
| EMA decay | 0.999 | |
| Score scale | 400 | Match your engine's internal scale |

---

## 4. EMA vs Raw Weights for Inference

### 4.1 What is EMA?

Exponential Moving Average maintains a shadow copy of the model parameters, updated
after each optimizer step:

```
theta_ema = decay * theta_ema + (1 - decay) * theta_current
```

With `decay = 0.999`, the EMA model is a smoothed average of the last ~1000 parameter
states.

### 4.2 Why Use EMA?

- **Smoother predictions**: Raw training weights oscillate as the optimizer navigates
  the loss landscape. EMA weights average out these oscillations, producing more
  consistent evaluations.
- **Better generalization**: EMA models often generalize better to unseen positions,
  analogous to Stochastic Weight Averaging (SWA) but applied continuously.
- **Robustness to noise**: Training data is inherently noisy (search scores vary with
  depth, game results are stochastic). EMA dampens the network's response to
  individual noisy samples.
- **Label noise resilience**: EMA has been shown to improve robustness to noisy labels,
  calibration, and transfer learning.

### 4.3 Practical Usage

- **During training**: Maintain both raw weights (for optimization) and EMA weights
  (for evaluation/export).
- **Validation**: Run validation using EMA weights to get a more accurate picture of
  model quality.
- **Export**: Always export EMA weights for the engine. The raw training weights should
  never be used for inference.
- **Checkpointing**: Save both raw and EMA weights in checkpoints to enable training
  resumption.

### 4.4 Decay Rate

- **0.999**: Standard choice. Averages ~1000 recent steps. Good balance between
  smoothing and responsiveness.
- **0.9999**: Heavier averaging. Better for very long training runs where you want
  strong smoothing. Can lag behind if the model is still improving rapidly.
- **0.99**: Light averaging. Tracks the raw weights more closely. Less smoothing
  benefit.

### 4.5 EMA Implementation

A minimal implementation (as used in this project's `nnue-train/trainer.py`):

```python
class EMA:
    def __init__(self, model, decay=0.999):
        self.decay = decay
        self.shadow = {k: v.clone() for k, v in model.state_dict().items()}

    @torch.no_grad()
    def update(self, model):
        for k, v in model.state_dict().items():
            self.shadow[k].mul_(self.decay).add_(v, alpha=1 - self.decay)

    def apply(self, model):
        model.load_state_dict(self.shadow)
```

Call `ema.update(model)` after every optimizer step. Use `ema.apply(model)` before
export or validation.

---

## 5. Quantization Strategies

### 5.1 Why Quantize?

NNUE networks are designed for CPU inference, not GPU. Quantization provides two
critical benefits:

1. **Speed**: Integer arithmetic (int8/int16) is faster than float32 on CPUs, and
   SIMD instructions (AVX2, NEON) can process 4-8x more int8 operations per cycle
   than float32 operations.
2. **Throughput**: Quantizing from float32 to int8 means 4x more values fit in the
   same SIMD register, enabling 4x more parallel operations.

Floating point is **not competitive** for maximum engine strength because the speed
penalty outweighs any accuracy advantage.

### 5.2 What Gets Quantized and How

The quantization scheme varies by layer, following a principle: use the smallest
integer type that avoids overflow.

#### Feature Transformer (FT)

| Component | Type | Scale | Range | Rationale |
|-----------|------|-------|-------|-----------|
| Weights | int16 | QA=255 | [-32768, 32767] | ~30 active features are summed; int8 would overflow |
| Bias | int16 | QA=255 | [-32768, 32767] | Same scale as accumulator |
| Accumulator | int16 | QA=255 | [-32768, 32767] | Sum of ~30 weight rows + bias |

The accumulator is the core of NNUE's incremental update efficiency. It stores the
feature transformer output as part of the position state, updated differentially on
each move.

#### SCReLU Activation (post-FT)

The SCReLU activation converts int16 accumulator values to uint8:

```
SCReLU(x) = clamp(x, 0, QA)^2 >> shift
```

For QA=255: `clamp(x, 0, 255)^2 >> 9` produces values in `[0, 127]` (uint8, scale
QA_HIDDEN=127).

#### Dense Hidden Layers

| Component | Type | Scale | Range | Rationale |
|-----------|------|-------|-------|-----------|
| Weights | int8 | QB=64 | [-128, 127] | Small enough for int8; enables fast int8 matmul |
| Bias | int32 | QAH_QB=8128 | [-2^31, 2^31-1] | Accumulation happens in int32 |
| Activation input | uint8 | QA_HIDDEN=127 | [0, 127] | Output of SCReLU |
| Matmul result | int32 | QAH_QB=8128 | [-2^31, 2^31-1] | int8 * uint8 accumulated in int32 |

The SIMD matmul for dense layers operates as:
```
output_i32 = sum(input_u8[j] * weight_i8[i][j])  // for all j in row
output_i32 += bias_i32[i]
```

Then SCReLU maps the int32 result back to uint8 for the next layer.

#### Output Layer

The output layer produces an int32 result divided by `QAH_QB` to recover centipawns.

### 5.3 Weight Clipping During Training

**Critical**: Weights must be clipped during training to stay within quantization
bounds. If a float weight exceeds the representable range after scaling, it will be
clamped during quantization, introducing error.

For int8 weights with scale QB=64:
- Representable range: `[-128/64, 127/64] = [-2.0, 1.984]`
- Safe clipping bound: `[-1.98, +1.98]`

This is enforced via a `WeightClippingCallback` that clamps weights after each
optimizer step. Without clipping, weights can grow beyond the quantization range,
and the model silently learns to depend on values it cannot represent at inference
time.

### 5.4 Quantization Error

Quantization introduces rounding error at every layer. The error compounds through
the network:

- **FT layer**: Low error (scale 255 provides ~0.004 resolution per weight).
- **Dense layers**: Higher error per weight (scale 64 provides ~0.016 resolution),
  but fewer parameters.
- **Output**: Accumulated error is typically 1-5 centipawns, which is insignificant
  for playing strength.

The network implicitly learns to be quantization-friendly during training if weight
clipping is applied. Weights naturally avoid the clipping boundaries, and the network
distributes information across many small weights rather than relying on a few large
ones.

### 5.5 Quantization Constants Reference

For the quantization scheme used in this project (`nnue-train/export.py` and
`src/nnue/compute_quant.hpp`):

```
QA        = 255    # FT accumulator scale (float -> int16)
QA_HIDDEN = 127    # Hidden activation scale (uint8 range)
QB        = 64     # Dense weight scale (float -> int8)
QAH_QB    = 8128   # = QA_HIDDEN * QB, bias scale for dense layers
```

---

## 6. Fine-Tuning vs Training from Scratch

### 6.1 When to Train from Scratch

- **New architecture**: Changed feature set, layer sizes, or activation function.
  The old weights are incompatible or suboptimal for the new architecture.
- **First network**: No prior checkpoint exists.
- **Very different data domain**: The new training data is fundamentally different
  (e.g., switching from standard chess to a variant with drops).
- **Architecture experiments**: When comparing architectures, training from scratch
  provides cleaner comparisons.

### 6.2 When to Fine-Tune

- **Better data available**: A network trained on depth-6 data can be fine-tuned on
  depth-12 data. The existing weights provide a strong initialization, and the higher-
  quality data refines the evaluation.
- **Different data distribution**: Retraining on a different opening book, time
  control, or opponent strength.
- **Post-training refinement**: Fine-tune on a curated dataset of positions where the
  current network is weakest.
- **Iterative improvement**: Generate new data with the current network, then fine-
  tune on it (the Stockfish development loop).

### 6.3 Fine-Tuning Protocol

Based on the nnue-pytorch best practices:

1. **Start from a checkpoint**: Use `--resume_from_checkpoint path/to/model.ckpt` to
   load both model weights and optimizer state.
2. **Reduce the learning rate**: Use 0.5x the original LR (e.g., `4.375e-4` instead
   of `8.75e-4`).
3. **Use a slower LR schedule**: Gamma of 0.995 instead of 0.992 (for step-decay
   schedules), or extend the cosine period.
4. **Extend training**: Use `max_epochs=800` instead of 600 to give the fine-tuned
   network more time to adapt.
5. **Adjust lambda**: If fine-tuning on higher-quality data (e.g., LC0-derived
   scores), you may want to increase the score weight (lower lambda).

### 6.4 Transfer Learning Hierarchy

The Stockfish community has established that:

1. Train a base network on large-scale self-play data (e.g., Stockfish depth-9,
   5000 nodes).
2. Fine-tune on higher-quality data (e.g., LC0-derived evaluations).
3. Fine-tune again on specialized data if needed.

High-quality datasets achieve better results when used to **retrain** a network
trained on lower-quality data than when training from scratch on the high-quality
data alone. The base network provides structural knowledge that the fine-tuning
data refines.

---

## 7. Data Requirements

### 7.1 Dataset Size

| Network Size | Minimum Positions | Recommended | Notes |
|-------------|-------------------|-------------|-------|
| Small (PS, 128 accum, ~100K params) | 5-10M | 20-50M | Small variants |
| Medium (HalfKP, 256 accum, ~10M params) | 100M | 500M-1B | Standard chess |
| Large (HalfKAv2, 512+ accum, ~20M+ params) | 500M | 1B+ | Competitive strength |

**Rules of thumb**:
- Minimum ~10-100 positions per parameter for a viable network.
- ~100 positions per parameter for a well-trained network.
- A few million positions can work for very small networks, but 15M is reported as
  insufficient for standard chess architectures.
- 1 billion positions is sufficient to train good 256-hidden-layer networks.

### 7.2 Data Generation Methods

#### Self-Play with Fixed Nodes

The most common approach:
1. Play games from varied starting positions (large opening book or random moves).
2. Use a fixed node budget per move (e.g., 5000 nodes) rather than fixed depth.
3. Record each position's board state, engine evaluation, and game result.
4. Adjudicate games when the evaluation exceeds a threshold (e.g., |eval| > 3000 cp
   for 5 consecutive moves).

#### Depth-Based Generation

Alternative approach:
1. Extract ~10% of positions from each self-play game.
2. Re-evaluate each position at a fixed depth (e.g., depth 8-12).
3. Use the deeper evaluation as the training target.

#### Random Opening Positions

To ensure diversity:
- Play 7-8 random moves from the start position, then begin recording.
- Use a large opening test suite (thousands of positions).
- Both approaches help prevent the network from overfitting to a narrow set of
  positions/structures.

### 7.3 Position Quality and Filtering

#### Quiet Positions Only

Train only on "quiet" positions where the evaluation is stable:
- **Skip positions where the side to move is in check**: These are tactical and the
  evaluation is volatile.
- **Skip positions where the best move is a capture** ("smart FEN skipping"): Capture
  positions are poorly understood by NNUE and training on them degrades the network.
- Only include positions where subsequent move sequences (captures, checks) do not
  drastically change the material balance.

#### Random FEN Skipping

The `--random-fen-skipping` parameter controls a probability of skipping each sample.
Higher values make the trainer see more diverse data in less time, at the cost of
potentially slower convergence per position seen. Values of 3-10 are common.

#### Eval-WDL Correlation Filtering

Optionally skip positions where the engine evaluation does not correlate with the
game result (e.g., the engine says +300 cp but the game was a loss). This removes
noisy samples but must be used carefully to avoid biasing the dataset.

### 7.4 Diversity Requirements

- **Opening variety**: Positions from many different openings and pawn structures.
  If all training games start from 1.e4 e5, the network will be weak in other
  openings.
- **Game phase coverage**: Include positions from openings, middlegames, and
  endgames in roughly natural proportions.
- **Score distribution**: Include positions with evaluations ranging from -3000 to
  +3000 cp. Overrepresentation of drawish positions (near 0 cp) can bias the
  network toward predicting draws.
- **Result balance**: Approximately equal numbers of white wins, draws, and black
  wins. Imbalanced results bias the network's baseline evaluation.

### 7.5 Data Provenance for Competition

If participating in competitions (TCEC, CCC), prefer generating your own data with
your own engine. Using LC0 or Stockfish data is generally acceptable for development
but may not be allowed in competition contexts.

---

## 8. Common Pitfalls and Failure Modes

### 8.1 Wrong Score Scale

**Symptom**: Training loss decreases but the exported network plays terribly.

**Cause**: The `SCORE_SCALE` constant in the loss function does not match the scale
of the engine evaluations in the training data. For example, if your engine reports
scores in units where pawn = 100 but you use `SCORE_SCALE = 400` (designed for
pawn = 400), the sigmoid mapping will be wrong.

**Fix**: Set `SCORE_SCALE` to match your engine's evaluation scale. A pawn should
map to approximately `sigmoid(pawn_value / SCORE_SCALE) = 0.62` (62% expected
score).

### 8.2 Weight Explosion / NaN Loss

**Symptom**: Loss suddenly becomes NaN or inf, or weights grow to extreme values.

**Causes**:
- Learning rate too high.
- No weight clipping, allowing weights to exceed quantization bounds.
- No gradient clipping, allowing explosive parameter updates.
- Bad training data (positions with extreme evaluations, e.g., mate scores stored
  as large integers).

**Fixes**:
- Reduce learning rate by 10x.
- Enable gradient clipping (`torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)`).
- Add weight clipping callback.
- Filter out positions with `|score| > 10000` from training data.
- Use warmup to stabilize early training.

### 8.3 Overfitting

**Symptom**: Training loss continues decreasing while validation loss plateaus or
increases.

**Causes**:
- Dataset too small for the model size.
- Too many epochs without early stopping.
- Insufficient data diversity (e.g., all positions from the same opening).
- No regularization.

**Fixes**:
- Generate more training data.
- Reduce model capacity (smaller accumulator or hidden layers).
- Use EMA weights (natural regularizer).
- Add dropout (though this is uncommon in NNUE).
- Increase `random-fen-skipping` to see more diverse data.
- Stop training when validation loss stagnates.

### 8.4 Quantization Mismatch

**Symptom**: Network plays well in float mode but poorly after quantization.

**Cause**: Training weights exceed quantization bounds, or the network relies on
fine-grained weight differences that are lost to rounding.

**Fixes**:
- Enable weight clipping during training (most important fix).
- Verify that the quantization constants in training match the C++ inference code.
- Compare float vs. quantized output on a set of test positions; if the mean
  absolute error exceeds ~5 cp, investigate.

### 8.5 Feature Factorization Issues

**Symptom**: Rare features (positions with unusual king placements) are poorly
evaluated.

**Cause**: With 40K+ input features but only ~30 active per position, most feature
weights receive very few gradient updates during training.

**Solution**: Feature factorization introduces "virtual" dense features that share
gradients across related sparse features. For example, a virtual PS feature that
ignores the king position will update all HalfKP features for that piece-square
simultaneously. This is especially important in early training to bootstrap all
feature weights to reasonable values.

**Caveat**: Some virtual feature sets may have a single position activating the same
virtual feature multiple times, which requires gradient scaling to handle correctly.

### 8.6 Poor Data Quality

**Symptom**: Training converges but the network plays weakly.

**Causes**:
- Training on tactical/noisy positions (in-check, captures).
- Inconsistent evaluation scale (mixing data from different engines with different
  scales).
- Too-shallow search depth for generating scores (depth 1-3 produces noisy labels).
- Mate scores not handled properly (stored as large values that dominate the loss).

**Fixes**:
- Filter to quiet positions (no in-check, no capture best-moves).
- Use consistent engine/settings for all data generation.
- Generate data at depth 6+ or 5000+ nodes.
- Cap scores to a reasonable range (e.g., [-3000, 3000] cp).

### 8.7 Perspective / Mirroring Bugs

**Symptom**: The network plays well as white but poorly as black (or vice versa).

**Cause**: The perspective flip (vertical mirror for chess, rotation for shogi) is
implemented incorrectly in either the training features or the inference code.

**Fix**: Verify on a known position that white_features and black_features are
correct. Verify that the C++ feature extraction mirrors the Python training code
exactly.

### 8.8 Incorrect Concatenation Order

**Symptom**: Network is weak despite good training metrics.

**Cause**: The concatenation order `[STM, NSTM]` in training does not match the
inference code. If training uses `[white, black]` but inference uses `[STM, NSTM]`
(or vice versa), the dense layers receive scrambled inputs.

**Fix**: Ensure both training and inference use the same convention. The standard is
`[STM_accumulator, NSTM_accumulator]`.

### 8.9 Not Using EMA for Export

**Symptom**: Exported network is slightly weaker than expected from validation metrics.

**Cause**: The raw training weights were exported instead of the EMA weights.

**Fix**: Always apply EMA weights to the model before exporting. The EMA weights are
what the validation metrics were computed on.

### 8.10 Insufficient Warmup

**Symptom**: Training is unstable in the first few hundred steps, possibly diverging.

**Cause**: Large initial gradients from randomly initialized weights combined with a
high learning rate.

**Fix**: Use 1000-2000 steps of linear learning rate warmup. This gives the network
time to find a reasonable region of parameter space before applying the full learning
rate.

---

## References and Sources

- [Stockfish NNUE Documentation](https://official-stockfish.github.io/docs/nnue-pytorch-wiki/docs/nnue.html)
- [nnue-pytorch GitHub Repository](https://github.com/official-stockfish/nnue-pytorch)
- [nnue-pytorch Wiki: Basic Training Procedure](https://github.com/official-stockfish/nnue-pytorch/wiki/Basic-training-procedure-(train.py))
- [nnue-pytorch Wiki: Training Datasets](https://github.com/official-stockfish/nnue-pytorch/wiki/Training-datasets)
- [nnue-pytorch NNUE Architecture Reference (DeepWiki)](https://deepwiki.com/official-stockfish/nnue-pytorch/9-nnue-architecture-reference)
- [Stockfish NNUE (Chessprogramming Wiki)](https://www.chessprogramming.org/Stockfish_NNUE)
- [NNUE (Chessprogramming Wiki)](https://www.chessprogramming.org/NNUE)
- [Features Documentation (Stockfish Docs)](https://official-stockfish.github.io/docs/nnue-pytorch-wiki/docs/features.html)
- [Fairy-Stockfish variant-nnue-pytorch](https://github.com/fairy-stockfish/variant-nnue-pytorch/blob/master/docs/nnue.md)
- [Study of the Proper NNUE Dataset (arXiv:2412.17948)](https://arxiv.org/html/2412.17948v1)
- [Best Practices for NNUE Training Data Generation (TalkChess)](https://talkchess.com/viewtopic.php?t=83944)
- [NNUE Training Set Generation (TalkChess)](https://talkchess.com/viewtopic.php?t=77606)
- [SCReLU and NNUE Research](https://cosmo.tardis.ac/files/2024-06-25-nnue-research-01.html)
- [Better Activation Functions for NNUE](https://cosmo.tardis.ac/files/2026-01-27-activation-2.html)
- [Exponential Moving Average of Weights in Deep Learning (arXiv:2411.18704)](https://arxiv.org/abs/2411.18704)
- [NNUE on Wikipedia](https://en.wikipedia.org/wiki/Efficiently_updatable_neural_network)
