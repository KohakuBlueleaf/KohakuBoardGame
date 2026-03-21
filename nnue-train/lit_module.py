"""Lightning module for NNUE training."""

import torch
import torch.nn as nn
import lightning.pytorch as pl
from anyschedule import AnySchedule

from .loss import nnue_loss, dual_loss, SCORE_SCALE, NO_MOVE
from .model import GameNNUE


class NNUELitModule(pl.LightningModule):
    def __init__(
        self,
        feature_size: int,
        accum_size: int = 128,
        l1_size: int = 32,
        l2_size: int = 32,
        sparse: bool = False,
        use_policy: bool = False,
        policy_size: int = 900,
        # Training config
        lr: float = 1e-3,
        wdl_weight: float = 0.5,
        policy_weight: float = 0.1,
        warmup_steps: int = 1000,
        total_steps: int = 100000,
    ):
        super().__init__()
        self.save_hyperparameters()

        self.model = GameNNUE(
            feature_size=feature_size,
            accum_size=accum_size,
            l1_size=l1_size,
            l2_size=l2_size,
            sparse=sparse,
            use_policy=use_policy,
            policy_size=policy_size,
        )

        self.lr = lr
        self.wdl_weight = wdl_weight
        self.policy_weight = policy_weight
        self.warmup_steps = warmup_steps
        self.total_steps = total_steps

    def forward(self, wf, bf, stm):
        return self.model(wf, bf, stm)

    def _compute_loss(self, batch):
        if len(batch) == 6:
            wf, bf, stm, sc, res, bm = batch
        else:
            wf, bf, stm, sc, res = batch
            bm = None

        if self.model.use_policy:
            value_pred, policy_logits = self.model(wf, bf, stm)
            loss = dual_loss(
                value_pred,
                policy_logits,
                sc,
                res,
                bm,
                self.wdl_weight,
                self.policy_weight,
            )
        else:
            value_pred = self.model(wf, bf, stm)
            loss = nnue_loss(value_pred, sc, res, self.wdl_weight)

        return loss, value_pred, sc, res

    def training_step(self, batch, batch_idx):
        loss, _, _, _ = self._compute_loss(batch)
        self.log("train/loss", loss, prog_bar=True)
        return loss

    def validation_step(self, batch, batch_idx):
        loss, value_pred, sc, res = self._compute_loss(batch)

        self.log("val/loss", loss, prog_bar=True, sync_dist=True)

        with torch.no_grad():
            pred_sig = torch.sigmoid(value_pred / SCORE_SCALE)
            pred_winner = (pred_sig > 0.5).float()
            actual_winner = (res > 0).float()
            decisive = res != 0
            if decisive.any():
                self.log(
                    "val/winner_acc",
                    (pred_winner[decisive] == actual_winner[decisive]).float().mean(),
                    sync_dist=True,
                )
            self.log(
                "val/mae_cp",
                (value_pred.detach() - sc).abs().mean(),
                sync_dist=True,
            )

        return loss

    def configure_optimizers(self):
        optimizer = torch.optim.Adam(self.parameters(), lr=self.lr)
        scheduler = AnySchedule(
            optimizer,
            config={
                "lr": {
                    "mode": "cosine",
                    "end": self.total_steps,
                    "min_value": 0.01,
                    "warmup": self.warmup_steps,
                },
            },
        )
        return {
            "optimizer": optimizer,
            "lr_scheduler": {
                "scheduler": scheduler,
                "interval": "step",
                "frequency": 1,
            },
        }
