"""Kohaku Chess game module for CLI -- board display, human input, game logic."""

import sys

try:
    from gui.games.kohaku_chess_engine import (
        KohakuChessState,
        format_move,
        BOARD_H,
        BOARD_W,
        MAX_STEP,
        PIECE_UNICODE,
    )
except ImportError:
    raise ImportError(
        "Kohaku Chess CLI requires gui.games.kohaku_chess_engine. "
        "Make sure the gui package is on sys.path."
    )

COL_LABELS = "ABCDEF"
ROW_LABELS = "7654321"


def print_board(state, game_ctx):
    """Print Kohaku Chess board with Unicode chess pieces from White's perspective."""
    print()
    print("    " + "  ".join(game_ctx["col_labels"]))
    for r in range(game_ctx["board_h"]):
        rank_label = game_ctx["row_labels"][r]
        row_chars = []
        for c in range(game_ctx["board_w"]):
            w_piece = state.board[0][r][c]
            b_piece = state.board[1][r][c]
            if w_piece:
                row_chars.append(game_ctx["piece_unicode"][0][w_piece])
            elif b_piece:
                row_chars.append(game_ctx["piece_unicode"][1][b_piece])
            else:
                row_chars.append(".")
        print(f" {rank_label}  " + "  ".join(row_chars) + f"  {rank_label}")
    print("    " + "  ".join(game_ctx["col_labels"]))
    print()


def get_human_move(state, game_ctx):
    """Prompt human player for a Kohaku Chess move via numbered list or algebraic notation."""
    legal = state.legal_actions
    player_name = "White" if state.player == 0 else "Black"

    print(f"  {player_name}'s legal moves:")
    entries = [
        f"{i + 1:>3}. {game_ctx['format_move'](mv)}" for i, mv in enumerate(legal)
    ]
    cols = 4
    for i in range(0, len(entries), cols):
        row = entries[i : i + cols]
        print("  " + "    ".join(f"{e:<16}" for e in row))
    print()

    while True:
        try:
            raw = input(f"  Enter move number (or algebraic e.g. b2b3): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGame aborted.")
            sys.exit(0)

        if not raw:
            continue

        try:
            num = int(raw)
            if 1 <= num <= len(legal):
                return legal[num - 1]
            print(f"  Invalid number. Enter 1-{len(legal)}.")
            continue
        except ValueError:
            pass

        uci_str = raw.replace("-", "").replace(">", "").lower()
        if len(uci_str) >= 4:
            try:
                move = game_ctx["uci_to_move"](uci_str)
                if move in legal:
                    return move
                print(f"  '{raw}' is not a legal move.")
                continue
            except (ValueError, IndexError, KeyError):
                pass

        print(
            f"  Could not parse '{raw}'. Enter a move number or algebraic (e.g. b2b3)."
        )


def check_game_over(state):
    """Check if the game is over. Returns (result, winner).

    result: 'win', 'draw', 'no_moves', or None (game continues).
    winner: 0 (White) or 1 (Black) for 'win'/'no_moves', None otherwise.
    """
    result, winner = state.check_game_over()
    if result == "win":
        return ("win", winner)
    elif result in ("draw", "stalemate"):
        return ("draw", None)
    elif result in ("checkmate", "perpetual_check"):
        return (result, winner)

    if not state.legal_actions:
        # Stalemate fallback (chess rule): no legal moves = draw
        return ("draw", None)

    return (None, None)


def apply_move(state, uci_str, game_ctx):
    """Apply a UCI move string to the state. Returns (new_state, move_tuple)."""
    move = game_ctx["uci_to_move"](uci_str)
    return state.next_state(move), move


def uci_to_move(uci_str):
    """Convert a UCI move string to internal move tuple.

    Formats:
        'a1b2'      -> ((from_r, from_c), (to_r, to_c))    board move
        'a7a8q'     -> promotion to queen
        'a7a8r'     -> promotion to rook
        'a7a8b'     -> promotion to bishop
        'a7a8n'     -> promotion to knight
    """
    if uci_str is None or len(uci_str) < 4:
        return None

    from_col = ord(uci_str[0].lower()) - ord("a")
    from_row = BOARD_H - int(uci_str[1])
    to_col = ord(uci_str[2].lower()) - ord("a")
    to_row = BOARD_H - int(uci_str[3])

    # Check for promotion suffix
    if len(uci_str) >= 5:
        promo_char = uci_str[4].lower()
        promo_map = {"q": 1, "r": 2, "b": 3, "n": 4}
        promo_idx = promo_map.get(promo_char, 0)
        if promo_idx > 0:
            to_row += BOARD_H * promo_idx

    return ((from_row, from_col), (to_row, to_col))


def move_to_uci(move):
    """Convert internal move tuple to UCI string."""
    (fr, fc), (tr, tc) = move

    actual_tr = tr % BOARD_H
    promo_idx = tr // BOARD_H

    s = (
        chr(ord("a") + fc)
        + str(BOARD_H - fr)
        + chr(ord("a") + tc)
        + str(BOARD_H - actual_tr)
    )

    if promo_idx > 0:
        promo_chars = {1: "q", 2: "r", 3: "b", 4: "n"}
        s += promo_chars.get(promo_idx, "")

    return s


def get_context():
    """Return the game context dict for Kohaku Chess."""
    ctx = {
        "name": "kohaku_chess",
        "state_class": KohakuChessState,
        "format_move": format_move,
        "uci_to_move": uci_to_move,
        "move_to_uci": move_to_uci,
        "board_h": BOARD_H,
        "board_w": BOARD_W,
        "max_step": MAX_STEP,
        "piece_unicode": PIECE_UNICODE,
        "col_labels": COL_LABELS,
        "row_labels": ROW_LABELS,
        "print_board": print_board,
        "get_human_move": get_human_move,
        "check_game_over": check_game_over,
        "apply_move": apply_move,
    }
    return ctx
