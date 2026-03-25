#!/usr/bin/env python3
"""
read_data.py -- Read and inspect training data files for MiniChess / MiniShogi / Connect6.

Usage:
    python scripts/read_data.py [options] [file1.bin] [file2.bin] ...

If no files specified, reads data/train.bin by default.
Game type is auto-detected from data file headers (v4+) or specified via --game.
Defaults to minichess for backward compatibility.
"""

import argparse
import struct
import sys
import os
import numpy as np

# ---------------------------------------------------------------------------
# Game configurations
# ---------------------------------------------------------------------------
GAME_CONFIGS = {
    "minichess": {
        "board_h": 6,
        "board_w": 5,
        "piece_names": [".", "P", "R", "N", "B", "Q", "K"],
        "col_labels": "ABCDE",
        "row_labels": ["6", "5", "4", "3", "2", "1"],
    },
    "minishogi": {
        "board_h": 5,
        "board_w": 5,
        "piece_names": [
            ".",
            "P",
            "S",
            "G",
            "B",
            "R",
            "K",
            "+P",
            "+S",
            "+B",
            "+R",
        ],
        "col_labels": "ABCDE",
        "row_labels": ["5", "4", "3", "2", "1"],
    },
    "connect6": {
        "board_h": 15,
        "board_w": 15,
        "piece_names": [".", "X", "O"],
        "col_labels": "ABCDEFGHIJKLMNO",
        "row_labels": [str(i) for i in range(15, 0, -1)],
    },
    "kohakushogi": {
        "board_h": 7,
        "board_w": 6,
        "piece_names": [
            ".", "P", "S", "G", "L", "N", "B", "R", "K",
            "+P", "+S", "+L", "+N", "+B", "+R",
        ],
        "col_labels": "ABCDEF",
        "row_labels": ["7", "6", "5", "4", "3", "2", "1"],
    },
    "kohakuchess": {
        "board_h": 6,
        "board_w": 6,
        "piece_names": [".", "P", "R", "N", "B", "Q", "K"],
        "col_labels": "ABCDEF",
        "row_labels": ["7", "6", "5", "4", "3", "2", "1"],
    },
}

DEFAULT_GAME = "minichess"


def get_game_config(game_name):
    """Return a game config dict with derived values filled in."""
    name = game_name.lower()
    if name not in GAME_CONFIGS:
        print(
            f"Error: unknown game '{game_name}'. Available: {', '.join(GAME_CONFIGS.keys())}"
        )
        sys.exit(1)
    cfg = dict(GAME_CONFIGS[name])
    cfg["name"] = name
    cfg["num_squares"] = cfg["board_h"] * cfg["board_w"]
    cfg["board_cells"] = 2 * cfg["board_h"] * cfg["board_w"]
    return cfg


# ---------------------------------------------------------------------------
# Header formats
# ---------------------------------------------------------------------------
# Legacy header: magic(4) + version(i32) + count(i32) = 12 bytes
HEADER_FMT = "<4sii"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

# Extended header (v4): legacy + board_h(u16) + board_w(u16) + game_name(16s) = 32 bytes
V4_HEADER_FMT = "<4siiHH16s"
V4_HEADER_SIZE = struct.calcsize(V4_HEADER_FMT)

# v5 header: legacy + board_h(u16) + board_w(u16) + num_hand(u16) + reserved(u16) + game_name(16s) = 36 bytes
V5_HEADER_FMT = "<4siiHHHH16s"
V5_HEADER_SIZE = struct.calcsize(V5_HEADER_FMT)

# Use the largest header size for reading
EXT_HEADER_SIZE = V5_HEADER_SIZE

