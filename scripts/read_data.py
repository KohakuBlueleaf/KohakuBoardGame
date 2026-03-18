#!/usr/bin/env python3
"""
read_data.py — Read and inspect MiniChess training data files.

Usage:
    python scripts/read_data.py [file1.bin] [file2.bin] ...

If no files specified, reads data/train.bin by default.
"""

import struct
import sys
import os
import numpy as np

# Must match the C++ structs exactly
HEADER_FMT = "<4sii"      # magic(4) + version(i32) + count(i32) = 12 bytes
HEADER_SIZE = struct.calcsize(HEADER_FMT)

RECORD_FMT = "<60sbh"     # board(60) + player(i8) + score(i16) = 63 bytes
RECORD_SIZE = struct.calcsize(RECORD_FMT)

BOARD_H = 6
BOARD_W = 5

PIECE_NAMES = [".", "P", "R", "N", "B", "Q", "K"]


def read_file(path):
    """Read a .bin data file. Returns (header_info, list_of_records)."""
    with open(path, "rb") as f:
        # Read header
        hdr_data = f.read(HEADER_SIZE)
        if len(hdr_data) < HEADER_SIZE:
            print(f"Error: file too small for header: {path}")
            return None, []

        magic, version, count = struct.unpack(HEADER_FMT, hdr_data)
        magic = magic.decode("ascii", errors="replace")

        if magic != "MCDT":
            print(f"Error: bad magic '{magic}' (expected 'MCDT'): {path}")
            return None, []

        header_info = {"magic": magic, "version": version, "count": count}

        # Read all records
        records = []
        for i in range(count):
            rec_data = f.read(RECORD_SIZE)
            if len(rec_data) < RECORD_SIZE:
                print(f"Warning: truncated at record {i}/{count}")
                break

            board_bytes, player, score = struct.unpack(RECORD_FMT, rec_data)
            # Reshape board bytes into [2][6][5]
            board = np.frombuffer(board_bytes, dtype=np.int8).reshape(2, BOARD_H, BOARD_W)
            records.append({
                "board": board.copy(),
                "player": player,
                "score": score,
            })

        return header_info, records


def print_board(board, player):
    """Print a board state in human-readable format."""
    print(f"  Side to move: {'White (0)' if player == 0 else 'Black (1)'}")
    print(f"  {'  '.join([str(c) for c in range(BOARD_W)])}")
    print(f"  {'-' * (BOARD_W * 3)}")
    for r in range(BOARD_H):
        row_str = ""
        for c in range(BOARD_W):
            w = board[0][r][c]
            b = board[1][r][c]
            if w > 0:
                row_str += f"w{PIECE_NAMES[w]} "
            elif b > 0:
                row_str += f"b{PIECE_NAMES[b]} "
            else:
                row_str += " .  "
        print(f"{r}|{row_str}")
    print()


def main():
    files = sys.argv[1:] if len(sys.argv) > 1 else ["data/train.bin"]

    all_scores = []

    for path in files:
        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue

        file_size = os.path.getsize(path)
        print(f"=== {path} ({file_size} bytes) ===")

        header, records = read_file(path)
        if header is None:
            continue

        print(f"  Magic:   {header['magic']}")
        print(f"  Version: {header['version']}")
        print(f"  Count:   {header['count']}")
        print(f"  Records read: {len(records)}")
        print()

        if not records:
            continue

        scores = np.array([r["score"] for r in records])
        all_scores.extend(scores.tolist())

        print(f"  Score stats:")
        print(f"    Mean:   {scores.mean():.1f}")
        print(f"    Std:    {scores.std():.1f}")
        print(f"    Min:    {scores.min()}")
        print(f"    Max:    {scores.max()}")
        print(f"    Median: {np.median(scores):.1f}")
        print()

        # Score distribution histogram (text-based)
        print(f"  Score distribution:")
        bins = [-10000, -1000, -500, -100, -50, 0, 50, 100, 500, 1000, 10000, 200000]
        hist, _ = np.histogram(scores, bins=bins)
        for i in range(len(hist)):
            lo = bins[i]
            hi = bins[i + 1]
            pct = 100.0 * hist[i] / len(scores)
            bar = "#" * int(pct / 2)
            print(f"    [{lo:>7},{hi:>7}): {hist[i]:>6} ({pct:>5.1f}%) {bar}")
        print()

        # Show a few sample positions
        n_samples = min(3, len(records))
        print(f"  Sample positions ({n_samples}):")
        # Show first, middle, last
        indices = [0, len(records) // 2, len(records) - 1][:n_samples]
        for idx in indices:
            rec = records[idx]
            print(f"  --- Record {idx} (score: {rec['score']}) ---")
            print_board(rec["board"], rec["player"])

    # Combined stats if multiple files
    if len(files) > 1 and all_scores:
        all_scores = np.array(all_scores)
        print(f"\n=== Combined ({len(all_scores)} records) ===")
        print(f"  Mean:   {all_scores.mean():.1f}")
        print(f"  Std:    {all_scores.std():.1f}")
        print(f"  Min:    {all_scores.min()}")
        print(f"  Max:    {all_scores.max()}")


if __name__ == "__main__":
    main()
