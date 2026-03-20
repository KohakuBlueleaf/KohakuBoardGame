#!/usr/bin/env python3
"""
train_nnue.py — Train a NNUE for MiniChess / MiniShogi / Gomoku.

Supports two feature types:
  PS:     PieceSquare  -> Accumulator -> SCReLU -> ...
  HalfKP: HalfKP      -> Accumulator -> SCReLU -> ...

Training target (following standard NNUE practice):
  target = (1 - wdl_weight) * sigmoid(score/scale) + wdl_weight * wdl_result
  loss   = MSE(sigmoid(predicted/scale), target)

Game is auto-detected from the data file header (v4+ format with metadata)
or selected via --game CLI argument.  Defaults to minichess for backward
compatibility with old data files that lack metadata.

Usage:
    python scripts/train_nnue.py --data "data/train_*.bin" --features halfkp --epochs 100
    python scripts/train_nnue.py --game minishogi --data "data/shogi_*.bin" --features ps
    python scripts/train_nnue.py --game gomoku --data "data/gomoku_*.bin" --features ps
"""

import argparse
import glob
import os
import struct
import sys
import time
from typing import Dict, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Game configurations
# ---------------------------------------------------------------------------
GAME_CONFIGS: Dict[str, dict] = {
    "minichess": {
        "board_h": 6,
        "board_w": 5,
        "num_piece_types": 6,
        "num_pt_no_king": 5,
        "king_id": 6,  # piece type ID used for king on the board
        "piece_names": [".", "P", "R", "N", "B", "Q", "K"],
        "has_hand": False,
        "num_hand_types": 0,
    },
    "minishogi": {
        "board_h": 5,
        "board_w": 5,
        "num_piece_types": 11,  # 0=empty, 1-6 base, 7-10 promoted
        "num_pt_no_king": 10,
        "king_id": 6,
        "piece_names": [
            ".",
            "P",
            "S",
            "G",
            "B",
            "R",
            "K",
            "+P",
            "+S",
            "+B",
            "+R",
        ],
        "has_hand": True,
        "num_hand_types": 5,  # pawn, silver, gold, bishop, rook (indices 1-5)
    },
    "gomoku": {
        "board_h": 9,
        "board_w": 9,
        "num_piece_types": 2,  # 1=X (black), 2=O (white) -- but no king
        "num_pt_no_king": 2,
        "king_id": None,  # gomoku has no king
        "piece_names": [".", "X", "O"],
        "has_hand": False,
        "num_hand_types": 0,
    },
}

DEFAULT_GAME = "minichess"


def get_game_config(game_name: str) -> dict:
    """Return the game config dict, raising an error if unknown."""
    name = game_name.lower()
    if name not in GAME_CONFIGS:
        raise ValueError(
            f"Unknown game '{game_name}'. "
            f"Available: {', '.join(GAME_CONFIGS.keys())}"
        )
    cfg = dict(GAME_CONFIGS[name])
    # Derived constants
    cfg["name"] = name
    cfg["num_squares"] = cfg["board_h"] * cfg["board_w"]
    cfg["num_colors"] = 2
    cfg["board_cells"] = 2 * cfg["board_h"] * cfg["board_w"]  # total int8s for board
    cfg["ps_size"] = cfg["num_colors"] * cfg["num_piece_types"] * cfg["num_squares"]
    cfg["num_piece_features"] = (
        cfg["num_colors"] * cfg["num_pt_no_king"] * cfg["num_squares"]
    )
    cfg["halfkp_size"] = cfg["num_squares"] * cfg["num_piece_features"]
    cfg["policy_size"] = cfg["num_squares"] * cfg["num_squares"]  # from-to
    # Hand features appended after HalfKP/PS board features
    if cfg["has_hand"] and cfg["num_hand_types"] > 0:
        # One feature per (color, hand_piece_type), activated count times
        cfg["hand_feature_size"] = cfg["num_colors"] * cfg["num_hand_types"]
    else:
        cfg["hand_feature_size"] = 0
    # Total feature space = board features + hand features
    cfg["halfkp_size_with_hand"] = cfg["halfkp_size"] + cfg["hand_feature_size"]
    cfg["ps_size_with_hand"] = cfg["ps_size"] + cfg["hand_feature_size"]
    cfg["max_active"] = max(20, cfg["num_squares"] + cfg.get("num_hand_types", 0) * 2)
    return cfg


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
NUM_COLORS = 2

