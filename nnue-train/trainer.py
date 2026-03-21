"""NNUE training entry point using PyTorch Lightning."""

import os
import time
from datetime import datetime

import numpy as np
import torch
from torch.utils.data import DataLoader

import lightning.pytorch as pl
from lightning.pytorch.callbacks import (
    ModelCheckpoint,
    LearningRateMonitor,
)
from lightning.pytorch.loggers import WandbLogger

from .data import MmapDataSource
from .dataset import NNUEDataset
from .export import export_binary_weights, export_quantized_weights
from .lit_module import NNUELitModule


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
    print(
        f"  PS: {gcfg['ps_size']}, HalfKP: {gcfg['halfkp_size']}, "
        f"Policy: {policy_size}"
    )
    if gcfg["has_hand"]:
        print(f"  Hand types: {gcfg['num_hand_types']}")

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

    # ---- Resolve val interval ----------------------------------------------
    val_interval = args.val_every_n_steps
    if val_interval <= 0:
        val_interval = max(500, steps_per_epoch // 4)

    warmup = args.warmup_steps
    if warmup < 0:
        warmup = min(2000, total_steps // 20)

    print(f"  Steps/epoch: {steps_per_epoch:,}, Total steps: {total_steps:,}")
    print(f"  Scheduler: cosine, warmup={warmup}, end={total_steps}")
    print(f"  Val every {val_interval:,} steps")

    # ---- Lightning module --------------------------------------------------
    model = NNUELitModule(
        feature_size=feature_size,
        accum_size=args.accum_size,
        l1_size=32,
        l2_size=32,
        sparse=use_sparse,
        use_policy=args.policy,
        policy_size=policy_size,
        lr=args.lr,
        wdl_weight=args.wdl_weight,
        policy_weight=args.policy_weight,
        warmup_steps=warmup,
        total_steps=total_steps,
    )

    total_params = sum(p.numel() for p in model.parameters())
    print(f"  Model params: {total_params:,}")

    # ---- Logger ------------------------------------------------------------
    logger = None
    if args.wandb:
        run_name = args.wandb_name or _generate_run_name(args, gcfg)
        logger = WandbLogger(
            project=args.wandb_project,
            name=run_name,
            config={k: v for k, v in vars(args).items() if k != "wandb_name"},
        )
        print(f"  wandb: {args.wandb_project}/{run_name}")

    # ---- Callbacks ---------------------------------------------------------
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(args.export) or ".", exist_ok=True)

    output_dir = os.path.dirname(args.output) or "."
    stem = os.path.splitext(os.path.basename(args.output))[0]

    callbacks = [
        LearningRateMonitor(logging_interval="step"),
        # Epoch-based checkpoint for resume
        ModelCheckpoint(
            dirpath=output_dir,
            filename=stem + "_epoch{epoch}",
            every_n_epochs=1,
            save_last=True,
        ),
        # Step-based best model by val loss
        ModelCheckpoint(
            dirpath=output_dir,
            filename=stem + "_best",
            monitor="val/loss",
            mode="min",
            save_top_k=1,
            every_n_train_steps=val_interval,
        ),
    ]

    # ---- Trainer -----------------------------------------------------------
    trainer = pl.Trainer(
        max_epochs=args.epochs,
        accelerator="auto",
        devices=1,
        logger=logger,
        callbacks=callbacks,
        val_check_interval=val_interval,
        log_every_n_steps=50,
    )

    # ---- Train -------------------------------------------------------------
    trainer.fit(model, train_loader, val_loader)

    # ---- Export weights -----------------------------------------------------
    print("-" * 72)
    print("Training complete.")

    # Save final model weights
    torch.save(model.model.state_dict(), args.output)
    print(f"  Final model: {args.output}")

    export_binary_weights(model.model, args.export, gcfg)
    quant_path = args.export.replace(".bin", "_quant.bin")
    export_quantized_weights(model.model, quant_path, gcfg)