NO_MOVE = 0xFFFF


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------
def detect_game_from_header(path):
    """Try to auto-detect game from data file header. Returns game name or None."""
    try:
        with open(path, "rb") as f:
            hdr_data = f.read(EXT_HEADER_SIZE)
        if len(hdr_data) < HEADER_SIZE:
            return None

        magic, version, count = struct.unpack(HEADER_FMT, hdr_data[:HEADER_SIZE])
        if magic.decode("ascii", errors="replace") not in ("MCDT", "BGDT"):
            return None

        if version >= 5 and len(hdr_data) >= V5_HEADER_SIZE:
            _, _, _, board_h, board_w, num_hand, _, game_raw = struct.unpack(
                V5_HEADER_FMT, hdr_data[:V5_HEADER_SIZE]
            )
        elif version >= 4 and len(hdr_data) >= V4_HEADER_SIZE:
            _, _, _, board_h, board_w, game_raw = struct.unpack(
                V4_HEADER_FMT, hdr_data[:V4_HEADER_SIZE]
            )
        else:
            return None

        if version >= 4:
            game_name = (
                game_raw.rstrip(b"\x00").decode("ascii", errors="replace").lower()
                .replace("_", "")
            )
            if game_name in GAME_CONFIGS:
                return game_name
            # Try matching by dimensions
            for name, cfg in GAME_CONFIGS.items():
                if cfg["board_h"] == board_h and cfg["board_w"] == board_w:
                    return name
    except (IOError, ValueError):
        pass
    return None


# ---------------------------------------------------------------------------
# Move decoding
# ---------------------------------------------------------------------------
def decode_best_move(best_move, gcfg):
    """Decode best_move into human-readable string. Returns None if no move."""
    if best_move is None or best_move == NO_MOVE:
        return None

    num_squares = gcfg["num_squares"]
    board_w = gcfg["board_w"]
    col_labels = gcfg["col_labels"]
    row_labels = gcfg["row_labels"]

    from_sq = best_move // num_squares
    to_sq = best_move % num_squares
    from_row, from_col = from_sq // board_w, from_sq % board_w
    to_row, to_col = to_sq // board_w, to_sq % board_w

    if (
        from_col < len(col_labels)
        and to_col < len(col_labels)
        and from_row < len(row_labels)
        and to_row < len(row_labels)
    ):
        return (
            f"{col_labels[from_col]}{row_labels[from_row]}"
            f"->{col_labels[to_col]}{row_labels[to_row]}"
        )
    return f"{from_sq}->{to_sq}"


# ---------------------------------------------------------------------------
# File reading
# ---------------------------------------------------------------------------
def read_file(path, gcfg):
    """Read a .bin data file. Returns (header_info, list_of_records)."""
    board_h = gcfg["board_h"]
    board_w = gcfg["board_w"]
    board_cells = gcfg["board_cells"]

    with open(path, "rb") as f:
        # Read header
        hdr_data = f.read(EXT_HEADER_SIZE)
        if len(hdr_data) < HEADER_SIZE:
            print(f"Error: file too small for header: {path}")
            return None, []

        magic, version, count = struct.unpack(HEADER_FMT, hdr_data[:HEADER_SIZE])
        magic_str = magic.decode("ascii", errors="replace")

        if magic_str not in ("MCDT", "BGDT"):
            print(f"Error: bad magic '{magic_str}' (expected 'MCDT' or 'BGDT'): {path}")
            return None, []

        header_info = {"magic": magic_str, "version": version, "count": count}

        # Parse num_hand from v5 header
        num_hand = 0
        if version >= 5 and len(hdr_data) >= V5_HEADER_SIZE:
            _, _, _, _, _, num_hand, _, _ = struct.unpack(
                V5_HEADER_FMT, hdr_data[:V5_HEADER_SIZE]
            )
            f.seek(V5_HEADER_SIZE)
        elif version >= 4 and len(hdr_data) >= V4_HEADER_SIZE:
            f.seek(V4_HEADER_SIZE)
        else:
            f.seek(HEADER_SIZE)

        header_info["num_hand"] = num_hand
        hand_cells = 2 * num_hand if num_hand > 0 else 2  # v5 always has hand[2][max(1,N)]

        # Build record format string
        board_fmt = f"{board_cells}s"
        if version >= 5:
            hand_fmt = f"{hand_cells}s"
            rec_fmt = f"<{board_fmt}{hand_fmt}bhbHH"
        elif version >= 3:
            rec_fmt = f"<{board_fmt}bhbHH"
        elif version == 2:
            rec_fmt = f"<{board_fmt}bhbH"
        elif version == 1:
            rec_fmt = f"<{board_fmt}bh"
        else:
            print(f"Error: unknown version {version}: {path}")
            return None, []

        rec_size = struct.calcsize(rec_fmt)

        # Read all records
        records = []
        for i in range(count):
            rec_data = f.read(rec_size)
            if len(rec_data) < rec_size:
                print(f"Warning: truncated at record {i}/{count}")
                break

            fields = struct.unpack(rec_fmt, rec_data)
            idx = 0
            board_bytes = fields[idx]; idx += 1

            # v5: hand data follows board
            hand = None
            if version >= 5:
                hand_bytes = fields[idx]; idx += 1
                if num_hand > 0:
                    hand = np.frombuffer(hand_bytes, dtype=np.int8).reshape(2, num_hand).copy()

            player = fields[idx]; idx += 1
            score = fields[idx]; idx += 1

            # Reshape board bytes into [2][H][W]
            board = np.frombuffer(board_bytes, dtype=np.int8).reshape(
                2, board_h, board_w
            )

            rec = {
                "board": board.copy(),
                "player": player,
                "score": score,
            }
            if hand is not None:
                rec["hand"] = hand

            if version >= 2:
                rec["result"] = fields[idx]; idx += 1
                rec["ply"] = fields[idx]; idx += 1
            if version >= 3 or version >= 5:
                rec["best_move"] = fields[idx]; idx += 1

            records.append(rec)

        return header_info, records


