# NNUE Evolution Strategy for MiniChess/MiniShogi

A unified strategy for iteratively evolving NNUE evaluation networks on small
boards, synthesized from research on data generation techniques and iterative
self-improvement loops. This document provides concrete iteration plans,
datagen configurations, training parameters, and decision frameworks tailored
to MiniChess (6x5, ~20 legal moves avg) and MiniShogi (5x5 with drops, ~25-30
legal moves avg).

---

## Table of Contents

1. [Critical Finding: The Raw Eval Bug](#1-critical-finding-the-raw-eval-bug)
2. [Multi-Iteration Improvement Plan](#2-multi-iteration-improvement-plan)
3. [Ply-Dependent Random Move Schedule for Small Boards](#3-ply-dependent-random-move-schedule-for-small-boards)
4. [When to Regenerate Data vs. Reuse](#4-when-to-regenerate-data-vs-reuse)
5. [When to Fine-Tune vs. Train from Scratch](#5-when-to-fine-tune-vs-train-from-scratch)
6. [The Knowledge Distillation Ceiling](#6-the-knowledge-distillation-ceiling)
7. [Decision Tree: After Iteration N, What Next?](#7-decision-tree-after-iteration-n-what-next)
8. [Position Filtering Pipeline](#8-position-filtering-pipeline)
9. [Monitoring and Plateau Detection](#9-monitoring-and-plateau-detection)
10. [Timeline and Resource Estimates](#10-timeline-and-resource-estimates)

---

## 1. Critical Finding: The Raw Eval Bug

### What Happened

All previous NNUE models (v1, v2) were trained on data where the datagen
system recorded **raw static eval** (the output of the evaluation function
without search) rather than **search scores** (the result of alpha-beta search
at the configured depth). The bug was recently fixed.

This means:
- The 67M existing positions at depth 6 have labels that are static eval
  outputs, not depth-6 search results.
- NNUE v1 and v2 learned to replicate the handcrafted eval's surface-level
  judgments, **not** the search-corrected assessments that incorporate tactical
  awareness and deeper positional understanding.

### Why This Matters

The entire self-improvement loop depends on **search acting as a policy
improvement operator**. The core insight of iterative NNUE training is:

```
Search at depth D produces evaluations BETTER than raw eval.
The network learns those better evaluations, making it stronger.
Next iteration, search with the stronger eval finds EVEN better evaluations.
```

When the recorded score is raw eval instead of search score, this loop
collapses into a mere copy operation. The NNUE learns to replicate the
handcrafted eval, gaining only from the neural network's ability to generalize
differently -- not from internalizing tactical and strategic corrections that
search discovers. The "virtual teacher" that makes distillation work (the
search) was effectively bypassed.

### Implications for v1 and v2

Despite the bug, v1/v2 may still have gained *some* Elo over the handcrafted
eval because:

1. **Generalization benefit**: The NNUE architecture generalizes differently
   from the handcrafted eval, sometimes producing better assessments in
   positions where the handcrafted heuristics were weak.
2. **Game result signal**: If any lambda < 1.0 blending was used, the game
   outcome component of the loss was unaffected by the bug.
3. **Implicit regularization**: The neural network smooths over discontinuities
   in the handcrafted eval.

However, the gains were almost certainly **far below** what correct search
scores would have produced. With proper search-score labels:

- v1 should see a **much larger** jump over handcrafted eval (possibly 2-3x
  the Elo gain seen with raw eval data).
- The iterative improvement loop should actually produce compounding gains
  instead of stalling.

### What to Do Now

**All existing training data (67M positions) should be considered compromised
for the eval label, but the positions themselves and the game results are
still valid.**

Options:

1. **Full regeneration (recommended)**: Regenerate data from scratch with the
   fixed datagen. This is the cleanest path forward.
2. **Rescore existing positions**: Run the search engine over the 67M stored
   positions and replace the raw eval with depth-6 search scores. This saves
   the cost of replaying games but requires infrastructure to load and rescore
   positions.
3. **Use game results only**: Train with lambda=0.0 (pure game outcome) on
   the existing data as a quick experiment. The game results are correct; only
   the eval labels are wrong. This produces a weaker signal but valid one.

The evolution plan below assumes **Option 1: full regeneration** from the
current best engine configuration (handcrafted eval or whichever NNUE version
plays strongest despite the bug).

---

## 2. Multi-Iteration Improvement Plan

### Overview

```
v0 (handcrafted eval)
 |
 | Generate 20M positions, depth 6, FIXED datagen (search scores)
 v
v1 (seed NNUE) ---- expected: +100-200 Elo over v0
 |
 | Generate 30-50M positions, depth 6, using v1 eval
 v
v2 (first refinement) ---- expected: +20-50 Elo over v1
 |
 | Architecture upgrade + generate 50M positions, depth 6-8
 v
v3 (arch upgrade) ---- expected: +30-80 Elo over v2
 |
 | Generate 50-80M positions, depth 8, mix with v3 data
 v
v4 (deep refinement) ---- expected: +10-30 Elo over v3
 |
 | Fine-tune iterations with decreasing LR and noise
 v
v5, v6, ... ---- expected: +5-15 Elo each, diminishing
```

### Iteration v1: Seed Network (Start Fresh)

This is the most important iteration. With the datagen bug fixed, this is
effectively the **true v1** -- the first network trained on correct data.

**Datagen parameters:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Positions | 20M | 10x rule for ~50K-param network |
| Depth | 6 | Equivalent to depth 9-10 on 8x8 due to lower branching |
| Random moves | Ply-dependent (see Section 3) | Better than uniform epsilon |
| Eval used | Handcrafted eval (v0) | Starting from scratch |
| Score recorded | **Search score** (depth 6 PVS result) | THE critical fix |
| Game result | Recorded, backfilled after game ends | For lambda blending |
| Eval limit | 2500 cp | Discard and adjudicate decided games |
| Write min ply | 4 | Small board = short games, start recording early |
| Position filter | Skip checks, skip capture-as-best-move | Smart FEN skipping |
| Games needed | ~700K (at ~30 usable positions/game) | Parallelizable |

**Training parameters:**

| Parameter | Value |
|-----------|-------|
| Architecture | (InputFeatures) -> 32x2 -> 1 |
| Learning rate | 1e-3, step decay to 1e-4 |
| Batch size | 8192 |
| Epochs | 400 |
| Lambda | 1.0 (pure search score) |
| Optimizer | Adam |

**Expected gains:** +100-200 Elo over handcrafted eval. This range is wide
because the magnitude depends on how good the handcrafted eval already is.
A weak handcrafted eval (material only) yields larger gains; a sophisticated
one (with king safety, piece-square tables, hand bonuses) yields smaller but
still significant gains.

**Validation:** Play 2000+ games at fixed time/depth between NNUE v1 and
handcrafted eval. Use `cutechess-cli` or equivalent with Elo estimation.

---

### Iteration v2: First Self-Improvement

The engine now uses NNUE v1 for evaluation. Self-play data reflects the
NNUE's understanding, and search corrects for the NNUE's blind spots.

**Datagen parameters:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Positions | 30-50M | More data for refinement |
| Depth | 6 | Same depth; quality comes from better eval |
| Random moves | Ply-dependent, slightly lower rates | Teacher is better, less noise needed |
| Eval used | NNUE v1 | Self-improvement begins |
| Data mixing | 100% new (v1-generated) | Old data was from handcrafted eval |

**Training parameters:**

| Parameter | Value |
|-----------|-------|
| Architecture | Same: (InputFeatures) -> 32x2 -> 1 |
| Initial weights | Resume from v1 |
| Learning rate | 5e-4, decay to 1e-4 |
| Epochs | 200 |
| Lambda | 1.0 -> 0.85 (linear decay over training) |

**Expected gains:** +20-50 Elo over v1.

**Decision point:** If gain is < 20 Elo, skip directly to architecture
upgrade (v3). If gain is > 40 Elo, consider one more iteration at the same
architecture before upgrading.

---

### Iteration v3: Architecture Upgrade

When same-architecture iterations show diminishing returns (< 20 Elo), it is
time to increase network capacity.

**Datagen parameters:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Positions | 50M | Larger network needs more data |
| Depth | 6-8 | Can afford deeper search with stronger eval |
| Random moves | Ply-dependent schedule | See Section 3 |
| Eval used | NNUE v2 (or best available) | Best teacher produces best data |
| Data mixing | 70% new + 30% from v2 iteration | Prevents catastrophic forgetting |

**Training parameters:**

| Parameter | Value |
|-----------|-------|
| Architecture | (InputFeatures) -> 64x2 -> 16 -> 1 |
| Initial weights | From scratch (architecture changed) |
| Learning rate | 1e-3, step decay |
| Epochs | 400 |
| Lambda | 0.85 |

**Expected gains:** +30-80 Elo over v2. Architecture upgrades typically
produce the second-largest gains after the initial seed network.

---

### Iterations v4-v6: Deep Refinement

Repeat the self-improvement cycle with progressively decreasing learning
rates, noise, and lambda.

| Parameter | v4 | v5 | v6 |
|-----------|-----|-----|-----|
| Positions | 50-80M | 80M | 80-100M |
| Depth | 8 | 8 | 8 |
| Eval used | v3 | v4 | v5 |
| Data mixing | 70% new + 30% old | 70/30 | 70/30 |
| Init weights | Resume from v3 | Resume from v4 | Resume from v5 |
| LR start | 5e-4 | 2.5e-4 | 1e-4 |
| LR end | 1e-4 | 5e-5 | 2e-5 |
| Epochs | 200 | 150 | 100 |
| Lambda | 0.80 | 0.75 | 0.70 |
| Random moves | Reduced rates | Further reduced | Minimal |
| Expected gain | +10-30 Elo | +5-20 Elo | +5-15 Elo |

**When to stop:** If two consecutive iterations gain < 5 Elo, the current
architecture/data regime has plateaued. See Section 7 for the decision tree.

---

### Cumulative Expected Gains

| Milestone | Cumulative Elo over v0 | Main Driver |
|-----------|------------------------|-------------|
| v1 (seed) | +100-200 | NNUE replaces handcrafted eval |
| v2 | +130-240 | Self-play improvement loop begins |
| v3 (arch) | +180-300 | Larger network capacity |
| v4 | +200-330 | Data quality + fine-tuning |
| v5 | +210-350 | Diminishing returns begin |
| v6 | +215-360 | Near plateau for this architecture |

These are rough estimates. Actual gains depend heavily on the quality of the
handcrafted eval, the search implementation, and the game variant.

---

## 3. Ply-Dependent Random Move Schedule for Small Boards

### Why Uniform Epsilon is Suboptimal

The current datagen uses a flat epsilon=0.15 at every ply. On a 6x5 or 5x5
board where games last 30-60 plies, this means:

- ~15% of all positions have a random move played into them, adding noise
  throughout the game.
- Random moves in the endgame (ply 25+) create nonsensical positions where
  pieces are hung or kings walk into danger. These waste training signal.
- Opening diversity (where randomization matters most) gets only the same 15%
  as the endgame.

### Recommended Schedule: MiniChess (6x5)

Average game length: ~40-60 plies. ~20 legal moves per position.

| Phase | Ply Range | Epsilon | Rationale |
|-------|-----------|---------|-----------|
| Early opening | 0-4 | 0.30 | Maximum diversity where it matters most. 4 plies = 2 full moves; with 30% randomness the engine explores many different opening structures. |
| Late opening | 5-10 | 0.20 | Still significant exploration. On a 6x5 board, ply 10 is roughly move 5 -- the transition from opening to middlegame. |
| Early middlegame | 11-16 | 0.10 | Moderate exploration. Positions are becoming tactical; random moves increasingly create unrealistic states. |
| Late middlegame | 17-24 | 0.05 | Light exploration. Most diversity has been established; the engine should play naturally to produce high-quality scores. |
| Endgame | 25+ | 0.00 | Fully deterministic. Endgame positions on 6x5 are highly tactical; random moves create garbage. |

**Implementation formula:**

```
epsilon(ply) = epsilon_max * max(0.0, 1.0 - ply / decay_ply)
```

With `epsilon_max = 0.30` and `decay_ply = 25`:

- Ply 0: 0.30
- Ply 5: 0.24
- Ply 10: 0.18
- Ply 15: 0.12
- Ply 20: 0.06
- Ply 25+: 0.00

### Recommended Schedule: MiniShogi (5x5 with drops)

MiniShogi has a higher branching factor (~25-30) due to drops, longer games
(~50-80 plies), and a wider position space. The schedule should reflect this.

| Phase | Ply Range | Epsilon | Rationale |
|-------|-----------|---------|-----------|
| Opening | 0-6 | 0.25 | Drops are not yet in play (no captured pieces). Standard piece move diversity. |
| Early middle | 7-14 | 0.20 | Drops begin. Higher epsilon here explores the vast drop-position space. |
| Middle | 15-24 | 0.10 | Position complexity is high; moderate randomness suffices. |
| Late middle | 25-35 | 0.05 | Positions are tactical with many drop options. |
| Endgame | 36+ | 0.00 | Deterministic play. |

**Formula:** `epsilon_max = 0.25`, `decay_ply = 36`.

### Noise Reduction Across Iterations

As the teacher network improves, less randomization is needed because the
teacher's own play is more diverse (it evaluates positions more accurately,
leading to more varied best-move choices). Reduce the schedule across
iterations:

| Iteration | epsilon_max | decay_ply |
|-----------|-------------|-----------|
| v1 (seed) | 0.30 | 25 |
| v2 | 0.25 | 25 |
| v3 | 0.20 | 20 |
| v4+ | 0.15 | 20 |

### Alternative: Hybrid Book + Random Moves

For small boards, an even better approach combines an exhaustive opening book
with limited random moves:

1. **Generate an opening book** by enumerating all positions at depth 3-4
   from the start position (feasible: ~40K-160K positions for 6x5).
2. **Filter** to balanced positions (|eval| < 300 cp at depth 2-3).
3. **Start each game** from a randomly sampled book position.
4. **Add 1-2 random moves** from multi-PV search in plies 4-8.
5. **Play deterministically** from ply 8 onward.

This gives guaranteed opening diversity with no garbage positions. The book
approach is recommended for v3+ iterations when the infrastructure is
available.

---

## 4. When to Regenerate Data vs. Reuse

### Regenerate When

| Condition | Rationale |
|-----------|-----------|
| The eval used for datagen has improved by 50+ Elo | Old data reflects old eval's biases; new eval sees positions differently |
| Architecture has changed | New architecture may need different position distributions |
| Previous data used wrong labels (the raw eval bug) | **This is our situation.** All previous data must be regenerated. |
| You hit a plateau | Fresh data from a stronger eval breaks local optima |
| You changed search parameters (depth, pruning) | Different search produces different position distributions and scores |
| You changed the random move schedule | Position diversity profile has changed |

### Reuse When

| Condition | Rationale |
|-----------|-----------|
| Old data came from a stronger source | Higher-quality data does not expire |
| You are mixing quality tiers | Old broad data + new deep data = good curriculum |
| Network capacity increased | Bigger networks benefit from more total data |
| Data generation is the bottleneck | Reuse saves compute; regenerate only partially |
| Only the game result (not eval label) matters | Old positions with correct results can train with lambda=0.0 |

### Practical Rules

1. **Always regenerate** when transitioning from handcrafted eval to NNUE
   eval for datagen. The position distributions are fundamentally different.

2. **Regenerate every 2-3 iterations** even when staying at the same
   architecture. The network evolves and its data should too.

3. **Keep old data for mixing** (30% old + 70% new) unless the old data is
   known to have label problems (as with the raw eval bug).

4. **Never discard high-quality data**. If you generated data at depth 8 with
   a strong network, keep it forever -- it can serve as a fine-tuning dataset
   in future iterations.

5. **For the current situation**: regenerate everything. The existing 67M
   positions have wrong eval labels. The positions and game results could
   theoretically be rescored, but fresh generation with the fixed datagen is
   cleaner and also benefits from any improvements to the random move schedule.

---

## 5. When to Fine-Tune vs. Train from Scratch

### Decision Matrix

| Scenario | Recommendation | Rationale |
|----------|---------------|-----------|
| First NNUE ever (v1) | From scratch | No prior weights exist |
| Same architecture, better data (v2) | Fine-tune from v1 | Preserves learned features; faster convergence |
| Architecture changed (v3) | From scratch | Weights are not compatible |
| Width increased only (e.g., 32->64 in L1) | Partial transfer + fine-tune | Copy old weights, zero-init new columns, train with higher LR |
| Hit a plateau with fine-tuning | From scratch on accumulated data | Escape local optima; fresh random init may find better basin |
| Training on fundamentally different data (e.g., first time with correct search scores) | From scratch | Old weights were optimized for wrong targets |

### Fine-Tuning Protocol

When fine-tuning (resuming from previous weights):

- **LR**: Start at 1/2 to 1/4 of the from-scratch LR. Too high will destroy
  learned features; too low will barely move.
- **Epochs**: 1/2 to 2/3 of from-scratch epochs. The network starts closer
  to the optimum.
- **Lambda**: Can be lower than from-scratch (e.g., 0.75-0.85 vs. 1.0)
  because the network already understands basic eval; game-result signal now
  adds value.

### From-Scratch Protocol

When training from scratch:

- **LR**: Full initial rate (1e-3).
- **Epochs**: Full count (400).
- **Lambda**: Start at 1.0 (pure search score) for the first iteration; the
  network needs clean signal while learning basic patterns.

### For Our Current Situation

Since all previous data had wrong labels, the existing v1/v2 weights were
optimized for the wrong objective. When retraining with correct search-score
data:

- **Recommended: train from scratch.** The old weights encode handcrafted-eval
  patterns, not search-corrected patterns. Starting fresh lets the network
  learn from the correct signal without interference.
- **Alternative: fine-tune briefly as a warm start.** The old weights are not
  garbage -- they encode useful material-balance and piece-activity patterns.
  A short fine-tuning run (50-100 epochs) with high LR could be faster than
  full from-scratch training. Worth trying as an experiment alongside the
  from-scratch run, then pick whichever plays stronger.

---

## 6. The Knowledge Distillation Ceiling

### The Ceiling and Why It Exists

In pure knowledge distillation (student mimics teacher), the student
asymptotically approaches but cannot exceed the teacher's quality. The
ceiling is the teacher's own accuracy.

In NNUE training, the "teacher" is not just the eval function -- it is the
**eval + search** system. This is why NNUE distillation can (and routinely
does) surpass the raw eval:

```
Effective teacher strength = eval_strength + search_amplification(depth)
```

The search at depth D finds tactical and strategic corrections that the eval
alone misses. The student network learns to predict these corrections without
search, effectively "compiling" depth-D knowledge into a static evaluation.

**But the ceiling still exists at the eval+search level.** Once the NNUE
accurately predicts depth-D search results, further iterations at the same
depth produce diminishing returns. The network has learned everything the
search at depth D can teach it.

### How to Quantify the Ceiling

The ceiling manifests as:

1. **Iteration gains dropping below 5 Elo** for two or more consecutive
   iterations.
2. **Validation loss plateauing** across iterations (not just within a
   training run).
3. **Position disagreement rate** between consecutive networks dropping
   below 5% (they agree on almost every position).

### Strategies to Break Through

Listed in order of expected impact and implementation difficulty:

**1. Increase search depth (easiest, medium impact)**

If data was generated at depth 6, generate new data at depth 8 or 10. Deeper
search produces a stronger "virtual teacher." On 6x5 boards where depth 6
already covers ~12% of the game, depth 8 covers ~16% -- a meaningful increase.

Cost: roughly 4-10x more compute per position (branching factor^2 more nodes).

**2. Upgrade network architecture (medium difficulty, high impact)**

A larger network can represent a more complex eval function. Follow the
Stockfish progression:

```
32x2 -> 1        (v1-v2)
64x2 -> 16 -> 1  (v3-v4)
128x2 -> 32 -> 1 (v5+)
```

Each width doubling roughly doubles the number of features the network can
track and requires roughly 4x more training data to saturate.

**3. Add new input features (hard, highest impact)**

Stockfish's biggest jumps came from feature set changes (HalfKP -> HalfKA ->
threat inputs). For MiniChess/MiniShogi, consider:

- King-relative piece placement features
- Attack/defense map features
- Hand piece features (MiniShogi)
- Threat features (piece X attacks square Y where piece Z sits)

Each feature set change requires retraining from scratch and regenerating data.

**4. Incorporate external or higher-quality data (variable)**

Analogous to Stockfish's use of Lc0 data. For small-board games, potential
sources include:

- Deeper search data (depth 12-16) for a subset of important positions
- Endgame tablebase scores for positions with few pieces
- Positions from a different engine playing the same variant

**5. Improve the search algorithm itself (hard, compounding impact)**

Better pruning, better move ordering, and better time management make the
search at the same depth *effectively deeper*. This changes the "virtual
teacher" quality and indirectly improves all subsequent NNUE iterations.

This is the most sustainable long-term lever: search improvements compound
with NNUE improvements.

**6. Curriculum learning with multi-depth mixing (medium difficulty)**

Instead of a single depth, mix positions from multiple depths:

| Depth | Proportion | Role |
|-------|-----------|------|
| 4 | 40% | Broad coverage, cheap labels |
| 6 | 35% | Core quality |
| 8 | 20% | High-quality anchors |
| 10+ | 5% | Critical positions, expensive |

Train in curriculum order: all depth-4 data first, then mix in depth-6,
then depth-8. This mirrors Stockfish's approach of training on self-play
data first, then refining on Lc0 data.

---

## 7. Decision Tree: After Iteration N, What Next?

```
After completing iteration N, measure Elo gain over iteration N-1.
|
+-- Gain >= 30 Elo?
|   |
|   YES --> Continue with same architecture.
|   |       Generate new data with current best network.
|   |       Fine-tune from current weights (reduced LR).
|   |       Reduce random move rates slightly.
|   |       Go to iteration N+1.
|   |
|   NO --> Gain >= 10 Elo?
|          |
|          YES --> Try ONE more iteration at same architecture.
|          |       If next iteration also < 30 Elo, go to architecture upgrade.
|          |       Also try: increase data volume (2x), increase search depth (+2).
|          |
|          NO --> Gain >= 5 Elo?
|                 |
|                 YES --> Architecture plateau reached.
|                 |       Go to "Architecture Upgrade" below.
|                 |
|                 NO --> Full plateau reached.
|                        Go to "Breaking the Plateau" below.

Architecture Upgrade:
|
+-- Current arch is (Features) -> Wx2 -> 1 (single hidden)?
|   |
|   YES --> Upgrade to (Features) -> (2W)x2 -> 16 -> 1
|           (double width, add second hidden layer)
|           Train from scratch on best available data.
|           Regenerate data with current best network.
|           Expect +30-80 Elo.
|
+-- Current arch is (Features) -> Wx2 -> H -> 1 (two hidden)?
|   |
|   YES --> Options (try in order):
|           a) Double W (first layer width)
|           b) Add third hidden layer: W x2 -> H -> H2 -> 1
|           c) Add SCReLU or pairwise multiplication activation
|           Train from scratch. Expect +15-50 Elo.
|
+-- Already at (Features) -> 128x2 -> 32 -> 32 -> 1 or larger?
    |
    YES --> Consider feature set changes (see Section 6, point 3).
            This is the highest-impact remaining lever.

Breaking the Plateau (all architectural options exhausted at current scale):
|
+-- 1. Increase search depth for datagen by +2 (e.g., 6 -> 8 -> 10)
|      Regenerate data. Retrain from scratch.
|
+-- 2. Implement opening book generation (perft-based)
|      Regenerate data with book + minimal random moves.
|
+-- 3. Add new input features (threat features, hand features for Shogi)
|      Requires code changes. Retrain from scratch.
|
+-- 4. Generate endgame tablebase data for small piece counts
|      Fine-tune existing network on tablebase-scored positions.
|
+-- 5. Improve the search algorithm
|      Better pruning/extensions change the "virtual teacher."
|      All subsequent iterations benefit.
|
+-- 6. Accept current strength as near-optimal for the project's scope.
```

---

## 8. Position Filtering Pipeline

Not all self-play positions are equally useful. Apply this filter chain
during data generation:

```
Position generated at ply P with score S
  |
  +-- P < write_minply (4 for MiniChess, 4 for MiniShogi)?
  |   YES --> DISCARD (opening positions are identical across games)
  |
  +-- Side to move is in check?
  |   YES --> DISCARD (tactical volatility; NNUE cannot learn check eval)
  |
  +-- Best move is a capture?
  |   YES --> DISCARD (position requires tactical resolution, not pattern matching)
  |
  +-- |S| > eval_limit (2500 cp)?
  |   YES --> DISCARD this position AND adjudicate game
  |           (decided games waste compute)
  |
  +-- Random move was played this ply?
  |   YES --> DISCARD (position entered via unrealistic move)
  |           Continue playing but skip recording for 1 ply to let search recover
  |
  +-- KEEP: record (position, search_score, game_result)
```

**Additional filtering at training time** (in the trainer, not datagen):

- Smart FEN skipping: skip positions where |static_eval - qsearch_score| > 60 cp
- Score distribution balancing: under-sample the dense region near eval=0
  if the dataset is heavily concentrated there
- Under-sample draws if draws dominate the game results (keep 50-70% of drawn
  game positions, 100% of decisive game positions)

---

## 9. Monitoring and Plateau Detection

### What to Measure After Each Iteration

**Primary: playing strength (Elo)**

Run a gauntlet of 2000-5000 games at fixed time/depth:
- New network vs. previous best network
- New network vs. handcrafted eval (tracks cumulative progress)

Use `cutechess-cli` or equivalent. An iteration is successful if the new
network gains >= 5 Elo with statistical significance.

**Secondary: training diagnostics**

| Metric | Healthy Sign | Warning Sign |
|--------|-------------|-------------|
| Validation loss | Decreasing across iterations | Flat or increasing |
| Score distribution on test set | Spreading (more extreme evals) | Collapsing to narrow band |
| Position disagreement rate (top move) | > 10% between consecutive versions | < 5% (networks are converging) |
| Game length distribution | Stable or slightly shorter | Wild changes (randomness issue) |

**Plateau signals:**

- Elo gain < 5 for two consecutive iterations
- Validation loss stops improving across iterations
- Position disagreement rate < 5%

When plateau is detected, refer to the decision tree in Section 7.

---

## 10. Timeline and Resource Estimates

### For MiniChess (6x5), Solo Developer

| Phase | CPU Hours | GPU Hours | Calendar |
|-------|-----------|-----------|----------|
| Datagen v1 (20M positions, depth 6, 64 workers) | 2-4h | -- | 1 day |
| Train v1 (400 epochs) | -- | 1-2h | 1 day |
| Validate v1 (2000 games) | 1-2h | -- | 0.5 day |
| Datagen v2 (30-50M positions) | 4-6h | -- | 1 day |
| Train v2 (200 epochs) | -- | 1h | 0.5 day |
| Validate v2 | 1-2h | -- | 0.5 day |
| Datagen v3 (50M positions, depth 6-8) | 6-10h | -- | 1-2 days |
| Train v3 (400 epochs, new arch) | -- | 2-3h | 1 day |
| Validate v3 | 1-2h | -- | 0.5 day |
| Fine-tuning v4-v6 (3 iterations) | 6-12h each | 1-2h each | 3-6 days |
| **Total** | **~30-50h** | **~8-12h** | **~2-3 weeks** |

For MiniShogi (5x5), times are similar but datagen may be 1.5-2x slower due
to the higher branching factor from drops.

### Parallelism

Data generation is embarrassingly parallel. The existing `gen_data.sh` script
supports 64 parallel workers. With 64 cores:

- 20M positions at depth 6: ~15-30 minutes wall time
- 50M positions at depth 6: ~40-75 minutes wall time
- 50M positions at depth 8: ~3-8 hours wall time

Training is GPU-bound. A single consumer GPU (RTX 3060 or better) handles
the small network sizes (32-128 hidden) with ease. Training is not the
bottleneck for this project.

---

## Appendix A: Summary of Key Principles

1. **The training loop works because search > eval.** Search at depth D
   produces evaluations better than the raw eval, and the network learns to
   approximate those better evaluations cheaply. This REQUIRES recording
   search scores, not raw eval.

2. **The raw eval bug invalidated all previous training data labels.** This
   is actually an opportunity: with correct data, expect large gains.

3. **Students surpass teachers** when the "teacher" is eval+search (not just
   eval) and when noise/regularization prevents mere memorization.

4. **Data quality and architecture co-evolve.** Neither better data alone
   nor a better architecture alone produces optimal results -- they must
   advance together.

5. **Start simple, iterate fast.** A small network trained through 3-4
   iterations outperforms a large network trained once. Iteration speed
   matters more than per-iteration perfection.

6. **Mix data strategically.** Lower-quality data provides breadth;
   higher-quality data provides accuracy. Use curriculum ordering.

7. **Decrease noise across iterations** as the teacher improves.

8. **Ply-dependent randomization** is strictly superior to uniform epsilon
   on small boards where endgame random moves create garbage positions.

9. **Regenerate data** when the eval has improved significantly, when
   switching from handcrafted to NNUE eval, or when labels are known to be
   wrong.

10. **Know when to stop iterating** and change something structural
    (architecture, features, search depth) instead.

---

## Appendix B: Quick Reference -- Iteration Checklist

For each iteration:

- [ ] Decide: from scratch or fine-tune? (See Section 5)
- [ ] Decide: regenerate data or reuse? (See Section 4)
- [ ] Set datagen parameters (depth, random move schedule, position filters)
- [ ] Generate data with the **current best** network (or handcrafted eval for v1)
- [ ] Verify data quality: check score distribution, unique position ratio, game length histogram
- [ ] Confirm scores are **search scores**, not raw eval (the bug check)
- [ ] Train with appropriate LR, epochs, lambda for this iteration
- [ ] Validate: run 2000+ game gauntlet, measure Elo
- [ ] Record results: Elo gain, validation loss, training time
- [ ] Decision: continue, upgrade architecture, or change approach? (See Section 7)