# Data file header formats
# Legacy header: magic(4) + version(i32) + count(i32) = 12 bytes
HEADER_FMT = "<4sii"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

# v4 header: legacy + board_h(u16) + board_w(u16) + game_name(16s) = 32 bytes
V4_HEADER_FMT = "<4siiHH16s"
V4_HEADER_SIZE = struct.calcsize(V4_HEADER_FMT)

# v5 header: legacy + board_h(u16) + board_w(u16) + num_hand(u16) + reserved(u16) + game_name(16s) = 36 bytes
V5_HEADER_FMT = "<4siiHHHH16s"
V5_HEADER_SIZE = struct.calcsize(V5_HEADER_FMT)

# Backward compat alias
EXT_HEADER_FMT = V4_HEADER_FMT
EXT_HEADER_SIZE = V5_HEADER_SIZE  # read enough for v5

SCORE_FILTER = 10000
NO_MOVE = 0xFFFF


# ---------------------------------------------------------------------------
# Data file header reading & game auto-detection
# ---------------------------------------------------------------------------
def read_data_header(path: str) -> dict:
    """Read a data file header and return metadata dict.

    Supports both legacy (12-byte) and extended (32-byte, v4+) headers.
    Returns: {magic, version, count, board_h, board_w, game_name (or None)}
    """
    with open(path, "rb") as f:
        hdr_data = f.read(EXT_HEADER_SIZE)

    if len(hdr_data) < HEADER_SIZE:
        raise ValueError(f"File too small for header: {path}")

    # Try legacy header first
    magic, version, count = struct.unpack(HEADER_FMT, hdr_data[:HEADER_SIZE])
    magic_str = magic.decode("ascii", errors="replace")
    if magic_str not in ("MCDT", "BGDT"):
        raise ValueError(f"Bad magic '{magic_str}' in {path}")

    result = {
        "magic": magic_str,
        "version": version,
        "count": count,
        "board_h": None,
        "board_w": None,
        "game_name": None,
    }

    # v5 header: includes num_hand
    if version >= 5 and len(hdr_data) >= V5_HEADER_SIZE:
        _, _, _, board_h, board_w, num_hand, _, game_name_raw = struct.unpack(
            V5_HEADER_FMT, hdr_data[:V5_HEADER_SIZE]
        )
        game_name = game_name_raw.rstrip(b"\x00").decode("ascii", errors="replace")
        result["board_h"] = board_h
        result["board_w"] = board_w
        result["num_hand"] = num_hand
        result["game_name"] = game_name.lower() if game_name else None
    elif version >= 4 and len(hdr_data) >= V4_HEADER_SIZE:
        _, _, _, board_h, board_w, game_name_raw = struct.unpack(
            V4_HEADER_FMT, hdr_data[:V4_HEADER_SIZE]
        )
        game_name = game_name_raw.rstrip(b"\x00").decode("ascii", errors="replace")
        result["board_h"] = board_h
        result["board_w"] = board_w
        result["game_name"] = game_name.lower() if game_name else None

    return result


def detect_game_from_file(path: str) -> Optional[str]:
    """Try to auto-detect game type from data file header.

    Returns game name string or None if detection fails (legacy format).
    """
    try:
        hdr = read_data_header(path)
        if hdr["game_name"] and hdr["game_name"] in GAME_CONFIGS:
            return hdr["game_name"]
        # Fall back: try to match by board dimensions
        if hdr["board_h"] is not None and hdr["board_w"] is not None:
            for name, cfg in GAME_CONFIGS.items():
                if (
                    cfg["board_h"] == hdr["board_h"]
                    and cfg["board_w"] == hdr["board_w"]
                ):
                    return name
    except (ValueError, IOError):
        pass
    return None


