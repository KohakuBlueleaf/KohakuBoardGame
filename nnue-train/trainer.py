"""NNUE Trainer — clean class-based training loop.

Lean custom loop for maximum throughput on small models where
Lightning overhead (~30-40%) is significant. Uses AnySchedule for
step-based LR, wandb for logging, step-based val, epoch checkpoints.
"""

import os
import time
from datetime import datetime
from typing import Optional

import numpy as np
import torch
from anyschedule import AnySchedule
from torch.utils.data import DataLoader
from tqdm import tqdm

from .data import MmapDataSource
from .dataset import NNUEDataset
from .export import export_binary_weights, export_quantized_weights
from .loss import dual_loss, nnue_loss, SCORE_SCALE
from .model import GameNNUE


class NNUETrainer:
    """Step-based NNUE trainer with val, checkpointing, and wandb."""

    def __init__(
        self,
        model: GameNNUE,
        train_loader: DataLoader,
        val_loader: DataLoader,
        *,
        lr: float = 1e-3,
        wdl_weight: float = 0.5,
        policy_weight: float = 0.1,
        warmup_steps: int = 1000,
        total_steps: int = 100000,
        val_every_n_steps: int = 1000,
        output_path: str = "models/nnue.pt",
        device: torch.device = torch.device("cpu"),
        wandb_run=None,
    ):
        self.model = model.to(device)
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.device = device
        self.wdl_weight = wdl_weight
        self.policy_weight = policy_weight
        self.val_every_n_steps = val_every_n_steps
        self.output_path = output_path
        self.wandb_run = wandb_run

        self.optimizer = torch.optim.Adam(model.parameters(), lr=lr)
        self.scheduler = AnySchedule(
            self.optimizer,
            config={
                "lr": {
                    "mode": "cosine",
                    "end": total_steps,
                    "min_value": 0.01,
                    "warmup": warmup_steps,
                },
            },
        )

        self.global_step = 0
        self.best_val_loss = float("inf")
        self.best_path = output_path.replace(".pt", "_best.pt")

    # ------------------------------------------------------------------
    # Core steps
    # ------------------------------------------------------------------

    def _forward_loss(self, batch):
        """Unpack batch, forward, compute loss. Returns (loss, value_pred, sc, res)."""
        if len(batch) == 6:
            wf, bf, stm, sc, res, bm = [x.to(self.device) for x in batch]
        else:
            wf, bf, stm, sc, res = [x.to(self.device) for x in batch]
            bm = None

        if self.model.use_policy:
            vp, pl = self.model(wf, bf, stm)
            loss = dual_loss(vp, pl, sc, res, bm, self.wdl_weight, self.policy_weight)
        else:
            vp = self.model(wf, bf, stm)
            loss = nnue_loss(vp, sc, res, self.wdl_weight)

        return loss, vp, sc, res

    def train_step(self, batch) -> float:
        """Single training step. Returns loss value."""
        self.model.train()
        loss, _, _, _ = self._forward_loss(batch)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        self.scheduler.step()
        self.global_step += 1
        return loss.item()

    @torch.no_grad()
    def validate(self) -> dict:
        """Run full validation. Returns metrics dict."""
        self.model.eval()
        total_loss = 0.0
        total_mae = 0.0
        total_correct = 0
        total_decisive = 0
        n = 0

        for batch in self.val_loader:
            loss, vp, sc, res = self._forward_loss(batch)
            total_loss += loss.item()
            total_mae += (vp - sc).abs().mean().item()

            pred_winner = (torch.sigmoid(vp / SCORE_SCALE) > 0.5).float()
            actual_winner = (res > 0).float()
            decisive = res != 0
            if decisive.any():
                total_correct += (
                    (pred_winner[decisive] == actual_winner[decisive]).sum().item()
                )
                total_decisive += decisive.sum().item()
            n += 1

        metrics = {
            "loss": total_loss / max(n, 1),
            "mae_cp": total_mae / max(n, 1),
        }
        if total_decisive > 0:
            metrics["winner_acc"] = total_correct / total_decisive
        return metrics

    # ------------------------------------------------------------------
    # Checkpointing
    # ------------------------------------------------------------------

    def save_best(self, val_loss: float):
        """Save model if val loss improved."""
        if val_loss < self.best_val_loss:
            self.best_val_loss = val_loss
            torch.save(self.model.state_dict(), self.best_path)
            return True
        return False

    def save_epoch_checkpoint(self, epoch: int, ema_loss: float):
        """Save full state for resume."""
        ckpt_path = self.output_path.replace(".pt", f"_epoch{epoch}.pt")
        torch.save(
            {
                "epoch": epoch,
                "global_step": self.global_step,
                "model_state_dict": self.model.state_dict(),
                "optimizer_state_dict": self.optimizer.state_dict(),
                "scheduler_state_dict": self.scheduler.state_dict(),
                "best_val_loss": self.best_val_loss,
                "ema_loss": ema_loss,
            },
            ckpt_path,
        )
        return ckpt_path

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_val(self, ema_loss: float, metrics: dict, improved: bool):
        lr = self.optimizer.param_groups[0]["lr"]
        parts = [
            f"[step {self.global_step:>7,}]",
            f"ema={ema_loss:.6f}",
            f"val={metrics['loss']:.6f}",
            f"best={self.best_val_loss:.6f}",
        ]
        if "winner_acc" in metrics:
            parts.append(f"acc={metrics['winner_acc']:.3f}")
        parts.append(f"mae={metrics['mae_cp']:.1f}")
        parts.append(f"lr={lr:.2e}")
        if improved:
            parts.append("*saved*")
        tqdm.write("  ".join(parts))

        if self.wandb_run is not None:
            log = {f"val/{k}": v for k, v in metrics.items()}
            log["lr"] = lr
            self.wandb_run.log(log, step=self.global_step)

    def _log_train(self, loss: float, ema_loss: float):
        if self.wandb_run is not None:
            self.wandb_run.log(
                {
                    "train/loss": loss,
                    "train/ema_loss": ema_loss,
                },
                step=self.global_step,
            )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def fit(self, epochs: int):
        """Run training for N epochs."""
        ema_loss = None
        print("-" * 72)

        for epoch in range(1, epochs + 1):
            pbar = tqdm(self.train_loader, desc=f"Epoch {epoch}/{epochs}", leave=False)
            for batch in pbar:
                loss = self.train_step(batch)

                if ema_loss is None:
                    ema_loss = loss
                else:
                    ema_loss = ema_loss * 0.99 + loss * 0.01

                pbar.set_postfix(
                    loss=f"{ema_loss:.6f}",
                    lr=f"{self.optimizer.param_groups[0]['lr']:.2e}",
                    step=self.global_step,
                )

                # Step-based val
                if self.global_step % self.val_every_n_steps == 0:
                    metrics = self.validate()
                    improved = self.save_best(metrics["loss"])
                    self._log_val(ema_loss, metrics, improved)

                # wandb train logging (every 50 steps to reduce overhead)
                elif self.wandb_run is not None and self.global_step % 50 == 0:
                    self._log_train(loss, ema_loss)

            # Epoch checkpoint
            ckpt_path = self.save_epoch_checkpoint(epoch, ema_loss)
            tqdm.write(
                f"--- Epoch {epoch}/{epochs} done "
                f"(step {self.global_step:,}, ema={ema_loss:.6f}) "
                f"ckpt: {ckpt_path} ---"
            )

        # Final val
        metrics = self.validate()
        improved = self.save_best(metrics["loss"])
        self._log_val(ema_loss, metrics, improved)

        return metrics


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _generate_run_name(args, gcfg):
    ts = datetime.now().strftime("%m%d-%H%M")
    game = gcfg["name"][:2].upper()
    feat = args.features[0].upper()
    parts = [
        game,
        f"{feat}{args.accum_size}",
        f"lr{args.lr:.0e}",
        f"bs{args.batch_size}",
        f"wdl{args.wdl_weight}",
    ]
    if args.policy:
        parts.append(f"pol{args.policy_weight}")
    parts.append(f"{args.epochs}ep")
    parts.append(ts)
    return "_".join(parts)


