"""Kohaku Chess game engine -- Python state tracking for GUI.

7x6 chess variant with 2 bishops per side, no castling, no en passant,
no pawn double-move. Pawn promotes on last rank to Q, R, B, or N.
"""

try:
    import gui.config as cfg
except ImportError:
    import config as cfg

BOARD_H = 7
BOARD_W = 6

# Piece codes
EMPTY = 0
PAWN = 1
ROOK = 2
KNIGHT = 3
BISHOP = 4
QUEEN = 5
KING = 6

PLAYER_LABELS = {0: "White", 1: "Black"}
PLAYER_COLORS = {0: (255, 255, 255), 1: (30, 30, 30)}

# Unicode chess piece symbols: [player][piece_type]
PIECE_UNICODE = {
    0: {
        PAWN: "\u2659",
        ROOK: "\u2656",
        KNIGHT: "\u2658",
        BISHOP: "\u2657",
        QUEEN: "\u2655",
        KING: "\u2654",
    },
    1: {
        PAWN: "\u265f",
        ROOK: "\u265c",
        KNIGHT: "\u265e",
        BISHOP: "\u265d",
        QUEEN: "\u265b",
        KING: "\u265a",
    },
}

# ---------------------------------------------------------------------------
# Move tables
# ---------------------------------------------------------------------------

# Sliding directions: indices 0-3 = rook, 4-7 = bishop, 0-7 = queen
_move_table_rook_bishop = [
    [(0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (0, 6), (0, 7)],
    [(0, -1), (0, -2), (0, -3), (0, -4), (0, -5), (0, -6), (0, -7)],
    [(1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0), (7, 0)],
    [(-1, 0), (-2, 0), (-3, 0), (-4, 0), (-5, 0), (-6, 0), (-7, 0)],
    [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7)],
    [(1, -1), (2, -2), (3, -3), (4, -4), (5, -5), (6, -6), (7, -7)],
    [(-1, 1), (-2, 2), (-3, 3), (-4, 4), (-5, 5), (-6, 6), (-7, 7)],
    [(-1, -1), (-2, -2), (-3, -3), (-4, -4), (-5, -5), (-6, -6), (-7, -7)],
]

_move_table_knight = [
    (1, 2),
    (1, -2),
    (-1, 2),
    (-1, -2),
    (2, 1),
    (2, -1),
    (-2, 1),
    (-2, -1),
]

_move_table_king = [
    (1, 0),
    (0, 1),
    (-1, 0),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
]

# Material values for MAX_STEP game-over
_material_table = [0, 2, 6, 7, 8, 20, 100]

MAX_STEP = 150


# ---------------------------------------------------------------------------
# Initial board layout
# ---------------------------------------------------------------------------


def _make_initial_board():
    """Return the starting position as board[2][BOARD_H][BOARD_W].

    White (player 0) -- bottom of board:
      Row 6 (rank 1): K  Q  .  N  B  R
      Row 5 (rank 2): B  .  P  P  P  P
      Row 4 (rank 3): P  P  .  .  .  .

    Black (player 1) -- top of board (180 degree rotated):
      Row 0 (rank 7): R  B  N  .  Q  K
      Row 1 (rank 6): P  P  P  P  .  B
      Row 2 (rank 5): .  .  .  .  P  P
    """
    board = [[[0] * BOARD_W for _ in range(BOARD_H)] for _ in range(2)]

    # White (player 0)
    # Row 6: K Q . N B R
    board[0][6][0] = KING
    board[0][6][1] = QUEEN
    # board[0][6][2] = EMPTY
    board[0][6][3] = KNIGHT
    board[0][6][4] = BISHOP
    board[0][6][5] = ROOK
    # Row 5: B . P P P P
    board[0][5][0] = BISHOP
    # board[0][5][1] = EMPTY
    board[0][5][2] = PAWN
    board[0][5][3] = PAWN
    board[0][5][4] = PAWN
    board[0][5][5] = PAWN
    # Row 4: P P . . . .
    board[0][4][0] = PAWN
    board[0][4][1] = PAWN

    # Black (player 1) -- 180 degree rotation
    # Row 0: R B N . Q K
    board[1][0][0] = ROOK
    board[1][0][1] = BISHOP
    board[1][0][2] = KNIGHT
    # board[1][0][3] = EMPTY
    board[1][0][4] = QUEEN
    board[1][0][5] = KING
    # Row 1: P P P P . B
    board[1][1][0] = PAWN
    board[1][1][1] = PAWN
    board[1][1][2] = PAWN
    board[1][1][3] = PAWN
    # board[1][1][4] = EMPTY
    board[1][1][5] = BISHOP
    # Row 2: . . . . P P
    board[1][2][4] = PAWN
    board[1][2][5] = PAWN

    return board


