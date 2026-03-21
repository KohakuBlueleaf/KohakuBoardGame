"""MiniShogi game module for CLI -- board display, human input, game logic."""

import sys

try:
    from gui.games.minishogi_engine import (
        MiniShogiState,
        format_move,
        BOARD_SIZE,
        MAX_STEP,
        EMPTY,
        PAWN,
        SILVER,
        GOLD,
        BISHOP,
        ROOK,
        KING,
        P_PAWN,
        P_SILVER,
        P_BISHOP,
        P_ROOK,
        PIECE_NAMES,
        DROP_PIECE_CHAR,
        CHAR_TO_DROP_PIECE,
    )
except ImportError:
    raise ImportError(
        "MiniShogi CLI requires gui.games.minishogi_engine. "
        "Make sure the gui package is on sys.path."
    )

BOARD_H = BOARD_SIZE
BOARD_W = BOARD_SIZE
COL_LABELS = "abcde"
ROW_LABELS = "54321"  # row_labels[internal_row] = display rank

# Piece display: uppercase = sente, lowercase = gote
_PIECE_DISPLAY = {
    0: {
        PAWN: " P",
        SILVER: " S",
        GOLD: " G",
        BISHOP: " B",
        ROOK: " R",
        KING: " K",
        P_PAWN: "+P",
        P_SILVER: "+S",
        P_BISHOP: "+B",
        P_ROOK: "+R",
    },
    1: {
        PAWN: " p",
        SILVER: " s",
        GOLD: " g",
        BISHOP: " b",
        ROOK: " r",
        KING: " k",
        P_PAWN: "+p",
        P_SILVER: "+s",
        P_BISHOP: "+b",
        P_ROOK: "+r",
    },
}

# Hand piece names for display
_HAND_NAMES = {1: "P", 2: "S", 3: "G", 4: "B", 5: "R"}


# ---------------------------------------------------------------------------
# UCI move conversion
# ---------------------------------------------------------------------------


def uci_to_move(uci_str):
    """Convert a UCI move string to internal move tuple.

    Formats:
        'a1b2'   -> ((from_r, from_c), (to_r, to_c))        board move
        'a1b2+'  -> ((from_r, from_c), (to_r + 5, to_c))    promotion
        'P*c3'   -> ((5, piece_type), (to_r, to_c))          drop
    """
    if uci_str is None or len(uci_str) < 2:
        return None

    # Drop move: X*rc (e.g. P*c3)
    if len(uci_str) >= 3 and uci_str[1] == "*":
        piece_char = uci_str[0].upper()
        pt = CHAR_TO_DROP_PIECE.get(piece_char)
        if pt is None:
            raise ValueError(f"Invalid drop piece: {piece_char}")
        col = ord(uci_str[2].lower()) - ord("a")
        row = BOARD_H - int(uci_str[3])
        return ((BOARD_H, pt), (row, col))

    # Placement move (2 chars): just destination (from == to)
    if len(uci_str) == 2:
        col = ord(uci_str[0].lower()) - ord("a")
        row = BOARD_H - int(uci_str[1])
        return ((row, col), (row, col))

    # Board move: 4 or 5 chars
    from_col = ord(uci_str[0].lower()) - ord("a")
    from_row = BOARD_H - int(uci_str[1])
    to_col = ord(uci_str[2].lower()) - ord("a")
    to_row = BOARD_H - int(uci_str[3])

    promote = len(uci_str) >= 5 and uci_str[4] == "+"
    if promote:
        to_row += BOARD_H

    return ((from_row, from_col), (to_row, to_col))


def move_to_uci(move):
    """Convert internal move tuple to UCI string.

    Board move:       ((fr,fc),(tr,tc))            -> 'a1b2'
    Promotion move:   ((fr,fc),(tr+5,tc))           -> 'a1b2+'
    Drop move:        ((5, piece_type),(tr,tc))     -> 'P*c3'
    """
    (fr, fc), (tr, tc) = move

    # Drop move
    if fr == BOARD_H:
        piece_char = DROP_PIECE_CHAR.get(fc, "?")
        col_ch = chr(ord("a") + tc)
        row_ch = str(BOARD_H - tr)
        return f"{piece_char}*{col_ch}{row_ch}"

    # Board move
    promote = tr >= BOARD_H
    actual_tr = tr - BOARD_H if promote else tr

    s = (
        chr(ord("a") + fc)
        + str(BOARD_H - fr)
        + chr(ord("a") + tc)
        + str(BOARD_H - actual_tr)
    )
    if promote:
        s += "+"
    return s


