"""Connect6 (六子棋) game module for CLI.

Single-stone moves: each player places 2 stones per turn as 2 separate
moves. The engine handles turn cycling via stones_left counter.
"""

import sys

try:
    from gui.games.connect6_engine import (
        Connect6State,
        format_move,
        BOARD_SIZE,
        WIN_LENGTH,
    )
except ImportError:
    raise ImportError(
        "Connect6 CLI requires gui.games.connect6_engine. "
        "Make sure the gui package is on sys.path."
    )


def print_board(state, game_ctx):
    board = state["board"]
    size = state["size"]
    print()
    cols = "ABCDEFGHIJKLMNO"[:size]
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
    stones = state.get("stones_left", 2)
    player = "White (O)" if state["player"] == 0 else "Black (X)"
    print(f"  {player} — stone {3 - stones} of 2")
    print()


def get_human_move(state, game_ctx):
    """Prompt for single-stone placement (e.g. 'H8')."""
    size = state["size"]
    player = state["player"]
    stones = state.get("stones_left", 2)
    name = "White (O)" if player == 0 else "Black (X)"
    print(f"  {name}'s turn — place stone {3 - stones} of 2:")

    while True:
        try:
            raw = input("  > ").strip().upper()
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
                print("  Invalid. Use column + row (e.g. H8).")
                continue
            row = size - row_num
            if 0 <= row < size and 0 <= col < size:
                if state["board"][row][col] == 0:
                    return raw[0].lower() + raw[1:]
                else:
                    print("  Square occupied.")
                    continue
            else:
                print(f"  Out of bounds.")
                continue

        print("  Invalid. Use column + row (e.g. H8).")


def make_state(size):
    board = [[0] * size for _ in range(size)]
    board[size // 2][size // 2] = 1
    return {
        "board": board,
        "size": size,
        "player": 0,
        "stones_left": 2,
        "move_count": 0,
    }


def uci_to_move(uci_str, size):
    """Convert 'h8' to ((r,c),(r,c))."""
    if not uci_str or len(uci_str) < 2:
        return None
    col = ord(uci_str[0].lower()) - ord("a")
    row = size - int(uci_str[1:])
    return ((row, col), (row, col))


def move_to_uci(move, size):
    """Convert ((r,c),(r,c)) to 'h8'."""
    _, (r, c) = move
    return chr(ord("a") + c) + str(size - r)


def apply_move(state, uci_str, game_ctx):
    size = state["size"]
    board = [row[:] for row in state["board"]]
    stone = 2 if state["player"] == 0 else 1
    stones_left = state.get("stones_left", 2)

    col = ord(uci_str[0].lower()) - ord("a")
    row = size - int(uci_str[1:])
    board[row][col] = stone

    switch = stones_left == 1
    new_state = {
        "board": board,
        "size": size,
        "player": (1 - state["player"]) if switch else state["player"],
        "stones_left": 2 if switch else 1,
        "move_count": state["move_count"] + 1,
    }
    return new_state, uci_str


def _check_winner(board, size):
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
                if count >= WIN_LENGTH:
                    return p
    return 0


def check_game_over(state):
    winner = _check_winner(state["board"], state["size"])
    if winner != 0:
        return ("win", winner)
    full = all(
        state["board"][r][c] != 0
        for r in range(state["size"])
        for c in range(state["size"])
    )
    if full:
        return ("draw", None)
    return (None, None)


def get_context(board_size=15):
    size = board_size
    ctx = {
        "name": "connect6",
        "state_class": Connect6State,
        "format_move": format_move,
        "uci_to_move": lambda uci: uci_to_move(uci, size),
        "move_to_uci": lambda move: move_to_uci(move, size),
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
