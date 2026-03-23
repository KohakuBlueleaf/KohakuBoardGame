# NNUE Training Quick Reference

## 1. Recommended Parameters

### Datagen Parameters

| Parameter | MiniChess (6x5) | MiniShogi (5x5) |
|-----------|-----------------|-----------------|
| Games | 500K-2M | 500K-2M |
| Target positions | 15M-60M | 20M-100M |
| Depth | 6 (equiv. depth 9-10 on 8x8) | 6 (equiv. depth 8-9 on 8x8) |
| Epsilon | 0.10 uniform; ply-dependent preferred | 0.10 uniform; ply-dependent preferred |
| Epsilon formula | `e_max * max(0, 1 - ply/decay_ply)` | same formula |
| e_max / decay_ply | 0.30 / 25 | 0.25 / 36 |
| Write min ply | 4 | 4 |
| Eval limit | 2500 cp (adjudicate) | 2500 cp (adjudicate) |
| Score type | **Search score (PVS)** -- never raw eval | same |
| Filter | Skip checks, skip capture-best-move | Same, but do NOT filter drops |
| HalfKP input size | ~7,500 | ~12,500 + hand features |
| Workers | 16-64 | 16-64 |

### Training Parameters

| Parameter | v1 (seed) | v2+ (fine-tune) | v3 (arch upgrade) |
|-----------|-----------|-----------------|-------------------|
| Architecture | Feat -> 32x2 -> 1 | Same as v1 | Feat -> 64x2 -> 16 -> 1 |
| Init weights | From scratch | Resume from prev | From scratch |
| Optimizer | Adam | Adam | Adam |
| Learning rate | 1e-3 | 5e-4 | 1e-3 |
| LR schedule | Cosine to 1%, 1000-step warmup | Cosine, warmup | Cosine, warmup |
| Batch size | 8192 | 8192 | 8192 |
| Epochs | 400 | 200 | 400 |
| Lambda (wdl_weight) | 1.0 (pure score) | 0.85 | 0.85 |
| EMA decay | 0.999 | 0.999 | 0.999 |
| SCORE_SCALE | 400 | 400 | 400 |
| Val size | 100K fixed | 100K fixed | 100K fixed |
| Val interval | 2000 steps | 2000 steps | 2000 steps |
| Loss exponent | 2.0 | 2.0 | 2.0 (try 2.6 later) |

---

## 2. Iteration Cheat Sheet

| | v1 (seed) | v2 (refine) | v3 (arch upgrade) | v4-v6 (deep) |
|---|-----------|-------------|-------------------|--------------|
| **Eval for datagen** | Handcrafted (v0) | NNUE v1 | Best available | Previous best |
| **Positions** | 20M | 30-50M | 50M | 50-80M |
| **Depth** | 6 | 6 | 6-8 | 8 |
| **e_max** | 0.30 | 0.25 | 0.20 | 0.15 |
| **Data mixing** | 100% new | 100% new | 70% new + 30% old | 70/30 |
| **Init** | Scratch | Fine-tune v1 | Scratch (new arch) | Fine-tune prev |
| **LR** | 1e-3 | 5e-4 | 1e-3 | 5e-4 -> 1e-4 |
| **Lambda** | 1.0 | 1.0 -> 0.85 | 0.85 | 0.80 -> 0.70 |
| **Epochs** | 400 | 200 | 400 | 200 -> 100 |
| **Expected Elo** | +100-200 | +20-50 | +30-80 | +5-30 |
| **Cumulative Elo** | +100-200 | +130-240 | +180-300 | +200-360 |

**Stop rule:** Two consecutive iterations gaining < 5 Elo = plateau. Upgrade architecture or search depth.

---

## 3. Loss Function Reference

```
SCORE_SCALE = 400.0

pred_sig   = sigmoid(predicted / SCORE_SCALE)
score_sig  = sigmoid(search_score / SCORE_SCALE)
wdl        = (game_result + 1) / 2            # maps {-1, 0, +1} -> {0, 0.5, 1}

target     = (1 - lambda) * score_sig + lambda * wdl
loss       = mean((pred_sig - target) ^ 2)
```

