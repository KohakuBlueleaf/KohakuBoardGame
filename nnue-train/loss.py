"""Loss functions for NNUE training.

Score normalization follows Stockfish/nnue-pytorch convention:
  win_prob = sigmoid((score - score_mean) / score_scale)

score_mean: shifts the score distribution center (default 0 = no shift).
  Useful when handcrafted eval has a systematic bias (e.g. first-mover
  advantage producing mean != 0). The network still outputs raw centipawns;
  only the loss target is adjusted so 50% win_prob corresponds to score_mean
  instead of 0.

score_scale: controls the sigmoid steepness (default 400 = Stockfish).
  Lower values (e.g. 300) make the sigmoid steeper — a smaller advantage
  maps to a higher win probability. Tune this to match your eval's scale.
"""

import torch
import torch.nn as nn

DEFAULT_SCORE_SCALE = 400.0
DEFAULT_SCORE_MEAN = 0.0
NO_MOVE = 0xFFFF


def _score_to_wp(
    score: torch.Tensor,
    score_scale: float = DEFAULT_SCORE_SCALE,
    score_mean: float = DEFAULT_SCORE_MEAN,
) -> torch.Tensor:
    """Convert centipawn score to win probability via sigmoid."""
    return torch.sigmoid((score - score_mean) / score_scale)


def nnue_loss(
    predicted: torch.Tensor,
    score: torch.Tensor,
    result: torch.Tensor,
    wdl_weight: float,
    score_scale: float = DEFAULT_SCORE_SCALE,
    score_mean: float = DEFAULT_SCORE_MEAN,
) -> torch.Tensor:
    """Blended NNUE loss: MSE in sigmoid space.

    target = (1 - wdl_weight) * sigmoid((score - mean) / scale) + wdl_weight * wdl
    where wdl = (result + 1) / 2  maps  -1->0.0, 0->0.5, 1->1.0
    """
    pred_wp = _score_to_wp(predicted, score_scale, score_mean)
    score_wp = _score_to_wp(score, score_scale, score_mean)
    wdl = (result + 1.0) / 2.0
    target = (1.0 - wdl_weight) * score_wp + wdl_weight * wdl
    return torch.mean((pred_wp - target) ** 2)


def dual_loss(
    value_pred: torch.Tensor,
    policy_logits: torch.Tensor,
    score: torch.Tensor,
    result: torch.Tensor,
    best_move: torch.Tensor,
    wdl_weight: float,
    policy_weight: float = 0.1,
    score_scale: float = DEFAULT_SCORE_SCALE,
    score_mean: float = DEFAULT_SCORE_MEAN,
) -> torch.Tensor:
    """Combined value + policy loss."""
    value_loss = nnue_loss(
        value_pred, score, result, wdl_weight, score_scale, score_mean
    )

    has_move = best_move != NO_MOVE
    if has_move.any() and policy_logits is not None:
        valid_logits = policy_logits[has_move]
        valid_targets = best_move[has_move]
        policy_loss = nn.functional.cross_entropy(valid_logits, valid_targets)
        return value_loss + policy_weight * policy_loss
    return value_loss
