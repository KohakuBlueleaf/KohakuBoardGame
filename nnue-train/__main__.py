#!/usr/bin/env python3
"""
nnue-train — Train a NNUE for MiniChess / MiniShogi / Connect6.

Usage:
    python -m nnue-train --data "data/train_*.bin" --features halfkp --epochs 100
    python -m nnue-train --game minishogi --data "data/shogi_*.bin" --features ps

    # Large-scale (50M+): fixed val size, step-based val, more workers
    python -m nnue-train --data "data/*.bin" --val-size 1000000 \\
        --val-every-n-steps 2000 --num-workers 4 --epochs 10
"""

import argparse

from .game_config import GAME_CONFIGS
from .trainer import train


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train a NNUE for MiniChess / MiniShogi / Connect6",
    )
    parser.add_argument(
        "--game",
        type=str,
        default=None,
        help="Game type (default: auto-detect from data). Options: "
        + ", ".join(GAME_CONFIGS.keys()),
    )
    parser.add_argument(
        "--data",
        type=str,
        default="data/train_*.bin",
        help="Glob pattern for data files (default: data/train_*.bin)",
    )
    parser.add_argument(
        "--features",
        type=str,
        default="halfkp",
        choices=["ps", "halfkp"],
        help="Feature type: ps or halfkp (default: halfkp)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="Number of training epochs (default: 100)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8192,
        help="Batch size (default: 8192)",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=1e-3,
        help="Learning rate (default: 1e-3)",
    )
    parser.add_argument(
        "--accum-size",
        type=int,
        default=128,
        help="Accumulator width (default: 128)",
    )
    parser.add_argument(
        "--wdl-weight",
        type=float,
        default=0.5,
        help="WDL blending weight: 0.0=pure score, 1.0=pure result (default: 0.5)",
    )
    parser.add_argument(
        "--min-ply",
        type=int,
        default=0,
        help="Skip positions with ply < this value (default: 0)",
    )
    parser.add_argument(
        "--score-scale",
        type=float,
        default=400.0,
        help="Sigmoid scale for score->win_prob (default: 400, Stockfish convention)",
    )
    parser.add_argument(
        "--score-mean",
        type=float,
        default=0.0,
        help="Score mean shift: sigmoid((score - mean) / scale) (default: 0)",
    )

    # --- Val split (choose one) ---
    val_group = parser.add_mutually_exclusive_group()
    val_group.add_argument(
        "--val-size",
        type=int,
        default=0,
        help="Fixed number of val samples (default: 0 = use --val-split fraction)",
    )
    val_group.add_argument(
        "--val-split",
        type=float,
        default=0.05,
        help="Fraction of data for validation (default: 0.05)",
    )

    # --- Step-based intervals ---
    parser.add_argument(
        "--val-every-n-steps",
        type=int,
        default=-1,
        help="Run validation every N steps (-1=auto ~4x/epoch, 0=epoch-only)",
    )
    parser.add_argument(
        "--warmup-steps",
        type=int,
        default=-1,
        help="LR warmup steps (default: -1 = auto 5%% of total, max 2000)",
    )
    parser.add_argument(
        "--ema-decay",
        type=float,
        default=0.999,
        help="EMA decay for model weights (default: 0.999)",
    )

    # --- wandb ---
    parser.add_argument(
        "--wandb",
        action="store_true",
        help="Enable wandb logging",
    )
    parser.add_argument(
        "--wandb-project",
        type=str,
        default="NNUE",
        help="wandb project name (default: NNUE)",
    )
    parser.add_argument(
        "--wandb-name",
        type=str,
        default=None,
        help="wandb run name (default: auto-generated)",
    )

    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
        help="DataLoader workers (default: 0)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Device: auto, cpu, cuda, cuda:0, etc. (default: auto)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="models/nnue_v1.pt",
        help="Save PyTorch model to (default: models/nnue_v1.pt)",
    )
    parser.add_argument(
        "--export",
        type=str,
        default="models/nnue_v1.bin",
        help="Export binary weights to (default: models/nnue_v1.bin)",
    )
    parser.add_argument(
        "--policy",
        action="store_true",
        help="Enable policy head (requires v3 data with best moves)",
    )
    parser.add_argument(
        "--policy-weight",
        type=float,
        default=0.1,
        help="Policy loss weight (default: 0.1)",
    )
    args = parser.parse_args()
    train(args)


if __name__ == "__main__":
    main()
