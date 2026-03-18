#!/usr/bin/env python3
"""
train_nnue.py — Train a NNUE for MiniChess (6x5 board).

Supports two feature types:
  PS:     PieceSquare(360)  -> Accumulator -> SCReLU -> ...
  HalfKP: HalfKP(9000)     -> Accumulator -> SCReLU -> ...

Training target (following standard NNUE practice):
  target = (1 - wdl_weight) * sigmoid(score/scale) + wdl_weight * wdl_result
  loss   = MSE(sigmoid(predicted/scale), target)

Usage:
    python scripts/train_nnue.py --data "data/train_*.bin" --features halfkp --epochs 100
"""

import argparse
import glob
import os
import struct
import sys
import time
from typing import Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BOARD_H = 6
BOARD_W = 5
NUM_SQUARES = BOARD_H * BOARD_W  # 30
NUM_PIECE_TYPES = 6  # Pawn(1)..King(6), indexed 0..5
NUM_PT_NO_KING = 5  # Piece types excluding king
NUM_COLORS = 2  # own=0, opponent=1

# PS: color * piece_type * square = 2*6*30 = 360
PS_SIZE = NUM_COLORS * NUM_PIECE_TYPES * NUM_SQUARES  # 360

# HalfKP: king_sq * color * piece_type_no_king * square = 30*2*5*30 = 9000
NUM_PIECE_FEATURES = NUM_COLORS * NUM_PT_NO_KING * NUM_SQUARES  # 300
HALFKP_SIZE = NUM_SQUARES * NUM_PIECE_FEATURES  # 9000
MAX_ACTIVE = 20

HEADER_FMT = "<4sii"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

# Data format v1: board(60) + player(1) + score(2) = 63 bytes
RECORD_V1_FMT = "<60sbh"
RECORD_V1_SIZE = struct.calcsize(RECORD_V1_FMT)

# Data format v2: board(60) + player(1) + score(2) + result(1) + ply(2) = 66 bytes
RECORD_V2_FMT = "<60sbhbH"
RECORD_V2_SIZE = struct.calcsize(RECORD_V2_FMT)

SCORE_FILTER = 10000


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def read_bin_file(
    path: str,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Read a single .bin data file (supports v1 and v2 formats).

    Returns:
        boards:  (N, 2, 6, 5) int8
        players: (N,) int8
        scores:  (N,) int16
        results: (N,) int8  — game result from STM perspective (1=win, 0=draw, -1=loss)
        plies:   (N,) uint16 — ply count (0 for v1 data)
    """
    with open(path, "rb") as f:
        hdr_data = f.read(HEADER_SIZE)
        if len(hdr_data) < HEADER_SIZE:
            raise ValueError(f"File too small for header: {path}")

        magic, version, count = struct.unpack(HEADER_FMT, hdr_data)
        magic = magic.decode("ascii", errors="replace")
        if magic != "MCDT":
            raise ValueError(f"Bad magic '{magic}' in {path}")

        if version == 1:
            record_size = RECORD_V1_SIZE
            dt = np.dtype(
                [
                    ("board", np.int8, (60,)),
                    ("player", np.int8),
                    ("score", "<i2"),
                ]
            )
        elif version == 2:
            record_size = RECORD_V2_SIZE
            dt = np.dtype(
                [
                    ("board", np.int8, (60,)),
                    ("player", np.int8),
                    ("score", "<i2"),
                    ("result", np.int8),
                    ("ply", "<u2"),
                ]
            )
        else:
            raise ValueError(f"Unknown data version {version} in {path}")

        raw = f.read(record_size * count)

    if len(raw) < record_size * count:
        actual = len(raw) // record_size
        print(f"Warning: {path} truncated, expected {count} records, got {actual}")
        count = actual

    records = np.frombuffer(raw[: count * record_size], dtype=dt)
    boards = records["board"].reshape(-1, 2, BOARD_H, BOARD_W).copy()
    players = records["player"].copy()
    scores = records["score"].copy()

    if version >= 2:
        results = records["result"].copy()
        plies = records["ply"].copy()
    else:
        results = np.zeros(count, dtype=np.int8)
        plies = np.zeros(count, dtype=np.uint16)

    return boards, players, scores, results, plies


def load_all_data(
    pattern: str,
    min_ply: int = 0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load and concatenate data from all files matching *pattern*."""
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"Error: no files match '{pattern}'")
        sys.exit(1)

    all_boards, all_players, all_scores, all_results, all_plies = [], [], [], [], []
    for fp in files:
        print(f"  Loading {fp} ...", end="", flush=True)
        b, p, s, r, ply = read_bin_file(fp)
        print(f" {len(b)} records (v{'2' if r.any() else '1'})")
        all_boards.append(b)
        all_players.append(p)
        all_scores.append(s)
        all_results.append(r)
        all_plies.append(ply)

    boards = np.concatenate(all_boards)
    players = np.concatenate(all_players)
    scores = np.concatenate(all_scores)
    results = np.concatenate(all_results)
    plies = np.concatenate(all_plies)

    total = len(scores)

    # Filter by score magnitude
    mask = np.abs(scores.astype(np.int32)) <= SCORE_FILTER
    # Filter by minimum ply
    if min_ply > 0:
        mask &= plies >= min_ply

    boards = boards[mask]
    players = players[mask]
    scores = scores[mask]
    results = results[mask]
    plies = plies[mask]
    filtered = total - len(scores)
    print(f"  Total: {total} records, filtered {filtered}, kept {len(scores)}")

    return boards, players, scores, results, plies