def _deep_copy_board(board):
    """Deep-copy a board[2][BOARD_H][BOARD_W] list."""
    return [[row[:] for row in player_board] for player_board in board]


# ---------------------------------------------------------------------------
# KohakuChessState
# ---------------------------------------------------------------------------


class KohakuChessState:
    """Game state for Kohaku Chess (7x6)."""

    def __init__(self, board=None, player=0, step=1):
        if board is None:
            self.board = _make_initial_board()
        else:
            self.board = _deep_copy_board(board)
        self.player = player
        self.step = step
        self.game_state = "unknown"
        self.legal_actions = []
        self.hash_counts = {}

    @property
    def current_player(self):
        return self.player

    @staticmethod
    def initial():
        """Return the starting-position state with legal actions computed."""
        s = KohakuChessState()
        s.get_legal_actions()
        return s

    # ------------------------------------------------------------------ #
    # Legal move generation
    # ------------------------------------------------------------------ #

    def get_legal_actions(self):
        """Populate self.legal_actions and set self.game_state.

        Move encoding:
          Board move: ((from_r, from_c), (to_r, to_c))
          Pawn promotion: ((from_r, from_c), (to_r + BOARD_H * promo_idx, to_c))
            where promo_idx: 0=no promotion, 1=Queen, 2=Rook, 3=Bishop, 4=Knight
        """
        self.game_state = "none"
        all_actions = []
        self_board = self.board[self.player]
        oppn_board = self.board[1 - self.player]

        for i in range(BOARD_H):
            for j in range(BOARD_W):
                now_piece = self_board[i][j]
                if not now_piece:
                    continue

                if now_piece == PAWN:
                    if self.player and i < BOARD_H - 1:
                        # Black pawn -- moves DOWN (row increases)
                        # Forward move (no capture)
                        if not oppn_board[i + 1][j] and not self_board[i + 1][j]:
                            if i + 1 == BOARD_H - 1:
                                # Promotion: Q, R, B, N
                                for pidx in range(1, 5):
                                    all_actions.append(
                                        ((i, j), (i + 1 + BOARD_H * pidx, j))
                                    )
                            else:
                                all_actions.append(((i, j), (i + 1, j)))
                        # Diagonal captures
                        for dc in (1, -1):
                            nc = j + dc
                            if 0 <= nc < BOARD_W:
                                oppn_piece = oppn_board[i + 1][nc]
                                if oppn_piece > 0:
                                    if oppn_piece == KING:
                                        self.game_state = "win"
                                        all_actions.append(((i, j), (i + 1, nc)))
                                        self.legal_actions = all_actions
                                        return
                                    if i + 1 == BOARD_H - 1:
                                        for pidx in range(1, 5):
                                            all_actions.append(
                                                ((i, j), (i + 1 + BOARD_H * pidx, nc))
                                            )
                                    else:
                                        all_actions.append(((i, j), (i + 1, nc)))

                    elif not self.player and i > 0:
                        # White pawn -- moves UP (row decreases)
                        if not oppn_board[i - 1][j] and not self_board[i - 1][j]:
                            if i - 1 == 0:
                                for pidx in range(1, 5):
                                    all_actions.append(
                                        ((i, j), (i - 1 + BOARD_H * pidx, j))
                                    )
                            else:
                                all_actions.append(((i, j), (i - 1, j)))
                        for dc in (1, -1):
                            nc = j + dc
                            if 0 <= nc < BOARD_W:
                                oppn_piece = oppn_board[i - 1][nc]
                                if oppn_piece > 0:
                                    if oppn_piece == KING:
                                        self.game_state = "win"
                                        all_actions.append(((i, j), (i - 1, nc)))
                                        self.legal_actions = all_actions
                                        return
                                    if i - 1 == 0:
                                        for pidx in range(1, 5):
                                            all_actions.append(
                                                ((i, j), (i - 1 + BOARD_H * pidx, nc))
                                            )
                                    else:
                                        all_actions.append(((i, j), (i - 1, nc)))

                elif now_piece in (ROOK, BISHOP, QUEEN):
                    if now_piece == ROOK:
                        st, end = 0, 4
                    elif now_piece == BISHOP:
                        st, end = 4, 8
                    else:  # queen
                        st, end = 0, 8

                    for part in range(st, end):
                        move_list = _move_table_rook_bishop[part]
                        for k in range(max(BOARD_H, BOARD_W)):
                            dr, dc = move_list[k]
                            pr, pc = dr + i, dc + j

                            if pr >= BOARD_H or pr < 0 or pc >= BOARD_W or pc < 0:
                                break
                            if self_board[pr][pc]:
                                break

                            all_actions.append(((i, j), (pr, pc)))

                            oppn_piece = oppn_board[pr][pc]
                            if oppn_piece:
                                if oppn_piece == KING:
                                    self.game_state = "win"
                                    self.legal_actions = all_actions
                                    return
                                else:
                                    break

                elif now_piece == KNIGHT:
                    for dr, dc in _move_table_knight:
                        x = dr + i
                        y = dc + j

                        if x >= BOARD_H or x < 0 or y >= BOARD_W or y < 0:
                            continue
                        if self_board[x][y]:
                            continue
                        all_actions.append(((i, j), (x, y)))

                        oppn_piece = oppn_board[x][y]
                        if oppn_piece == KING:
                            self.game_state = "win"
                            self.legal_actions = all_actions
                            return

                elif now_piece == KING:
                    for dr, dc in _move_table_king:
                        pr, pc = dr + i, dc + j

                        if pr >= BOARD_H or pr < 0 or pc >= BOARD_W or pc < 0:
                            continue
                        if self_board[pr][pc]:
                            continue

                        all_actions.append(((i, j), (pr, pc)))

                        oppn_piece = oppn_board[pr][pc]
                        if oppn_piece == KING:
                            self.game_state = "win"
                            self.legal_actions = all_actions
                            return

        self.legal_actions = all_actions

    def position_key(self):
        """Hashable key for the current board + side-to-move."""
        return (
            self.player,
            tuple(
                self.board[p][r][c]
                for p in range(2)
                for r in range(BOARD_H)
                for c in range(BOARD_W)
            ),
        )

    # ------------------------------------------------------------------ #
    # Next state
    # ------------------------------------------------------------------ #

    def next_state(self, move):
        """Return a new KohakuChessState after applying move."""
        frm, to = move
        fr, fc = frm
        tr, tc = to

        new_board = _deep_copy_board(self.board)

        moved = new_board[self.player][fr][fc]

        # Check for promotion
        actual_tr = tr % BOARD_H
        promo_idx = tr // BOARD_H  # 0=none, 1=Q, 2=R, 3=B, 4=N

        if moved == PAWN and promo_idx > 0:
            promo_map = {1: QUEEN, 2: ROOK, 3: BISHOP, 4: KNIGHT}
            moved = promo_map[promo_idx]
        elif moved == PAWN and (actual_tr == BOARD_H - 1 or actual_tr == 0):
            # Auto-promote to queen if reaching last rank without explicit promo
            moved = QUEEN

        # Capture
        if new_board[1 - self.player][actual_tr][tc]:
            new_board[1 - self.player][actual_tr][tc] = EMPTY

        # Move
        new_board[self.player][fr][fc] = EMPTY
        new_board[self.player][actual_tr][tc] = moved

        ns = KohakuChessState(new_board, 1 - self.player, self.step + 1)
        ns.hash_counts = dict(self.hash_counts)
        key = self.position_key()
        ns.hash_counts[key] = ns.hash_counts.get(key, 0) + 1

        if self.game_state != "win":
            ns.get_legal_actions()

        return ns

    # ------------------------------------------------------------------ #
    # Game-over check
    # ------------------------------------------------------------------ #

    def check_game_over(self):
        """Check if the game ended.

        Returns:
            ("checkmate", winner_player) -- in check with no escape.
            ("win", winner_player) -- if king can be captured.
            ("draw", None) -- if material is equal after MAX_STEP.
            (None, None) -- game is not over.
        """
        if self.game_state == "win":
            return ("win", self.player)

        # 4-fold repetition -> draw
        key = self.position_key()
        if self.hash_counts.get(key, 0) + 1 >= 4:
            return ("draw", None)

        if self.step > MAX_STEP:
            white_material = 0
            black_material = 0
            for i in range(BOARD_H):
                for j in range(BOARD_W):
                    piece = self.board[0][i][j]
                    if piece:
                        white_material += _material_table[piece]
                    piece = self.board[1][i][j]
                    if piece:
                        black_material += _material_table[piece]

            if white_material < black_material:
                return ("win", 1)
            elif white_material > black_material:
                return ("win", 0)
            else:
                return ("draw", None)

        # Checkmate
        probe = KohakuChessState(self.board, 1 - self.player, self.step)
        probe.get_legal_actions()
        if probe.game_state == "win":  # we are in check
            for move in self.legal_actions:
                child = self.next_state(move)
                if child.game_state != "win":
                    return (None, None)
            return ("checkmate", 1 - self.player)

        return (None, None)

    # ------------------------------------------------------------------ #
    # State encoding
    # ------------------------------------------------------------------ #

    def encode_state(self):
        """Encode state for the C++ engine."""
        lines = []
        lines.append(str(self.player))
        for pl in range(2):
            for i in range(BOARD_H):
                lines.append(
                    " ".join(str(self.board[pl][i][j]) for j in range(BOARD_W)) + " "
                )
            lines.append("")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------ #
    # Deep copy
    # ------------------------------------------------------------------ #

    def copy(self):
        """Return a deep copy of this state."""
        s = KohakuChessState.__new__(KohakuChessState)
        s.board = _deep_copy_board(self.board)
        s.player = self.player
        s.step = self.step
        s.game_state = self.game_state
        s.legal_actions = list(self.legal_actions)
        s.hash_counts = dict(self.hash_counts)
        return s

    def __repr__(self):
        return (
            f"KohakuChessState(player={self.player}, step={self.step}, "
            f"game_state={self.game_state!r}, "
            f"legal_actions={len(self.legal_actions)})"
        )


# ---------------------------------------------------------------------------
# Move formatting
# ---------------------------------------------------------------------------

COL_LABELS = "ABCDEF"
ROW_LABELS = "7654321"


def format_move(move):
    """Format move as an algebraic string like 'B2->B3'.

    For promotion moves, appends the promotion piece: 'B7->B8=Q'
    """
    (fr, fc), (tr, tc) = move

    actual_tr = tr % BOARD_H
    promo_idx = tr // BOARD_H

    result = (
        f"{COL_LABELS[fc]}{ROW_LABELS[fr]}->" f"{COL_LABELS[tc]}{ROW_LABELS[actual_tr]}"
    )

    if promo_idx > 0:
        promo_chars = {1: "Q", 2: "R", 3: "B", 4: "N"}
        result += f"={promo_chars.get(promo_idx, '?')}"

    return result
