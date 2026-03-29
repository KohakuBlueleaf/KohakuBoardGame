"""Connect6 (六子棋) game engine — Python implementation for GUI state tracking.

Connect6 rules:
- 15x15 board, black stone pre-placed at center
- Player 0 (white) moves first, each turn places 2 stones
- Single-stone moves: stones_left tracks turn progression
  stones_left=2 → place stone, same player (stones_left=1)
  stones_left=1 → place stone, switch player (stones_left=2)
- Win: 6 in a row (horizontal, vertical, diagonal)
- Move = ((r,c), (r,c)) with from == to (single placement)
"""

BOARD_SIZE = 15
WIN_LENGTH = 6
EMPTY = 0

# Player 0 = white (stone 2), Player 1 = black (stone 1)
PLAYER_LABELS = {0: "White", 1: "Black"}
PLAYER_COLORS = {0: (240, 240, 240), 1: (20, 20, 20)}


class Connect6State:
    def __init__(self):
        """Initial position: black stone at center, white moves first."""
        self.board = [[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.board[BOARD_SIZE // 2][BOARD_SIZE // 2] = 1  # black at center
        self.player = 0  # white moves first
        self.step = 0
        self.stones_left = 2  # first stone of turn
        self.game_state = "none"
        self.legal_actions = []
        self.last_move = None
        self._generate_legal_actions()

    @staticmethod
    def initial():
        return Connect6State()

    @property
    def current_player(self):
        return self.player

    def _stone_id(self, player):
        return 2 if player == 0 else 1

    def _generate_legal_actions(self):
        """Generate single-stone placement moves for nearby empty squares."""
        self.legal_actions = []
        if self.game_state != "none":
            return

        # Check for existing win
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self.board[r][c] != EMPTY and self._check_win(
                    r, c, self.board[r][c]
                ):
                    self.game_state = "win"
                    # Winner is whoever owns the winning stones
                    winning_stone = self.board[r][c]
                    self.player = 0 if winning_stone == 2 else 1
                    return

        # Collect nearby empty squares
        near = set()
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self.board[r][c] != EMPTY:
                    for dr in range(-3, 4):
                        for dc in range(-3, 4):
                            nr, nc = r + dr, c + dc
                            if (
                                0 <= nr < BOARD_SIZE
                                and 0 <= nc < BOARD_SIZE
                                and self.board[nr][nc] == EMPTY
                            ):
                                near.add((nr, nc))

        if not near:
            self.game_state = "draw"
            return

        for r, c in sorted(near):
            self.legal_actions.append(((r, c), (r, c)))

    def next_state(self, move):
        _, (r, c) = move
        stone = self._stone_id(self.player)
        switch_player = self.stones_left == 1

        new = Connect6State.__new__(Connect6State)
        new.board = [row[:] for row in self.board]
        new.board[r][c] = stone
        new.player = (1 - self.player) if switch_player else self.player
        new.stones_left = 2 if switch_player else 1
        new.step = self.step + 1
        new.game_state = "none"
        new.last_move = move

        new._generate_legal_actions()
        return new

    def _check_win(self, row, col, stone):
        dirs = [(0, 1), (1, 0), (1, 1), (1, -1)]
        for dr, dc in dirs:
            count = 1
            for sign in (1, -1):
                r, c = row + sign * dr, col + sign * dc
                while (
                    0 <= r < BOARD_SIZE
                    and 0 <= c < BOARD_SIZE
                    and self.board[r][c] == stone
                ):
                    count += 1
                    r += sign * dr
                    c += sign * dc
            if count >= WIN_LENGTH:
                return True
        return False

    def check_game_over(self):
        if self.game_state == "win":
            return ("win", self.player)
        if self.game_state == "draw":
            return ("draw", None)
        return (None, None)


def format_move(move):
    """Format a Connect6 move as algebraic (e.g. 'H8')."""
    _, (r, c) = move
    col_labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return f"{col_labels[c]}{BOARD_SIZE - r}"
