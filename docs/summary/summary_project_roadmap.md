# UBGI Project Roadmap — Next Steps

Synthesized from the training pipeline, evolution strategy, and variant recommendation documents. This is a planning document with concrete actions, commands, and parameter values.

---

## 1. Immediate Actions (This Week)

### 1a. Datagen Bug — FIXED

The datagen was recording `evaluate()` (raw static eval) instead of the PVS search score. This broke the entire self-improvement loop: the NNUE learned to copy the handcrafted eval rather than internalize depth-6 search knowledge. All 67M existing positions have wrong eval labels. The fix (commit `f662186`) now records `-search_score` correctly.

### 1b. Regenerate Data with Search Scores

Discard all previous training data. Generate fresh positions with the fixed datagen using the handcrafted eval as the starting point.

```bash
make minichess-datagen

bash scripts/gen_data.sh \
  -g minichess \
  -n 700000 \
  -w 64 \
  -d 6 \
  -e 0.10 \
  -o data_v1_fixed
```

Target: **20M positions** (~700K games x ~30 usable positions/game). With 64 workers this takes roughly 15-30 minutes wall time.

### 1c. Retrain v1 from Scratch on Correct Data

Do NOT fine-tune the old v1/v2 weights — they were optimized for wrong targets. Train from scratch.

```bash
python -m nnue-train \
  --game minichess \
  --data "data_v1_fixed/train_*.bin" \
  --features halfkp \
  --accum-size 128 \
  --batch-size 8192 \
  --lr 1e-3 \
  --wdl-weight 0.0 \
  --ema-decay 0.999 \
  --warmup-steps 1000 \
  --epochs 400 \
  --val-size 100000 \
  --val-every-n-steps 2000 \
  --num-workers 2 \
  --device auto \
  --output models/nnue_v1.pt \
  --export models/nnue_v1.bin
```

Key settings: `--wdl-weight 0.0` (pure search score for seed network), `--lr 1e-3`, 400 epochs.

### 1d. Validate v1

Run 2000+ games: NNUE v1 vs handcrafted eval at fixed depth. Expected gain: **+100-200 Elo** (a much larger jump than the bugged v1/v2 ever showed).

```bash
./build/minichess-selfplay -m models/nnue_v1.bin -n 2000
```

---

## 2. Short-Term Goals (Next 2 Weeks)

### 2a. Iterative Self-Improvement: v1 -> v2 -> v3

| Step | Datagen Eval | Positions | Depth | LR | Epochs | Lambda (wdl_weight) | Init Weights | Expected Gain |
|------|-------------|-----------|-------|----|--------|---------------------|-------------|---------------|
| v1 | Handcrafted | 20M | 6 | 1e-3 | 400 | 0.0 | Scratch | +100-200 Elo |
| v2 | NNUE v1 | 30-50M | 6 | 5e-4 | 200 | 0.15 | Resume v1 | +20-50 Elo |
| v3 | NNUE v2 | 50M | 6-8 | 1e-3 | 400 | 0.15 | Scratch (new arch) | +30-80 Elo |

v3 upgrades architecture from `128x2 -> 1` to `64x2 -> 16 -> 1` (double width, add second hidden layer). Train from scratch since weights are incompatible.

Decision rule after each iteration:
- Gain >= 30 Elo: continue same architecture, fine-tune
- Gain 10-29 Elo: try one more iteration, then upgrade architecture
- Gain < 10 Elo: upgrade architecture immediately

### 2b. Implement Ply-Dependent Random Moves

Replace the uniform `epsilon=0.10` with a linear decay schedule in `src/datagen.cpp`:

```
epsilon(ply) = epsilon_max * max(0.0, 1.0 - ply / decay_ply)
```

**MiniChess:** `epsilon_max=0.30`, `decay_ply=25`
- Ply 0: 0.30, Ply 10: 0.18, Ply 20: 0.06, Ply 25+: 0.00

**MiniShogi:** `epsilon_max=0.25`, `decay_ply=36`

Reduce `epsilon_max` across iterations: 0.30 (v1) -> 0.25 (v2) -> 0.20 (v3) -> 0.15 (v4+).

### 2c. Add --resume Flag for Fine-Tuning

Enable loading previous weights for v2+ iterations. Fine-tuning protocol:
- LR: 1/2 of from-scratch rate (e.g., 5e-4 instead of 1e-3)
- Epochs: 1/2 to 2/3 of from-scratch count
- Lambda: can be lower (0.75-0.85) since the network already understands basic eval

### 2d. MiniShogi NNUE (Now Viable)

With the datagen fix, MiniShogi NNUE training is worth pursuing for the first time.

```bash
bash scripts/gen_data.sh -g minishogi -n 700000 -w 64 -d 6 -e 0.10 -o data_shogi_v1

python -m nnue-train \
  --game minishogi \
  --data "data_shogi_v1/train_*.bin" \
  --features halfkp \
  --accum-size 128 \
  --epochs 100 \
  --output models/shogi_v1.pt \
  --export models/shogi_v1.bin
```

