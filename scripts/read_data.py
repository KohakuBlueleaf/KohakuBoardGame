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
HEADER_FMT = "<4sii"  # magic(4) + version(i32) + count(i32) = 12 bytes
HEADER_SIZE = struct.calcsize(HEADER_FMT)

# v1: board(60) + player(i8) + score(i16) = 63 bytes
RECORD_V1_FMT = "<60sbh"
RECORD_V1_SIZE = struct.calcsize(RECORD_V1_FMT)

# v2: board(60) + player(i8) + score(i16) + result(i8) + ply(u16) = 66 bytes
RECORD_V2_FMT = "<60sbhbH"
RECORD_V2_SIZE = struct.calcsize(RECORD_V2_FMT)

# v3: adds best_move(u16) = 68 bytes
RECORD_V3_FMT = "<60sbhbHH"  # board(60) + player(i8) + score(i16) + result(i8) + ply(u16) + best_move(u16)
RECORD_V3_SIZE = struct.calcsize(RECORD_V3_FMT)

BOARD_H = 6
BOARD_W = 5

PIECE_NAMES = [".", "P", "R", "N", "B", "Q", "K"]

COL_LABELS = "ABCDE"
ROW_LABELS = ["6", "5", "4", "3", "2", "1"]  # row 0 = "6", row 5 = "1"

NO_MOVE = 0xFFFF


def decode_best_move(best_move):
    """Decode best_move into human-readable string. Returns None if no move."""
    if best_move is None or best_move == NO_MOVE:
        return None
    from_sq = best_move // 30
    to_sq = best_move % 30
    from_row, from_col = from_sq // 5, from_sq % 5
    to_row, to_col = to_sq // 5, to_sq % 5
    return f"{COL_LABELS[from_col]}{ROW_LABELS[from_row]}->{COL_LABELS[to_col]}{ROW_LABELS[to_row]}"


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

        # Select record format based on version
        if version == 1:
            rec_fmt = RECORD_V1_FMT
            rec_size = RECORD_V1_SIZE
        elif version == 2:
            rec_fmt = RECORD_V2_FMT
            rec_size = RECORD_V2_SIZE
        elif version >= 3:
            rec_fmt = RECORD_V3_FMT
            rec_size = RECORD_V3_SIZE
        else:
            print(f"Error: unknown version {version}: {path}")
            return None, []

        # Read all records
        records = []
        for i in range(count):
            rec_data = f.read(rec_size)
            if len(rec_data) < rec_size:
                print(f"Warning: truncated at record {i}/{count}")
                break

            fields = struct.unpack(rec_fmt, rec_data)
            board_bytes = fields[0]
            player = fields[1]
            score = fields[2]

            # Reshape board bytes into [2][6][5]
            board = np.frombuffer(board_bytes, dtype=np.int8).reshape(
                2, BOARD_H, BOARD_W
            )

            rec = {
                "board": board.copy(),
                "player": player,
                "score": score,
            }

            if version >= 2:
                rec["result"] = fields[3]
                rec["ply"] = fields[4]
            if version >= 3:
                rec["best_move"] = fields[5]

            records.append(rec)

        return header_info, records


def print_board(board, player):
    """Print a board state in human-readable format."""
    print(f"  Side to move: {'White (0)' if player == 0 else 'Black (1)'}")
    print(f"   {'   '.join(COL_LABELS)}")
    print(f"  {'-' * (BOARD_W * 4)}")
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
        print(f"{ROW_LABELS[r]}|{row_str}")
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
            move_str = decode_best_move(rec.get("best_move"))
            if move_str:
                print(f"  --- Record {idx} (score: {rec['score']}, move: {move_str}) ---")
            else:
                print(f"  --- Record {idx} (score: {rec['score']}) ---")
            extra_parts = []
            if "result" in rec:
                result_map = {1: "win", 0: "draw", -1: "loss"}
                extra_parts.append(f"result={result_map.get(rec['result'], rec['result'])}")
            if "ply" in rec:
                extra_parts.append(f"ply={rec['ply']}")
            if extra_parts:
                print(f"  {', '.join(extra_parts)}")
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
