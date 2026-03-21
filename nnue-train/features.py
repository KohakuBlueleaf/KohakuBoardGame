"""Per-sample feature extraction for PS and HalfKP.

Two modes:
- Dense: returns float32 tensors of size (feature_size,). Used for PS.
- Sparse: returns int32 index arrays of active features, padded to max_active.
  The training loop expands these to dense on GPU via scatter. This is critical
  for multi-worker DataLoader on Windows — dense HalfKP tensors (9000-dim)
  exhaust shared memory in the prefetch queue.
"""

import numpy as np
import torch


def extract_ps_features(board: np.ndarray, player: int, gcfg: dict) -> tuple:
    """Extract PieceSquare dense features for one position.

    Args:
        board: (2, H, W) int8
        player: 0 or 1
    Returns:
        (white_feat, black_feat, stm) — float32 tensors
    """
    board_h = gcfg["board_h"]
    board_w = gcfg["board_w"]
    num_sq = gcfg["num_squares"]
    npt = gcfg["num_piece_types"]
    ps_size = gcfg["ps_size"]

    wf = np.zeros(ps_size, dtype=np.float32)
    bf = np.zeros(ps_size, dtype=np.float32)

    for color in range(2):
        for r in range(board_h):
            for c in range(board_w):
                pt = int(board[color, r, c])
                if pt <= 0:
                    continue
                pt_idx = pt - 1
                sq = r * board_w + c
                wf[color * npt * num_sq + pt_idx * num_sq + sq] = 1.0
                mir_sq = (board_h - 1 - r) * board_w + c
                bf[(1 - color) * npt * num_sq + pt_idx * num_sq + mir_sq] = 1.0

    return torch.from_numpy(wf), torch.from_numpy(bf), bool(player)


def extract_halfkp_features(
    board: np.ndarray,
    player: int,
    gcfg: dict,
    hand: np.ndarray = None,
) -> tuple:
    """Extract HalfKP sparse features for one position, return dense tensors.

    Args:
        board: (2, H, W) int8
        player: 0 or 1
        hand: (2, num_hand_types) int8 or None
    Returns:
        (white_feat, black_feat, stm) — float32 dense tensors
    """
    board_h = gcfg["board_h"]
    board_w = gcfg["board_w"]
    num_sq = gcfg["num_squares"]
    num_pt_no_king = gcfg["num_pt_no_king"]
    king_id = gcfg["king_id"]
    num_piece_features = gcfg["num_piece_features"]
    halfkp_size = gcfg["halfkp_size"]
    total_size = gcfg["halfkp_size_with_hand"]

    wf = np.zeros(total_size, dtype=np.float32)
    bf = np.zeros(total_size, dtype=np.float32)

    # Find king squares
    if king_id is not None:
        w_king_sq = 0
        b_king_sq = 0
        for r in range(board_h):
            for c in range(board_w):
                if board[0, r, c] == king_id:
                    w_king_sq = r * board_w + c
                if board[1, r, c] == king_id:
                    b_king_sq = r * board_w + c
        b_king_mir = (
            board_h - 1 - b_king_sq // board_w
        ) * board_w + b_king_sq % board_w
    else:
        w_king_sq = 0
        b_king_mir = 0

    # Board features
    for color in range(2):
        for r in range(board_h):
            for c in range(board_w):
                pt = int(board[color, r, c])
                if pt <= 0 or (king_id is not None and pt == king_id):
                    continue
                pt_idx = pt - 1
                sq = r * board_w + c
                mir_sq = (board_h - 1 - r) * board_w + c

                w_feat = (
                    w_king_sq * num_piece_features
                    + color * (num_pt_no_king * num_sq)
                    + pt_idx * num_sq
                    + sq
                )
                wf[w_feat] += 1.0

                b_feat = (
                    b_king_mir * num_piece_features
                    + (1 - color) * (num_pt_no_king * num_sq)
                    + pt_idx * num_sq
                    + mir_sq
                )
                bf[b_feat] += 1.0

    # Hand features
    if hand is not None and gcfg["has_hand"]:
        num_ht = gcfg["num_hand_types"]
        base = halfkp_size
        for color in range(2):
            for pt in range(num_ht):
                cnt = hand[color, pt]
                if cnt <= 0:
                    continue
                wf[base + color * num_ht + pt] += cnt
                bf[base + (1 - color) * num_ht + pt] += cnt

    return torch.from_numpy(wf), torch.from_numpy(bf), bool(player)