def resolve_game(cli_game: Optional[str], data_pattern: str) -> dict:
    """Resolve game config from CLI arg and/or data file auto-detection.

    Priority: CLI arg > auto-detect from first data file > default (minichess).
    """
    detected = None
    files = sorted(glob.glob(data_pattern))
    if files:
        detected = detect_game_from_file(files[0])

    if cli_game:
        game_name = cli_game.lower()
        if detected and detected != game_name:
            print(
                f"Warning: --game={game_name} overrides auto-detected "
                f"game '{detected}' from data file"
            )
        return get_game_config(game_name)

    if detected:
        print(f"Auto-detected game: {detected}")
        return get_game_config(detected)

    print(f"No game specified or detected, defaulting to '{DEFAULT_GAME}'")
    return get_game_config(DEFAULT_GAME)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def _make_record_dtype(board_cells: int, version: int, hand_cells: int = 0) -> Tuple[np.dtype, int]:
    """Create numpy dtype for a data record given board size and format version.

    board_cells = 2 * BOARD_H * BOARD_W (total int8 elements for the board).
    hand_cells  = 2 * num_hand_types (v5+), or 2 if num_hand_types==0 (min 1 per player in C struct).
    """
    fields = [("board", np.int8, (board_cells,))]

    if version >= 5:
        fields.append(("hand", np.int8, (hand_cells,)))

    if version == 1:
        fields += [("player", np.int8), ("score", "<i2")]
    elif version == 2:
        fields += [
            ("player", np.int8),
            ("score", "<i2"),
            ("result", np.int8),
            ("ply", "<u2"),
        ]
    elif version >= 3:
        fields += [
            ("player", np.int8),
            ("score", "<i2"),
            ("result", np.int8),
            ("ply", "<u2"),
            ("best_move", "<u2"),
        ]
    else:
        raise ValueError(f"Unknown data version {version}")

    dt = np.dtype(fields)
    return dt, dt.itemsize


def read_bin_file(
    path: str,
    gcfg: dict,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Read a single .bin data file (supports v1-v5 formats).

    Returns:
        boards:     (N, 2, H, W) int8
        players:    (N,) int8
        scores:     (N,) int16
        results:    (N,) int8
        plies:      (N,) uint16
        best_moves: (N,) uint16
    Also sets gcfg["_hands"] = (N, 2, num_hand) int8 if v5 with hand > 0.
    """
    board_h = gcfg["board_h"]
    board_w = gcfg["board_w"]
    board_cells = gcfg["board_cells"]

    with open(path, "rb") as f:
        # Read header
        peek = f.read(V5_HEADER_SIZE)
        if len(peek) < HEADER_SIZE:
            raise ValueError(f"File too small for header: {path}")

        magic, version, count = struct.unpack(HEADER_FMT, peek[:HEADER_SIZE])
        magic_str = magic.decode("ascii", errors="replace")
        if magic_str not in ("MCDT", "BGDT"):
            raise ValueError(f"Bad magic '{magic_str}' in {path}")

        # Parse v5 header for hand info
        num_hand = 0
        if version >= 5 and len(peek) >= V5_HEADER_SIZE:
            _, _, _, _, _, num_hand, _, _ = struct.unpack(
                V5_HEADER_FMT, peek[:V5_HEADER_SIZE]
            )
            header_end = V5_HEADER_SIZE
        elif version >= 4 and len(peek) >= V4_HEADER_SIZE:
            header_end = V4_HEADER_SIZE
        else:
            header_end = HEADER_SIZE

        f.seek(header_end)

        # Hand cells in the record: 2 * max(1, num_hand) matching C struct
        hand_cells = 2 * num_hand if num_hand > 0 else 2

        # Build record dtype
        dt, record_size = _make_record_dtype(board_cells, version, hand_cells)
        raw = f.read(record_size * count)

    if len(raw) < record_size * count:
        actual = len(raw) // record_size
        print(f"Warning: {path} truncated, expected {count} records, got {actual}")
        count = actual

    records = np.frombuffer(raw[: count * record_size], dtype=dt)
    boards = records["board"].reshape(-1, 2, board_h, board_w).copy()
    players = records["player"].copy()
    scores = records["score"].copy()

    # Store hand data if available
    if version >= 5 and num_hand > 0:
        hands = records["hand"].reshape(-1, 2, num_hand).copy()
        gcfg["_hands"] = hands
        gcfg["_num_hand"] = num_hand

    if version >= 2:
        results = records["result"].copy()
        plies = records["ply"].copy()
    else:
        results = np.zeros(count, dtype=np.int8)
        plies = np.zeros(count, dtype=np.uint16)

    if version >= 3:
        best_moves = records["best_move"].copy()
    else:
        best_moves = np.full(count, NO_MOVE, dtype=np.uint16)

    return boards, players, scores, results, plies, best_moves


def load_all_data(
    pattern: str,
    gcfg: dict,
    min_ply: int = 0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load and concatenate data from all files matching *pattern*."""
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"Error: no files match '{pattern}'")
        sys.exit(1)

    all_boards, all_players, all_scores, all_results, all_plies, all_best_moves = (
        [],
        [],
        [],
        [],
        [],
        [],
    )
    for fp in files:
        print(f"  Loading {fp} ...", end="", flush=True)
        b, p, s, r, ply, bm = read_bin_file(fp, gcfg)
        has_moves = np.any(bm != NO_MOVE)
        ver_str = "3" if has_moves else ("2" if r.any() else "1")
        print(f" {len(b)} records (v{ver_str})")
        all_boards.append(b)
        all_players.append(p)
        all_scores.append(s)
        all_results.append(r)
        all_plies.append(ply)
        all_best_moves.append(bm)

    boards = np.concatenate(all_boards)
    players = np.concatenate(all_players)
    scores = np.concatenate(all_scores)
    results = np.concatenate(all_results)
    plies = np.concatenate(all_plies)
    best_moves = np.concatenate(all_best_moves)

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
    best_moves = best_moves[mask]
    filtered = total - len(scores)
    print(f"  Total: {total} records, filtered {filtered}, kept {len(scores)}")

    return boards, players, scores, results, plies, best_moves


