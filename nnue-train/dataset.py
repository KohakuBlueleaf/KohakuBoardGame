"""PyTorch Datasets: memory-mapped with on-the-fly feature extraction.

Key design: raw data lives in mmap'd files. Each __getitem__ reads one
record and extracts features on the fly. This keeps RAM at O(index_size)
instead of O(N * feature_size).  DataLoader workers parallelise the I/O
and feature extraction automatically.

For HalfKP, features are returned as sparse index arrays (int32, ~80 bytes)
instead of dense tensors (float32, ~36KB). The training loop expands to
dense on GPU via scatter. This avoids exhausting Windows shared memory
when using many DataLoader workers.
"""

import numpy as np
import torch
from torch.utils.data import Dataset

from .data import MmapDataSource, NO_MOVE
from .features import (
    extract_halfkp_features,
    extract_halfkp_sparse,
    extract_ps_features,
)


class NNUEDataset(Dataset):
    """Memory-mapped dataset with lazy feature extraction.

    For halfkp: returns sparse indices (expanded to dense on GPU in train loop).
    For ps: returns dense tensors directly.
    """

    def __init__(
        self,
        source: MmapDataSource,
        indices: np.ndarray,
        gcfg: dict,
        feature_type: str = "halfkp",
        use_policy: bool = False,
    ):
        self.source = source
        self.indices = indices
        self.gcfg = gcfg
        self.feature_type = feature_type
        self.use_policy = use_policy

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, idx):
        global_idx = self.indices[idx]
        rec = self.source.get_record(int(global_idx))

        board = rec["board"]
        player = rec["player"]
        hand = rec["hand"]

        if self.feature_type == "ps":
            wf, bf, stm = extract_ps_features(board, player, self.gcfg)
        else:
            # Sparse: returns int32 index arrays (~80 bytes vs ~36KB dense)
            wf, bf, stm = extract_halfkp_sparse(board, player, self.gcfg, hand)

        score = torch.tensor(rec["score"], dtype=torch.float32)
        result = torch.tensor(rec["result"], dtype=torch.float32)
        stm_t = torch.tensor(stm, dtype=torch.bool)

        if self.use_policy:
            bm = torch.tensor(rec["best_move"], dtype=torch.int64)
            return wf, bf, stm_t, score, result, bm
        return wf, bf, stm_t, score, result