MiniShogi needs 20-100M positions due to more piece types (11 vs 6) and hand features.

---

## 3. Medium-Term Goals (Next Month)

### 3a. New Variant: Judkins Shogi (6x6)

**Recommended as the next variant.** Scored 9.0/10 across all evaluation axes.

Why Judkins Shogi:
- **Minimal code:** ~200-400 new lines. Only new piece is shogi Knight. 85-90% of MiniShogi code reuses directly.
- **Meaningful NNUE payoff:** 31K HalfKP features, ~4M params, game tree complexity ~10^32 (firmly unsolved).
- **Exercises full pipeline:** Hand pieces, drops, promotion — validates infrastructure at scale.
- **Community tooling:** Supported by Fairy-Stockfish for reference comparison.

Implementation order:
1. Copy `src/games/minishogi/` -> `src/games/judkins/`, set 6x6, add Knight (~1-2 days)
2. Add `"judkins"` entry to `game_config.py`
3. Generate 30M positions with handcrafted eval (~3 hours)
4. Train NNUE (128 accum, HalfKP+hand) (~2 hours)
5. Iterate to v2 with 50M positions (~6 hours total)

Runner-up: **Tori Shogi (7x7)** — highest ceiling and NNUE value-add, but 3-4x more implementation work (~800-1200 lines). Best pursued after Judkins is stable.

### 3b. Architecture Experiments

Progression to follow as iterations plateau:
```
32x2 -> 1         (if starting small)
128x2 -> 32 -> 32 -> 1   (current default)
64x2 -> 16 -> 1   (v3 upgrade)
128x2 -> 32 -> 1  (v5+)
```

Each width doubling needs ~4x more training data to saturate.

### 3c. Training Infrastructure Improvements

Priority order by expected impact:

1. **Position filtering in datagen** — skip positions where STM is in check or best move is a capture. Reduces training noise significantly.
2. **Opening book from perft** — enumerate all positions at depth 3-4 (~40K-160K for 6x5), filter to balanced positions (|eval| < 300cp), use as game starting points.
3. **Eval-limit adjudication** — when |eval| > 2500cp for 3 consecutive moves, adjudicate as won. Saves compute on decided games.
4. **Multi-depth data mixing** — 70% depth 4 (cheap, broad) + 30% depth 8 (expensive, precise).
5. **Softmax multi-PV move selection** — replace uniform random with score-weighted selection for more realistic jitter.

---

## 4. Key Learnings

### The Datagen Bug
- The datagen recorded `evaluate()` instead of the PVS search score returned by `PVS::search()`. The search ran at depth 6 but its result was thrown away.
- This collapsed the self-improvement loop into a copy operation. The NNUE learned to replicate the handcrafted eval, not to internalize search knowledge.
- The bug was subtle because training loss still decreased and networks still played — the game-result signal (WDL) and neural generalization provided marginal gains. EMA smoothing made everything look stable.

### Why Previous NNUE Iterations Did Not Improve
- v1 and v2 were trained on labels that were just the handcrafted eval's output. The score component of the loss was circular (teaching the network to predict what it could already compute).
- The iterative loop (v1 -> v2 -> ...) could not compound gains because regenerating data with NNUE v1 would just record NNUE v1's static eval — zero new information.
- Any gains observed were from game-result blending and the neural network's different generalization surface, not from distilling search knowledge.

### Best Practices Going Forward
- **Always verify the score source.** Print a few records and manually confirm they match depth-D search output, not `evaluate()`.
- **The score source is the single most important datagen decision** — more important than depth, epsilon, or filtering.
- **Train from scratch when data labels change fundamentally.** Old weights optimized for wrong targets interfere with learning from correct targets.
- **Use lambda=1.0 (wdl_weight=0.0) for the seed network.** Pure search-score signal while the network learns basic patterns. Blend in game results (wdl_weight=0.15-0.50) in later iterations.
- **Regenerate data when:** the eval improves 50+ Elo, architecture changes, labels were wrong, or you hit a plateau.
- **Ply-dependent randomization is strictly superior** to uniform epsilon on small boards. Endgame random moves create garbage positions and corrupt the game-result signal.
- **Stop iterating and change something structural** (architecture, features, search depth) when two consecutive iterations gain < 5 Elo.

---

## Timeline Summary

| Week | Milestone | Key Deliverable |
|------|-----------|----------------|
| 1 | Regenerate + retrain v1 | First correct NNUE, validated at +100-200 Elo |
| 2 | v2 iteration + ply-dependent epsilon | Self-improvement loop proven, +20-50 Elo more |
| 3 | v3 arch upgrade + MiniShogi v1 | Larger network, second game variant with NNUE |
| 4 | Judkins Shogi implementation | Third game variant, full pipeline validation |
| 5-6 | v4-v5 refinement + position filtering | Cumulative +200-350 Elo over handcrafted eval |
