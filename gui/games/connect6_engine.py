"""Connect6 (六子棋) game engine — Python implementation for GUI state tracking.

Connect6 rules:
- 15x15 board, black stone pre-placed at center
- Player 0 (white) moves first, placing 2 stones per turn
- Player 1 (black) places 2 stones per turn
- Win: 6 in a row (horizontal, vertical, diagonal)
- Move = ((r1,c1), (r2,c2)) — two placement positions
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
        """Player 0 = white = stone 2, Player 1 = black = stone 1."""
        return 2 if player == 0 else 1

    def _nearby_empty(self):
        """Return list of empty squares within Manhattan distance 2 of any stone."""
        near = set()
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self.board[r][c] != EMPTY:
                    for dr in range(-2, 3):
                        for dc in range(-2, 3):
                            if abs(dr) + abs(dc) > 2:
                                continue
                            nr, nc = r + dr, c + dc
                            if (
                                0 <= nr < BOARD_SIZE
                                and 0 <= nc < BOARD_SIZE
                                and self.board[nr][nc] == EMPTY
                            ):
                                near.add((nr, nc))
        return sorted(near)

    def _generate_legal_actions(self):
        """Generate all legal move pairs from nearby empty squares."""
        self.legal_actions = []
        if self.game_state != "none":
            return

        # Check if opponent already won
        opp_stone = self._stone_id(1 - self.player)
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self.board[r][c] == opp_stone and self._check_win(r, c, opp_stone):
                    self.game_state = "win"
                    self.player = 1 - self.player  # winner
                    return

        candidates = self._nearby_empty()
        if not candidates:
            self.game_state = "draw"
            return

        # Generate all ordered pairs
        n = len(candidates)
        for i in range(n):
            for j in range(i + 1, n):
                self.legal_actions.append((candidates[i], candidates[j]))

        if not self.legal_actions and candidates:
            # Only 1 candidate — degenerate
            sq = candidates[0]
            self.legal_actions.append((sq, sq))

    def next_state(self, move):
        (r1, c1), (r2, c2) = move
        stone = self._stone_id(self.player)

        new = Connect6State.__new__(Connect6State)
        new.board = [row[:] for row in self.board]
        new.player = 1 - self.player
        new.step = self.step + 1
        new.game_state = "none"
        new.last_move = move

        # Place both stones
        new.board[r1][c1] = stone
        if (r1, c1) != (r2, c2):
            new.board[r2][c2] = stone

        # Check if either placement creates a win
        if new._check_win(r1, c1, stone) or (
            (r1, c1) != (r2, c2) and new._check_win(r2, c2, stone)
        ):
            new.game_state = "win"
            new.player = self.player  # winner
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
    """Format a Connect6 move as 'E5+F6' (two placements)."""
    (r1, c1), (r2, c2) = move
    col_labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    s1 = f"{col_labels[c1]}{BOARD_SIZE - r1}"
    s2 = f"{col_labels[c2]}{BOARD_SIZE - r2}"
    if (r1, c1) == (r2, c2):
        return s1
    return f"{s1}+{s2}"
