"""Game-specific configurations for NNUE training."""

import glob
import struct
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Game configurations
# ---------------------------------------------------------------------------
GAME_CONFIGS: Dict[str, dict] = {
    "minichess": {
        "board_h": 6,
        "board_w": 5,
        "num_piece_types": 6,
        "num_pt_no_king": 5,
        "king_id": 6,
        "piece_names": [".", "P", "R", "N", "B", "Q", "K"],
        "has_hand": False,
        "num_hand_types": 0,
    },
    "minishogi": {
        "board_h": 5,
        "board_w": 5,
        "num_piece_types": 11,  # 0=empty, 1-6 base, 7-10 promoted
        "num_pt_no_king": 10,
        "king_id": 6,
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
        "has_hand": True,
        "num_hand_types": 5,
    },
    "gomoku": {
        "board_h": 15,
        "board_w": 15,
        "num_piece_types": 2,
        "num_pt_no_king": 2,
        "king_id": None,
        "piece_names": [".", "X", "O"],
        "has_hand": False,
        "num_hand_types": 0,
    },
    "kohaku_shogi": {
        "board_h": 7,
        "board_w": 6,
        "num_piece_types": 15,  # 0=empty, 1-8 base, 9-14 promoted
        "num_pt_no_king": 13,   # piece types 1-7 + 9-14, excluding KING=8
        "king_id": 8,
        "piece_names": [
            ".",
            "P", "S", "G", "L", "N", "B", "R", "K",
            "+P", "+S", "+L", "+N", "+B", "+R",
        ],
        "has_hand": True,
        "num_hand_types": 7,
    },
    "kohaku_chess": {
        "board_h": 7,
        "board_w": 6,
        "num_piece_types": 6,
        "num_pt_no_king": 5,
        "king_id": 6,
        "piece_names": [".", "P", "R", "N", "B", "Q", "K"],
        "has_hand": False,
        "num_hand_types": 0,
    },
}

DEFAULT_GAME = "minichess"


def get_game_config(game_name: str) -> dict:
    """Return the game config dict, raising an error if unknown."""
    name = game_name.lower()
    if name not in GAME_CONFIGS:
        raise ValueError(
            f"Unknown game '{game_name}'. "
            f"Available: {', '.join(GAME_CONFIGS.keys())}"
        )
    cfg = dict(GAME_CONFIGS[name])
    cfg["name"] = name
    cfg["num_squares"] = cfg["board_h"] * cfg["board_w"]
    cfg["num_colors"] = 2
    cfg["board_cells"] = 2 * cfg["board_h"] * cfg["board_w"]
    cfg["ps_size"] = cfg["num_colors"] * cfg["num_piece_types"] * cfg["num_squares"]
    cfg["num_piece_features"] = (
        cfg["num_colors"] * cfg["num_pt_no_king"] * cfg["num_squares"]
    )
    cfg["halfkp_size"] = cfg["num_squares"] * cfg["num_piece_features"]
    cfg["policy_size"] = cfg["num_squares"] * cfg["num_squares"]
    if cfg["has_hand"] and cfg["num_hand_types"] > 0:
        cfg["hand_feature_size"] = cfg["num_colors"] * cfg["num_hand_types"]
    else:
        cfg["hand_feature_size"] = 0
    cfg["halfkp_size_with_hand"] = cfg["halfkp_size"] + cfg["hand_feature_size"]
    cfg["ps_size_with_hand"] = cfg["ps_size"] + cfg["hand_feature_size"]
    cfg["max_active"] = max(20, cfg["num_squares"] + cfg.get("num_hand_types", 0) * 2)
    return cfg


# ---------------------------------------------------------------------------
# Data file header parsing & game auto-detection
# ---------------------------------------------------------------------------
HEADER_FMT = "<4sii"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

V4_HEADER_FMT = "<4siiHH16s"
V4_HEADER_SIZE = struct.calcsize(V4_HEADER_FMT)

V5_HEADER_FMT = "<4siiHHHH16s"
V5_HEADER_SIZE = struct.calcsize(V5_HEADER_FMT)

EXT_HEADER_SIZE = V5_HEADER_SIZE


def read_data_header(path: str) -> dict:
    """Read a data file header and return metadata dict."""
    with open(path, "rb") as f:
        hdr_data = f.read(EXT_HEADER_SIZE)

    if len(hdr_data) < HEADER_SIZE:
        raise ValueError(f"File too small for header: {path}")

    magic, version, count = struct.unpack(HEADER_FMT, hdr_data[:HEADER_SIZE])
    magic_str = magic.decode("ascii", errors="replace")
    if magic_str not in ("MCDT", "BGDT"):
        raise ValueError(f"Bad magic '{magic_str}' in {path}")

    result = {
        "magic": magic_str,
        "version": version,
        "count": count,
        "board_h": None,
        "board_w": None,
        "num_hand": 0,
        "game_name": None,
    }

    if version >= 5 and len(hdr_data) >= V5_HEADER_SIZE:
        _, _, _, board_h, board_w, num_hand, _, game_name_raw = struct.unpack(
            V5_HEADER_FMT, hdr_data[:V5_HEADER_SIZE]
        )
        game_name = game_name_raw.rstrip(b"\x00").decode("ascii", errors="replace")
        result["board_h"] = board_h
        result["board_w"] = board_w
        result["num_hand"] = num_hand
        result["game_name"] = game_name.lower() if game_name else None
    elif version >= 4 and len(hdr_data) >= V4_HEADER_SIZE:
        _, _, _, board_h, board_w, game_name_raw = struct.unpack(
            V4_HEADER_FMT, hdr_data[:V4_HEADER_SIZE]
        )
        game_name = game_name_raw.rstrip(b"\x00").decode("ascii", errors="replace")
        result["board_h"] = board_h
        result["board_w"] = board_w
        result["game_name"] = game_name.lower() if game_name else None

    return result


def detect_game_from_file(path: str) -> Optional[str]:
    """Try to auto-detect game type from data file header."""
    try:
        hdr = read_data_header(path)
        if hdr["game_name"] and hdr["game_name"] in GAME_CONFIGS:
            return hdr["game_name"]
        if hdr["board_h"] is not None and hdr["board_w"] is not None:
            for name, cfg in GAME_CONFIGS.items():
                if (
                    cfg["board_h"] == hdr["board_h"]
                    and cfg["board_w"] == hdr["board_w"]
                ):
                    return name
    except (ValueError, IOError):
        pass
    return None


def resolve_game(cli_game: Optional[str], data_pattern: str) -> dict:
    """Resolve game config from CLI arg and/or data file auto-detection."""
    detected = None
    files = sorted(glob.glob(data_pattern))
    if files:
        detected = detect_game_from_file(files[0])

    if cli_game:
        game_name = cli_game.lower()
        if detected and detected != game_name:
            print(
                f"Warning: --game={game_name} overrides auto-detected "
                f"game '{detected}' from data file"
            )
        return get_game_config(game_name)

    if detected:
        print(f"Auto-detected game: {detected}")
        return get_game_config(detected)

    print(f"No game specified or detected, defaulting to '{DEFAULT_GAME}'")
    return get_game_config(DEFAULT_GAME)
