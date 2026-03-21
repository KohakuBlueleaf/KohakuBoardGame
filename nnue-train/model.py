"""NNUE model architecture.

Two FT modes:
- Dense: nn.Linear(feature_size, accum_size) — takes (B, feature_size) float tensors.
- Sparse: nn.EmbeddingBag(feature_size, accum_size) — takes (B, max_active) int indices.
  Only sums the active feature rows (~20 out of 9000), 450x less compute.
"""

import torch
import torch.nn as nn


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
        sparse: bool = False,
    ):
        super().__init__()
        self.feature_size = feature_size
        self.accum_size = accum_size
        self.l1_size = l1_size
        self.l2_size = l2_size
        self.use_policy = use_policy
        self.policy_size = policy_size
        self.sparse = sparse

        if sparse:
            # EmbeddingBag: weight is (feature_size, accum_size)
            # Equivalent to Linear but takes index arrays instead of dense vectors
            self.ft = nn.EmbeddingBag(
                feature_size, accum_size, mode="sum", padding_idx=None
            )
            self.ft_bias = nn.Parameter(torch.zeros(accum_size))
        else:
            self.ft = nn.Linear(feature_size, accum_size)

        self.l1 = nn.Linear(accum_size * 2, l1_size)
        self.l2 = nn.Linear(l1_size, l2_size)
        self.out = nn.Linear(l2_size, 1)

        if use_policy:
            self.policy_l1 = nn.Linear(accum_size * 2, 128)
            self.policy_out = nn.Linear(128, policy_size)

    def _ft_sparse(self, indices: torch.Tensor) -> torch.Tensor:
        """Feature transform via EmbeddingBag. indices: (B, max_active) int32.

        Padding value = feature_size (out of range for EmbeddingBag).
        We clamp to valid range and zero out padding contributions.
        """
        B, M = indices.shape
        # Build per_sample_weights: 1.0 for valid, 0.0 for padding
        valid = (indices < self.feature_size).float()
        clamped = indices.clamp(max=self.feature_size - 1).long()
        # Flatten for EmbeddingBag
        flat_idx = clamped.reshape(-1)
        flat_w = valid.reshape(-1)
        offsets = torch.arange(0, B * M, M, device=indices.device, dtype=torch.long)
        return self.ft(flat_idx, offsets, per_sample_weights=flat_w) + self.ft_bias

    def forward(self, white_features, black_features, stm):
        if self.sparse:
            w_accum = screlu(self._ft_sparse(white_features))
            b_accum = screlu(self._ft_sparse(black_features))
        else:
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
            p = torch.relu(self.policy_l1(x))
            policy_logits = self.policy_out(p)
            return value, policy_logits
        return value

    def get_linear_ft_state(self) -> dict:
        """Get FT weights in Linear-compatible format for export.

        Returns dict with 'ft.weight' (accum, feat) and 'ft.bias' (accum,).
        """
        if self.sparse:
            # EmbeddingBag weight: (feat, accum) → Linear weight: (accum, feat)
            return {
                "ft.weight": self.ft.weight.data.t(),
                "ft.bias": self.ft_bias.data,
            }
        else:
            return {
                "ft.weight": self.ft.weight.data,
                "ft.bias": self.ft.bias.data,
            }


# Backward-compatible alias
MiniChessNNUE = GameNNUE
