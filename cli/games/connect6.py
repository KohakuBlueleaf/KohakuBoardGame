"""Connect6 (六子棋) game module for CLI."""

import sys

try:
    from gui.games.connect6_engine import Connect6State, format_move, BOARD_SIZE, WIN_LENGTH
except ImportError:
    raise ImportError(
        "Connect6 CLI requires gui.games.connect6_engine. "
        "Make sure the gui package is on sys.path."
    )


def print_board(state, game_ctx):
    """Print Connect6 board."""
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
    print()


def _parse_square(s, size):
    """Parse 'E5' → (row, col) or None."""
    s = s.strip().upper()
    if len(s) < 2 or not s[0].isalpha():
        return None
    col = ord(s[0]) - ord("A")
    try:
        row_num = int(s[1:])
    except ValueError:
        return None
    row = size - row_num
    if 0 <= row < size and 0 <= col < size:
        return (row, col)
    return None


def get_human_move(state, game_ctx):
    """Prompt for Connect6 move: two squares (e.g. 'E5 F6')."""
    size = state["size"]
    player_num = state["player"]
    player_name = "White (O)" if player_num == 0 else "Black (X)"
    board = state["board"]

    print(f"  {player_name}'s turn. Enter two squares (e.g. E5 F6):")

    while True:
        try:
            raw = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGame aborted.")
            sys.exit(0)

        if not raw:
            continue

        parts = raw.split()
        if len(parts) != 2:
            print("  Enter exactly two squares separated by space (e.g. E5 F6)")
            continue

        sq1 = _parse_square(parts[0], size)
        sq2 = _parse_square(parts[1], size)

        if sq1 is None or sq2 is None:
            print("  Invalid square. Use column letter + row number (e.g. E5).")
            continue

        if sq1 == sq2:
            print("  Must place on two different squares.")
            continue

        if board[sq1[0]][sq1[1]] != 0 or board[sq2[0]][sq2[1]] != 0:
            print("  One or both squares are occupied.")
            continue

        # Return as UCI string: "e5f6"
        uci = (
            chr(ord("a") + sq1[1]) + str(size - sq1[0])
            + chr(ord("a") + sq2[1]) + str(size - sq2[0])
        )
        return uci


def make_state(size):
    """Create initial Connect6 state dict."""
    board = [[0] * size for _ in range(size)]
    board[size // 2][size // 2] = 1  # black at center
    return {
        "board": board,
        "size": size,
        "player": 0,  # white moves first
        "move_count": 0,
    }


def uci_to_move(uci_str, size):
    """Convert Connect6 UCI 'e5f6' to ((r1,c1),(r2,c2))."""
    if uci_str is None or len(uci_str) < 4:
        return None
    # Parse first square
    pos = 0
    c1 = ord(uci_str[pos].lower()) - ord("a")
    pos += 1
    num_start = pos
    while pos < len(uci_str) and uci_str[pos].isdigit():
        pos += 1
    r1 = size - int(uci_str[num_start:pos])
    # Parse second square
    if pos >= len(uci_str):
        return ((r1, c1), (r1, c1))
    c2 = ord(uci_str[pos].lower()) - ord("a")
    pos += 1
    r2 = size - int(uci_str[pos:])
    return ((r1, c1), (r2, c2))


def move_to_uci(move, size):
    """Convert ((r1,c1),(r2,c2)) to 'e5f6'."""
    (r1, c1), (r2, c2) = move
    s = chr(ord("a") + c1) + str(size - r1)
    if (r1, c1) != (r2, c2):
        s += chr(ord("a") + c2) + str(size - r2)
    return s


def apply_move(state, uci_str, game_ctx):
    """Apply a UCI move to Connect6 state."""
    size = state["size"]
    board = [row[:] for row in state["board"]]
    stone = 2 if state["player"] == 0 else 1

    move = uci_to_move(uci_str, size)
    if move is None:
        return state, uci_str

    (r1, c1), (r2, c2) = move
    board[r1][c1] = stone
    if (r1, c1) != (r2, c2):
        board[r2][c2] = stone

    new_state = {
        "board": board,
        "size": size,
        "player": 1 - state["player"],
        "move_count": state["move_count"] + 1,
    }
    return new_state, uci_str


def _check_winner(board, size):
    """Check for 6-in-a-row. Returns winner (1 or 2) or 0."""
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
    """Check if game is over. Returns (result, winner)."""
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
    """Return game context dict for Connect6."""
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