# ---------------------------------------------------------------------------
# Board display
# ---------------------------------------------------------------------------


def _format_hand(hand_counts):
    """Format a player's hand pieces as a compact string like 'P S B'."""
    parts = []
    for pt in range(1, 6):
        count = hand_counts[pt]
        if count > 0:
            name = _HAND_NAMES[pt]
            if count == 1:
                parts.append(name)
            else:
                parts.append(f"{name}x{count}")
    return " ".join(parts) if parts else "(empty)"


def print_board(state, game_ctx):
    """Print MiniShogi board with piece abbreviations and hand pieces."""
    print()

    # Gote's hand (top)
    gote_hand = _format_hand(state.hand[1])
    print(f"  Gote hand: [{gote_hand}]")
    print()

    # Column labels
    print("     " + "  ".join(c.upper() for c in COL_LABELS))

    for r in range(BOARD_H):
        rank_label = ROW_LABELS[r]
        row_chars = []
        for c in range(BOARD_W):
            sente_piece = state.board[0][r][c]
            gote_piece = state.board[1][r][c]
            if sente_piece:
                row_chars.append(_PIECE_DISPLAY[0][sente_piece])
            elif gote_piece:
                row_chars.append(_PIECE_DISPLAY[1][gote_piece])
            else:
                row_chars.append(" .")
        print(f"  {rank_label}  " + " ".join(row_chars) + f"   {rank_label}")

    print("     " + "  ".join(c.upper() for c in COL_LABELS))
    print()

    # Sente's hand (bottom)
    sente_hand = _format_hand(state.hand[0])
    print(f"  Sente hand: [{sente_hand}]")
    print()


# ---------------------------------------------------------------------------
# Human move input
# ---------------------------------------------------------------------------


def get_human_move(state, game_ctx):
    """Prompt human player for a MiniShogi move via numbered list or algebraic notation."""
    legal = state.legal_actions
    player_name = "Sente" if state.player == 0 else "Gote"

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
            raw = input(f"  Enter move number (or e.g. a1b2, a1b2+, P*c3): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGame aborted.")
            sys.exit(0)

        if not raw:
            continue

        # Try as a number first
        try:
            num = int(raw)
            if 1 <= num <= len(legal):
                return legal[num - 1]
            print(f"  Invalid number. Enter 1-{len(legal)}.")
            continue
        except ValueError:
            pass

        # Try to parse as UCI string
        uci_str = raw.strip()
        try:
            move = uci_to_move(uci_str)
            if move in legal:
                return move
            print(f"  '{raw}' is not a legal move.")
            continue
        except (ValueError, IndexError, KeyError):
            pass

        print(
            f"  Could not parse '{raw}'. Enter a move number or algebraic "
            f"(e.g. a1b2, a1b2+, P*c3)."
        )


# ---------------------------------------------------------------------------
# Apply engine move
# ---------------------------------------------------------------------------


def apply_move(state, uci_str, game_ctx):
    """Apply a UCI move string to the state. Returns (new_state, move_tuple)."""
    move = uci_to_move(uci_str)
    return state.next_state(move), move


# ---------------------------------------------------------------------------
# Game over check
# ---------------------------------------------------------------------------


def check_game_over(state):
    """Check if the game is over. Returns (result, winner).

    result: 'win', 'draw', 'no_moves', or None (game continues).
    winner: 0 (Sente) or 1 (Gote) for 'win'/'no_moves', None otherwise.
    """
    result, winner = state.check_game_over()
    if result == "win":
        return ("win", winner)
    elif result == "draw":
        return ("draw", None)

    if not state.legal_actions:
        # Side to move has no legal moves -- they lose
        return ("no_moves", 1 - state.player)

    return (None, None)


# ---------------------------------------------------------------------------
# Game context
# ---------------------------------------------------------------------------


def get_context(board_size=5):
    """Return the game context dict for MiniShogi."""
    ctx = {
        "name": "minishogi",
        "state_class": MiniShogiState,
        "format_move": format_move,
        "uci_to_move": uci_to_move,
        "move_to_uci": move_to_uci,
        "board_h": BOARD_H,
        "board_w": BOARD_W,
        "max_step": MAX_STEP,
        "col_labels": COL_LABELS,
        "row_labels": ROW_LABELS,
        "print_board": print_board,
        "get_human_move": get_human_move,
        "check_game_over": check_game_over,
        "apply_move": apply_move,
    }
    return ctx
