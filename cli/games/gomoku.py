"""Gomoku game module for CLI -- board display, human input, game logic."""

import sys

try:
    from gui.games.gomoku_engine import GomokuState, format_move
except ImportError:
    raise ImportError(
        "Gomoku CLI requires gui.games.gomoku_engine. "
        "Make sure the gui package is on sys.path."
    )


def print_board(state, game_ctx):
    """Print Gomoku board with X and O markers.

    state: dict with 'board' (2D list) and 'size'.
    """
    board = state["board"]
    size = state["size"]
    print()
    cols = "ABCDEFGHIJKLMNOPQRS"[:size]
    print("    " + "  ".join(cols))
    for r in range(size):
        rank = str(size - r)
        row_chars = []
        for c in range(size):
            v = board[r][c]
            if v == 1:
                row_chars.append("X")
            elif v == 2:
                row_chars.append("O")
            else:
                row_chars.append(".")
        print(f" {rank:>2}  " + "  ".join(row_chars) + f"  {rank}")
    print("    " + "  ".join(cols))
    print()


def get_human_move(state, game_ctx):
    """Prompt human player for a Gomoku move (e.g. 'E5')."""
    size = state["size"]
    player_num = state["player"]
    player_name = "Player 1 (X)" if player_num == 1 else "Player 2 (O)"
    board = state["board"]

    print(f"  {player_name}'s turn.")

    while True:
        try:
            raw = input("  Enter move (e.g. E5): ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            print("\nGame aborted.")
            sys.exit(0)

        if not raw:
            continue

        if len(raw) >= 2 and raw[0].isalpha():
            col = ord(raw[0]) - ord("A")
            try:
                row_num = int(raw[1:])
            except ValueError:
                print(
                    "  Invalid move format. Use column letter + row number (e.g. E5)."
                )
                continue

            row = size - row_num
            if 0 <= row < size and 0 <= col < size:
                if board[row][col] == 0:
                    # Return UCI string (lowercase letter + number)
                    return raw[0].lower() + raw[1:]
                else:
                    print("  That square is already occupied.")
                    continue
            else:
                print(f"  Out of bounds. Use A-{chr(ord('A') + size - 1)}, 1-{size}.")
                continue

        print("  Invalid move format. Use column letter + row number (e.g. E5).")


def make_state(size):
    """Create initial Gomoku state dict."""
    return {
        "board": [[0] * size for _ in range(size)],
        "size": size,
        "player": 1,  # player 1 = X goes first
        "move_count": 0,
    }


def uci_to_move(uci_str, size):
    """Convert gomoku UCI string (e.g. 'e5') to ((r,c),(r,c)) tuple."""
    if uci_str is None or len(uci_str) < 2:
        return None
    col = ord(uci_str[0].lower()) - ord("a")
    row = size - int(uci_str[1:])
    return ((row, col), (row, col))


def move_to_uci(move, size):
    """Convert ((r,c),(r,c)) tuple to gomoku UCI string (e.g. 'e5')."""
    _, (r, c) = move
    return chr(ord("a") + c) + str(size - r)


def apply_move(state, uci_str, game_ctx):
    """Apply a UCI move string to Gomoku state. Returns (new_state, uci_str).

    Gomoku UCI move format: column letter + row number, e.g. 'e5'.
    """
    size = state["size"]
    board = [row[:] for row in state["board"]]

    col = ord(uci_str[0].lower()) - ord("a")
    try:
        row_num = int(uci_str[1:])
    except ValueError:
        return state, uci_str  # invalid move, return unchanged

    row = size - row_num
    if 0 <= row < size and 0 <= col < size:
        board[row][col] = state["player"]

    new_player = 2 if state["player"] == 1 else 1
    new_state = {
        "board": board,
        "size": size,
        "player": new_player,
        "move_count": state["move_count"] + 1,
    }
    return new_state, uci_str


def _check_gomoku_winner(board, size):
    """Check for 5-in-a-row. Returns winning player (1 or 2) or 0 for none."""
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    for r in range(size):
        for c in range(size):
            p = board[r][c]
            if p == 0:
                continue
            for dr, dc in directions:
                count = 0
                rr, cc = r, c
                while 0 <= rr < size and 0 <= cc < size and board[rr][cc] == p:
                    count += 1
                    rr += dr
                    cc += dc
                if count >= 5:
                    return p
    return 0


def check_game_over(state):
    """Check if the game is over. Returns (result, winner).

    result: 'win', 'draw', or None (game continues).
    winner: 1 or 2 for 'win', None otherwise.
    Maps to 'white'/'black' in the caller: player 1 = white, player 2 = black.
    """
    winner = _check_gomoku_winner(state["board"], state["size"])
    if winner != 0:
        return ("win", winner)

    # Check for full board (draw)
    full = all(
        state["board"][r][c] != 0
        for r in range(state["size"])
        for c in range(state["size"])
    )
    if full:
        return ("draw", None)

    return (None, None)


def get_context(board_size=15):
    """Return the game context dict for Gomoku with the given board size."""
    size = board_size

    def _uci_to_move(uci_str):
        return uci_to_move(uci_str, size)

    def _move_to_uci(move):
        return move_to_uci(move, size)

    ctx = {
        "name": "gomoku",
        "state_class": GomokuState,
        "format_move": format_move,
        "uci_to_move": _uci_to_move,
        "move_to_uci": _move_to_uci,
        "board_h": size,
        "board_w": size,
        "max_step": size * size,
        "col_labels": "".join(chr(65 + i) for i in range(size)),
        "row_labels": [str(size - i) for i in range(size)],
        "print_board": print_board,
        "get_human_move": get_human_move,
        "check_game_over": check_game_over,
        "apply_move": apply_move,
        "make_state": make_state,
        "board_size": size,
    }
    return ctx
