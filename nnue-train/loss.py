"""Loss functions for NNUE training."""

import torch
import torch.nn as nn

SCORE_SCALE = 400.0
NO_MOVE = 0xFFFF


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
    """Combined value + policy loss."""
    value_loss = nnue_loss(value_pred, score, result, wdl_weight)

    has_move = best_move != NO_MOVE
    if has_move.any() and policy_logits is not None:
        valid_logits = policy_logits[has_move]
        valid_targets = best_move[has_move]
        policy_loss = nn.functional.cross_entropy(valid_logits, valid_targets)
        return value_loss + policy_weight * policy_loss
    return value_loss
