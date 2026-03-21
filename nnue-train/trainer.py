"""Training loop for NNUE with callback system.

Execution order per step:
  train step → on_step_end(cb1) → on_step_end(cb2) → ...

Default callback order:
  [ValidationCallback, BestModelCallback, ConsoleLogCallback, WandbCallback, EpochCheckpointCallback]

This guarantees: val runs → best model saves → logs → epoch ckpt.
"""

import os
import time
from datetime import datetime
from typing import List

import numpy as np
import torch
from anyschedule import AnySchedule
from torch.utils.data import DataLoader
from tqdm import tqdm

from .callbacks import (
    Callback,
    TrainState,
    ValidationCallback,
    BestModelCallback,
    ConsoleLogCallback,
    WandbCallback,
    EpochCheckpointCallback,
)
from .data import MmapDataSource
from .dataset import NNUEDataset
from .export import export_binary_weights, export_quantized_weights
from .loss import dual_loss, nnue_loss
from .model import GameNNUE


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
    print(
        f"  PS: {gcfg['ps_size']}, HalfKP: {gcfg['halfkp_size']}, "
        f"Policy: {policy_size}"
    )
    if gcfg["has_hand"]:
        print(f"  Hand types: {gcfg['num_hand_types']}")

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    print(f"Device: {device}")

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

    train_ds = NNUEDataset(source, train_idx, gcfg, feature_type, args.policy)
    val_ds = NNUEDataset(source, val_idx, gcfg, feature_type, args.policy)

    print(f"  Features: {feature_type.upper()}, size: {feature_size}")
    print(f"  Train: {len(train_ds):,}, Val: {len(val_ds):,}")

    loader_kw = dict(
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        pin_memory=(device.type == "cuda"),
        persistent_workers=(args.num_workers > 0),
    )
    train_loader = DataLoader(train_ds, shuffle=True, drop_last=False, **loader_kw)
    val_loader = DataLoader(val_ds, shuffle=False, drop_last=False, **loader_kw)

    steps_per_epoch = len(train_loader)
    total_steps = steps_per_epoch * args.epochs
    print(f"  Steps/epoch: {steps_per_epoch:,}, Total steps: {total_steps:,}")

    # ---- Model -------------------------------------------------------------
    # Use sparse (EmbeddingBag) FT for halfkp — 450x less compute + shared mem
    use_sparse = feature_type == "halfkp"
    model = GameNNUE(
        feature_size=feature_size,
        accum_size=args.accum_size,
        l1_size=32,
        l2_size=32,
        use_policy=args.policy,
        policy_size=policy_size,
        sparse=use_sparse,
    ).to(device)

    total_params = sum(p.numel() for p in model.parameters())
    print(f"Model params: {total_params:,}")
    print(f"WDL weight: {args.wdl_weight}")
    if args.policy:
        print(f"Policy head: weight={args.policy_weight}")

    # ---- Optimizer + scheduler ---------------------------------------------
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    warmup = args.warmup_steps
    if warmup < 0:
        warmup = min(2000, total_steps // 20)

    scheduler = AnySchedule(
        optimizer,
        config={
            "lr": {
                "mode": "cosine",
                "end": total_steps,
                "min_value": 0.01,
                "warmup": warmup,
            },
        },
    )
    print(f"  Scheduler: cosine, warmup={warmup}, end={total_steps}")

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(args.export) or ".", exist_ok=True)

    # ---- Build callback list (ORDER MATTERS) -------------------------------
    val_interval = args.val_every_n_steps
    if val_interval <= 0:
        val_interval = max(500, steps_per_epoch // 4)

    callbacks: List[Callback] = [
        ValidationCallback(every_n_steps=val_interval),
        BestModelCallback(),
        ConsoleLogCallback(),
        WandbCallback(),
        EpochCheckpointCallback(),
    ]
    print(f"  Val every {val_interval:,} steps")
    print(f"  Callbacks: {[type(c).__name__ for c in callbacks]}")

    # ---- Populate TrainState -----------------------------------------------
    state = TrainState()
    state.model = model
    state.optimizer = optimizer
    state.scheduler = scheduler
    state.device = device
    state.global_step = 0
    state.epoch = 0
    state.epochs = args.epochs
    state.ema_loss = None
    state.lr = args.lr
    state.wandb_run = wandb_run
    state.args = args
    state.gcfg = gcfg
    state.train_loader = train_loader
    state.val_loader = val_loader
    state.best_path = args.output.replace(".pt", "_best.pt")

    # ---- on_train_begin ----------------------------------------------------
    for cb in callbacks:
        cb.on_train_begin(state)

    # ---- Training loop -----------------------------------------------------
    print("-" * 72)
    for epoch in range(1, args.epochs + 1):
        state.epoch = epoch
        model.train()

        pbar = tqdm(train_loader, desc=f"Epoch {epoch}/{args.epochs}", leave=False)
        for batch in pbar:
            # --- Forward / backward ---
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
                vp, pl = model(wf, bf, s)
                loss = dual_loss(
                    vp, pl, sc, res, bm, args.wdl_weight, args.policy_weight
                )
            else:
                pred = model(wf, bf, s)
                loss = nnue_loss(pred, sc, res, args.wdl_weight)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            scheduler.step()

            state.global_step += 1
            state.loss = loss.item()
            state.lr = optimizer.param_groups[0]["lr"]

            if state.ema_loss is None:
                state.ema_loss = state.loss
            else:
                state.ema_loss = state.ema_loss * 0.99 + state.loss * 0.01

            pbar.set_postfix(
                loss=f"{state.ema_loss:.6f}",
                lr=f"{state.lr:.2e}",
                step=state.global_step,
            )

            # --- Callbacks: on_step_end (order guaranteed) ---
            for cb in callbacks:
                cb.on_step_end(state)

        # --- Callbacks: on_epoch_end (order guaranteed) ---
        for cb in callbacks:
            cb.on_epoch_end(state)

    # ---- Callbacks: on_train_end -------------------------------------------
    for cb in callbacks:
        cb.on_train_end(state)

    # ---- Final export ------------------------------------------------------
    print("-" * 72)
    m = state.val_metrics or {}
    print("Training complete.")
    print(f"  Steps:         {state.global_step:,}")
    print(f"  Best val loss: {state.best_val_loss:.6f}")
    if "winner_acc" in m:
        print(f"  Winner acc:    {m['winner_acc']:.3f}")
    if "mae_cp" in m:
        print(f"  MAE (cp):      {m['mae_cp']:.1f}")
    print(f"  Params:        {total_params:,}")

    torch.save(model.state_dict(), args.output)
    print(f"  Final model: {args.output}")
    print(f"  Best model:  {state.best_path}")

    export_binary_weights(model, args.export, gcfg)
    quant_path = args.export.replace(".bin", "_quant.bin")
    export_quantized_weights(model, quant_path, gcfg)

    if wandb_run is not None:
        wandb_run.finish()
