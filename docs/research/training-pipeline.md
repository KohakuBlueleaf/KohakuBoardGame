# Optimal NNUE Training Pipeline for Small Board Games

A practical, end-to-end guide for training NNUE evaluation networks for
MiniChess (6x5), MiniShogi (5x5), and similar small-board variants. This
document merges data generation strategy with training best practices into
a single actionable pipeline, with concrete configurations tuned for this
project's architecture.

---

## Table of Contents

1. [Pipeline Overview](#1-pipeline-overview)
2. [Quick Start Recipe](#2-quick-start-recipe)
3. [Stage 1: Data Generation](#3-stage-1-data-generation)
4. [Stage 2: Training](#4-stage-2-training)
5. [Stage 3: Export and Quantization](#5-stage-3-export-and-quantization)
6. [Stage 4: Evaluation and Iteration](#6-stage-4-evaluation-and-iteration)
7. [Cross-Cutting Interactions: Data Quality Meets Training](#7-cross-cutting-interactions-data-quality-meets-training)
8. [The Raw Eval Bug: Lessons and Downstream Impact](#8-the-raw-eval-bug-lessons-and-downstream-impact)
9. [Recommended Configuration Reference](#9-recommended-configuration-reference)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Pipeline Overview

The NNUE training pipeline is a loop of four stages. Each stage's output feeds
directly into the next:

```
 +-------------+      +-------------+      +------------------+      +------------------+
 | 1. DATAGEN  | ---> | 2. TRAINING | ---> | 3. EXPORT/QUANT  | ---> | 4. EVAL/ITERATE  |
 | Self-play   |      | PyTorch     |      | Float + int8/16  |      | Engine strength  |
 | positions + |      | Sigmoid MSE |      | binary weights   |      | testing, then    |
 | scores +    |      | WDL blend   |      |                  |      | loop back to (1) |
 | results     |      | EMA, cosine |      |                  |      |                  |
 +-------------+      +-------------+      +------------------+      +------------------+
       ^                                                                      |
       +----------------------------------------------------------------------+
                               Iterative refinement loop
```

**Key principle:** The quality of each stage constrains the next. Fast,
cheap data with noisy labels will waste training compute. Perfect training
on bad data will produce a bad network. The pipeline is only as strong as
its weakest link.

### This Project's Stack

| Component | Implementation |
|-----------|---------------|
| Engine | C++ PVS alpha-beta with optional NNUE eval |
| Datagen | `src/datagen.cpp` -- self-play with epsilon-greedy jitter |
| Data format | Binary `.bin` files (BGDT header + packed records) |
| Training | `nnue-train/` package -- custom PyTorch loop |
| Features | HalfKP with `nn.EmbeddingBag` (sparse) or PieceSquare (dense) |
| Activation | SCReLU (`clamp(x,0,1)^2`) |
| Loss | Sigmoid-space MSE with WDL blending |
| LR schedule | AnySchedule: cosine decay + linear warmup |
| Weight averaging | EMA (exponential moving average, decay=0.999) |
| Export | Float32 `.bin` + quantized int16/int8 `.bin` |
| Orchestration | `scripts/gen_data.sh` (parallel datagen), `python -m nnue-train` |

---

## 2. Quick Start Recipe

This section provides exact commands for a complete cycle. Adjust paths and
game name as needed.

### 2.1 Generate Data (MiniChess)

```bash
# Build the datagen binary
make minichess-datagen

# Generate ~1.5M positions (50K games x ~30 pos/game) with 16 parallel workers
bash scripts/gen_data.sh \
  -g minichess \
  -n 50000 \
  -w 16 \
  -d 6 \
  -e 0.10 \
  -o data
```

For a first training run, 1-2M positions is enough to verify the pipeline works.
For competitive strength, target 10M-50M positions (see Section 3.6).

### 2.2 Train

```bash
python -m nnue-train \
  --game minichess \
  --data "data/train_*.bin" \
  --features halfkp \
  --accum-size 128 \
  --batch-size 8192 \
  --lr 1e-3 \
  --wdl-weight 0.5 \
  --ema-decay 0.999 \
  --warmup-steps 1000 \
  --epochs 100 \
  --val-size 100000 \
  --val-every-n-steps 2000 \
  --num-workers 2 \
  --device auto \
  --output models/nnue_v1.pt \
  --export models/nnue_v1.bin \
  --wandb
```

### 2.3 Evaluate

```bash
# Run the engine with the new NNUE
./build/minichess-selfplay -m models/nnue_v1.bin -n 200

# Compare against previous net or handcrafted eval
# (use your existing benchmark/selfplay infrastructure)
```

### 2.4 Iterate

```bash
# Generate new data with the NNUE-powered engine
bash scripts/gen_data.sh \
  -g minichess \
  -n 100000 \
  -w 16 \
  -d 6 \
  -e 0.10 \
  -m models/nnue_v1.bin \
  -o data_v2

# Retrain (fine-tune) on the new data
python -m nnue-train \
  --data "data_v2/train_*.bin" \
  --features halfkp \
  --lr 5e-4 \
  --epochs 50 \
  --output models/nnue_v2.pt \
  --export models/nnue_v2.bin
```

### 2.5 MiniShogi Variant

```bash
# Datagen for MiniShogi (5x5, with hand pieces/drops)
bash scripts/gen_data.sh -g minishogi -n 50000 -w 16 -d 6 -e 0.10 -o data_shogi

# Train -- same command, just change --game
python -m nnue-train \
  --game minishogi \
  --data "data_shogi/train_*.bin" \
  --features halfkp \
  --accum-size 128 \
  --epochs 100 \
  --output models/shogi_v1.pt \
  --export models/shogi_v1.bin
```

---

## 3. Stage 1: Data Generation

### 3.1 What Gets Recorded

Each self-play position produces a `DataRecord` containing:

| Field | Size | Description |
|-------|------|-------------|
| `board[2][H][W]` | 2xHxW bytes | Piece placement per player |
| `hand[2][K]` | 2xK bytes | Hand pieces (MiniShogi only) |
| `player` | 1 byte | Side to move (0 or 1) |
| `score` | 2 bytes (int16) | PVS search score from STM perspective |
| `result` | 1 byte | Game outcome from STM: +1 win, 0 draw, -1 loss |
| `ply` | 2 bytes | Ply count from game start |
| `best_move` | 2 bytes | Encoded as `from_sq * NUM_SQUARES + to_sq` |

The score and result fields are the two components of the training target.
They are combined at training time via WDL blending (lambda), not at
generation time. **Always record both.**

### 3.2 Search Depth: Depth 6 Is the Sweet Spot

On small boards, depth 6 is proportionally deep:

| Game | Avg game length | Depth 6 coverage | Equivalent on 8x8 |
|------|----------------|-------------------|--------------------|
| MiniChess (6x5) | ~50 plies | 12.0% | ~depth 9-10 |
| MiniShogi (5x5) | ~60 plies | 10.0% | ~depth 8-9 |

The lower branching factor (~15-20 vs. ~35 for standard chess) means
alpha-beta explores the tree more thoroughly at the same nominal depth.
**Use depth 6 for cost-effective generation; go to depth 8 for
high-quality refinement data.**

### 3.3 Random Move Injection (Epsilon)

Random move injection prevents the self-play echo chamber, where the engine
plays the same openings and generates data clustered in a tiny region of the
position space.

**Current implementation:** Uniform epsilon-greedy at every ply.

```cpp
bool jitter = (rng_float() < cfg.epsilon);  // default epsilon = 0.15
```

**Recommended improvement:** Ply-dependent epsilon that concentrates
randomness in the opening and fades to zero by the endgame:

| Phase | Ply range (5x5) | Suggested epsilon |
|-------|------------------|-------------------|
| Opening | 0-8 | 0.25-0.30 |
| Middlegame | 8-20 | 0.10-0.15 |
| Endgame | 20+ | 0.00-0.05 |

**Training impact of random move injection:**

- **Too much randomness (epsilon > 0.20 uniform):** Creates unrealistic
  positions. The network spends capacity learning to evaluate positions that
  never occur in real play. Loss converges but playing strength is poor.
- **Too little randomness (epsilon < 0.05):** Dataset lacks diversity. The
  network overfits to the engine's opening repertoire. Validation loss
  plateaus early. Training hyperparameters cannot compensate for missing
  position coverage.
- **Ply-dependent epsilon:** Best of both worlds. High opening diversity for
  broad coverage, clean endgame play for high-quality game results. The WDL
  signal (game outcome) is less noisy because random blunders in the endgame
  are avoided.

### 3.4 Position Filtering

Not all positions from self-play are equally useful. The datagen should
ideally filter:

```
Position generated
  |
  +-- Side to move in check? --> DISCARD
  |
  +-- Best move is a capture? --> DISCARD ("smart FEN skipping")
  |
  +-- |eval| > 2500? --> DISCARD (and adjudicate game as won)
  |
  +-- ply < write_minply? --> DISCARD
  |
  +-- Random move was played this ply? --> DISCARD position (but keep score)
  |
  +-- KEEP
```

**Training impact:** Unfiltered data includes tactical positions where the
evaluation depends entirely on reading ahead. NNUE cannot learn these from
the board alone; training on them adds noise to the loss without improving
strength. Filtering these out lets the network focus on quiet positional
patterns, which is NNUE's strength.

**Current status:** Our datagen does not yet filter checks or captures.
This is a high-priority improvement (see Section 9).

### 3.5 Score Type Matters: Search Score vs. Static Eval

The score recorded for each position **must** be the search score (the
result returned by PVS at the specified depth), not the raw static eval.

| Score type | What the network learns | Training quality |
|-----------|------------------------|-----------------|
| Static eval | To copy the existing eval function | Circular; no improvement possible |
| Search score (depth D) | To approximate depth-D search in one forward pass | The network compresses search knowledge into pattern recognition |

This distinction is the fundamental mechanism by which NNUE training
improves playing strength: the search score at depth D is strictly more
informed than the static eval, so the network learns to predict something
better than it could compute directly. See Section 8 for the bug we
discovered where datagen was recording static eval instead.

### 3.6 How Much Data

| Network arch | Params (est.) | Minimum | Recommended | Our target |
|-------------|--------------|---------|-------------|------------|
| PS, 128 accum | ~100K | 1M | 5-10M | 5M |
| HalfKP, 128 accum | ~1.2M | 5M | 10-50M | 20M |
| HalfKP, 256 accum | ~5M | 20M | 50-100M | 50M |

**Rule of thumb:** At least 10 positions per parameter; 50-100 per
parameter for a well-trained network.

**Generation cost for MiniChess:** At depth 6, ~30 usable positions per
game, ~0.5-2 seconds per game on a modern CPU. Generating 20M positions
requires ~670K games, feasible in under an hour with 64 parallel workers.

### 3.7 Data Diversity Checklist

Track these metrics across your dataset to catch distribution problems:

- [ ] Score distribution: roughly symmetric, not a spike at 0
- [ ] Material count distribution: covers various piece combinations
- [ ] Game length distribution: not dominated by very short or very long games
- [ ] Unique positions ratio: > 95%
- [ ] Result balance: roughly equal white wins, draws, black wins

---

## 4. Stage 2: Training

### 4.1 Architecture Summary

```
HalfKP Features (sparse, ~9000 inputs for 6x5)
  -> EmbeddingBag (feature_size, accum_size=128)  [most parameters live here]
  -> + bias
  -> SCReLU (clamp(x,0,1)^2)
  -> [STM accumulator, NSTM accumulator]  (concatenate: 2 x accum_size)
  -> Linear(256, 32) -> SCReLU
  -> Linear(32, 32) -> SCReLU
  -> Linear(32, 1)  (scalar eval output)
```

The `EmbeddingBag` with `mode="sum"` is equivalent to a `Linear` layer but
takes sparse index arrays instead of dense float vectors. For HalfKP with
~20 active features out of ~9000, this is ~450x less compute than dense
multiplication.

### 4.2 Loss Function

```python
SCORE_SCALE = 400.0

pred_sig  = sigmoid(predicted / SCORE_SCALE)
score_sig = sigmoid(score / SCORE_SCALE)
wdl       = (result + 1.0) / 2.0              # -1->0, 0->0.5, 1->1

target    = (1 - wdl_weight) * score_sig + wdl_weight * wdl
loss      = mean((pred_sig - target) ** 2)
```

**Why sigmoid space?** Large evaluations (+1500 vs. +2000) are compressed
together (both are "winning"), while small differences near 0 are expanded.
This focuses network capacity on balanced positions where accuracy matters
most for playing strength.

**SCORE_SCALE (400):** Controls the sigmoid steepness. Must match the scale
of your engine's evaluations. If the engine uses centipawns where pawn=100,
a pawn should map to approximately `sigmoid(100/400) = 0.56`. If using a
different internal scale, adjust accordingly. **Wrong SCORE_SCALE is a
common cause of training failure** -- loss decreases but the exported
network plays terribly.

### 4.3 WDL Blending (wdl_weight / Lambda)

The `wdl_weight` parameter controls the balance between two training signals:

| wdl_weight | Signal mix | When to use |
|-----------|-----------|-------------|
| 0.0 | 100% search score | Score-only data; bootstrapping from handcrafted eval |
| 0.3-0.5 | Balanced | **Default: best for most training runs** |
| 0.7-1.0 | Mostly game result | When search scores are unreliable (shallow depth, noisy eval) |
| 1.0 | 100% game result | No score data; or intentionally training a pure WDL predictor |

**Interaction with data quality:**

- **High-quality search scores** (depth 6+, proper PVS, quiet positions):
  Use wdl_weight=0.3-0.5. The search score provides a low-variance signal
  that the game result refines.
- **Low-quality scores** (raw static eval, depth 1-2, noisy positions):
  Use wdl_weight=0.7-1.0. The game result provides a ground-truth anchor
  when scores are unreliable.
- **If datagen was recording raw eval instead of search scores** (see
  Section 8): wdl_weight should be increased toward 1.0, since the score
  signal is nearly worthless for learning beyond the current eval.

### 4.4 Optimizer and Learning Rate

| Parameter | Value | Notes |
|-----------|-------|-------|
| Optimizer | Adam | Robust default for NNUE |
| Base LR | 1e-3 | With batch size 8192 |
| Schedule | Cosine decay to 1% | Via AnySchedule |
| Warmup | 1000 steps (linear) | Prevents early instability |

**LR-batch size coupling:** If you double the batch size to 16384, consider
increasing LR to ~1.4e-3 (sqrt scaling) or 2e-3 (linear scaling). NNUE
training is moderately sensitive to this.

**For fine-tuning:** Use 0.5x the base LR (5e-4) and optionally extend the
cosine period.

### 4.5 EMA (Exponential Moving Average)

```python
theta_ema = 0.999 * theta_ema + 0.001 * theta_current
```

EMA maintains a smoothed copy of the model parameters. Benefits:

- **Smoother predictions:** Raw training weights oscillate; EMA averages
  out the noise.
- **Better generalization:** EMA acts as implicit regularization, similar
  to Stochastic Weight Averaging.
- **Noise resilience:** Training labels are inherently noisy (search scores
  vary with depth, game results are stochastic). EMA dampens the network's
  response to individual noisy samples.

**Critical rules:**
- Always validate with EMA weights (the trainer does this automatically).
- Always export EMA weights, never raw training weights.
- Save both raw and EMA weights in checkpoints for training resumption.

| Decay | Averaging window | Use case |
|-------|-----------------|----------|
| 0.99 | ~100 steps | Very short runs, fast adaptation |
| 0.999 | ~1000 steps | **Default: good balance** |
| 0.9999 | ~10000 steps | Very long runs (500K+ steps) |

### 4.6 Training Duration

| Dataset size | Steps/epoch (BS=8192) | Recommended epochs | Total steps |
|-------------|----------------------|-------------------|-------------|
| 2M positions | ~244 | 200-400 | 50K-100K |
| 10M positions | ~1220 | 50-100 | 60K-120K |
| 50M positions | ~6100 | 10-30 | 60K-180K |

**Step-based thinking is better than epoch-based.** Target 60K-200K total
steps regardless of dataset size. Use early stopping based on validation
loss: if val loss has not improved for 10K-20K steps, stop.

### 4.7 Batch Size

- **Default:** 8192 (fits easily on any GPU for our model size)
- **Range:** 4096-16384
- **On CPU:** Use 4096 and 0 workers for minimal overhead
- **On GPU:** Use 8192-16384 with 2-4 workers and pin_memory=True

### 4.8 Validation Strategy

- **Val split:** Fixed 100K positions (from `--val-size 100000`) rather
  than a percentage, so val set size does not change as you add more
  training data.
- **Val frequency:** Every 2000-5000 steps. More frequent early in
  training (when the model changes rapidly), less later.
- **Val metrics:** Loss (primary), winner accuracy on decisive games,
  MAE in centipawns. The trainer reports all three.

---

## 5. Stage 3: Export and Quantization

### 5.1 Export Flow

```
EMA weights (float32)
  |
  +---> models/nnue_v1.bin       (float32 binary, for C++ inference)
  |
  +---> models/nnue_v1_quant.bin (int16/int8 quantized, for SIMD inference)
```

The trainer's `train()` function handles this automatically after training
completes. Both files use the `MCNN` magic header with metadata (feature
size, accumulator size, layer sizes).

### 5.2 Quantization Scheme

| Layer | Weight type | Scale | Activation output |
|-------|------------|-------|-------------------|
| Feature Transformer | int16 | QA=255 | int16 accumulator |
| SCReLU (post-FT) | -- | -- | uint8 (0-127) |
| Dense L1, L2 | int8 | QB=64 | uint8 via SCReLU |
| Output | int8 weights | QAH_QB=8128 (bias) | int32 -> centipawns |

**Weight clipping during training:** Weights must stay within representable
ranges. For dense layers with QB=64, the range is [-2.0, +1.98]. The
export script reports clipped weight counts; if this number is high,
consider adding a weight clipping callback during training.

### 5.3 Verifying Quantization Quality

After export, compare float and quantized outputs on test positions. The
expected mean absolute error is 1-5 centipawns. If significantly larger,
check:

1. Weight clipping is active during training
2. Quantization constants match between Python export and C++ inference
3. The model is not relying on a few extreme-valued weights

---

## 6. Stage 4: Evaluation and Iteration

### 6.1 Strength Testing

The only metric that ultimately matters is playing strength. Validation loss
is a proxy; a lower loss generally correlates with stronger play, but not
always (especially across different data distributions).

**Method:** Run a tournament of the NNUE-powered engine against a baseline:
- Handcrafted eval (for first NNUE)
- Previous NNUE version (for iterations)
- Play at least 200 games for statistically meaningful results
- Use varied time controls or fixed-depth settings

### 6.2 The Iterative Refinement Loop

The Stockfish community established that iterative refinement is the primary
path to strong NNUE networks:

1. **V1:** Train on self-play data from handcrafted eval (depth 6)
2. **V2:** Generate new data using V1 NNUE for eval. Train on new data
   (or mix of old + new). Use reduced LR (5e-4).
3. **V3+:** Repeat. Each generation produces slightly different positions
   because the evaluation function has changed.

**Why this works:** Search at depth D with eval function E(n) produces
scores that are strictly better than E(n) alone. The network E(n+1)
learns to approximate those depth-D scores, effectively compressing search
knowledge into a single forward pass. E(n+1) then becomes a better eval
for the next round of search.

### 6.3 Curriculum: Shallow Then Deep

An effective data strategy is to train on a large volume of shallow-depth
data first, then fine-tune on a smaller volume of deep-depth data:

| Phase | Data | LR | Epochs |
|-------|------|----|--------|
| Base training | 20M pos at depth 4-6 | 1e-3 | 50-100 |
| Refinement | 5M pos at depth 8+ | 5e-4 | 20-50 |

For 5x5 boards where depth 6 is already proportionally deep, a mix of
depth 4 (70%) and depth 8 (30%) within the same dataset is a simpler
alternative.

---

## 7. Cross-Cutting Interactions: Data Quality Meets Training

This section explains how datagen choices directly affect training outcomes.
Getting these interactions right is more important than tuning any single
hyperparameter.

### 7.1 Random Move Injection vs. Loss Convergence

| Epsilon | Data diversity | Loss behavior | Playing strength |
|---------|---------------|---------------|-----------------|
| 0.00 | Very low (echo chamber) | Loss drops fast, then plateaus early | Weak in unfamiliar positions |
| 0.05 | Low | Smooth convergence, moderate floor | Decent but narrow |
| 0.10 | Good | Slightly slower convergence, lower floor | **Best balance** |
| 0.20+ | High | Slower convergence, higher noise | Good breadth but positions are unrealistic |

**Why:** Higher epsilon creates more diverse but noisier training data. The
optimizer needs more steps to extract signal from noise, but the final model
generalizes better because it has seen more of the position space. Too much
noise (epsilon > 0.20 uniform) wastes network capacity on unrealistic
positions.

**Ply-dependent epsilon resolves this tension:** High randomness in openings
generates diverse starting points without polluting the game result signal
(which depends on late-game play quality).

### 7.2 Score Type vs. Loss Function

| Score source | Loss function choice | wdl_weight | Expected outcome |
|-------------|---------------------|-----------|-----------------|
| Search score (depth 6+) | Sigmoid MSE | 0.3-0.5 | **Standard: best results** |
| Raw static eval | Sigmoid MSE | 0.8-1.0 | Weak; must lean heavily on game results |
| Search score (depth 1-2) | Sigmoid MSE | 0.5-0.7 | Shallow scores are noisy; rely more on results |
| No score (result only) | Sigmoid MSE | 1.0 | Works but needs more data for convergence |

The loss function assumes the score represents a "teacher" signal that is
better than the current model. If the score is just the raw eval (the same
function the model is trying to replace), the learning signal is circular
and no improvement is possible from the score component.

### 7.3 Position Filtering vs. Training Stability

| Filtering level | Loss noise | Convergence speed | Final strength |
|----------------|-----------|-------------------|---------------|
| None | High | Slow, unstable | Weak |
| Basic (skip checks) | Moderate | Moderate | Good |
| Smart FEN skipping | Low | Fast, smooth | **Best** |
| Aggressive (strict qsearch match) | Very low | Fastest | Slightly better, but fewer positions |

Unfiltered data includes positions where the "correct" eval depends on
reading tactical sequences the NNUE cannot perform. Training on these creates
opposing gradient signals: the network is pulled toward a score it cannot
predict from the board position alone. This manifests as training loss noise
and slower convergence.

### 7.4 Data Volume vs. Training Hyperparameters

| Data volume | Model risk | Recommended adjustments |
|------------|-----------|------------------------|
| < 1M positions | Severe overfitting | Reduce accum to 64; increase wdl_weight; short training (20K steps); heavy EMA (0.9999) |
| 1M-10M | Moderate overfitting | Default config works; monitor val loss carefully |
| 10M-50M | Balanced | Can increase model capacity (accum=256); longer training |
| 50M+ | Underfitting possible | Increase accum; reduce wdl_weight toward 0.3; add a training epoch |

**More data is almost always better than more hyperparameter tuning.** If
val loss is not improving, generate more data before adjusting the learning
rate.

### 7.5 SCORE_SCALE Must Match Datagen

The `SCORE_SCALE` constant in the loss function must match the scale of the
engine evaluations in the training data. This project uses centipawns where
pawn = 100, and `SCORE_SCALE = 400`.

Verification: A position with a one-pawn advantage (score = 100 cp) should
map to approximately `sigmoid(100/400) = sigmoid(0.25) = 0.562`, meaning
the side with the extra pawn is expected to score 56.2%. This is a
reasonable calibration.

If the engine's internal scale changes (e.g., switching to a pawn = 200
scale), the `SCORE_SCALE` must be updated to `800` to maintain the same
sigmoid mapping.

---

## 8. The Raw Eval Bug: Lessons and Downstream Impact

### 8.1 What Happened

**Commit:** `f662186` ("fix: datagen records search score instead of raw eval")

The datagen was calling `PVS::search()` for move selection but then
recording `evaluate()` (the raw static eval output) as the position's
training score. The depth-6 search score -- the entire point of running a
search during datagen -- was discarded.

```
Before (bug):
  search_score = PVS::search(game, depth, ctx).score  // used only for move selection
  rec.score = evaluate(game)                           // raw eval recorded as label

After (fix):
  search_score = PVS::search(game, depth, ctx).score
  rec.score = -search_score                            // search score recorded (negated for STM)
```

### 8.2 Why This Matters

The entire NNUE training mechanism depends on the training target being
**better** than the current eval:

```
  Static eval (current model) < Search score (depth D with current model)
```

When the training target IS the static eval, the network learns to copy
itself. There is no information gain. The only useful signal comes from the
game result component (WDL), which is high-variance and requires much more
data to converge.

### 8.3 Downstream Impact

| Pipeline stage | Impact of the bug |
|---------------|------------------|
| **Loss function** | The score component of the loss was circular. Only the WDL component (wdl_weight fraction) provided useful signal. Effective training was at `wdl_weight=1.0` regardless of the configured value. |
| **Convergence speed** | Much slower. The network needed to extract all learning from game outcomes alone, which are noisy and high-variance. |
| **Network quality** | Severely limited. The network could not surpass the handcrafted eval because it was trained to copy it. |
| **SCORE_SCALE calibration** | Accidentally irrelevant. Since the score was just the raw eval, the sigmoid mapping compressed the same function the model was already computing. |
| **Iterative refinement** | Broken. Regenerating data with a new NNUE would record the new NNUE's static eval, creating a perfect circular loop with zero learning signal. |

### 8.4 Mitigation for Existing Data

If you have data generated before the fix:

1. **Discard and regenerate.** This is the cleanest approach. The positions
   and game results in old data are still valid, but the scores are not
   useful as training targets.

2. **Train with wdl_weight=1.0.** If regeneration is too expensive, you
   can still extract value from the game results by setting wdl_weight=1.0
   (ignore scores entirely). This requires more data for convergence but
   avoids the circular score signal.

3. **Re-score existing positions.** Extract positions from old data files,
   re-evaluate them at depth 6+ with the engine, and write new data files.
   This preserves position diversity while fixing the scores.

### 8.5 Lessons

1. **Verify your data pipeline end-to-end.** Print a few records and
   manually check that scores match what a depth-6 search would produce,
   not what `evaluate()` returns.
2. **The score source is the single most important datagen decision.** More
   important than depth, epsilon, or filtering. A perfect pipeline with
   wrong scores produces a network that cannot improve.
3. **EMA and WDL blending partially masked the bug.** EMA smoothing made
   training look stable, and the WDL component provided enough signal for
   the network to learn basic patterns. The bug was subtle because the
   network did learn -- just much less than it should have.

---

## 9. Recommended Configuration Reference

### 9.1 MiniChess (6x5) -- Full Configuration

#### Datagen

| Parameter | Value | Flag | Rationale |
|-----------|-------|------|-----------|
| Games | 500K-2M | `-n` | 15M-60M positions |
| Depth | 6 | `-d` | Equivalent to depth 9-10 on 8x8 |
| Epsilon | 0.10 | `-e` | Reduced from 0.15; ply-dependent preferred |
| Workers | 16-64 | `-w` (gen_data.sh) | Saturate available cores |
| Seed | Per-worker | `-s` | Automatic in gen_data.sh |
| NNUE model | Optional | `-m` | Use for V2+ data generation |

#### Training

| Parameter | Value | Flag | Notes |
|-----------|-------|------|-------|
| Features | halfkp | `--features` | Sparse EmbeddingBag; king-relative |
| Accumulator | 128 | `--accum-size` | 128x2 -> 32 -> 32 -> 1 |
| Batch size | 8192 | `--batch-size` | |
| Learning rate | 1e-3 | `--lr` | Adam |
| WDL weight | 0.5 | `--wdl-weight` | Equal blend score + result |
| EMA decay | 0.999 | `--ema-decay` | ~1000 step averaging |
| Warmup | 1000 steps | `--warmup-steps` | Linear ramp |
| Epochs | 50-100 | `--epochs` | Or until val loss plateau |
| Val size | 100K | `--val-size` | Fixed, not percentage |
| Val interval | 2000 steps | `--val-every-n-steps` | |
| Workers | 2-4 | `--num-workers` | DataLoader |
| Loss function | Sigmoid MSE | (hardcoded) | SCORE_SCALE=400 |
| Loss exponent | 2.0 | (hardcoded) | Start here; try 2.6 later |

#### Export

| Output | Path | Format |
|--------|------|--------|
| PyTorch model | `models/nnue_v1.pt` | EMA weights, state_dict |
| Float binary | `models/nnue_v1.bin` | MCNN header + float32 |
| Quantized binary | `models/nnue_v1_quant.bin` | MCNN header + int16/int8 |

### 9.2 MiniShogi (5x5) -- Differences from MiniChess

| Parameter | MiniChess | MiniShogi | Why different |
|-----------|-----------|-----------|--------------|
| Piece types | 6 | 11 (base + promoted) | Promoted pieces in shogi |
| Hand types | 0 | 5 | Captured pieces go to hand |
| HalfKP size | ~7500 | ~12500 + hand features | Larger due to more piece types |
| Depth | 6 | 6 | Drops increase branching; may need depth 4 for cost |
| Epsilon | 0.10 | 0.10 | |
| Data needed | 10-50M | 20-100M | More piece types = more features to learn |
| Filtering | No drops as captures | Drops are legal, not captures | Do NOT filter drop moves |

### 9.3 Priority Improvements (Roadmap)

In order of expected impact:

1. **Ply-dependent epsilon** -- Concentrate randomness in opening, zero in
   endgame. Improves both data diversity and game result quality.
2. **Position filtering** -- Skip positions where STM is in check or best
   move is a capture. Reduces training noise significantly.
3. **Opening book from perft** -- Enumerate all positions at depth 3-4,
   filter by eval balance, use as starting positions. Guarantees diversity
   without nonsensical positions.
4. **Eval-limit adjudication** -- When |eval| > 2500 for 3 consecutive
   moves, adjudicate as won. Saves compute on decided games.
5. **Multi-depth mixing** -- Generate 70% at depth 4 (cheap, broad) and
   30% at depth 8 (expensive, precise).
6. **Softmax multi-PV move selection** -- Replace uniform random with
   score-weighted move selection for more realistic jitter.
7. **Weight clipping callback** -- Clamp weights after each optimizer step
   to stay within quantization bounds.

---

## 10. Troubleshooting

### Training loss decreases but the network plays poorly

**Most likely cause:** SCORE_SCALE mismatch. Check that `SCORE_SCALE=400`
matches your engine's centipawn scale. A pawn should map to ~0.56 win
probability.

**Second most likely:** Data generated with raw eval instead of search
scores (the Section 8 bug). Verify by comparing a few recorded scores
against what `./build/minichess-selfplay` reports for the same positions.

### Loss is very noisy / slow to converge

**Causes (in order of likelihood):**
1. Unfiltered data (positions in check, captures). Add smart FEN skipping.
2. Too-high uniform epsilon (> 0.15). Switch to ply-dependent.
3. Too-shallow search depth (< 4). Increase depth.
4. Too-high learning rate. Try 5e-4.

### Validation loss plateaus early

**Causes:**
1. Insufficient data diversity. Generate more games with different seeds
   and/or higher opening randomization.
2. Dataset too small for model capacity. Either generate more data or
   reduce accum_size.
3. Learning rate too low. Try increasing to 2e-3 (with batch size 8192).

### Network plays well as one color but poorly as the other

**Cause:** Perspective flip bug. Verify that white features and black
features are computed identically (with appropriate mirroring) in both the
Python training code and C++ inference code. For MiniChess, black's board
is vertically flipped; for MiniShogi, 180-degree rotation is used.

### Good float performance but poor after quantization

**Causes:**
1. No weight clipping during training. Weights exceed int8/int16 range.
2. Quantization constants mismatch between `export.py` (QA=255, QB=64) and
   C++ `compute_quant.hpp`.
3. Check the export log: if "clipped" count is high, add weight clipping.

### NaN or inf loss

**Fixes:**
1. Reduce learning rate by 10x.
2. Add gradient clipping: `clip_grad_norm_(model.parameters(), 1.0)`.
3. Increase warmup steps to 2000.
4. Filter out positions with |score| > 10000 (mate scores stored as large
   values).

---

## References

- Stockfish nnue-pytorch: https://github.com/official-stockfish/nnue-pytorch
- Stockfish NNUE docs: https://official-stockfish.github.io/docs/nnue-pytorch-wiki/docs/nnue.html
- Study of the Proper NNUE Dataset (arXiv:2412.17948)
- Fairy-Stockfish variant-nnue-pytorch: https://github.com/fairy-stockfish/variant-nnue-pytorch
- Fairy-Stockfish bookgen: https://github.com/fairy-stockfish/bookgen
- SCReLU research: https://cosmo.tardis.ac/files/2024-06-25-nnue-research-01.html
- EMA in deep learning (arXiv:2411.18704)
- Best practices for NNUE training data (TalkChess): https://talkchess.com/viewtopic.php?t=83944
