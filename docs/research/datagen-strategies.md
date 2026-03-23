# Seed Data Generation Strategies for NNUE Training

This document surveys data generation strategies used by Stockfish and the broader
chess engine community for training NNUE (Efficiently Updatable Neural Network)
evaluation functions, with specific attention to how these ideas apply to small-board
games (5x5 to 7x7) like MiniChess and MiniShogi.

---

## Table of Contents

1. [How Stockfish Generates Training Data](#1-how-stockfish-generates-training-data)
2. [Random Move Injection Strategies](#2-random-move-injection-strategies)
3. [Score Recording](#3-score-recording)
4. [Position Filtering](#4-position-filtering)
5. [Data Diversity](#5-data-diversity)
6. [Game Result Recording and WDL Signal Quality](#6-game-result-recording-and-wdl-signal-quality)
7. [Multi-Depth Data Mixing](#7-multi-depth-data-mixing)
8. [How Many Games / Positions Are Needed](#8-how-many-games--positions-are-needed)
9. [Practical Tips for Small-Board Games](#9-practical-tips-for-small-board-games)

---

## 1. How Stockfish Generates Training Data

### The `gensfen` Command

Stockfish's NNUE training data is generated through the `gensfen` command
(originally from [nodchip's Stockfish fork](https://github.com/nodchip/Stockfish/blob/master/docs/gensfen.md)).
The engine plays self-play games from starting positions, recording each position
along with its search evaluation and eventual game result.

#### Core search parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `depth` | 3 | Minimum evaluation depth |
| `depth2` | same as `depth` | Maximum evaluation depth |
| `nodes` | (none) | Node count per position; whichever limit (depth or nodes) is reached first applies |
| `loop` | 8,000,000,000 | Number of positions to generate |

#### Output parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `output_file_name` | `generated_kifu` | Output file name (extension auto-appended) |
| `sfen_format` | `binpack` | Data format (`bin` or `binpack`) |
| `save_every` | (none) | Entries per file; splits into numbered files |

#### Position emission controls

| Parameter | Default | Description |
|-----------|---------|-------------|
| `eval_limit` | 3000 | Discard positions with |eval| exceeding this; also used to adjudicate won games |
| `write_minply` | 16 | Minimum ply before recording positions |
| `write_maxply` | 400 | Maximum ply to record positions |
| `ensure_quiet` | (flag) | Only emit positions at quiescence search leaf nodes |

#### Draw adjudication

| Parameter | Default | Description |
|-----------|---------|-------------|
| `detect_draw_by_consecutive_low_score` | 1 | Adjudicate draw when score stays 0 for 8+ plies after ply 80 |
| `detect_draw_by_insufficient_mating_material` | 1 | Adjudicate on insufficient material |
| `write_out_draw_game_in_training_data_generation` | 1 | Whether to include drawn games |

### Depth vs. Nodes

Stockfish's most successful datasets use **depth 9** for search evaluations, which
remains the community-recommended sweet spot. An alternative is **fixed node count**
(typically 5000 nodes per move), which normalizes compute per position regardless of
position complexity. The dataset `dfrc_n5000.binpack` was generated with 5000 nodes
per move and produced competitive results.

In practice:
- **Fixed depth** gives consistent evaluation quality but spends wildly different
  amounts of time on simple vs. complex positions.
- **Fixed nodes** normalizes compute time but produces variable-depth evaluations.
- Both approaches work well; depth 9 remains the most widely validated choice.

### The Modern Pipeline

The best Stockfish nets (2022 onward) are trained on a **mix** of:
1. Stockfish self-play data at depth 9 (e.g., 16 billion positions)
2. Lc0 (Leela Chess Zero) data rescored into binpack format

The Lc0-derived data tends to produce higher-quality networks, but training on Lc0
data alone from scratch gives poor results. The recommended workflow is: train first
on Stockfish self-play data, then retrain on Lc0-derived data. This suggests the
self-play data provides essential "coverage" of the position space that higher-quality
evaluations can then refine.

---

## 2. Random Move Injection Strategies

Random move injection is the single most important factor for training data diversity
in self-play generation. Without it, a strong engine will play the same openings
repeatedly and the dataset will cover a tiny fraction of the position space.

### 2.1 Uniform Epsilon-Greedy (Current Approach)

**How it works:** At every move, with probability epsilon, play a uniformly random
legal move instead of the search's best move.

This is what our `datagen.cpp` currently implements:

```cpp
bool jitter = (rng_float() < cfg.epsilon);  // default epsilon = 0.15
if (jitter) {
    int idx = rng_int((int)game->legal_actions.size());
    chosen_move = game->legal_actions[idx];
}
```

**Pros:**
- Simple to implement
- Every position has a chance of diverging from the principal variation

**Cons:**
- Random moves in the endgame can create nonsensical positions (hanging king,
  giving away won games) that waste training signal
- A 15% random move rate throughout the game means roughly 15% of all recorded
  positions have an artificially bad move played *into* them, which adds noise
- Uniform randomness does not match where diversity is most needed (openings)

### 2.2 Ply-Dependent Epsilon

**How it works:** The probability of a random move decreases as the game progresses.

```
epsilon(ply) = epsilon_start * max(0, 1 - ply / decay_ply)
```

For example, with `epsilon_start=0.25` and `decay_ply=40`:
- Ply 0: 25% random
- Ply 20: 12.5% random
- Ply 40+: 0% random (fully deterministic)

**Rationale:** Opening diversity is critical because the opening determines which
region of the position space the game explores. Late-game random moves mostly create
garbage positions since tactical considerations dominate. This mirrors the
epsilon-decay schedule used in reinforcement learning, where agents explore more at
the beginning of training and exploit more later.

**Recommended for our engine:** This is a straightforward improvement over uniform
epsilon. A reasonable starting configuration:

| Phase | Ply range (5x5) | Suggested epsilon |
|-------|------------------|-------------------|
| Opening | 0-8 | 0.25-0.30 |
| Middlegame | 8-20 | 0.10-0.15 |
| Endgame | 20+ | 0.00-0.05 |

### 2.3 Temperature-Based Move Selection (Softmax on Scores)

**How it works:** Instead of choosing uniformly at random among all legal moves,
run a multi-PV search and select a move with probability proportional to:

```
P(move_i) = exp(score_i / T) / sum(exp(score_j / T))
```

where `T` is the temperature parameter:
- `T -> 0`: always pick the best move (greedy)
- `T -> infinity`: uniform random
- `T = 100`: moderate exploration, preferring good moves

This is related to Stockfish's `random_multi_pv` parameter, which runs a multi-PV
search and selects among the top moves:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `random_multi_pv` | (none) | Number of PVs for random move selection |
| `random_multi_pv_diff` | 30000 | Only consider moves within this score of best |
| `random_multi_pv_depth` | depth2 | Depth for the multi-PV search |

**Pros:**
- Random moves are "semi-reasonable" -- they deviate from optimal but don't
  usually blunder pieces
- Score-weighted selection produces more realistic positions
- The multi-PV depth can be low (depth 2-4) to keep cost manageable

**Cons:**
- More expensive than uniform random (requires multi-PV search)
- On small boards where depth 2 sees a lot, even "bad" multi-PV moves may not
  provide enough diversity
- Temperature tuning is another hyperparameter to manage

**AlphaZero's approach:** AlphaZero uses softmax sampling by visit count (from MCTS)
with temperature = 1 for the first 30 moves, then switches to greedy. Additionally,
Dirichlet noise (Dir(alpha)) is added to the root prior probabilities to ensure
exploration. The noise weight is typically 0.25, with alpha scaled inversely to the
number of legal moves.

### 2.4 Random Plies at Game Start Then Deterministic (Stockfish's Approach)

**How it works:** Play N random moves at the start of each game (the "opening
randomization phase"), then play deterministically for the remainder.

Stockfish's gensfen parameters for this:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `random_move_minply` | 1 | Earliest ply for random moves |
| `random_move_maxply` | 24 | Latest ply for random moves |
| `random_move_count` | 5 | Maximum number of random moves per game |
| `random_move_like_apery` | 0 | If 1, random king moves get a 50% chance of a reciprocal king move from opponent |

A common effective configuration for standard chess:
- 7-8 random moves in the first 24 plies
- Remainder of game played at fixed depth (depth 9)
- This creates ~C(24,8) * (avg_legal_moves)^8 potential opening paths -- enormous
  diversity

**Pros:**
- Clean separation: noisy opening phase + clean evaluation phase
- Deterministic play after the opening means recorded scores are high quality
- Avoids contaminating late-game positions with random noise
- Well-validated by the Stockfish community

**Cons:**
- Games from the same random opening will follow the same path (deterministic
  from the same position with the same engine)
- On small boards, 24 plies of random moves can end the game; the count and
  ply window must be scaled down

**Recommended adaptation for 5x5 boards:**

| Parameter | Standard chess | 5x5 adaptation |
|-----------|---------------|----------------|
| `random_move_minply` | 1 | 1 |
| `random_move_maxply` | 24 | 8-10 |
| `random_move_count` | 5 | 2-4 |

### 2.5 Opening Book Randomization

**How it works:** Instead of random moves, start games from positions taken from a
curated opening book (EPD/FEN file). Each game begins from a different book position.

Stockfish's `gensfen` supports this via the `book` parameter, which accepts an EPD
file. The widely-used `noob_3moves.epd` book contains positions after 3 moves of
play, providing diversity without the quality problems of random moves.

[Fairy-Stockfish's bookgen tool](https://github.com/fairy-stockfish/bookgen) can
automatically generate opening books for chess variants using perft enumeration and
multi-PV filtering.

**For small-board games**, the total number of positions reachable after N plies is
much smaller than in standard chess, making exhaustive or near-exhaustive book
generation feasible:

| Game | Board | Branching factor | Positions after 4 plies |
|------|-------|-----------------|------------------------|
| Standard chess | 8x8 | ~35 | ~1.5 million |
| MiniChess | 6x5 | ~15-20 | ~40,000-160,000 |
| MiniShogi | 5x5 | ~20-30 | ~160,000-810,000 |

**Practical approach:**
1. Run perft to enumerate all positions at depth 3-4 from the start
2. Filter to balanced positions (|eval| < 200-300 cp at shallow depth)
3. Sample from this filtered set as starting positions for self-play
4. This gives guaranteed diversity with no nonsensical positions

**Hybrid:** Use a book for the first 3-4 plies, then add 1-2 random moves from
multi-PV, then play deterministically. This is likely the best approach for small
boards.

---

## 3. Score Recording

Each training position needs a target value. There are three main options for what
score to record, and they can be combined.

### 3.1 Raw Static Eval

Record the output of the evaluation function (handcrafted or NNUE) without search.

- **Pros:** Fastest to generate; no search needed
- **Cons:** Static eval is noisy and misses tactics; training on static eval
  just teaches the network to replicate the current eval, which does not improve
  playing strength

**Verdict:** Not recommended as the sole target. Useful only for bootstrapping a
very first NNUE from a handcrafted eval.

### 3.2 Search Score (Current Approach)

Record the score from an alpha-beta search at fixed depth or fixed nodes. This is
what our `datagen.cpp` does:

```cpp
SearchContext score_ctx;
search_score = PVS::search(game, cfg.depth, score_ctx).score;
```

- **Pros:** Incorporates tactical awareness; at depth 6-9, catches most
  short-range tactics
- **Cons:** Search score can be unstable near horizon effects; deeper search is
  more expensive

**This is the standard approach used by Stockfish and most engines.**

### 3.3 Q-Value (Quiescence Search Score)

Instead of recording the raw search score, record the score after quiescence search
from the stored position. This is what "ensure_quiet" achieves in Stockfish's gensfen:
only emit positions that are at quiescence search leaf nodes, where the static eval
and qsearch score agree.

- **Pros:** Filters out horizon effects; positions with unstable evaluations are
  excluded
- **Cons:** Loses some training positions; bias toward quiet positions

### 3.4 Combining Score and Game Result

The most effective approach, used by Stockfish's nnue-pytorch trainer, combines the
search score with the game result using a lambda parameter:

```
loss = lambda * loss_eval + (1 - lambda) * loss_result
```

Where:
- `loss_eval`: cross-entropy between the model's WDL prediction and the target
  score (converted to WDL via sigmoid)
- `loss_result`: cross-entropy between the model's WDL prediction and the actual
  game result (1.0 for win, 0.5 for draw, 0.0 for loss)

| Lambda | Meaning |
|--------|---------|
| 1.0 | Train purely on search score |
| 0.0 | Train purely on game result |
| 0.75 | 75% score, 25% result (common starting point) |

**Our datagen already records both** -- the search score (`rec.score`) and the
game result (`rec.result`). The lambda mixing happens at training time, not during
data generation.

**Recommendation:** Record both. Start training with lambda=1.0 (pure score), then
experiment with lambda=0.75 to incorporate game outcome signal. The game result
provides a "ground truth" anchor that prevents the network from merely memorizing
the search function's biases.

---

## 4. Position Filtering

Not all positions from self-play are equally useful for training. Filtering out
problematic positions improves network quality significantly.

### 4.1 Tactical / Non-Quiet Positions

**Problem:** Positions where the best move is a capture, or where the side to move
is in check, have evaluations that are dominated by short-range tactics. The NNUE
network struggles to learn these because the evaluation depends on reading ahead,
not on pattern recognition.

**Stockfish's "smart fen skipping"** filters out:
- Positions where the best move is a capture
- Positions where the side to move is in check

This is enabled by default in nnue-pytorch and controlled by the
`--no-smart-fen-skipping` flag.

**The "Study of the Proper NNUE Dataset" (Tan & Watkinson Medina, 2024)** proposes
stricter filtering:
- Reject if the position contains check against either king
- Reject if |static_eval - qsearch_score| > 60 centipawns
- Reject if |static_eval - negamax_score| > 70 centipawns

### 4.2 Extreme Evaluations

Positions with very high or very low evaluations (e.g., |score| > 3000 cp) are
effectively decided. The network gains little from learning to distinguish between
"winning by 3000 cp" and "winning by 5000 cp." Stockfish uses `eval_limit = 3000`
to discard these.

**For small-board games** where games are shorter and material swings are sharper,
consider a lower threshold: `eval_limit = 2000-2500`.

### 4.3 Early-Game / Late-Game Filtering

Stockfish's `write_minply = 16` skips the first 16 plies (8 full moves). This
avoids recording opening positions that are identical across many games.

**For 5x5 boards**, where games are 30-60 plies total, `write_minply` should be
much lower: 4-6 plies at most, or even 0 if using opening book randomization.

### 4.4 Positions After Random Moves

When a random (jitter) move is played, the resulting position may be unrealistic.
Some engines skip recording for 1-2 plies after a random move to let the search
"recover" to a natural position.

### 4.5 Recommended Filtering Pipeline

```
Position generated
  |
  +-- Is side to move in check? --> DISCARD
  |
  +-- Is best move a capture? --> DISCARD
  |
  +-- |eval| > eval_limit? --> DISCARD (and adjudicate game)
  |
  +-- ply < write_minply? --> DISCARD
  |
  +-- Random move played this ply? --> DISCARD (record score but not position)
  |
  +-- KEEP
```

---

## 5. Data Diversity

### 5.1 The Self-Play Echo Chamber

The fundamental problem with self-play data generation: a strong engine plays
similar openings, reaches similar positions, and generates training data clustered
in a narrow region of the position space. Training on this data makes the engine
even more confident in those positions, reinforcing the cycle.

Symptoms of the echo chamber:
- The engine evaluates well in positions it has seen but poorly in novel positions
- Performance against other engines stagnates despite more training
- Score distributions are heavily concentrated near 0 (many draws in quiet openings)

### 5.2 Strategies to Break the Echo Chamber

**A) Aggressive random move injection** (see Section 2)
The most direct approach. More random moves = more position diversity, at the cost
of position quality.

**B) Multiple starting positions**
Use an opening book with thousands of distinct starting positions. For variants,
[fairy-stockfish/bookgen](https://github.com/fairy-stockfish/bookgen) can generate
these automatically. An EPD opening book with at least 5000 positions is recommended
for standard chess; for 5x5 games, 1000-3000 positions after 3-4 plies would provide
comparable coverage.

**C) Multi-engine data**
Train on data generated by multiple different engines or different versions of the
same engine. Each engine has different biases, so the combined dataset has better
coverage. Stockfish's best nets use a mix of Stockfish self-play + Lc0-derived data.

**D) Iterative refinement (generation loops)**
1. Train NNUE v1 on handcrafted-eval self-play data
2. Generate new data using NNUE v1 as the evaluation
3. Train NNUE v2 on the new data (or a mix of old + new)
4. Repeat

Each generation explores slightly different positions because the evaluation function
has changed. This is analogous to policy iteration in reinforcement learning.

**E) Score distribution targeting**
The "Study of the Proper NNUE Dataset" recommends specific distribution targets:
- 50% of positions should have positive eval (from STM perspective)
- 50% of positions should have negative eval
- At least 50% of positions should have |eval| between 0 and 100 cp
- At least 40% of positions should feature material imbalance

If the natural distribution from self-play is too concentrated (e.g., 80% of evals
between -50 and +50), under-sample the common region and over-sample the tails.

**F) DFRC / random starting positions**
For standard chess, Double Fischer Random Chess (DFRC) starting positions provide
enormous opening diversity. For small board games, this is equivalent to randomly
placing pieces on the back ranks (while respecting game rules).

### 5.3 Measuring Diversity

Track these metrics across your dataset:
- **Score distribution**: histogram of evaluations (should be roughly symmetric,
  not a spike at 0)
- **Material count distribution**: how many positions have each material combination
- **Game length distribution**: avoid datasets dominated by very short or very long
  games
- **Unique positions**: the ratio of unique positions to total positions should be
  high (>95%)

---

## 6. Game Result Recording and WDL Signal Quality

### 6.1 What to Record

Each position needs:
1. **Score**: search evaluation from the side-to-move perspective (centipawns)
2. **Result**: final game outcome from the side-to-move perspective
   - +1 = side to move eventually won
   - 0 = game was drawn
   - -1 = side to move eventually lost

Our `datagen.cpp` already records both correctly, backfilling the result after each
game completes.

### 6.2 WDL Signal Quality Concerns

**Draw adjudication:** In standard chess, many self-play games are drawn. If 60-70%
of games are draws, the result signal is weak (most positions get result=0 regardless
of their evaluation). Stockfish detects and adjudicates draws early to save compute.

**For small-board games**, draws may be less common (especially in MiniChess where
checkmate is easier to force), making the result signal stronger.

**Win adjudication:** When one side has a decisive advantage (|eval| > eval_limit
for several consecutive moves), adjudicating the game as won avoids wasting compute
on trivially decided games. This also prevents endgame play from polluting the
dataset with positions that are "technically interesting" but practically settled.

**Noisy results from random moves:** If a random move blunders a piece and the
game is then lost, the result=-1 is "correct" but the signal is noisy -- the loss
was caused by a random move, not by the position being inherently bad. This is
another argument for concentrating random moves early and playing deterministically
later.

### 6.3 The Sigmoid Mapping

Stockfish converts centipawn scores to WDL probabilities using:

```
WDL = sigmoid(cp_score / scaling_factor)
```

where `scaling_factor` is approximately 400 for standard chess. For small-board
games where scores are more volatile and the range of meaningful evaluations is
different, this scaling factor will need calibration. A good approach:

1. Generate a dataset with game results
2. Fit a sigmoid to predict win probability from search score
3. Use the fitted scaling factor in training

---

## 7. Multi-Depth Data Mixing

### 7.1 Rationale

Not all positions need the same evaluation depth. Mixing positions evaluated at
different depths provides several benefits:

- **Shallow-depth positions** (depth 4-6) are cheap to generate and provide broad
  coverage of the position space with moderate-quality labels
- **Deep-depth positions** (depth 8-12) are expensive but provide high-quality labels
  for the most important positions
- The network learns to interpolate between the "gist" from shallow data and the
  "precision" from deep data

### 7.2 Curriculum Learning

A principled approach is **curriculum learning**: start training on easy/cheap data,
then progressively introduce harder/more accurate data.

For NNUE training:
1. **Phase 1:** Train on a large dataset of depth-4 positions (cheap, broad coverage)
2. **Phase 2:** Fine-tune on a smaller dataset of depth-8 positions (expensive,
   precise)
3. **Phase 3 (optional):** Further fine-tune on depth-12 or node-limited positions

This is roughly what Stockfish does when it first trains on self-play data (moderate
depth) and then retrains on Lc0-rescored data (higher quality evaluations).

### 7.3 Practical Mixing

An alternative to sequential curriculum is to **mix depths within the same dataset**:

| Depth | Proportion | Purpose |
|-------|-----------|---------|
| 4 | 60% | Broad coverage, cheap |
| 6 | 25% | Balanced quality/cost |
| 8 | 10% | High-quality anchors |
| 10+ | 5% | Critical positions (from book, endgame tablebases) |

**For 5x5 boards**, depth 6 already sees proportionally deep into the game tree
(see Section 9), so multi-depth mixing is less critical. A mix of depth 4 (70%)
and depth 8 (30%) would be reasonable.

---

## 8. How Many Games / Positions Are Needed

### 8.1 Community Guidelines

The chess engine community provides these rough guidelines:

| Network size | Minimum positions | Recommended | Notes |
|-------------|------------------|-------------|-------|
| Small (32-64 hidden) | 10M | 50-100M | For initial bootstrap |
| Medium (128-256 hidden) | 100M | 500M-1B | Sweet spot for most engines |
| Large (512+ hidden) | 500M+ | 1B-16B | Stockfish-tier networks |

**Rule of thumb:** use at least 10x the number of network parameters in training
positions. For a network with 10M parameters, that means 100M+ positions.

**Practical minimum for a first attempt:** 100M positions. Developers have reported
that 15M positions was insufficient, while 100M gave reasonable results.

### 8.2 Scaling for Small-Board Games

Small-board games have fundamentally different scaling requirements:

**Smaller state space:** A 5x5 board with 10 pieces has vastly fewer possible
positions than 8x8 chess with 32 pieces. The NNUE network is proportionally smaller,
and less data is needed to cover the position space.

**Smaller networks:** For a 5x5 board, the input layer is much smaller
(e.g., 5x5x(piece_types) vs. 8x8x(piece_types)), resulting in a network with
far fewer parameters. A 32-hidden-unit network for 5x5 might have ~50K parameters
vs. ~10M for Stockfish's architecture.

**Rough scaling:**

| Game | Board | Positions needed (estimate) |
|------|-------|---------------------------|
| Standard chess | 8x8 | 1B-16B |
| MiniChess (6x5) | 30 squares | 10M-100M |
| MiniShogi (5x5) | 25 squares | 10M-100M |
| Gomoku (9x9) | 81 squares | 50M-500M |

### 8.3 Positions Per Game

In self-play, each game generates some number of usable positions (after filtering):

| Game | Avg game length | Usable positions/game (after filtering) |
|------|----------------|----------------------------------------|
| Standard chess | 80-120 plies | 40-80 |
| MiniChess | 40-80 plies | 20-40 |
| MiniShogi | 50-100 plies | 25-50 |

To generate 50M positions for MiniChess at ~30 usable positions per game, you need
roughly **1.7M games**. At depth 6, a game of MiniChess takes ~0.5-2 seconds on a
modern CPU, so this is feasible in hours with parallelism (our `gen_data.sh` already
supports 64 parallel workers).

---

## 9. Practical Tips for Small-Board Games (5x5 to 7x7)

### 9.1 Depth Sees Proportionally Deeper

On a 5x5 board with ~15-20 legal moves per position (vs. ~35 for standard chess),
depth 6 searches proportionally deeper into the game. The effective "game coverage"
of a fixed-depth search scales roughly as:

```
coverage = depth / average_game_length
```

| Game | Avg game length | Depth 6 coverage | Depth 9 coverage |
|------|----------------|-------------------|-------------------|
| Standard chess | 80 plies | 7.5% | 11.3% |
| MiniChess | 50 plies | 12.0% | 18.0% |
| MiniShogi | 60 plies | 10.0% | 15.0% |

Additionally, the lower branching factor means alpha-beta pruning is more effective,
so the search tree at depth 6 on 5x5 is far more thoroughly explored than depth 6
on 8x8.

**Implication:** Depth 6 on a 5x5 board produces evaluation quality roughly
comparable to depth 9-10 on an 8x8 board. You can use shallower depths and still
get high-quality labels.

### 9.2 Exhaustive Opening Books

With a branching factor of ~15-20, all positions up to depth 4 fit in memory
(~50K-160K positions). This makes exhaustive opening book generation practical:

```bash
# Pseudo-approach for generating opening books
# 1. Run perft to depth 3-4
# 2. Filter positions by eval balance
# 3. Use as starting positions for self-play
```

### 9.3 Shorter Games Mean Cheaper Data

A typical MiniChess game at depth 6 completes in 0.5-2 seconds, vs. 5-20 seconds
for standard chess at depth 9. This means you can generate proportionally more data
per hour. Use this budget to:
- Generate more games (for diversity) rather than searching deeper
- Run multiple generation passes with different random seeds
- Experiment with different epsilon/random move configurations

### 9.4 Beware of Overfitting to Drawn Positions

On small boards, games may converge to known drawn patterns more quickly. If your
dataset is dominated by draws, the NNUE will learn to output ~0.0 for many positions,
losing the ability to distinguish between "slightly better" and "slightly worse."

**Mitigations:**
- Aggressive opening randomization to avoid drawn openings
- Win/loss adjudication at lower thresholds (|eval| > 500 for 5 consecutive moves)
- Under-sample drawn games relative to decisive games (e.g., keep 50% of drawn
  games, 100% of won/lost games)

### 9.5 The MiniShogi Hand Complication

MiniShogi has piece drops from the hand, which dramatically increases the branching
factor and makes the game tree wider than its small board might suggest. This means:
- Depth 6 is less "deep" than for MiniChess in practice
- More training data is needed to cover drop positions
- Position filtering should NOT exclude drop moves as "captures"

### 9.6 Recommended Configuration for First Data Generation

For MiniChess (6x5) or MiniShogi (5x5), a reasonable starting configuration:

```bash
# Generate 50M+ positions
./build/datagen \
  -n 2000000 \       # 2M games
  -d 6 \             # depth 6 (effective depth 9-10 equivalent)
  -e 0.10 \          # 10% epsilon (reduced from 15%)
  -o data/train.bin \
  -s 42

# Or with the parallel script:
bash scripts/gen_data.sh -g minichess -n 2000000 -w 64 -d 6 -e 0.10
```

**Future improvements** (in rough priority order):
1. Implement ply-dependent epsilon (high in opening, zero in endgame)
2. Add position filtering (skip checks, skip captures-as-best-move)
3. Generate an opening book from perft and use it for starting positions
4. Implement multi-PV random move selection (softmax on top-K moves)
5. Add eval_limit adjudication to terminate decided games early
6. Experiment with multi-depth mixing (70% depth 4 + 30% depth 8)

---

## References and Sources

- [Stockfish gensfen documentation (nodchip fork)](https://github.com/nodchip/Stockfish/blob/master/docs/gensfen.md)
- [Stockfish nnue-pytorch training datasets](https://github.com/official-stockfish/nnue-pytorch/wiki/Training-datasets)
- [Stockfish nnue-pytorch NNUE documentation](https://official-stockfish.github.io/docs/nnue-pytorch-wiki/docs/nnue.html)
- [Basic training procedure (nnue-pytorch)](https://github.com/official-stockfish/nnue-pytorch/wiki/Basic-training-procedure-(train.py))
- [Study of the Proper NNUE Dataset (Tan & Watkinson Medina, 2024)](https://arxiv.org/abs/2412.17948)
- [Fairy-Stockfish NNUE wiki](https://github.com/fairy-stockfish/Fairy-Stockfish/wiki/NNUE)
- [Fairy-Stockfish variant-nnue-tools](https://github.com/fairy-stockfish/variant-nnue-tools)
- [Fairy-Stockfish bookgen (opening book generator)](https://github.com/fairy-stockfish/bookgen)
- [NNUE - Chessprogramming wiki](https://www.chessprogramming.org/NNUE)
- [Stockfish NNUE - Chessprogramming wiki](https://www.chessprogramming.org/Stockfish_NNUE)
- [Best practices for NNUE training data generation (TalkChess)](https://talkchess.com/viewtopic.php?t=83944)
- [NNUE training set generation (TalkChess)](https://talkchess.com/viewtopic.php?t=77606)
- [AlphaZero - Chessprogramming wiki](https://www.chessprogramming.org/AlphaZero)
- [Stockfish NNUE training data (robotmoon.com)](https://robotmoon.com/nnue-training-data/)
- [About NNUE - Fairy-Stockfish](https://fairy-stockfish.github.io/about-nnue/)
