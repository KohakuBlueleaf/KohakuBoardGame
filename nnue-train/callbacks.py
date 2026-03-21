"""Trainer callbacks.

Callback list order = execution order. The training loop calls:
  on_train_begin(state)
  on_step_end(state)       — after each optimizer step
  on_epoch_end(state)      — after the last step of each epoch
  on_train_end(state)      — after all epochs
"""

import os

import torch
from tqdm import tqdm

from .loss import dual_loss, nnue_loss, SCORE_SCALE


class TrainState:
    """Mutable bag of training state, passed to every callback."""

    __slots__ = (
        "model",
        "optimizer",
        "scheduler",
        "device",
        "global_step",
        "epoch",
        "epochs",
        "loss",
        "ema_loss",
        "lr",
        "val_metrics",
        "best_val_loss",
        "wandb_run",
        "args",
        "gcfg",
        "train_loader",
        "val_loader",
        "output_dir",
        "best_path",
    )

    def __init__(self):
        self.val_metrics = None
        self.best_val_loss = float("inf")


class Callback:
    def on_train_begin(self, state: TrainState):
        pass

    def on_step_end(self, state: TrainState):
        pass

    def on_epoch_end(self, state: TrainState):
        pass

    def on_train_end(self, state: TrainState):
        pass


# ---------------------------------------------------------------------------
# Validation callback (step-based)
# ---------------------------------------------------------------------------


class ValidationCallback(Callback):
    """Run validation every N steps. Sets state.val_metrics for downstream."""

    def __init__(self, every_n_steps: int):
        self.every_n_steps = every_n_steps

    def on_step_end(self, state: TrainState):
        if state.global_step % self.every_n_steps != 0:
            state.val_metrics = None
            return
        state.val_metrics = _evaluate(
            state.model,
            state.val_loader,
            state.device,
            state.args.wdl_weight,
            state.args.policy_weight,
        )

    def on_train_end(self, state: TrainState):
        # Always run a final val
        state.val_metrics = _evaluate(
            state.model,
            state.val_loader,
            state.device,
            state.args.wdl_weight,
            state.args.policy_weight,
            desc="Final val",
        )


# ---------------------------------------------------------------------------
# Best model saver (fires after val)
# ---------------------------------------------------------------------------


class BestModelCallback(Callback):
    """Save model weights when val loss improves. Must come after ValidationCallback."""

    def on_step_end(self, state: TrainState):
        if state.val_metrics is None:
            return
        val_loss = state.val_metrics["loss"]
        if val_loss < state.best_val_loss:
            state.best_val_loss = val_loss
            torch.save(state.model.state_dict(), state.best_path)

    def on_train_end(self, state: TrainState):
        # Check final val too
        self.on_step_end(state)


# ---------------------------------------------------------------------------
# Console logging (fires after val + best save)
# ---------------------------------------------------------------------------


class ConsoleLogCallback(Callback):
    """Print val results to console. Must come after BestModelCallback."""

    def __init__(self):
        self._prev_best = float("inf")

    def on_step_end(self, state: TrainState):
        if state.val_metrics is None:
            return
        m = state.val_metrics
        improved = state.best_val_loss < self._prev_best
        self._prev_best = state.best_val_loss

        parts = [
            f"[step {state.global_step:>7,}]",
            f"ema={state.ema_loss:.6f}",
            f"val={m['loss']:.6f}",
            f"best={state.best_val_loss:.6f}",
        ]
        if "winner_acc" in m:
            parts.append(f"acc={m['winner_acc']:.3f}")
        parts.append(f"mae={m['mae_cp']:.1f}")
        parts.append(f"lr={state.lr:.2e}")
        if improved:
            parts.append("*saved*")
        tqdm.write("  ".join(parts))

    def on_train_end(self, state: TrainState):
        self.on_step_end(state)


# ---------------------------------------------------------------------------
# wandb logging
# ---------------------------------------------------------------------------


class WandbCallback(Callback):
    """Log train + val metrics to wandb."""

    def on_step_end(self, state: TrainState):
        if state.wandb_run is None:
            return
        log = {
            "train/loss": state.loss,
            "train/ema_loss": state.ema_loss,
            "lr": state.lr,
        }
        if state.val_metrics is not None:
            for k, v in state.val_metrics.items():
                log[f"val/{k}"] = v
        state.wandb_run.log(log, step=state.global_step)

    def on_train_end(self, state: TrainState):
        if state.wandb_run is None or state.val_metrics is None:
            return
        state.wandb_run.log(
            {f"val/{k}": v for k, v in state.val_metrics.items()},
            step=state.global_step,
        )


# ---------------------------------------------------------------------------
# Epoch checkpoint (for resume)
# ---------------------------------------------------------------------------


class EpochCheckpointCallback(Callback):
    """Save full training state at end of each epoch (for resume)."""

    def on_epoch_end(self, state: TrainState):
        ckpt = {
            "epoch": state.epoch,
            "global_step": state.global_step,
            "model_state_dict": state.model.state_dict(),
            "optimizer_state_dict": state.optimizer.state_dict(),
            "scheduler_state_dict": state.scheduler.state_dict(),
            "best_val_loss": state.best_val_loss,
            "ema_loss": state.ema_loss,
            "args": vars(state.args),
        }
        ckpt_path = state.args.output.replace(".pt", f"_epoch{state.epoch}.pt")
        torch.save(ckpt, ckpt_path)
        tqdm.write(
            f"--- Epoch {state.epoch}/{state.epochs} done "
            f"(step {state.global_step:,}, ema={state.ema_loss:.6f}) "
            f"ckpt: {ckpt_path} ---"
        )


# ---------------------------------------------------------------------------
# Eval helper (used by ValidationCallback)
# ---------------------------------------------------------------------------


@torch.no_grad()
def _evaluate(model, loader, device, wdl_weight, policy_weight, desc="Val"):
    model.eval()
    accum = {}
    n = 0
    for batch in tqdm(loader, desc=desc, leave=False):
        if len(batch) == 6:
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
                value_pred, policy_logits, sc, res, bm, wdl_weight, policy_weight
            )
        else:
            value_pred = model(wf, bf, s)
            loss = nnue_loss(value_pred, sc, res, wdl_weight)

        metrics = {"loss": loss.item()}
        pred_sig = torch.sigmoid(value_pred / SCORE_SCALE)
        pred_winner = (pred_sig > 0.5).float()
        actual_winner = (res > 0).float()
        decisive = res != 0
        if decisive.any():
            metrics["winner_acc"] = (
                (pred_winner[decisive] == actual_winner[decisive]).float().mean().item()
            )
        metrics["mae_cp"] = (value_pred.detach() - sc).abs().mean().item()

        for k, v in metrics.items():
            accum[k] = accum.get(k, 0.0) + v
        n += 1

    model.train()
    return {k: v / max(n, 1) for k, v in accum.items()}