# ---------------------------------------------------------------------------
# PS Feature extraction (dense, precomputed)
# ---------------------------------------------------------------------------
def board_to_ps_features(
    boards: np.ndarray,
    players: np.ndarray,
    gcfg: dict,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert board arrays to PieceSquare dense feature tensors.

    Returns:
        white_feats: (N, PS_SIZE) float32
        black_feats: (N, PS_SIZE) float32
        stm:         (N,) bool
    """
    board_h = gcfg["board_h"]
    board_w = gcfg["board_w"]
    num_squares = gcfg["num_squares"]
    num_piece_types = gcfg["num_piece_types"]
    ps_size = gcfg["ps_size"]

    N = len(boards)
    white_feats = np.zeros((N, ps_size), dtype=np.float32)
    black_feats = np.zeros((N, ps_size), dtype=np.float32)

    for color_plane in range(2):
        for r in range(board_h):
            for c in range(board_w):
                piece_types = boards[:, color_plane, r, c]
                has_piece = piece_types > 0
                if not np.any(has_piece):
                    continue
                pt = piece_types[has_piece].astype(np.int32) - 1
                sq = r * board_w + c

                w_color = color_plane
                w_idx = w_color * num_piece_types * num_squares + pt * num_squares + sq
                white_feats[has_piece, w_idx] = 1.0

                b_color = 1 - color_plane
                mir_r = board_h - 1 - r
                b_sq = mir_r * board_w + c
                b_idx = (
                    b_color * num_piece_types * num_squares + pt * num_squares + b_sq
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
    gcfg: dict,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert board arrays to HalfKP sparse feature indices.

    For games without a king (e.g. gomoku), falls back to PS features
    stored in HalfKP-style sparse format (king_sq fixed to 0).

    Returns:
        white_indices: (N, MAX_ACTIVE) int16/int32, padded with halfkp_size
        black_indices: (N, MAX_ACTIVE) int16/int32, padded with halfkp_size
        stm:           (N,) bool
    """
    board_h = gcfg["board_h"]
    board_w = gcfg["board_w"]
    num_squares = gcfg["num_squares"]
    num_pt_no_king = gcfg["num_pt_no_king"]
    king_id = gcfg["king_id"]
    num_piece_features = gcfg["num_piece_features"]
    halfkp_size = gcfg["halfkp_size"]  # board-only feature space
    total_feature_size = gcfg["halfkp_size_with_hand"]  # board + hand
    max_active = gcfg["max_active"]

    N = len(boards)

    # Use int32 for indices when feature space > 32767
    idx_dtype = np.int32 if total_feature_size > 32767 else np.int16

    if king_id is not None:
        # Standard HalfKP: find king squares
        w_plane = boards[:, 0].reshape(N, -1)
        b_plane = boards[:, 1].reshape(N, -1)
        w_king_sq = np.argmax(w_plane == king_id, axis=1).astype(np.int32)
        b_king_sq = np.argmax(b_plane == king_id, axis=1).astype(np.int32)

        b_king_r = b_king_sq // board_w
        b_king_c = b_king_sq % board_w
        b_king_mir = ((board_h - 1 - b_king_r) * board_w + b_king_c).astype(np.int32)
    else:
        # No king (e.g. gomoku): use fixed king_sq=0 (degenerates to PS)
        w_king_sq = np.zeros(N, dtype=np.int32)
        b_king_mir = np.zeros(N, dtype=np.int32)

    white_idx = np.full((N, max_active), total_feature_size, dtype=idx_dtype)
    black_idx = np.full((N, max_active), total_feature_size, dtype=idx_dtype)
    w_cnt = np.zeros(N, dtype=np.int32)
    b_cnt = np.zeros(N, dtype=np.int32)

    for color_plane in range(2):
        for r in range(board_h):
            for c in range(board_w):
                pts = boards[:, color_plane, r, c]
                if king_id is not None:
                    mask = (pts > 0) & (pts != king_id)
                else:
                    mask = pts > 0
                if not np.any(mask):
                    continue

                indices = np.where(mask)[0]
                pt_idx = pts[indices].astype(np.int32) - 1
                sq = r * board_w + c

                w_color = color_plane
                w_feat = (
                    w_king_sq[indices] * num_piece_features
                    + w_color * (num_pt_no_king * num_squares)
                    + pt_idx * num_squares
                    + sq
                )
                pos_w = w_cnt[indices]
                # Clamp to max_active
                valid_w = pos_w < max_active
                if np.any(valid_w):
                    vi = indices[valid_w]
                    white_idx[vi, pos_w[valid_w]] = w_feat[valid_w].astype(idx_dtype)
                w_cnt[indices] = pos_w + 1

                b_color = 1 - color_plane
                mir_sq = (board_h - 1 - r) * board_w + c
                b_feat = (
                    b_king_mir[indices] * num_piece_features
                    + b_color * (num_pt_no_king * num_squares)
                    + pt_idx * num_squares
                    + mir_sq
                )
                pos_b = b_cnt[indices]
                valid_b = pos_b < max_active
                if np.any(valid_b):
                    vi = indices[valid_b]
                    black_idx[vi, pos_b[valid_b]] = b_feat[valid_b].astype(idx_dtype)
                b_cnt[indices] = pos_b + 1

    # Append hand features if available
    if gcfg["has_hand"] and "_hands" in gcfg:
        hands = gcfg["_hands"]  # (N, 2, num_hand_types)
        num_ht = gcfg["num_hand_types"]
        base = halfkp_size  # hand features start after board features

        for color in range(2):
            for pt in range(num_ht):
                counts = hands[:, color, pt]
                has = counts > 0
                if not np.any(has):
                    continue
                indices = np.where(has)[0]
                cnts = counts[indices].astype(np.int32)

                # White perspective: color as-is
                w_feat_idx = base + color * num_ht + pt
                for i in range(len(indices)):
                    idx = indices[i]
                    c = cnts[i]
                    for _ in range(c):
                        pw = w_cnt[idx]
                        if pw < max_active:
                            white_idx[idx, pw] = w_feat_idx
                        w_cnt[idx] = pw + 1

                # Black perspective: flip color
                b_feat_idx = base + (1 - color) * num_ht + pt
                for i in range(len(indices)):
                    idx = indices[i]
                    c = cnts[i]
                    for _ in range(c):
                        pb = b_cnt[idx]
                        if pb < max_active:
                            black_idx[idx, pb] = b_feat_idx
                        b_cnt[idx] = pb + 1

    stm = players.astype(bool)
    return white_idx, black_idx, stm


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------
class PSDenseDataset(Dataset):
    """PS features -- precomputed dense tensors."""

    def __init__(self, white_feats, black_feats, stm, scores, results, best_moves=None):
        self.white_feats = torch.from_numpy(white_feats)
        self.black_feats = torch.from_numpy(black_feats)
        self.stm = torch.from_numpy(stm)
        self.scores = torch.from_numpy(scores.astype(np.float32))
        self.results = torch.from_numpy(results.astype(np.float32))
        self.best_moves = (
            torch.from_numpy(best_moves.astype(np.int64))
            if best_moves is not None
            else None
        )

    def __len__(self):
        return len(self.scores)

    def __getitem__(self, idx):
        items = (
            self.white_feats[idx],
            self.black_feats[idx],
            self.stm[idx],
            self.scores[idx],
            self.results[idx],
        )
        if self.best_moves is not None:
            items = items + (self.best_moves[idx],)
        return items


class HalfKPSparseDataset(Dataset):
    """HalfKP -- sparse indices expanded to dense on access."""

    def __init__(
        self,
        white_indices,
        black_indices,
        stm,
        scores,
        results,
        halfkp_size,
        best_moves=None,
    ):
        self.white_indices = white_indices
        self.black_indices = black_indices
        self.halfkp_size = halfkp_size
        self.stm = torch.from_numpy(stm)
        self.scores = torch.from_numpy(scores.astype(np.float32))
        self.results = torch.from_numpy(results.astype(np.float32))
        self.best_moves = (
            torch.from_numpy(best_moves.astype(np.int64))
            if best_moves is not None
            else None
        )

    def __len__(self):
        return len(self.scores)

    def __getitem__(self, idx):
        halfkp_size = self.halfkp_size

        w = torch.zeros(halfkp_size)
        wi = self.white_indices[idx]
        valid_w = wi[wi != halfkp_size]
        if len(valid_w) > 0:
            # Use scatter_add to handle duplicate indices (hand pieces with count > 1)
            w.scatter_add_(0, torch.from_numpy(valid_w.astype(np.int64)),
                          torch.ones(len(valid_w)))

        b = torch.zeros(halfkp_size)
        bi = self.black_indices[idx]
        valid_b = bi[bi != halfkp_size]
        if len(valid_b) > 0:
            b.scatter_add_(0, torch.from_numpy(valid_b.astype(np.int64)),
                          torch.ones(len(valid_b)))

        items = (w, b, self.stm[idx], self.scores[idx], self.results[idx])
        if self.best_moves is not None:
            items = items + (self.best_moves[idx],)
        return items


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
def screlu(x: torch.Tensor) -> torch.Tensor:
    """Squared Clipped ReLU: clamp(x, 0, 1)^2"""
    return torch.clamp(x, 0.0, 1.0).square()


class GameNNUE(nn.Module):
    def __init__(
        self,
        feature_size: int,
        accum_size: int = 128,
        l1_size: int = 32,
        l2_size: int = 32,
        use_policy: bool = False,
        policy_size: int = 900,
    ):
        super().__init__()
        self.feature_size = feature_size
        self.accum_size = accum_size
        self.l1_size = l1_size
        self.l2_size = l2_size
        self.use_policy = use_policy
        self.policy_size = policy_size

        self.ft = nn.Linear(feature_size, accum_size)
        self.l1 = nn.Linear(accum_size * 2, l1_size)
        self.l2 = nn.Linear(l1_size, l2_size)
        self.out = nn.Linear(l2_size, 1)

        if use_policy:
            self.policy_l1 = nn.Linear(accum_size * 2, 128)
            self.policy_out = nn.Linear(128, policy_size)

    def forward(self, white_features, black_features, stm):
        w_accum = screlu(self.ft(white_features))
        b_accum = screlu(self.ft(black_features))

        stm_mask = stm.unsqueeze(1)
        stm_accum = torch.where(stm_mask, b_accum, w_accum)
        nstm_accum = torch.where(stm_mask, w_accum, b_accum)

        x = torch.cat([stm_accum, nstm_accum], dim=1)

        # Value head
        v = screlu(self.l1(x))
        v = screlu(self.l2(v))
        value = self.out(v).squeeze(1)

        if self.use_policy:
            p = torch.relu(self.policy_l1(x))  # ReLU not SCReLU for policy
            policy_logits = self.policy_out(p)
            return value, policy_logits
        return value


# Backward-compatible alias
MiniChessNNUE = GameNNUE


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
    where wdl = (result + 1) / 2  maps  -1->0.0, 0->0.5, 1->1.0
    """
    pred_sig = torch.sigmoid(predicted / SCORE_SCALE)
    score_sig = torch.sigmoid(score / SCORE_SCALE)
    wdl = (result + 1.0) / 2.0
    target = (1.0 - wdl_weight) * score_sig + wdl_weight * wdl
    return torch.mean((pred_sig - target) ** 2)


def dual_loss(
    value_pred: torch.Tensor,
    policy_logits: torch.Tensor,
    score: torch.Tensor,
    result: torch.Tensor,
    best_move: torch.Tensor,
    wdl_weight: float,
    policy_weight: float = 0.1,
) -> torch.Tensor:
    """Combined value + policy loss.

    Policy loss is only computed on records that have a valid best move
    (best_move != NO_MOVE).
    """
    # Value loss (unchanged)
    value_loss = nnue_loss(value_pred, score, result, wdl_weight)

    # Policy loss: only on records that HAVE a best move
    has_move = best_move != NO_MOVE
    if has_move.any() and policy_logits is not None:
        valid_logits = policy_logits[has_move]
        valid_targets = best_move[has_move]
        policy_loss = nn.functional.cross_entropy(valid_logits, valid_targets)
        return value_loss + policy_weight * policy_loss
    return value_loss


# ---------------------------------------------------------------------------
# Binary weight export
# ---------------------------------------------------------------------------
# Quantization constants (must match C++ compute_quant.hpp)
QA = 255  # FT accumulator scale (int16)
QA_HIDDEN = 127  # hidden activation scale (uint8)
QB = 64  # dense weight scale (int8)
QAH_QB = QA_HIDDEN * QB  # 8128 -- dense matmul output scale


def export_binary_weights(model: GameNNUE, path: str, gcfg: dict) -> None:
    """Export float32 weights for C++ inference.

    Header (24 bytes): magic "MCNN", version, feature_size, accum_size, l1_size, l2_size
    ft_weight (feature_size, accum_size), ft_bias, l1..out weights/biases.
    """
    ps_size = gcfg["ps_size"]
    version = 1 if model.feature_size == ps_size else 2
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
    if model.use_policy:
        print(
            "  Note: Policy head weights NOT exported to binary (C++ support pending)"
        )


def export_quantized_weights(model: GameNNUE, path: str, gcfg: dict) -> None:
    """Export quantized int16/int8 weights for C++ SIMD inference.

    Same header as float, but version += 10 (11=PS_quant, 12=HalfKP_quant).
    """
    ps_size = gcfg["ps_size"]
    version = (1 if model.feature_size == ps_size else 2) + 10
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
    if model.use_policy:
        print(
            "  Note: Policy head weights NOT exported to binary (C++ support pending)"
        )


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def train(args: argparse.Namespace) -> None:
    # ---- Resolve game config ----------------------------------------------
    gcfg = resolve_game(args.game, args.data)
    game_name = gcfg["name"]
    ps_size = gcfg["ps_size"]
    halfkp_size = gcfg["halfkp_size"]
    policy_size = gcfg["policy_size"]
    max_active = gcfg["max_active"]

    print(f"Game: {game_name}")
    print(
        f"  Board: {gcfg['board_h']}x{gcfg['board_w']}, "
        f"Piece types: {gcfg['num_piece_types']}, "
        f"Squares: {gcfg['num_squares']}"
    )
    print(
        f"  PS size: {ps_size}, HalfKP size: {halfkp_size}, Policy size: {policy_size}"
    )
    if gcfg["has_hand"]:
        print(
            f"  Hand types: {gcfg['num_hand_types']} (hand features embedded in board)"
        )

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    print(f"Device: {device}")

    # ---- Load data --------------------------------------------------------
    print("Loading data...")
    boards, players, scores, results, plies, best_moves = load_all_data(
        args.data,
        gcfg,
        min_ply=args.min_ply,
    )
    has_wdl = np.any(results != 0)
    if args.wdl_weight > 0 and not has_wdl:
        print(
            "Warning: --wdl-weight > 0 but data has no game results (v1 format). "
            "Falling back to pure score loss."
        )
        args.wdl_weight = 0.0

    has_best_moves = np.any(best_moves != NO_MOVE)
    if args.policy and not has_best_moves:
        print(
            "Warning: --policy enabled but no best_move data found (all v1/v2). "
            "Policy loss will be skipped (value-only training)."
        )

    # Hand features are now integrated into board_to_halfkp_indices()

    # ---- Train/val split --------------------------------------------------
    N = len(scores)
    perm = np.random.RandomState(seed=42).permutation(N)
    val_size = max(1, int(N * args.val_split))
    train_idx, val_idx = perm[val_size:], perm[:val_size]

    # ---- Feature extraction -----------------------------------------------
    feature_type = args.features.lower()
    print(f"Extracting {feature_type.upper()} features...")
    t0 = time.time()

    # Prepare best_moves for datasets (pass only when policy is enabled)
    bm_train = best_moves[train_idx] if args.policy else None
    bm_val = best_moves[val_idx] if args.policy else None

    if feature_type == "ps":
        feature_size = ps_size
        wf, bf, stm = board_to_ps_features(boards, players, gcfg)
        print(f"  Feature extraction: {time.time() - t0:.2f}s")
        print(f"  Active features per position: {wf.sum(axis=1).mean():.1f}")
        train_ds = PSDenseDataset(
            wf[train_idx],
            bf[train_idx],
            stm[train_idx],
            scores[train_idx],
            results[train_idx],
            bm_train,
        )
        val_ds = PSDenseDataset(
            wf[val_idx],
            bf[val_idx],
            stm[val_idx],
            scores[val_idx],
            results[val_idx],
            bm_val,
        )
    elif feature_type == "halfkp":
        feature_size = gcfg["halfkp_size_with_hand"]
        wi, bi, stm = board_to_halfkp_indices(boards, players, gcfg)
        print(f"  Feature extraction: {time.time() - t0:.2f}s")
        active = (wi != feature_size).sum(axis=1).mean()
        print(f"  Active features per position: {active:.1f}")
        train_ds = HalfKPSparseDataset(
            wi[train_idx],
            bi[train_idx],
            stm[train_idx],
            scores[train_idx],
            results[train_idx],
            feature_size,
            bm_train,
        )
        val_ds = HalfKPSparseDataset(
            wi[val_idx],
            bi[val_idx],
            stm[val_idx],
            scores[val_idx],
            results[val_idx],
            feature_size,
            bm_val,
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
        persistent_workers=(args.num_workers > 0),
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=(device.type == "cuda"),
        drop_last=False,
        persistent_workers=(args.num_workers > 0),
    )

    # ---- Model ------------------------------------------------------------
    model = GameNNUE(
        feature_size=feature_size,
        accum_size=args.accum_size,
        l1_size=32,
        l2_size=32,
        use_policy=args.policy,
        policy_size=policy_size,
    ).to(device)

    total_params = sum(p.numel() for p in model.parameters())
    print(f"Model parameters: {total_params:,}")
    print(f"WDL weight: {args.wdl_weight}")
    if args.policy:
        print(f"Policy head: enabled (weight={args.policy_weight})")

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
            for batch in tqdm(loader, desc=desc, leave=False):
                if len(batch) == 6:  # has best_move
                    wf, bf, s, sc, res, bm = batch
                else:
                    wf, bf, s, sc, res = batch
                    bm = None

                wf, bf, s, sc, res = (
                    wf.to(device),
                    bf.to(device),
                    s.to(device),
                    sc.to(device),
                    res.to(device),
                )
                if bm is not None:
                    bm = bm.to(device)

                if model.use_policy:
                    value_pred, policy_logits = model(wf, bf, s)
                    total_loss += dual_loss(
                        value_pred,
                        policy_logits,
                        sc,
                        res,
                        bm,
                        args.wdl_weight,
                        args.policy_weight,
                    ).item()
                else:
                    pred = model(wf, bf, s)
                    total_loss += nnue_loss(pred, sc, res, args.wdl_weight).item()
                n += 1
        return total_loss / max(n, 1)

    # ---- Baseline loss ----------------------------------------------------
    baseline_train = evaluate(train_loader, "Baseline train")
    baseline_val = evaluate(val_loader, "Baseline val")
    print(f"\nBaseline loss -- train: {baseline_train:.6f}, val: {baseline_val:.6f}")

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
        for batch in pbar:
            if len(batch) == 6:  # has best_move
                wf, bf, s, sc, res, bm = batch
            else:
                wf, bf, s, sc, res = batch
                bm = None

            wf, bf, s, sc, res = (
                wf.to(device),
                bf.to(device),
                s.to(device),
                sc.to(device),
                res.to(device),
            )
            if bm is not None:
                bm = bm.to(device)

            if model.use_policy:
                value_pred, policy_logits = model(wf, bf, s)
                loss = dual_loss(
                    value_pred,
                    policy_logits,
                    sc,
                    res,
                    bm,
                    args.wdl_weight,
                    args.policy_weight,
                )
            else:
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

    export_binary_weights(model, args.export, gcfg)

    # Export quantized version alongside
    quant_path = args.export.replace(".bin", "_quant.bin")
    export_quantized_weights(model, quant_path, gcfg)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train a NNUE for MiniChess / MiniShogi / Gomoku",
    )
    parser.add_argument(
        "--game",
        type=str,
        default=None,
        choices=list(GAME_CONFIGS.keys()),
        help=(
            "Game type (default: auto-detect from data, "
            f"fallback to '{DEFAULT_GAME}'). "
            f"Options: {', '.join(GAME_CONFIGS.keys())}"
        ),
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
        help="Feature type: ps or halfkp (default: halfkp)",
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
    parser.add_argument(
        "--policy",
        action="store_true",
        help="Enable policy head (requires v3 data with best moves)",
    )
    parser.add_argument(
        "--policy-weight",
        type=float,
        default=0.1,
        help="Policy loss weight (default: 0.1)",
    )
    args = parser.parse_args()
    train(args)


if __name__ == "__main__":
    main()
