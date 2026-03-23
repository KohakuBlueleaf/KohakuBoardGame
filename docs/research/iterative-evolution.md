# Iterative NNUE Self-Improvement: From Seed Network to Strong Play

A comprehensive guide to evolving NNUE evaluation networks through iterative
training, covering theory, practical recipes, and lessons from Stockfish's
multi-year journey.

---

## Table of Contents

1. [The NNUE Training Loop](#1-the-nnue-training-loop)
2. [Knowledge Distillation Theory](#2-knowledge-distillation-theory)
3. [When to Regenerate Data vs. Reuse Old Data](#3-when-to-regenerate-data-vs-reuse-old-data)
4. [Data Mixing Strategies](#4-data-mixing-strategies)
5. [Learning Rate Scheduling Across Iterations](#5-learning-rate-scheduling-across-iterations)
6. [How Stockfish Evolved from v1 to Current](#6-how-stockfish-evolved-from-v1-to-current)
7. [The Role of External Data](#7-the-role-of-external-data)
8. [Plateau Detection](#8-plateau-detection)
9. [Architecture Changes Between Iterations](#9-architecture-changes-between-iterations)
10. [The "Noisy Student" Approach](#10-the-noisy-student-approach)
11. [Practical Recipe for a Small Project](#11-practical-recipe-for-a-small-project)

---

## 1. The NNUE Training Loop

The core idea behind iterative NNUE improvement is a feedback loop where each
generation of network produces higher-quality training data for the next.

### The Basic Cycle

```
Handcrafted Eval (v0)
    |
    v
Generate self-play data using v0
    |
    v
Train NNUE v1 on that data (knowledge distillation from v0)
    |
    v
Generate self-play data using v1   <---+
    |                                    |
    v                                    |
Train NNUE v2 on new + old data         |
    |                                    |
    v                                    |
Generate self-play data using v2 -------+
    |
    ...continues...
```

### How Each Stage Works

**Stage 0 -- Seed data from handcrafted eval:**
The engine plays millions of self-play games using its handcrafted evaluation.
Each position is recorded alongside its evaluation score (from search at a
moderate depth, typically depth 7-9) and the game outcome (win/draw/loss).
These (position, score, outcome) triples form the initial training dataset.

**Stage 1 -- Train NNUE v1:**
A neural network is trained to predict the handcrafted engine's evaluations.
The loss function blends two targets controlled by a `lambda` parameter:
- `lambda = 1.0`: Train purely on the search score (eval distillation)
- `lambda = 0.0`: Train purely on game outcome (result prediction)
- Typical values: `lambda = 0.75` to `1.0` for early iterations

This is knowledge distillation: the network learns to replicate the
handcrafted eval's judgments, but in a form that generalizes differently.

**Stage 2+ -- Regenerate and retrain:**
The engine now uses NNUE v1 for evaluation. New self-play games produce data
that reflects the NNUE's own understanding, not the handcrafted eval. Training
NNUE v2 on this data reinforces the network's strengths while the search
component (alpha-beta with the NNUE eval) corrects for weaknesses the network
had -- the search sees deeper than the eval alone.

### Why This Loop Improves Strength

The key insight is that **search acts as a policy improvement operator**. Even
if the eval function has blind spots, the tree search compensates for many of
them. When the search at depth D finds a line that refutes the eval's naive
assessment, that corrected score becomes training data for the next generation.
The new network internalizes corrections that previously required search
depth to discover, freeing the search to find even deeper insights.

This is analogous to AlphaZero's loop, but with alpha-beta search instead of
MCTS: the search provides "better-than-eval" position assessments, and the
network learns to approximate those assessments cheaply.

### Example: Seer's Retrograde Learning

The Seer chess engine demonstrates a pure self-play loop starting from
minimal knowledge:

1. **Bootstrap**: Train initial network solely from 6-man Syzygy endgame
   tablebase WDL values.
2. **Retrograde propagation**: Use search to back up endgame knowledge from
   N-piece positions to (N+1)-piece positions, iteratively reaching full
   32-piece positions.
3. **Self-play iteration**: Generate new data using the current network,
   retrain, repeat. Each iteration added roughly 50-100 Elo.
4. **Training target**: A mixture of self-play game result (WDL) and search
   score, which "yielded far superior results" to either alone.

---

## 2. Knowledge Distillation Theory

### Classical Distillation

In standard knowledge distillation, a "teacher" model's outputs train a
"student" model. The student learns from the teacher's soft probability
distribution over outputs, which contains richer information than hard labels
alone. This "dark knowledge" encodes the teacher's uncertainty and similarity
judgments between classes.

### Can the Student Surpass the Teacher?

**In pure distillation: generally no.** If a student of identical capacity is
trained only to mimic the teacher, it approaches but rarely exceeds the
teacher's accuracy. The student's ceiling is bounded by the quality of the
teacher's predictions.

**In chess NNUE training: yes, and here is why.** The training data is not the
raw eval output -- it is the eval output *after search*. Alpha-beta search at
depth D effectively creates a "virtual teacher" that is stronger than the
static eval alone. The network learns to predict depth-D search results using
only the position, compressing search knowledge into a single forward pass.

### Born-Again Networks

Research on "Born-Again Networks" (Furlanello et al., 2018) showed that
training a student of identical architecture on a teacher's outputs can
paradoxically surpass the teacher. Key findings:

- On CIFAR-10, a DenseNet teacher at 3.81% error produced a student at 3.50%
- The improvement comes from the "dark knowledge" gradient, which differs
  from ground-truth gradients and provides a form of implicit regularization
- Multiple generations show diminishing but real gains: each generation k
  learns from generation k-1
- An ensemble of all generations ("BANE" -- Born-Again Network Ensemble)
  performs better still

### Application to NNUE

In the NNUE context, each generation benefits from three mechanisms:

1. **Search amplification**: Search at depth D with eval_v(k) produces
   targets that are effectively "eval_v(k) at depth D", which is stronger
   than eval_v(k) alone.
2. **Dark knowledge**: The network learns inter-position relationships from
   the teacher's continuous-valued scores, not just binary win/loss.
3. **Regularization through retraining**: Starting fresh (or with learning
   rate resets) forces the network to find new, potentially better optima.

### The Lambda Blending Trick

The `lambda` parameter blends two supervision signals:

```
loss = lambda * MSE(predicted, search_score)
     + (1 - lambda) * MSE(predicted, game_outcome)
```

- **Search score** (lambda toward 1.0): High-quality positional signal, but
  can encode search artifacts and horizon effects.
- **Game outcome** (lambda toward 0.0): Ground truth about who won, but
  very noisy for individual positions (a winning position can occur in a
  lost game due to later blunders).
- **Blending**: Using `lambda = 0.75`-`1.0` gives the best of both worlds.
  Stockfish's SFNNv5 training linearly reduced lambda from 1.0 to 0.75
  across 800 epochs.

---

## 3. When to Regenerate Data vs. Reuse Old Data

### Regenerate When:

| Signal | Why |
|--------|-----|
| Network has improved significantly (50+ Elo) | Old data reflects the old eval's biases; the new eval sees positions differently |
| Architecture has changed | New architectures may need different position distributions |
| Old data trained on handcrafted eval, new data should use NNUE | NNUE-generated scores are more "learnable" by a subsequent NNUE |
| You are at a plateau | Fresh data from a stronger eval breaks out of local optima |
| You changed search parameters | Different search depths/nodes produce different position distributions |

### Reuse Old Data When:

| Signal | Why |
|--------|-----|
| Old data came from a stronger source (e.g., Lc0) | Higher-quality data does not expire |
| You are mixing data quality tiers | Old low-depth data provides breadth; new high-depth data provides accuracy |
| Network capacity has increased | Bigger networks benefit from more total positions, even if some are stale |
| Data generation is expensive | For small projects, regenerating millions of games is time-consuming |

### Practical Heuristic

**Regenerate your self-play data every 2-3 significant training iterations**,
or whenever your network has gained more than ~50 Elo from the version that
generated the current data. Keep old data around for mixing (see next section).

### Data Volume Guidelines

| Network size | Minimum positions | Recommended positions |
|-------------|-------------------|----------------------|
| 16 hidden neurons | 10M | 50M |
| 128 hidden neurons | 50M | 200M |
| 256x2-32-32 | 150M+ | 500M-1B |
| Stockfish-scale | 1B+ | Multiple billions |

Larger networks require much larger quantities of training data to saturate.
Start small and increase the hidden layer size as you gather more training data.

---

## 4. Data Mixing Strategies

### The Stockfish Approach: Tiered Data Quality

Stockfish's strongest networks use a two-stage training approach with data
from multiple quality tiers:

**Tier 1 -- Stockfish self-play (low-medium quality):**
- Generated with Stockfish at depth 9 or 5000 nodes
- Provides broad position coverage
- Good for initial training from scratch
- Example: `data_d9_2021_09_02.binpack`

**Tier 2 -- Lc0-derived data (high quality):**
- Converted from Leela Chess Zero training data (T60, T70 series)
- More "positional" evaluations with fewer tactical artifacts
- Best used to *retrain* a network already trained on Tier 1 data
- Example: `T60T70wIsRightFarseer.binpack`

**Critical finding**: Training from scratch on high-quality data alone
produces *worse* networks than the two-stage approach. The hypothesis is
that lower-quality data provides necessary position diversity and coverage
that the higher-quality but narrower data lacks.

### Dataset Ordering Matters

The order of training datasets significantly affects results:

```
Recommended sequence:
1. Train on broad, lower-quality self-play data (Tier 1)
2. Fine-tune on narrow, higher-quality data (Tier 2)

NOT recommended:
- Training only on high-quality data from scratch
- Random interleaving without curriculum structure
```

This follows a curriculum learning pattern: learn general patterns first,
then refine with expert-quality data.

### Mixing Old and New Data

When regenerating data, do not discard old data entirely. Effective mixing
strategies include:

**Proportional mixing**: Combine 70% new data with 30% old data.
Prevents catastrophic forgetting of positions the old network handled well.

**Quality-weighted mixing**: Weight samples by the quality of the engine
that generated them. Data from your best network gets higher weight.

**Diversity mixing**: Combine data from different opening sets:
- Standard openings
- Unbalanced openings (UHO -- Unbalanced Human Openings)
- Fischer Random / Chess960 positions
- Endgame-heavy positions

### Position Filtering

Not all positions are equally valuable for training. Filter out:

- Positions in check (tactically volatile)
- Positions where static eval and quiescence search eval differ by more than
  ~60 centipawns (captures available that distort static assessment)
- Positions where static eval and deeper search differ by more than ~70
  centipawns (strong tactical motifs that the network should not try to
  evaluate statically)

The Stockfish trainer calls this "smart FEN skipping" -- excluding captures
and positions in check from training improves network quality.

### Ideal Dataset Balance

Research suggests good NNUE training data should have:
- 50% positions with positive evaluations, 50% negative (relative to side to move)
- At least 50% of positions with evaluations between -100 and +100 centipawns
- At least 40% materially imbalanced positions (evals outside the +/-100 range)

---

## 5. Learning Rate Scheduling Across Iterations

### Within a Single Training Run

**Epoch count**: Stockfish NNUE networks typically require ~400 epochs to
mature, though networks become competitive after ~100 epochs. Beyond 400
epochs, improvement becomes marginal.

**Batch size**: 16384 is the standard for Stockfish NNUE training.

**Learning rate schedule**: The most effective approach for NNUE training
uses a step-decay or cosine-annealing schedule:

```
Epochs   1-100:  LR = 1e-3   (exploration phase)
Epochs 100-250:  LR = 5e-4   (refinement phase)
Epochs 250-400:  LR = 2.5e-4 (fine-tuning phase)
```

### Across Iterations (v1 -> v2 -> v3)

Different learning rate strategies apply depending on whether you are
training from scratch or fine-tuning:

**Iteration 1 (from scratch on handcrafted eval data):**
- Higher initial LR: `1e-3`
- Full 400 epochs
- The network is learning everything from zero; needs aggressive exploration

**Iteration 2 (retraining on NNUE v1 data):**
- Two options:
  - **Resume from v1 weights** with reduced LR: `5e-4` to `2.5e-4`
  - **Train from scratch** with standard LR: `1e-3`
- Resume approach is faster but risks getting stuck in local optima
- Scratch approach is slower but may find better global optima

**Iteration 3+ (fine-tuning on high-quality data):**
- Lower LR: `2.5e-4` to `1e-4`
- Fewer epochs: 100-200
- The network is already good; large learning rates would destroy
  previously learned knowledge

### The Lambda Schedule

Stockfish's SFNNv5 training introduced a lambda schedule across epochs:
- Start at `lambda = 1.0` (train purely on eval scores)
- Linearly decay to `lambda = 0.75` by epoch 800
- This gradually introduces game-outcome signal as the network matures

### Practical Recommendations

| Iteration | From Scratch? | LR Start | LR End | Epochs | Lambda |
|-----------|---------------|----------|--------|--------|--------|
| v1 | Yes | 1e-3 | 1e-4 | 400 | 1.0 |
| v2 | Resume from v1 | 5e-4 | 1e-4 | 200-400 | 1.0 -> 0.75 |
| v3 | Resume from v2 | 2.5e-4 | 5e-5 | 100-200 | 0.75 |
| v3-ft | Resume from v3 | 1e-4 | 1e-5 | 50-100 | 0.6 |

---

## 6. How Stockfish Evolved from v1 to Current

### Timeline of Key Milestones

**2018 -- Invention:**
Yu Nasu invents NNUE for the Shogi engine YaneuraOu. The architecture exploits
sparse, incrementally updatable inputs for fast neural network inference
compatible with alpha-beta search.

**Early 2020 -- Chess Adaptation:**
Hisayori Noda ("Nodchip") ports NNUE to Stockfish 10. Initial architecture:
`HalfKP -> 256x2 -> 32 -> 32 -> 1`. The network is trained on evaluations
from classical Stockfish, achieving an immediate ~80 Elo improvement.

**August 6, 2020 -- Official Merge:**
NNUE evaluation merged into the official Stockfish repository. The gain is
measured at 80-100 Elo -- a massive leap for a field where 5-10 Elo gains
are typical per patch.

**September 2, 2020 -- Stockfish 12:**
First official release with NNUE. Wins 10x more game pairs than it loses
against Stockfish 11. A hybrid mode uses NNUE only for balanced positions,
gaining 20 extra Elo.

**Late 2020 -- PyTorch Trainer:**
Gary Linscott implements the nnue-pytorch trainer, enabling GPU-accelerated
training and opening the door to rapid iteration.

**February 2021 -- Lc0 Collaboration:**
Billions of positions from Leela Chess Zero training data become available
for Stockfish NNUE training, dramatically improving network quality.

**2021 -- Stockfish 14 (HalfKAv2):**
Architecture shifts from HalfKP to HalfKAv2, reducing input redundancy.
Tomasz Sobczyk introduces the binpack storage format for compact training
data and the factorized feature training approach.

**February 2022 -- SFNNv4:**
Introduces pairwise elementwise multiplication of 1024x2 activated neurons,
a non-linearity that provides benefits similar to sigmoid activation but
faster to compute.

**May 2022 -- SFNNv5:**
Adds Squared ClippedReLU (SqrClippedReLU) after the first hidden layer,
doubling the effective feature dimensions. Lambda scheduling (1.0 -> 0.75)
introduced during training.

**2022-2023 -- SFNNv6 through SFNNv9 (Scaling Up L1):**
Progressive increases in the first hidden layer size:
- SFNNv6: L1 = 1536
- SFNNv7: L1 = 2048
- SFNNv8: L1 = 2560
- SFNNv9: L1 = 3072

**July 2023 -- Stockfish 16:**
The classical handcrafted evaluation is completely removed. Stockfish is now
100% NNUE. All training data for default nets comes from Lc0-derived sources.

**November 2025 -- SFNNv10 (Threat Inputs):**
Introduces "Full Threat Input" features: Piece(Square)-Piece(Square) pairs
where the second piece's square lies in the attack set of the first piece.
This adds explicit attack relationship information to the network inputs.
Gains ~14 Elo on ARM platforms.

**February 2026 -- SFNNv11:**
Removes threat features of the form piece-to-king, saving 13MB of net space
with negligible strength loss.

**February 2026 -- SFNNv12, SFNNv13:**
SFNNv13 doubles the L2 layer from 16 to 32 neurons, taking advantage of the
smaller accumulator sizes made possible by threat inputs. The accumulator
shrank enough that the computational budget could be reallocated to deeper
layers.

**March 2026 -- Current Status:**
Stockfish rated ~3653 Elo (CCRL 40/15). Dominant in TCEC since Season 18.
The architecture has evolved from a simple 256x2->32->32->1 network to a
sophisticated system with threat inputs, multiple feature sets, and carefully
tuned layer sizes.

### Key Insight: Architecture and Data Co-Evolved

Stockfish's progress was not purely from better architectures or better
data -- it was from both evolving together. Each architecture change enabled
different data to become effective, and each data improvement motivated
architectural experiments. The iterative cycle of architecture change, data
regeneration, and training refinement drove cumulative gains of several
hundred Elo over five years.

---

## 7. The Role of External Data

### Lc0 Data for Stockfish NNUE

One of the most impactful developments in Stockfish NNUE history was
incorporating training data from Leela Chess Zero (Lc0). Starting in 2021,
Lc0 training data (T60 and T70 series) was converted to the Stockfish
binpack format and used for NNUE training.

**Why Lc0 data helps:**

1. **Different evaluation philosophy**: Lc0 learns from self-play
   reinforcement learning with MCTS, producing evaluations that emphasize
   long-term positional factors differently than Stockfish's classical eval.
2. **Higher quality evaluations**: Lc0's evaluations at the positions it
   generates tend to be more "positional" and less influenced by tactical
   search artifacts.
3. **Complementary coverage**: Lc0 explores different parts of the game tree
   than Stockfish, providing position diversity the self-play data lacks.

**How the data is used:**

The training follows a two-stage pipeline:
1. Train a base network on Stockfish-generated data (depth 9, 5000 nodes)
2. Retrain (fine-tune) that network on Lc0-derived data

**Critical finding**: Training from scratch on Lc0 data alone produces
weaker networks. The Stockfish self-play data provides necessary breadth
of position coverage, while the Lc0 data provides depth of evaluation
quality.

**Data conversion tools**: The `lc0-data-converter` and `lc0-to-nnue-data`
projects convert Lc0's training format into Stockfish's binpack format,
performing WDL rescoring and evaluation mapping in the process.

### Lessons for Small Projects

Even if you don't have access to Lc0-scale data, the principle applies:

- **Use any stronger evaluation source available** -- even a slow but
  accurate evaluator can generate high-quality training targets.
- **External data is a fine-tuning tool**, not a replacement for self-play
  data from your own engine.
- **Format conversion matters** -- ensure score scales and position
  representations match your engine's conventions.

---

## 8. Plateau Detection

### How to Know When Iteration Stops Helping

Detecting a plateau in NNUE iterative training requires monitoring multiple
signals, since training loss alone is not a reliable indicator of playing
strength.

### Primary Signals

**1. Tournament Elo measurement:**
The gold standard. After each training iteration, run a gauntlet of games
(e.g., 5000-10000 games at fast time control) between the new network and
the previous best. Use tools like `cutechess-cli`, `c-chess-cli`, or
`fastchess` with Elo estimation via `ordo` or `bayeselo`.

A plateau is signaled when:
- Elo gain drops below ~5 Elo for two consecutive iterations
- Confidence intervals of new vs old network overlap zero

**2. Validation loss stagnation:**
Track the validation set loss across training epochs and across iterations.

- Within a run: If validation loss stops decreasing for 50+ epochs, the
  current run has converged.
- Across iterations: If the best validation loss of iteration N is not
  meaningfully better than iteration N-1, the iterative loop may have
  plateaued.

**3. Score distribution analysis:**
Compare the distribution of evaluation scores between iterations. If the
new network produces nearly identical score distributions on a test set of
positions, it has stopped learning new patterns.

### Secondary Signals

**4. Position disagreement rate:**
Measure how often the new network's top move (by eval) differs from the
previous network's top move across a set of test positions. If the
disagreement rate drops below ~5%, the networks are converging.

**5. Search quality metrics:**
If the engine with the new network searches the same positions to the
same depth, compare:
- Nodes per second (efficiency)
- Agreement with the old network's PV at various depths
- Performance on test suites (e.g., WAC, STS, ECM)

### What to Do at a Plateau

When iterative improvement stalls, consider these interventions in order:

1. **Change the data source** -- Switch from self-play to external data,
   or vice versa. Different data can break the network out of local optima.
2. **Change the architecture** -- Increase network capacity (wider/deeper),
   add new feature types, or change activation functions. (See Section 9.)
3. **Change the search** -- Improvements to the search algorithm (better
   pruning, time management, etc.) create a different "virtual teacher"
   that produces different training data.
4. **Change the training target** -- Adjust lambda, switch from eval-based
   to WDL-based training, or try a different loss function.
5. **Accept the plateau** -- At some point, the architecture cannot
   represent a stronger eval. This is the signal to make a structural
   change, not to keep iterating with the same setup.

### Plateau vs. Overfitting

Be careful to distinguish between:
- **Plateau**: Training and validation loss both stagnate. The network has
  learned all it can from the current data/architecture combination.
- **Overfitting**: Training loss decreases but validation loss increases.
  The network is memorizing training positions. Solution: more data, more
  regularization, or smaller network.

---

## 9. Architecture Changes Between Iterations

### When to Change Architecture

Architecture changes are the most powerful lever for breaking through
plateaus, but they also carry the highest risk (you may lose progress).
Change architecture when:

- Iterative training has plateaued for 2-3 consecutive iterations
- You have evidence that the current architecture is capacity-limited
- A new architectural idea has been validated in another engine
- You can afford to regenerate data for the new architecture

### Stockfish's Architecture Evolution Patterns

Stockfish provides a roadmap for architecture evolution. Each change was
empirically validated through tens of thousands of test games on Fishtest:

**Phase 1 -- Feature set changes (high impact):**
HalfKP -> HalfKA -> HalfKAv2 -> HalfKAv2_hm + Threat Inputs

Changing what the network *sees* has the highest impact. Each feature
set change required retraining from scratch with regenerated data.

**Phase 2 -- Layer width scaling (medium impact):**
256 -> 512 -> 1024 -> 1536 -> 2048 -> 2560 -> 3072

Increasing the first layer (feature transformer) width is the safest
architectural change because:
- Most NNUE knowledge resides in the first layer
- Sparse input means the first layer can be enormous while remaining fast
- Only ~30 of 40K+ features are active per position

**Phase 3 -- Activation function changes (medium impact):**
ClippedReLU -> Squared ClippedReLU (SCReLU) -> Pairwise multiplication

These provide better gradient flow and expressiveness without changing
the overall structure.

**Phase 4 -- Deeper layer tuning (low-medium impact):**
After threat inputs reduced the accumulator size, Stockfish could
double the L2 layer from 16 to 32 neurons. Deeper layers are dense
(not sparse), so changes here have both accuracy and speed implications.

### Practical Architecture Progression for a Small Project

For a MiniChess-scale project, follow this progression:

```
Stage 1: (InputFeatures) -> 16x2 -> 1
         Simplest possible NNUE. Fast to train, needs ~10M positions.

Stage 2: (InputFeatures) -> 64x2 -> 1
         4x wider first layer. Needs ~50M positions.

Stage 3: (InputFeatures) -> 128x2 -> 16 -> 1
         Add a second hidden layer. Needs ~100M positions.

Stage 4: (InputFeatures) -> 256x2 -> 32 -> 32 -> 1
         Standard Stockfish-era architecture. Needs ~200M+ positions.

Stage 5: Add SCReLU, pairwise multiplication, or other activation
         improvements.
```

### Transfer Learning Across Architecture Changes

When changing architecture, you generally cannot reuse old weights directly.
Options:

- **Train from scratch**: Safest but slowest. Required for feature set changes.
- **Partial transfer**: If you only increased layer width, you can initialize
  the new wider layer by copying old weights and zero-initializing the new
  columns. Then train with a higher LR to adapt.
- **Distillation transfer**: Use the old architecture as a teacher --
  generate data with the old network, then train the new architecture on
  that data. This is effectively what the iterative loop does anyway.

---

## 10. The "Noisy Student" Approach

### Origin: Vision AI

The "Noisy Student" method (Xie et al., 2020) is a self-training approach
from computer vision that achieved state-of-the-art results on ImageNet:

**Algorithm:**
1. Train a teacher model on labeled data
2. Use the teacher to generate pseudo-labels for a large unlabeled dataset
3. Train a student model (equal or larger capacity) on labeled + pseudo-
   labeled data, **with noise injected during training**
4. Replace the teacher with the student; repeat from step 2

**Key innovation: noise during student training.** The student is trained
with dropout, stochastic depth, and data augmentation, forcing it to
generalize beyond the teacher's specific predictions. This is why the
student can surpass the teacher -- it is not simply memorizing the
teacher's outputs but learning robust patterns from noisy versions of them.

**Results:**
- 88.4% ImageNet top-1 accuracy (2.0% above prior state-of-the-art)
- Dramatic robustness improvements on corrupted/adversarial images
- Gains continued across multiple student-teacher iterations

### Application to NNUE Training

The Noisy Student concept maps naturally onto NNUE iterative training:

| Vision AI | NNUE Training |
|-----------|---------------|
| Teacher model | Current best NNUE network |
| Labeled data | Positions with search-derived evaluations |
| Unlabeled data | Random/sampled positions without evaluations |
| Pseudo-labels | Evaluations generated by search with current NNUE |
| Noise in student training | See below |
| Student model | Next-generation NNUE network |

### Sources of Noise in NNUE Training

In the NNUE context, noise comes from several sources, some intentional
and some inherent:

**Inherent noise (always present):**
- **Search depth variation**: Different positions are evaluated at different
  effective depths due to pruning, producing inconsistent "teacher" quality.
- **Game outcome noise**: The `lambda` blend introduces game results as a
  target. A single position's game outcome is extremely noisy -- a winning
  position might be in a lost game. Averaging over millions of games
  mitigates this.
- **Opening randomness**: Self-play games start from random or varied
  openings, exposing the network to diverse position types.

**Intentional noise (can be added):**
- **Random move injection**: During data generation, play random moves with
  some probability (e.g., 10%) to create "off-policy" positions the network
  has not seen before. Stockfish uses `multipv` and random move selection
  during data generation.
- **Position perturbation**: Add/remove pieces randomly from training
  positions to increase diversity.
- **Training regularization**: Apply dropout during NNUE training (though
  this is uncommon in current NNUE trainers due to the aggressive
  quantization that already acts as an implicit regularizer).
- **Score noise**: Add small random noise to training scores to prevent
  overfitting to exact evaluations.

### Why Equal-or-Larger Student Models Matter

In Noisy Student training, using a student that is at least as large as the
teacher is important because the noise degrades the effective training
signal. A smaller student lacks the capacity to compensate for this
degradation. In NNUE terms, this means:

- When iterating, do not shrink the network
- When increasing network capacity, the new (larger) network can absorb
  more information from the noisy training signal
- This is one reason why Stockfish progressively increased L1 size across
  architecture versions (256 -> 512 -> ... -> 3072)

### Practical Noisy Student Recipe for NNUE

```
Iteration 1:
  - Generate 100M positions with handcrafted eval at depth 7-9
  - Add 10% random moves during generation
  - Train NNUE v1 from scratch, 400 epochs

Iteration 2:
  - Generate 200M positions with NNUE v1 at depth 7-9
  - Add 8% random moves (slightly less noise as teacher improves)
  - Optionally mix 50M positions from iteration 1
  - Train NNUE v2 from v1 weights with reduced LR, 200 epochs

Iteration 3:
  - Generate 200M positions with NNUE v2
  - Add 5% random moves
  - Mix with 50M best positions from iteration 2
  - Train NNUE v3 from v2 weights with further reduced LR

Pattern: Decrease noise as teacher quality improves.
The best teacher does not need much noise to produce useful targets.
```

---

## 11. Practical Recipe for a Small Project

### Context: MiniChess / Small-Board Variants

For a small project (e.g., MiniShogi on a 5x5 board), the NNUE iteration
cycle can be completed much faster than for standard chess because:

- Fewer possible positions means less data is needed
- Smaller networks are sufficient
- Games are shorter, so data generation is faster
- You can run more iterations in less time

### Complete Recipe

#### Phase 0: Preparation

1. **Implement a handcrafted eval** -- Even a simple material-counting
   eval is sufficient to bootstrap the process. For MiniShogi, include:
   - Material values (with hand piece bonuses)
   - King safety (tropism)
   - Basic piece-square tables

2. **Implement data generation** -- Your engine needs a "self-play data
   generation" mode that outputs positions with evaluations in a standard
   format. Each record should contain:
   - Board position
   - Side to move
   - Evaluation score from search
   - Game result (1.0 / 0.5 / 0.0)

3. **Set up a trainer** -- Use an existing trainer if possible:
   - Bullet trainer (Rust, fast, widely used)
   - nnue-pytorch (Python, well-documented, Stockfish-oriented)
   - Custom PyTorch trainer for non-standard board sizes

#### Phase 1: Seed Network (Iteration 1)

**Data generation:**
- Generate 5-10M positions using handcrafted eval
- Search depth: 5-7 (less than standard chess; smaller game trees)
- Use varied opening positions
- Include 10% random moves for exploration

**Training:**
- Architecture: `(features) -> 32x2 -> 1` (start small)
- Learning rate: 1e-3 with step decay
- Batch size: 8192
- Epochs: 200-400
- Lambda: 1.0 (pure eval target for first iteration)

**Validation:**
- Play 2000+ games: NNUE v1 vs handcrafted eval
- Expected gain: 50-200 Elo (often dramatic for the first NNUE)

#### Phase 2: First Improvement (Iteration 2)

**Data generation:**
- Generate 10-20M positions using NNUE v1
- Same depth, but positions will be different because the engine plays
  differently now
- Reduce random move rate to 8%

**Training:**
- Same architecture, resume from v1 weights
- Learning rate: 5e-4 (lower, since we are refining)
- Epochs: 200
- Lambda: 1.0 -> 0.8 (introduce game outcome signal)

**Validation:**
- Play 2000+ games: NNUE v2 vs NNUE v1
- Expected gain: 20-50 Elo

#### Phase 3: Architecture Upgrade (Iteration 3)

If Iteration 2 showed diminishing returns (< 20 Elo), upgrade architecture:

**Architecture change:**
- `(features) -> 64x2 -> 16 -> 1` (wider + deeper)
- Train from scratch (cannot directly transfer weights to different arch)

**Data generation:**
- Generate 20-30M positions using NNUE v2
- Consider mixing: 70% new + 30% from iteration 2

**Training:**
- Learning rate: 1e-3 (from scratch, need higher LR)
- Epochs: 400
- Lambda: 0.8

**Validation:**
- Expected gain: 30-80 Elo from architecture + better data

#### Phase 4: Fine-Tuning (Iterations 4-6)

Repeat the data-generation -> retrain cycle 2-3 more times:
- Progressively lower learning rates: 5e-4 -> 2.5e-4 -> 1e-4
- Progressively lower lambda: 0.8 -> 0.7
- Mix data from last 2 iterations
- Expected gain per iteration: 10-30 Elo, diminishing

#### Phase 5: Plateau and Next Steps

When gains drop below ~5-10 Elo per iteration:

1. **Try a larger architecture** -- increase first layer width
2. **Try different feature sets** -- add king-relative features, threat
   features, or piece-pair features
3. **Try external data** -- if available, use data from a stronger engine
4. **Improve the search** -- better pruning, extensions, and time
   management can improve data quality without changing the network
5. **Accept the current strength** -- for a small project, 4-6 iterations
   often capture 80%+ of the achievable NNUE improvement

### Expected Total Gains by Iteration

| Iteration | Cumulative Elo Gain | Main Driver |
|-----------|-------------------|-------------|
| 1 (seed) | +100-200 | NNUE replaces handcrafted eval |
| 2 | +130-240 | Better data from NNUE-guided search |
| 3 (arch change) | +180-300 | Larger network capacity |
| 4 | +200-330 | Data quality + fine-tuning |
| 5 | +210-350 | Diminishing returns begin |
| 6 | +215-360 | Near plateau |

These numbers are approximate and vary significantly based on the quality
of the handcrafted eval, the game variant, and the search implementation.

### Timeline Estimate for a Solo Developer

| Phase | GPU Hours | Calendar Time |
|-------|-----------|---------------|
| Data gen iter 1 | 2-4h CPU | 1 day |
| Training iter 1 | 1-2h GPU | 1 day |
| Data gen iter 2 | 4-8h CPU | 1 day |
| Training iter 2 | 1-2h GPU | 1 day |
| Arch change + data gen | 8-12h CPU | 2 days |
| Training iter 3 | 2-4h GPU | 1 day |
| Fine-tuning iters 4-6 | 6-12h each | 3-6 days |
| **Total** | **~30-60h** | **~2-3 weeks** |

For a small variant like 5x5 MiniShogi, these times could be 2-5x shorter
due to faster games and smaller networks.

---

## Summary of Key Principles

1. **The training loop works because search > eval.** Search at depth D
   produces evaluations better than the raw eval, and the network learns
   to approximate those better evaluations cheaply.

2. **Students can surpass teachers** when the "teacher" is not just the
   network but the network-plus-search system, and when noise/regularization
   prevents mere memorization.

3. **Data quality and architecture co-evolve.** Neither better data alone
   nor a better architecture alone produces optimal results -- they must
   advance together.

4. **Start simple, iterate fast.** A small network trained through 3-4
   iterations will outperform a large network trained once. Iteration speed
   matters more than per-iteration perfection.

5. **Mix data strategically.** Lower-quality data provides breadth;
   higher-quality data provides accuracy. Use curriculum ordering (broad
   first, refined second).

6. **Decrease learning rate and noise across iterations** as the teacher
   improves and the student needs less exploration.

7. **Monitor playing strength, not just training loss.** The only metric
   that matters is Elo gain in actual games.

8. **Know when to stop iterating and change something structural**
   (architecture, features, search) instead.

---

## References and Further Reading

- [Stockfish NNUE - Chessprogramming Wiki](https://www.chessprogramming.org/Stockfish_NNUE)
- [NNUE - Chessprogramming Wiki](https://www.chessprogramming.org/NNUE)
- [Official nnue-pytorch Training Guide](https://github.com/official-stockfish/nnue-pytorch/wiki/Basic-training-procedure-(train.py))
- [nnue-pytorch Training Datasets](https://github.com/official-stockfish/nnue-pytorch/wiki/Training-datasets)
- [Stockfish NNUE Architecture Reference](https://official-stockfish.github.io/docs/nnue-pytorch-wiki/docs/nnue.html)
- [Introducing NNUE Evaluation - Stockfish Blog](https://stockfishchess.org/blog/2020/introducing-nnue-evaluation/)
- [Seer Chess Engine (Retrograde Learning)](https://github.com/connormcmonigle/seer-nnue)
- [Born Again Neural Networks (Furlanello et al., 2018)](https://arxiv.org/abs/1805.04770)
- [Self-Training with Noisy Student (Xie et al., 2020)](https://arxiv.org/abs/1911.04252)
- [Study of the Proper NNUE Dataset (2024)](https://arxiv.org/html/2412.17948v1)
- [Stockfish NNUE Training Data](https://robotmoon.com/nnue-training-data/)
- [Efficiently Updatable Neural Network - Wikipedia](https://en.wikipedia.org/wiki/Efficiently_updatable_neural_network)
- [Fairy-Stockfish Variant NNUE Training](https://fairy-stockfish.github.io/about-nnue/)
- [Stockfish SFNNv10 Commit (Threat Inputs)](https://github.com/official-stockfish/Stockfish/commit/8e5392d79a36aba5b997cf6fb590937e3e624e80)
- [Stockfish SFNNv5 Commit (Squared ClippedReLU)](https://github.com/official-stockfish/Stockfish/commit/c079acc26f93acc2eda08c7218c60559854f52f0)
- [Stockfish SFNNv13 Commit](https://github.com/official-stockfish/Stockfish/commit/a6d055d7e27ab3e29a42e8b94215102824760057)
- [Knowledge Distillation in Deep Learning](https://pmc.ncbi.nlm.nih.gov/articles/PMC8053015/)
- [Lc0 Data Converter for Stockfish NNUE](https://github.com/linrock/lc0-data-converter)