def extract_halfkp_sparse(
    board: np.ndarray,
    player: int,
    gcfg: dict,
    hand: np.ndarray = None,
) -> tuple:
    """Extract HalfKP as sparse index arrays (compact for shared memory).

    Returns:
        (white_indices, black_indices, stm)
        Indices are int32 arrays of length max_active, padded with feature_size.
    """
    board_h = gcfg["board_h"]
    board_w = gcfg["board_w"]
    num_sq = gcfg["num_squares"]
    num_pt_no_king = gcfg["num_pt_no_king"]
    king_id = gcfg["king_id"]
    num_piece_features = gcfg["num_piece_features"]
    halfkp_size = gcfg["halfkp_size"]
    total_size = gcfg["halfkp_size_with_hand"]
    max_active = gcfg["max_active"]

    PAD = total_size
    wi = np.full(max_active, PAD, dtype=np.int32)
    bi = np.full(max_active, PAD, dtype=np.int32)
    wn = 0
    bn = 0

    if king_id is not None:
        w_king_sq = 0
        b_king_sq = 0
        for r in range(board_h):
            for c in range(board_w):
                if board[0, r, c] == king_id:
                    w_king_sq = r * board_w + c
                if board[1, r, c] == king_id:
                    b_king_sq = r * board_w + c
        b_king_mir = (
            board_h - 1 - b_king_sq // board_w
        ) * board_w + b_king_sq % board_w
    else:
        w_king_sq = 0
        b_king_mir = 0

    for color in range(2):
        for r in range(board_h):
            for c in range(board_w):
                pt = int(board[color, r, c])
                if pt <= 0 or (king_id is not None and pt == king_id):
                    continue
                pt_idx = pt - 1
                sq = r * board_w + c
                mir_sq = (board_h - 1 - r) * board_w + c

                if wn < max_active:
                    wi[wn] = (
                        w_king_sq * num_piece_features
                        + color * (num_pt_no_king * num_sq)
                        + pt_idx * num_sq
                        + sq
                    )
                    wn += 1
                if bn < max_active:
                    bi[bn] = (
                        b_king_mir * num_piece_features
                        + (1 - color) * (num_pt_no_king * num_sq)
                        + pt_idx * num_sq
                        + mir_sq
                    )
                    bn += 1

    if hand is not None and gcfg["has_hand"]:
        num_ht = gcfg["num_hand_types"]
        base = halfkp_size
        for color in range(2):
            for pt in range(num_ht):
                cnt = int(hand[color, pt])
                for _ in range(cnt):
                    if wn < max_active:
                        wi[wn] = base + color * num_ht + pt
                        wn += 1
                    if bn < max_active:
                        bi[bn] = base + (1 - color) * num_ht + pt
                        bn += 1

    return torch.from_numpy(wi), torch.from_numpy(bi), bool(player)


def sparse_to_dense(indices: torch.Tensor, feature_size: int) -> torch.Tensor:
    """Expand sparse indices (B, max_active) to dense (B, feature_size) on GPU.

    Padding value = feature_size (out of range), ignored via masking.
    """
    B = indices.shape[0]
    dense = torch.zeros(B, feature_size, device=indices.device)
    valid = indices < feature_size
    clamped = indices.clamp(max=feature_size - 1).long()
    dense.scatter_add_(1, clamped, valid.float())
    return dense
