"""Gomoku game engine — Python implementation for GUI state tracking."""

BOARD_SIZE = 15  # 15x15 standard board
WIN_LENGTH = 5
EMPTY = 0

PLAYER_LABELS = {0: "Black", 1: "White"}
PLAYER_COLORS = {0: (20, 20, 20), 1: (240, 240, 240)}  # for rendering


class GomokuState:
    def __init__(self):
        self.board = [[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.player = 0  # Black moves first
        self.step = 0
        self.game_state = "none"
        self.legal_actions = []
        self.last_move = None
        self._generate_legal_actions()

    @staticmethod
    def initial():
        return GomokuState()

    @property
    def current_player(self):
        return self.player

    def _generate_legal_actions(self):
        self.legal_actions = []
        if self.game_state != "none":
            return
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self.board[r][c] == EMPTY:
                    self.legal_actions.append(((r, c), (r, c)))

    def next_state(self, move):
        _, (r, c) = move
        new = GomokuState.__new__(GomokuState)
        new.board = [row[:] for row in self.board]
        new.player = 1 - self.player
        new.step = self.step + 1
        new.board[r][c] = self.player + 1  # 1=black, 2=white
        new.game_state = "none"
        new.last_move = move

        if new._check_win(r, c, self.player + 1):
            new.game_state = "win"
            new.player = self.player  # winner stays as player
            new.legal_actions = []
        elif new.step >= BOARD_SIZE * BOARD_SIZE:
            new.game_state = "draw"
            new.legal_actions = []
        else:
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
    """Format a gomoku move as algebraic (e.g. 'E5')."""
    _, (r, c) = move
    col_labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    row_label = str(BOARD_SIZE - r)
    return f"{col_labels[c]}{row_label}"
