"""Standard Chess game engine -- Python state tracking for GUI.

8x8 chess with full rules: castling, en passant, pawn double-push,
promotion to Q/R/B/N. Win by king capture (same as other variants).
"""

try:
    import gui.config as cfg
except ImportError:
    import config as cfg

BOARD_H = 8
BOARD_W = 8

EMPTY = 0
PAWN = 1
ROOK = 2
KNIGHT = 3
BISHOP = 4
QUEEN = 5
KING = 6

PLAYER_LABELS = {0: "White", 1: "Black"}
PLAYER_COLORS = {0: (255, 255, 255), 1: (30, 30, 30)}

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

# Sliding directions
_ROOK_DIRS = [(0, 1), (0, -1), (1, 0), (-1, 0)]
_BISHOP_DIRS = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
_KNIGHT_MOVES = [(1, 2), (1, -2), (-1, 2), (-1, -2), (2, 1), (2, -1), (-2, 1), (-2, -1)]
_KING_MOVES = [(1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]

PROMOTE_MAP = {1: QUEEN, 2: ROOK, 3: BISHOP, 4: KNIGHT}

_material_table = [0, 1, 5, 3, 3, 9, 100]
MAX_STEP = 300

CASTLE_WK = 1
CASTLE_WQ = 2
CASTLE_BK = 4
CASTLE_BQ = 8


def _make_initial_board():
    board = [[[0] * BOARD_W for _ in range(BOARD_H)] for _ in range(2)]
    # White
    board[0][7] = [ROOK, KNIGHT, BISHOP, QUEEN, KING, BISHOP, KNIGHT, ROOK]
    board[0][6] = [PAWN] * 8
    # Black
    board[1][0] = [ROOK, KNIGHT, BISHOP, QUEEN, KING, BISHOP, KNIGHT, ROOK]
    board[1][1] = [PAWN] * 8
    return board


def _deep_copy_board(board):
    return [[row[:] for row in player_board] for player_board in board]


class ChessState:
    def __init__(self, board=None, player=0, step=0):
        if board is None:
            self.board = _make_initial_board()
        else:
            self.board = _deep_copy_board(board)
        self.player = player
        self.step = step
        self.game_state = "unknown"
        self.legal_actions = []
        self.hash_counts = {}
        self.castling = CASTLE_WK | CASTLE_WQ | CASTLE_BK | CASTLE_BQ
        self.ep_col = -1

    @property
    def current_player(self):
        return self.player

    @staticmethod
    def initial():
        s = ChessState()
        s.get_legal_actions()
        return s

    def get_legal_actions(self):
        self.game_state = "none"
        all_actions = []
        me = self.player
        opp = 1 - me
        my = self.board[me]
        op = self.board[opp]
        pawn_dir = -1 if me == 0 else 1
        start_rank = 6 if me == 0 else 1
        promo_rank = 0 if me == 0 else 7

        for r in range(8):
            for c in range(8):
                piece = my[r][c]
                if not piece:
                    continue

                if piece == PAWN:
                    tr = r + pawn_dir
                    if 0 <= tr < 8 and not my[tr][c] and not op[tr][c]:
                        if tr == promo_rank:
                            for pi in range(1, 5):
                                all_actions.append(((r, c), (tr + 8 * pi, c)))
                        else:
                            all_actions.append(((r, c), (tr, c)))
                        # Double push
                        if r == start_rank:
                            tr2 = r + 2 * pawn_dir
                            if not my[tr2][c] and not op[tr2][c]:
                                all_actions.append(((r, c), (tr2, c)))
                    # Captures
                    for dc in (-1, 1):
                        tc = c + dc
                        if tc < 0 or tc >= 8 or tr < 0 or tr >= 8:
                            continue
                        is_cap = op[tr][tc] != 0
                        is_ep = self.ep_col == tc and tr == (2 if me == 0 else 5)
                        if is_cap or is_ep:
                            if op[tr][tc] == KING:
                                self.game_state = "win"
                                self.legal_actions = [((r, c), (tr, tc))]
                                return
                            if tr == promo_rank:
                                for pi in range(1, 5):
                                    all_actions.append(((r, c), (tr + 8 * pi, tc)))
                            else:
                                all_actions.append(((r, c), (tr, tc)))

                elif piece == KNIGHT:
                    for dr, dc in _KNIGHT_MOVES:
                        tr, tc = r + dr, c + dc
                        if 0 <= tr < 8 and 0 <= tc < 8 and not my[tr][tc]:
                            if op[tr][tc] == KING:
                                self.game_state = "win"
                                self.legal_actions = [((r, c), (tr, tc))]
                                return
                            all_actions.append(((r, c), (tr, tc)))

                elif piece == KING:
                    for dr, dc in _KING_MOVES:
                        tr, tc = r + dr, c + dc
                        if 0 <= tr < 8 and 0 <= tc < 8 and not my[tr][tc]:
                            if op[tr][tc] == KING:
                                self.game_state = "win"
                                self.legal_actions = [((r, c), (tr, tc))]
                                return
                            all_actions.append(((r, c), (tr, tc)))
                    # Castling
                    king_row = 7 if me == 0 else 0
                    if r == king_row and c == 4:
                        ks = CASTLE_WK if me == 0 else CASTLE_BK
                        qs = CASTLE_WQ if me == 0 else CASTLE_BQ
                        if (
                            self.castling & ks
                            and not my[king_row][5]
                            and not op[king_row][5]
                            and not my[king_row][6]
                            and not op[king_row][6]
                            and my[king_row][7] == ROOK
                        ):
                            all_actions.append(((r, c), (king_row, 6)))
                        if (
                            self.castling & qs
                            and not my[king_row][3]
                            and not op[king_row][3]
                            and not my[king_row][2]
                            and not op[king_row][2]
                            and not my[king_row][1]
                            and not op[king_row][1]
                            and my[king_row][0] == ROOK
                        ):
                            all_actions.append(((r, c), (king_row, 2)))

                elif piece in (ROOK, BISHOP, QUEEN):
                    dirs = []
                    if piece in (ROOK, QUEEN):
                        dirs += _ROOK_DIRS
                    if piece in (BISHOP, QUEEN):
                        dirs += _BISHOP_DIRS
                    for dr, dc in dirs:
                        tr, tc = r + dr, c + dc
                        while 0 <= tr < 8 and 0 <= tc < 8:
                            if my[tr][tc]:
                                break
                            if op[tr][tc] == KING:
                                self.game_state = "win"
                                self.legal_actions = [((r, c), (tr, tc))]
                                return
                            all_actions.append(((r, c), (tr, tc)))
                            if op[tr][tc]:
                                break
                            tr += dr
                            tc += dc

        self.legal_actions = all_actions
        if not all_actions and self.step >= MAX_STEP:
            self.game_state = "draw"

    def next_state(self, move):
        (fr, fc), (tr, tc) = move
        promote = tr >= 8
        promo_idx = 0
        if promote:
            promo_idx = tr // 8
            tr = tr % 8

        me = self.player
        opp = 1 - me
        new_board = _deep_copy_board(self.board)
        piece = new_board[me][fr][fc]
        captured = new_board[opp][tr][tc]

        new_board[me][fr][fc] = 0

        # En passant capture
        if piece == PAWN and fc != tc and captured == 0:
            new_board[opp][fr][tc] = 0

        new_board[opp][tr][tc] = 0

        if promote:
            new_board[me][tr][tc] = PROMOTE_MAP.get(promo_idx, QUEEN)
        else:
            new_board[me][tr][tc] = piece

        # Castling rook move (must happen before ChessState copies new_board)
        if piece == KING:
            king_row = 7 if me == 0 else 0
            if fr == king_row and fc == 4:
                if tc == 6:
                    new_board[me][king_row][7] = 0
                    new_board[me][king_row][5] = ROOK
                elif tc == 2:
                    new_board[me][king_row][0] = 0
                    new_board[me][king_row][3] = ROOK

        ns = ChessState(new_board, opp, self.step + 1)
        ns.castling = self.castling
        ns.hash_counts = dict(self.hash_counts)

        # Update castling rights
        if piece == KING:
            if me == 0:
                ns.castling &= ~(CASTLE_WK | CASTLE_WQ)
            else:
                ns.castling &= ~(CASTLE_BK | CASTLE_BQ)
        if piece == ROOK:
            if me == 0 and fr == 7 and fc == 0:
                ns.castling &= ~CASTLE_WQ
            if me == 0 and fr == 7 and fc == 7:
                ns.castling &= ~CASTLE_WK
            if me == 1 and fr == 0 and fc == 0:
                ns.castling &= ~CASTLE_BQ
            if me == 1 and fr == 0 and fc == 7:
                ns.castling &= ~CASTLE_BK
        if tr == 0 and tc == 0:
            ns.castling &= ~CASTLE_BQ
        if tr == 0 and tc == 7:
            ns.castling &= ~CASTLE_BK
        if tr == 7 and tc == 0:
            ns.castling &= ~CASTLE_WQ
        if tr == 7 and tc == 7:
            ns.castling &= ~CASTLE_WK

        # En passant
        ns.ep_col = -1
        if piece == PAWN and abs(tr - fr) == 2:
            ns.ep_col = fc

        if ns.game_state != "win":
            ns.get_legal_actions()
        return ns

    def check_game_over(self):
        if self.game_state == "win":
            return ("win", self.player)
        key = self._position_key()
        if self.hash_counts.get(key, 0) + 1 >= 3:
            return ("draw", None)
        if self.step > MAX_STEP:
            w_mat = sum(
                _material_table[self.board[0][r][c]] for r in range(8) for c in range(8)
            )
            b_mat = sum(
                _material_table[self.board[1][r][c]] for r in range(8) for c in range(8)
            )
            if w_mat > b_mat:
                return ("win", 0)
            if b_mat > w_mat:
                return ("win", 1)
            return ("draw", None)
        if not self.legal_actions:
            return ("stalemate", None)
        return (None, None)

    def _position_key(self):
        return (
            tuple(tuple(row) for row in self.board[0]),
            tuple(tuple(row) for row in self.board[1]),
            self.player,
            self.castling,
            self.ep_col,
        )

    def position_key(self):
        return self._position_key()


def format_move(move):
    (fr, fc), (tr, tc) = move
    promo = ""
    if tr >= 8:
        pi = tr // 8
        tr = tr % 8
        promo_chars = {1: "q", 2: "r", 3: "b", 4: "n"}
        promo = promo_chars.get(pi, "")
    col = "abcdefgh"
    return f"{col[fc]}{8-fr}{col[tc]}{8-tr}{promo}"