| Variable | Definition |
|----------|-----------|
| `predicted` | Network output (centipawns, STM perspective) |
| `search_score` | PVS result at depth D (centipawns, STM perspective) |
| `game_result` | +1 STM wins, 0 draw, -1 STM loses |
| `SCORE_SCALE` | Sigmoid steepness; 100cp pawn -> sigmoid(0.25) = 0.562 win prob |
| `lambda` | 0.0 = pure score, 1.0 = pure game result, 0.3-0.5 typical |

**EMA update:** `theta_ema = 0.999 * theta_ema + 0.001 * theta_current` (always export EMA weights)

---

## 4. Architecture Reference

```
HalfKP Features (sparse)
  -> EmbeddingBag(feature_dim, accum_size)     # most params here
  -> + bias -> SCReLU                          # SCReLU = clamp(x,0,1)^2
  -> [STM accum | NSTM accum]                  # concat: 2 * accum_size
  -> Linear(2*accum, L1) -> SCReLU
  -> Linear(L1, L2) -> SCReLU                  # optional second hidden
  -> Linear(L2, 1)                             # scalar eval
```

| Arch tier | Layout | ~Params (HalfKP 6x5) | Use at |
|-----------|--------|----------------------|--------|
| Small | Feat -> 32x2 -> 1 | ~50K | v1-v2 |
| Medium | Feat -> 64x2 -> 16 -> 1 | ~200K | v3-v4 |
| Large | Feat -> 128x2 -> 32 -> 1 | ~1M | v5+ |

**Feature space:** `king_squares * piece_squares * piece_types * colors`
- MiniChess: 30 * 30 * 5 * 2 = ~9,000 (excl. kings from pieces)
- MiniShogi: 25 * 25 * 10 * 2 = ~12,500 + hand features

**Quantization constants:** QA=255 (FT, int16), QA_HIDDEN=127 (activations, uint8), QB=64 (dense, int8), QAH_QB=8128 (bias, int32)

---

## 5. Common Commands

```bash
# --- BUILD ---
make minichess-datagen

# --- DATAGEN (v1, 20M positions) ---
bash scripts/gen_data.sh -g minichess -n 670000 -w 64 -d 6 -e 0.10 -o data_v1

# --- DATAGEN (v2+, with NNUE model) ---
bash scripts/gen_data.sh -g minichess -n 1000000 -w 64 -d 6 -e 0.10 \
  -m models/nnue_v1.bin -o data_v2

# --- TRAIN (v1 from scratch) ---
python -m nnue-train \
  --game minichess --data "data_v1/train_*.bin" --features halfkp \
  --accum-size 128 --batch-size 8192 --lr 1e-3 --wdl-weight 0.5 \
  --ema-decay 0.999 --warmup-steps 1000 --epochs 100 \
  --val-size 100000 --val-every-n-steps 2000 --num-workers 2 \
  --device auto --output models/nnue_v1.pt --export models/nnue_v1.bin

# --- TRAIN (v2 fine-tune) ---
python -m nnue-train \
  --data "data_v2/train_*.bin" --features halfkp \
  --lr 5e-4 --epochs 50 \
  --output models/nnue_v2.pt --export models/nnue_v2.bin

# --- EVALUATE (tournament) ---
./build/minichess-selfplay -m models/nnue_v1.bin -n 200

# --- MINISHOGI VARIANT ---
bash scripts/gen_data.sh -g minishogi -n 50000 -w 16 -d 6 -e 0.10 -o data_shogi
python -m nnue-train --game minishogi --data "data_shogi/train_*.bin" \
  --features halfkp --accum-size 128 --epochs 100 \
  --output models/shogi_v1.pt --export models/shogi_v1.bin
```

---

## 6. Troubleshooting Quick Fixes

| Problem | One-Line Fix |
|---------|-------------|
| Loss decreases but network plays poorly | Verify `SCORE_SCALE=400` matches engine's centipawn scale (pawn=100 -> sigmoid(0.25)=0.562) |
| Loss is noisy / slow to converge | Enable position filtering: skip in-check positions and capture-best-move positions |
| Network strong as white, weak as black | Perspective flip bug -- verify mirroring matches between Python training and C++ inference |
| Good float eval, bad after quantization | Add weight clipping callback; verify QA=255/QB=64 match between `export.py` and `compute_quant.hpp` |
| NaN / inf loss | Reduce LR by 10x, add `clip_grad_norm_(params, 1.0)`, increase warmup to 2000 steps |