def train(args) -> None:
    from .game_config import resolve_game

    gcfg = resolve_game(args.game, args.data)
    game_name = gcfg["name"]
    policy_size = gcfg["policy_size"]

    print(f"Game: {game_name}")
    print(
        f"  Board: {gcfg['board_h']}x{gcfg['board_w']}, "
        f"Piece types: {gcfg['num_piece_types']}, "
        f"Squares: {gcfg['num_squares']}"
    )
    if gcfg["has_hand"]:
        print(f"  Hand types: {gcfg['num_hand_types']}")

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    print(f"Device: {device}")

    # ---- Data --------------------------------------------------------------
    print("Indexing data files (memory-mapped)...")
    t0 = time.time()
    source = MmapDataSource(args.data, gcfg, min_ply=args.min_ply)
    print(f"  Indexing done in {time.time() - t0:.2f}s")

    N = len(source)
    if N == 0:
        print("Error: no valid records found")
        return

    perm = np.random.RandomState(seed=42).permutation(N)
    val_size = (
        min(args.val_size, N // 2)
        if args.val_size > 0
        else max(1, int(N * args.val_split))
    )
    train_idx, val_idx = perm[val_size:], perm[:val_size]

    feature_type = args.features.lower()
    feature_size = (
        gcfg["ps_size_with_hand"]
        if feature_type == "ps"
        else gcfg["halfkp_size_with_hand"]
    )
    use_sparse = feature_type == "halfkp"

    train_ds = NNUEDataset(source, train_idx, gcfg, feature_type, args.policy)
    val_ds = NNUEDataset(source, val_idx, gcfg, feature_type, args.policy)

    print(f"  Features: {feature_type.upper()}, size: {feature_size}")
    print(f"  Train: {len(train_ds):,}, Val: {len(val_ds):,}")

    loader_kw = dict(
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        pin_memory=True,
        persistent_workers=(args.num_workers > 0),
    )
    train_loader = DataLoader(train_ds, shuffle=True, drop_last=False, **loader_kw)
    val_loader = DataLoader(val_ds, shuffle=False, drop_last=False, **loader_kw)

    steps_per_epoch = len(train_loader)
    total_steps = steps_per_epoch * args.epochs

    val_interval = args.val_every_n_steps
    if val_interval <= 0:
        val_interval = max(500, steps_per_epoch // 4)

    warmup = args.warmup_steps
    if warmup < 0:
        warmup = min(2000, total_steps // 20)

    print(f"  Steps/epoch: {steps_per_epoch:,}, Total steps: {total_steps:,}")
    print(f"  Scheduler: cosine, warmup={warmup}, end={total_steps}")
    print(f"  Val every {val_interval:,} steps")

    # ---- Model -------------------------------------------------------------
    model = GameNNUE(
        feature_size=feature_size,
        accum_size=args.accum_size,
        l1_size=32,
        l2_size=32,
        sparse=use_sparse,
        use_policy=args.policy,
        policy_size=policy_size,
    )
    total_params = sum(p.numel() for p in model.parameters())
    print(f"  Model params: {total_params:,}")

    # ---- wandb -------------------------------------------------------------
    wandb_run = None
    if args.wandb:
        import wandb

        run_name = args.wandb_name or _generate_run_name(args, gcfg)
        wandb_run = wandb.init(
            project=args.wandb_project,
            name=run_name,
            config={k: v for k, v in vars(args).items() if k != "wandb_name"},
        )
        print(f"  wandb: {args.wandb_project}/{run_name}")

    # ---- Train -------------------------------------------------------------
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(args.export) or ".", exist_ok=True)

    trainer = NNUETrainer(
        model,
        train_loader,
        val_loader,
        lr=args.lr,
        wdl_weight=args.wdl_weight,
        policy_weight=args.policy_weight,
        warmup_steps=warmup,
        total_steps=total_steps,
        val_every_n_steps=val_interval,
        output_path=args.output,
        device=device,
        wandb_run=wandb_run,
    )

    metrics = trainer.fit(args.epochs)

    # ---- Export -------------------------------------------------------------
    print("-" * 72)
    print("Training complete.")
    print(f"  Steps:         {trainer.global_step:,}")
    print(f"  Best val loss: {trainer.best_val_loss:.6f}")
    if "winner_acc" in metrics:
        print(f"  Winner acc:    {metrics['winner_acc']:.3f}")
    print(f"  MAE (cp):      {metrics['mae_cp']:.1f}")
    print(f"  Params:        {total_params:,}")

    torch.save(model.state_dict(), args.output)
    print(f"  Final model: {args.output}")
    print(f"  Best model:  {trainer.best_path}")

    export_binary_weights(model, args.export, gcfg)
    quant_path = args.export.replace(".bin", "_quant.bin")
    export_quantized_weights(model, quant_path, gcfg)

    if wandb_run is not None:
        wandb_run.finish()