# ---------------------------------------------------------------------------
# PS Feature extraction (dense, precomputed)
# ---------------------------------------------------------------------------
def board_to_ps_features(
    boards: np.ndarray,
    players: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert board arrays to PieceSquare dense feature tensors.

    Returns:
        white_feats: (N, 360) float32
        black_feats: (N, 360) float32
        stm:         (N,) bool
    """
    N = len(boards)
    white_feats = np.zeros((N, PS_SIZE), dtype=np.float32)
    black_feats = np.zeros((N, PS_SIZE), dtype=np.float32)

    for color_plane in range(2):
        for r in range(BOARD_H):
            for c in range(BOARD_W):
                piece_types = boards[:, color_plane, r, c]
                has_piece = piece_types > 0
                if not np.any(has_piece):
                    continue
                pt = piece_types[has_piece].astype(np.int32) - 1
                sq = r * BOARD_W + c

                w_color = color_plane
                w_idx = w_color * NUM_PIECE_TYPES * NUM_SQUARES + pt * NUM_SQUARES + sq
                white_feats[has_piece, w_idx] = 1.0

                b_color = 1 - color_plane
                mir_r = BOARD_H - 1 - r
                b_sq = mir_r * BOARD_W + c
                b_idx = (
                    b_color * NUM_PIECE_TYPES * NUM_SQUARES + pt * NUM_SQUARES + b_sq
                )
                black_feats[has_piece, b_idx] = 1.0

    stm = players.astype(bool)
    return white_feats, black_feats, stm


# ---------------------------------------------------------------------------
# HalfKP Feature extraction (sparse indices)
# ---------------------------------------------------------------------------
def board_to_halfkp_indices(
    boards: np.ndarray,
    players: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert board arrays to HalfKP sparse feature indices.

    Returns:
        white_indices: (N, MAX_ACTIVE) int16, padded with HALFKP_SIZE
        black_indices: (N, MAX_ACTIVE) int16, padded with HALFKP_SIZE
        stm:           (N,) bool
    """
    N = len(boards)

    w_plane = boards[:, 0].reshape(N, -1)
    b_plane = boards[:, 1].reshape(N, -1)
    w_king_sq = np.argmax(w_plane == 6, axis=1).astype(np.int32)
    b_king_sq = np.argmax(b_plane == 6, axis=1).astype(np.int32)

    b_king_r = b_king_sq // BOARD_W
    b_king_c = b_king_sq % BOARD_W
    b_king_mir = ((BOARD_H - 1 - b_king_r) * BOARD_W + b_king_c).astype(np.int32)

    white_idx = np.full((N, MAX_ACTIVE), HALFKP_SIZE, dtype=np.int16)
    black_idx = np.full((N, MAX_ACTIVE), HALFKP_SIZE, dtype=np.int16)
    w_cnt = np.zeros(N, dtype=np.int32)
    b_cnt = np.zeros(N, dtype=np.int32)

    for color_plane in range(2):
        for r in range(BOARD_H):
            for c in range(BOARD_W):
                pts = boards[:, color_plane, r, c]
                mask = (pts > 0) & (pts != 6)
                if not np.any(mask):
                    continue

                indices = np.where(mask)[0]
                pt_idx = pts[indices].astype(np.int32) - 1
                sq = r * BOARD_W + c

                w_color = color_plane
                w_feat = (
                    w_king_sq[indices] * NUM_PIECE_FEATURES
                    + w_color * (NUM_PT_NO_KING * NUM_SQUARES)
                    + pt_idx * NUM_SQUARES
                    + sq
                )
                pos_w = w_cnt[indices]
                white_idx[indices, pos_w] = w_feat.astype(np.int16)
                w_cnt[indices] = pos_w + 1

                b_color = 1 - color_plane
                mir_sq = (BOARD_H - 1 - r) * BOARD_W + c
                b_feat = (
                    b_king_mir[indices] * NUM_PIECE_FEATURES
                    + b_color * (NUM_PT_NO_KING * NUM_SQUARES)
                    + pt_idx * NUM_SQUARES
                    + mir_sq
                )
                pos_b = b_cnt[indices]
                black_idx[indices, pos_b] = b_feat.astype(np.int16)
                b_cnt[indices] = pos_b + 1

    stm = players.astype(bool)
    return white_idx, black_idx, stm


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------
class PSDenseDataset(Dataset):
    """PS features — precomputed dense tensors."""

    def __init__(self, white_feats, black_feats, stm, scores, results):
        self.white_feats = torch.from_numpy(white_feats)
        self.black_feats = torch.from_numpy(black_feats)
        self.stm = torch.from_numpy(stm)
        self.scores = torch.from_numpy(scores.astype(np.float32))
        self.results = torch.from_numpy(results.astype(np.float32))

    def __len__(self):
        return len(self.scores)

    def __getitem__(self, idx):
        return (
            self.white_feats[idx],
            self.black_feats[idx],
            self.stm[idx],
            self.scores[idx],
            self.results[idx],
        )


class HalfKPSparseDataset(Dataset):
    """HalfKP — sparse indices expanded to dense on access."""

    def __init__(self, white_indices, black_indices, stm, scores, results):
        self.white_indices = white_indices
        self.black_indices = black_indices
        self.stm = torch.from_numpy(stm)
        self.scores = torch.from_numpy(scores.astype(np.float32))
        self.results = torch.from_numpy(results.astype(np.float32))

    def __len__(self):
        return len(self.scores)

    def __getitem__(self, idx):
        w = torch.zeros(HALFKP_SIZE)
        wi = self.white_indices[idx]
        valid_w = wi[wi != HALFKP_SIZE]
        if len(valid_w) > 0:
            w[valid_w.astype(np.int64)] = 1.0

        b = torch.zeros(HALFKP_SIZE)
        bi = self.black_indices[idx]
        valid_b = bi[bi != HALFKP_SIZE]
        if len(valid_b) > 0:
            b[valid_b.astype(np.int64)] = 1.0

        return w, b, self.stm[idx], self.scores[idx], self.results[idx]


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
def screlu(x: torch.Tensor) -> torch.Tensor:
    """Squared Clipped ReLU: clamp(x, 0, 1)^2"""
    return torch.clamp(x, 0.0, 1.0).square()


class MiniChessNNUE(nn.Module):
    def __init__(
        self,
        feature_size: int = HALFKP_SIZE,
        accum_size: int = 128,
        l1_size: int = 32,
        l2_size: int = 32,
    ):
        super().__init__()
        self.feature_size = feature_size
        self.accum_size = accum_size
        self.l1_size = l1_size
        self.l2_size = l2_size

        self.ft = nn.Linear(feature_size, accum_size)
        self.l1 = nn.Linear(accum_size * 2, l1_size)
        self.l2 = nn.Linear(l1_size, l2_size)
        self.out = nn.Linear(l2_size, 1)

    def forward(self, white_features, black_features, stm):
        w_accum = screlu(self.ft(white_features))
        b_accum = screlu(self.ft(black_features))

        stm_mask = stm.unsqueeze(1)
        stm_accum = torch.where(stm_mask, b_accum, w_accum)
        nstm_accum = torch.where(stm_mask, w_accum, b_accum)

        x = torch.cat([stm_accum, nstm_accum], dim=1)
        x = screlu(self.l1(x))
        x = screlu(self.l2(x))
        x = self.out(x)
        return x.squeeze(1)


# ---------------------------------------------------------------------------
# Loss
# ---------------------------------------------------------------------------
SCORE_SCALE = 400.0


def nnue_loss(
    predicted: torch.Tensor,
    score: torch.Tensor,
    result: torch.Tensor,
    wdl_weight: float,
) -> torch.Tensor:
    """Blended NNUE loss: MSE in sigmoid space.

    target = (1 - wdl_weight) * sigmoid(score/scale) + wdl_weight * wdl
    where wdl = (result + 1) / 2  maps  -1→0.0, 0→0.5, 1→1.0
    """
    pred_sig = torch.sigmoid(predicted / SCORE_SCALE)
    score_sig = torch.sigmoid(score / SCORE_SCALE)
    wdl = (result + 1.0) / 2.0
    target = (1.0 - wdl_weight) * score_sig + wdl_weight * wdl
    return torch.mean((pred_sig - target) ** 2)


# ---------------------------------------------------------------------------
# Binary weight export
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Quantization constants (must match C++ compute_quant.hpp)
# ---------------------------------------------------------------------------
QA = 255  # FT accumulator scale (int16)
QA_HIDDEN = 127  # hidden activation scale (uint8)
QB = 64  # dense weight scale (int8)
QAH_QB = QA_HIDDEN * QB  # 8128 — dense matmul output scale


def export_binary_weights(model: MiniChessNNUE, path: str) -> None:
    """Export float32 weights for C++ inference.

    Header (24 bytes): magic "MCNN", version, feature_size, accum_size, l1_size, l2_size
    ft_weight (feature_size, accum_size), ft_bias, l1..out weights/biases.
    """
    version = 1 if model.feature_size == PS_SIZE else 2
    sd = model.state_dict()
    with open(path, "wb") as f:
        f.write(b"MCNN")
        f.write(struct.pack("<i", version))
        f.write(struct.pack("<i", model.feature_size))
        f.write(struct.pack("<i", model.accum_size))
        f.write(struct.pack("<i", model.l1_size))
        f.write(struct.pack("<i", model.l2_size))

        # FT: transpose (accum, feat) -> (feat, accum) for C++ row accumulation
        ft_w = sd["ft.weight"].detach().cpu().float().t().contiguous()
        f.write(ft_w.numpy().tobytes())
        ft_b = sd["ft.bias"].detach().cpu().float().contiguous()
        f.write(ft_b.numpy().tobytes())

        for name in [
            "l1.weight",
            "l1.bias",
            "l2.weight",
            "l2.bias",
            "out.weight",
            "out.bias",
        ]:
            tensor = sd[name].detach().cpu().float().contiguous()
            f.write(tensor.numpy().tobytes())

    total_bytes = os.path.getsize(path)
    print(f"  Exported float weights to {path} ({total_bytes} bytes)")


def export_quantized_weights(model: MiniChessNNUE, path: str) -> None:
    """Export quantized int16/int8 weights for C++ SIMD inference.

    Same header as float, but version += 10 (11=PS_quant, 12=HalfKP_quant).
    Data layout:
        ft_weight:   int16 (feature_size, accum_size) — scale QA
        ft_bias:     int16 (accum_size) — scale QA
        l1_weight:   int8  (accum_size*2, l1_size) — TRANSPOSED, scale QB
        l1_bias:     int32 (l1_size) — scale QA*QB
        l2_weight:   int8  (l1_size, l2_size) — TRANSPOSED, scale QB
        l2_bias:     int32 (l2_size) — scale QA*QB
        out_weight:  int8  (l2_size, 1) — TRANSPOSED, scale QB
        out_bias:    int32 (1) — scale QA*QB
    """
    version = (1 if model.feature_size == PS_SIZE else 2) + 10
    sd = model.state_dict()

    def quant_i16(t, scale):
        return torch.clamp(torch.round(t * scale), -32768, 32767).to(torch.int16)

    def quant_i8(t, scale):
        return torch.clamp(torch.round(t * scale), -128, 127).to(torch.int8)

    def quant_i32(t, scale):
        return torch.clamp(torch.round(t * scale), -(2**31), 2**31 - 1).to(torch.int32)

    with open(path, "wb") as f:
        f.write(b"MCNN")
        f.write(struct.pack("<i", version))
        f.write(struct.pack("<i", model.feature_size))
        f.write(struct.pack("<i", model.accum_size))
        f.write(struct.pack("<i", model.l1_size))
        f.write(struct.pack("<i", model.l2_size))

        # FT: (feat, accum) int16, scale QA=255
        ft_w = sd["ft.weight"].detach().cpu().float().t().contiguous()
        f.write(quant_i16(ft_w, QA).numpy().tobytes())
        ft_b = sd["ft.bias"].detach().cpu().float().contiguous()
        f.write(quant_i16(ft_b, QA).numpy().tobytes())

        # Dense layers: weight TRANSPOSED to (in_size, out_size) int8 scale QB=64
        # Bias: int32 scale QA_HIDDEN*QB=8128
        for w_name, b_name in [
            ("l1.weight", "l1.bias"),
            ("l2.weight", "l2.bias"),
            ("out.weight", "out.bias"),
        ]:
            w = sd[w_name].detach().cpu().float().t().contiguous()  # transpose
            f.write(quant_i8(w, QB).numpy().tobytes())
            b = sd[b_name].detach().cpu().float().contiguous()
            f.write(quant_i32(b, QAH_QB).numpy().tobytes())

    total_bytes = os.path.getsize(path)

    # Report quantization statistics
    ft_w_float = sd["ft.weight"].detach().cpu().float()
    ft_w_range = ft_w_float.abs().max().item()
    l1_w_float = sd["l1.weight"].detach().cpu().float()
    l1_w_range = l1_w_float.abs().max().item()

    print(f"  Exported quantized weights to {path} ({total_bytes} bytes)")
    print(
        f"  FT weight range: [{-ft_w_range:.4f}, {ft_w_range:.4f}] "
        f"(QA={QA}, resolution={1/QA:.4f})"
    )
    print(
        f"  L1 weight range: [{-l1_w_range:.4f}, {l1_w_range:.4f}] "
        f"(QB={QB}, clipped={int((l1_w_float.abs() > 127/QB).sum())})"
    )


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def train(args: argparse.Namespace) -> None:
    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    print(f"Device: {device}")

    # ---- Load data --------------------------------------------------------
    print("Loading data...")
    boards, players, scores, results, plies = load_all_data(
        args.data,
        min_ply=args.min_ply,
    )
    has_wdl = np.any(results != 0)
    if args.wdl_weight > 0 and not has_wdl:
        print(
            "Warning: --wdl-weight > 0 but data has no game results (v1 format). "
            "Falling back to pure score loss."
        )
        args.wdl_weight = 0.0

    # ---- Train/val split --------------------------------------------------
    N = len(scores)
    perm = np.random.RandomState(seed=42).permutation(N)
    val_size = max(1, int(N * args.val_split))
    train_idx, val_idx = perm[val_size:], perm[:val_size]

    # ---- Feature extraction -----------------------------------------------
    feature_type = args.features.lower()
    print(f"Extracting {feature_type.upper()} features...")
    t0 = time.time()

    if feature_type == "ps":
        feature_size = PS_SIZE
        wf, bf, stm = board_to_ps_features(boards, players)
        print(f"  Feature extraction: {time.time() - t0:.2f}s")
        print(f"  Active features per position: {wf.sum(axis=1).mean():.1f}")
        train_ds = PSDenseDataset(
            wf[train_idx],
            bf[train_idx],
            stm[train_idx],
            scores[train_idx],
            results[train_idx],
        )
        val_ds = PSDenseDataset(
            wf[val_idx], bf[val_idx], stm[val_idx], scores[val_idx], results[val_idx]
        )
    elif feature_type == "halfkp":
        feature_size = HALFKP_SIZE
        wi, bi, stm = board_to_halfkp_indices(boards, players)
        print(f"  Feature extraction: {time.time() - t0:.2f}s")
        active = (wi != HALFKP_SIZE).sum(axis=1).mean()
        print(f"  Active features per position: {active:.1f}")
        train_ds = HalfKPSparseDataset(
            wi[train_idx],
            bi[train_idx],
            stm[train_idx],
            scores[train_idx],
            results[train_idx],
        )
        val_ds = HalfKPSparseDataset(
            wi[val_idx], bi[val_idx], stm[val_idx], scores[val_idx], results[val_idx]
        )
    else:
        print(f"Error: unknown feature type '{feature_type}' (use 'ps' or 'halfkp')")
        sys.exit(1)

    print(f"  Feature space: {feature_size}")
    print(f"  Train: {len(train_ds)}, Val: {len(val_ds)}")

    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=(device.type == "cuda"),
        drop_last=False,
        persistent_workers=True,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=(device.type == "cuda"),
        drop_last=False,
        persistent_workers=True,
    )

    # ---- Model ------------------------------------------------------------
    model = MiniChessNNUE(
        feature_size=feature_size,
        accum_size=args.accum_size,
        l1_size=32,
        l2_size=32,
    ).to(device)

    total_params = sum(p.numel() for p in model.parameters())
    print(f"Model parameters: {total_params:,}")
    print(f"WDL weight: {args.wdl_weight}")

    # ---- Optimizer & scheduler --------------------------------------------
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=args.epochs, eta_min=args.lr * 0.01
    )

    # ---- Ensure output directories exist ----------------------------------
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(args.export) or ".", exist_ok=True)

    # ---- Eval helper ------------------------------------------------------
    def evaluate(loader, desc="Eval"):
        model.eval()
        total_loss = 0.0
        n = 0
        with torch.no_grad():
            for wf, bf, s, sc, res in tqdm(loader, desc=desc, leave=False):
                wf = wf.to(device)
                bf = bf.to(device)
                s = s.to(device)
                sc = sc.to(device)
                res = res.to(device)
                pred = model(wf, bf, s)
                total_loss += nnue_loss(pred, sc, res, args.wdl_weight).item()
                n += 1
        return total_loss / max(n, 1)

    # ---- Baseline loss ----------------------------------------------------
    baseline_train = evaluate(train_loader, "Baseline train")
    baseline_val = evaluate(val_loader, "Baseline val")
    print(f"\nBaseline loss — train: {baseline_train:.6f}, val: {baseline_val:.6f}")

    # ---- Training loop ----------------------------------------------------
    print(
        f"Training for {args.epochs} epochs, "
        f"batch_size={args.batch_size}, lr={args.lr}"
    )
    print("-" * 72)

    best_val_loss = float("inf")

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss = 0.0
        n_batches = 0

        pbar = tqdm(train_loader, desc=f"Epoch {epoch:>3d}/{args.epochs}", leave=False)
        for wf, bf, s, sc, res in pbar:
            wf = wf.to(device)
            bf = bf.to(device)
            s = s.to(device)
            sc = sc.to(device)
            res = res.to(device)

            pred = model(wf, bf, s)
            loss = nnue_loss(pred, sc, res, args.wdl_weight)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1
            pbar.set_postfix(loss=f"{loss.item():.6f}")

        scheduler.step()
        avg_train = epoch_loss / max(n_batches, 1)
        val_loss = evaluate(val_loader, "Val")
        lr_now = scheduler.get_last_lr()[0]

        if val_loss < best_val_loss:
            best_val_loss = val_loss

        tqdm.write(
            f"Epoch {epoch:>4d}/{args.epochs}  "
            f"train={avg_train:.6f}  "
            f"val={val_loss:.6f}  "
            f"best_val={best_val_loss:.6f}  "
            f"lr={lr_now:.2e}"
        )

        if epoch % 10 == 0:
            ckpt_path = args.output.replace(".pt", f"_epoch{epoch}.pt")
            torch.save(model.state_dict(), ckpt_path)

    # ---- Save final model -------------------------------------------------
    print("-" * 72)
    print("Training complete.")
    print(f"  Final train loss: {avg_train:.6f}")
    print(f"  Best val loss:    {best_val_loss:.6f}")
    print(f"  Parameters:       {total_params:,}")

    torch.save(model.state_dict(), args.output)
    print(f"  Saved PyTorch model to {args.output}")

    export_binary_weights(model, args.export)

    # Export quantized version alongside
    quant_path = args.export.replace(".bin", "_quant.bin")
    export_quantized_weights(model, quant_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train a NNUE for MiniChess (6x5)",
    )
    parser.add_argument(
        "--data",
        type=str,
        default="data/train_*.bin",
        help="Glob pattern for data files (default: data/train_*.bin)",
    )
    parser.add_argument(
        "--features",
        type=str,
        default="halfkp",
        choices=["ps", "halfkp"],
        help="Feature type: ps (360) or halfkp (9000) (default: halfkp)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="Number of training epochs (default: 100)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8192,
        help="Batch size (default: 8192)",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=1e-3,
        help="Learning rate (default: 1e-3)",
    )
    parser.add_argument(
        "--accum-size",
        type=int,
        default=128,
        help="Accumulator width (default: 128)",
    )
    parser.add_argument(
        "--wdl-weight",
        type=float,
        default=0.5,
        help="WDL blending weight: 0.0=pure score, 1.0=pure game result (default: 0.5)",
    )
    parser.add_argument(
        "--min-ply",
        type=int,
        default=0,
        help="Skip positions with ply < this value (default: 0)",
    )
    parser.add_argument(
        "--val-split",
        type=float,
        default=0.05,
        help="Fraction of data for validation (default: 0.05)",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
        help="DataLoader workers (default: 0)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Device to train on: auto, cpu, cuda, cuda:0, etc. (default: auto)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="models/nnue_v1.pt",
        help="Save PyTorch model to (default: models/nnue_v1.pt)",
    )
    parser.add_argument(
        "--export",
        type=str,
        default="models/nnue_v1.bin",
        help="Export binary weights to (default: models/nnue_v1.bin)",
    )
    args = parser.parse_args()
    train(args)


if __name__ == "__main__":
    main()