# ---------------------------------------------------------------------------
# Board display
# ---------------------------------------------------------------------------
def print_board(board, player, gcfg):
    """Print a board state in human-readable format."""
    board_h = gcfg["board_h"]
    board_w = gcfg["board_w"]
    piece_names = gcfg["piece_names"]
    col_labels = gcfg["col_labels"]
    row_labels = gcfg["row_labels"]

    print(f"  Side to move: {'Player 0' if player == 0 else 'Player 1'}")
    col_header = "   ".join(col_labels[:board_w])
    print(f"   {col_header}")
    print(f"  {'-' * (board_w * 4)}")
    for r in range(board_h):
        row_str = ""
        for c in range(board_w):
            w = board[0][r][c]
            b = board[1][r][c]
            if w > 0 and w < len(piece_names):
                # Pad short piece names for alignment
                pname = piece_names[w]
                row_str += f"w{pname:<2s}"
            elif b > 0 and b < len(piece_names):
                pname = piece_names[b]
                row_str += f"b{pname:<2s}"
            else:
                row_str += " .  "
        label = row_labels[r] if r < len(row_labels) else str(r)
        print(f"{label}|{row_str}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Read and inspect training data files for MiniChess / MiniShogi / Connect6",
    )
    parser.add_argument(
        "--game",
        type=str,
        default=None,
        choices=list(GAME_CONFIGS.keys()),
        help=(
            "Game type (default: auto-detect from data, "
            f"fallback to '{DEFAULT_GAME}'). "
            f"Options: {', '.join(GAME_CONFIGS.keys())}"
        ),
    )
    parser.add_argument(
        "files",
        nargs="*",
        default=["data/train.bin"],
        help="Data files to read (default: data/train.bin)",
    )
    args = parser.parse_args()

    files = args.files
    all_scores = []

    for path in files:
        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue

        # Resolve game config for this file
        if args.game:
            gcfg = get_game_config(args.game)
        else:
            detected = detect_game_from_header(path)
            if detected:
                gcfg = get_game_config(detected)
                print(f"  Auto-detected game: {detected}")
            else:
                gcfg = get_game_config(DEFAULT_GAME)

        file_size = os.path.getsize(path)
        print(f"=== {path} ({file_size} bytes) ===")

        header, records = read_file(path, gcfg)
        if header is None:
            continue

        print(f"  Magic:   {header['magic']}")
        print(f"  Version: {header['version']}")
        print(f"  Count:   {header['count']}")
        print(f"  Records read: {len(records)}")
        print(f"  Game:    {gcfg['name']}")
        print(f"  Board:   {gcfg['board_h']}x{gcfg['board_w']}")
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
            move_str = decode_best_move(rec.get("best_move"), gcfg)
            if move_str:
                print(
                    f"  --- Record {idx} (score: {rec['score']}, move: {move_str}) ---"
                )
            else:
                print(f"  --- Record {idx} (score: {rec['score']}) ---")
            extra_parts = []
            if "result" in rec:
                result_map = {1: "win", 0: "draw", -1: "loss"}
                extra_parts.append(
                    f"result={result_map.get(rec['result'], rec['result'])}"
                )
            if "ply" in rec:
                extra_parts.append(f"ply={rec['ply']}")
            if extra_parts:
                print(f"  {', '.join(extra_parts)}")
            print_board(rec["board"], rec["player"], gcfg)

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
