"""MiniShogi game engine -- Python state tracking for GUI."""

try:
    import gui.config as cfg
except ImportError:
    import config as cfg

BOARD_SIZE = 5

# Piece types
EMPTY = 0
PAWN = 1
SILVER = 2
GOLD = 3
BISHOP = 4
ROOK = 5
KING = 6
P_PAWN = 7
P_SILVER = 8
P_BISHOP = 9
P_ROOK = 10

PLAYER_LABELS = {0: "Sente", 1: "Gote"}
PLAYER_COLORS = {0: (200, 160, 80), 1: (80, 60, 40)}  # wood-like

PIECE_NAMES = {
    PAWN: "P", SILVER: "S", GOLD: "G", BISHOP: "B", ROOK: "R", KING: "K",
    P_PAWN: "+P", P_SILVER: "+S", P_BISHOP: "+B", P_ROOK: "+R",
}

# Kanji/symbol for rendering
PIECE_SYMBOLS = {
    0: {PAWN: "\u6b69", SILVER: "\u9280", GOLD: "\u91d1", BISHOP: "\u89d2",
        ROOK: "\u98db", KING: "\u738b",
        P_PAWN: "\u3068", P_SILVER: "\u5168", P_BISHOP: "\u99ac", P_ROOK: "\u9f8d"},
    1: {PAWN: "\u6b69", SILVER: "\u9280", GOLD: "\u91d1", BISHOP: "\u89d2",
        ROOK: "\u98db", KING: "\u7389",
        P_PAWN: "\u3068", P_SILVER: "\u5168", P_BISHOP: "\u99ac", P_ROOK: "\u9f8d"},
}

# Drop piece name abbreviations (for UCI-style notation)
_DROP_PIECE_CHAR = {PAWN: "P", SILVER: "S", GOLD: "G", BISHOP: "B", ROOK: "R"}
_CHAR_TO_DROP_PIECE = {"P": PAWN, "S": SILVER, "G": GOLD, "B": BISHOP, "R": ROOK}

# Promotable pieces and their promoted forms
_PROMOTE_MAP = {
    PAWN: P_PAWN,
    SILVER: P_SILVER,
    BISHOP: P_BISHOP,
    ROOK: P_ROOK,
}

# Reverse: promoted piece -> base piece (for captures going to hand)
_DEMOTE_MAP = {
    P_PAWN: PAWN,
    P_SILVER: SILVER,
    P_BISHOP: BISHOP,
    P_ROOK: ROOK,
}

# Material values for MAX_STEP game-over
_MATERIAL_TABLE = {
    EMPTY: 0, PAWN: 1, SILVER: 5, GOLD: 5, BISHOP: 8, ROOK: 10, KING: 100,
    P_PAWN: 5, P_SILVER: 5, P_BISHOP: 12, P_ROOK: 14,
}

MAX_STEP = 200

# ---------------------------------------------------------------------------
# Movement tables
# ---------------------------------------------------------------------------

# Gold moves: one step in 6 directions (orthogonal + forward-diagonals)
# For sente (player 0), forward = row decreasing.
# For gote (player 1), forward = row increasing.
# We store directions relative to sente; flip for gote.
_GOLD_MOVES_SENTE = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0)]
_GOLD_MOVES_GOTE = [(1, -1), (1, 0), (1, 1), (0, -1), (0, 1), (-1, 0)]

_SILVER_MOVES_SENTE = [(-1, -1), (-1, 0), (-1, 1), (1, -1), (1, 1)]
_SILVER_MOVES_GOTE = [(1, -1), (1, 0), (1, 1), (-1, -1), (-1, 1)]

_KING_MOVES = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

# Rook: 4 orthogonal sliding directions
_ROOK_DIRS = [(0, 1), (0, -1), (1, 0), (-1, 0)]
# Bishop: 4 diagonal sliding directions
_BISHOP_DIRS = [(1, 1), (1, -1), (-1, 1), (-1, -1)]


# ---------------------------------------------------------------------------
# Promotion zone helpers
# ---------------------------------------------------------------------------

def _in_promotion_zone(row, player):
    """Return True if (row) is in the promotion zone for player."""
    if player == 0:
        return row == 0  # sente promotes on row 0
    else:
        return row == BOARD_SIZE - 1  # gote promotes on row 4


def _can_promote(piece_type):
    """Return True if piece_type can promote."""
    return piece_type in _PROMOTE_MAP


def _is_promoted(piece_type):
    """Return True if piece_type is already promoted."""
    return piece_type in _DEMOTE_MAP


def _must_promote(piece_type, to_row, player):
    """Return True if the piece MUST promote (pawn reaching last rank)."""
    if piece_type == PAWN:
        if player == 0 and to_row == 0:
            return True
        if player == 1 and to_row == BOARD_SIZE - 1:
            return True
    return False


# ---------------------------------------------------------------------------
# Initial board layout
# ---------------------------------------------------------------------------

def _make_initial_board():
    """Return the starting position as board[2][BOARD_SIZE][BOARD_SIZE]."""
    board = [[[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)] for _ in range(2)]

    # Gote (player 1) -- top of board
    # Row 0: k g s b r
    board[1][0][0] = KING
    board[1][0][1] = GOLD
    board[1][0][2] = SILVER
    board[1][0][3] = BISHOP
    board[1][0][4] = ROOK
    # Row 1: pawn at col 4
    board[1][1][4] = PAWN

    # Sente (player 0) -- bottom of board
    # Row 4: R B S G K
    board[0][4][0] = ROOK
    board[0][4][1] = BISHOP
    board[0][4][2] = SILVER
    board[0][4][3] = GOLD
    board[0][4][4] = KING
    # Row 3: pawn at col 0
    board[0][3][0] = PAWN

    return board


def _make_initial_hand():
    """Return hand[2][6] -- all zeros. Index 0 unused, 1-5 = P,S,G,B,R."""
    return [[0] * 6 for _ in range(2)]


def _deep_copy_board(board):
    """Deep-copy a board[2][BOARD_SIZE][BOARD_SIZE] list."""
    return [[row[:] for row in player_board] for player_board in board]


def _deep_copy_hand(hand):
    """Deep-copy a hand[2][6] list."""
    return [counts[:] for counts in hand]


# ---------------------------------------------------------------------------
# Step-move helpers for each piece type
# ---------------------------------------------------------------------------

def _step_moves(piece_type, player):
    """Return list of (dr, dc) step offsets for a stepping piece."""
    if piece_type == GOLD or piece_type == P_PAWN or piece_type == P_SILVER:
        return _GOLD_MOVES_SENTE if player == 0 else _GOLD_MOVES_GOTE
    elif piece_type == SILVER:
        return _SILVER_MOVES_SENTE if player == 0 else _SILVER_MOVES_GOTE
    elif piece_type == KING:
        return _KING_MOVES
    elif piece_type == P_BISHOP:
        # Horse: bishop sliding + king orthogonal steps
        return None  # handled specially
    elif piece_type == P_ROOK:
        # Dragon: rook sliding + king diagonal steps
        return None  # handled specially
    return []


# ---------------------------------------------------------------------------
# MiniShogiState
# ---------------------------------------------------------------------------

class MiniShogiState:
    """Game state for MiniShogi (5x5)."""

    def __init__(self, board=None, hand=None, player=0, step=1):
        if board is None:
            self.board = _make_initial_board()
        else:
            self.board = _deep_copy_board(board)
        if hand is None:
            self.hand = _make_initial_hand()
        else:
            self.hand = _deep_copy_hand(hand)
        self.player = player
        self.step = step
        self.game_state = "unknown"
        self.legal_actions = []
        self.last_move = None

    @property
    def current_player(self):
        return self.player

    @staticmethod
    def initial():
        """Return the starting-position state with legal actions computed."""
        s = MiniShogiState()
        s.get_legal_actions()
        return s

    # ------------------------------------------------------------------ #
    # Legal move generation
    # ------------------------------------------------------------------ #

    def get_legal_actions(self):
        """Populate self.legal_actions and set self.game_state.

        Move encoding:
          Board move: ((from_r, from_c), (to_r, to_c))
          Board move with promotion: ((from_r, from_c), (to_r + BOARD_SIZE, to_c))
          Drop move: ((BOARD_SIZE, piece_type), (to_r, to_c))
        """
        self.game_state = "none"
        actions = []
        me = self.player
        opp = 1 - me
        my_board = self.board[me]
        opp_board = self.board[opp]

        # --- Board moves ---
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                piece = my_board[r][c]
                if piece == EMPTY:
                    continue

                dests = []  # list of (to_r, to_c)

                if piece == PAWN:
                    # Pawn moves one step forward
                    dr = -1 if me == 0 else 1
                    nr = r + dr
                    if 0 <= nr < BOARD_SIZE:
                        if my_board[nr][c] == EMPTY:
                            dests.append((nr, c))

                elif piece == SILVER:
                    moves = _SILVER_MOVES_SENTE if me == 0 else _SILVER_MOVES_GOTE
                    for dr, dc in moves:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                            if my_board[nr][nc] == EMPTY:
                                dests.append((nr, nc))

                elif piece == GOLD or piece == P_PAWN or piece == P_SILVER:
                    moves = _GOLD_MOVES_SENTE if me == 0 else _GOLD_MOVES_GOTE
                    for dr, dc in moves:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                            if my_board[nr][nc] == EMPTY:
                                dests.append((nr, nc))

                elif piece == KING:
                    for dr, dc in _KING_MOVES:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                            if my_board[nr][nc] == EMPTY:
                                dests.append((nr, nc))

                elif piece == BISHOP:
                    for dr, dc in _BISHOP_DIRS:
                        nr, nc = r + dr, c + dc
                        while 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                            if my_board[nr][nc] != EMPTY:
                                break
                            dests.append((nr, nc))
                            if opp_board[nr][nc] != EMPTY:
                                break
                            nr += dr
                            nc += dc

                elif piece == ROOK:
                    for dr, dc in _ROOK_DIRS:
                        nr, nc = r + dr, c + dc
                        while 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                            if my_board[nr][nc] != EMPTY:
                                break
                            dests.append((nr, nc))
                            if opp_board[nr][nc] != EMPTY:
                                break
                            nr += dr
                            nc += dc

                elif piece == P_BISHOP:
                    # Horse: bishop sliding + orthogonal one-step
                    for dr, dc in _BISHOP_DIRS:
                        nr, nc = r + dr, c + dc
                        while 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                            if my_board[nr][nc] != EMPTY:
                                break
                            dests.append((nr, nc))
                            if opp_board[nr][nc] != EMPTY:
                                break
                            nr += dr
                            nc += dc
                    for dr, dc in _ROOK_DIRS:  # orthogonal one-step
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                            if my_board[nr][nc] == EMPTY:
                                dests.append((nr, nc))

                elif piece == P_ROOK:
                    # Dragon: rook sliding + diagonal one-step
                    for dr, dc in _ROOK_DIRS:
                        nr, nc = r + dr, c + dc
                        while 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                            if my_board[nr][nc] != EMPTY:
                                break
                            dests.append((nr, nc))
                            if opp_board[nr][nc] != EMPTY:
                                break
                            nr += dr
                            nc += dc
                    for dr, dc in _BISHOP_DIRS:  # diagonal one-step
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                            if my_board[nr][nc] == EMPTY:
                                dests.append((nr, nc))

                # Generate moves for each destination
                for tr, tc in dests:
                    captured = opp_board[tr][tc]
                    if captured == KING:
                        # King capture -- immediate win
                        self.game_state = "win"
                        actions.append(((r, c), (tr, tc)))
                        self.legal_actions = actions
                        return

                    promotable = _can_promote(piece) and not _is_promoted(piece)
                    in_promo_from = _in_promotion_zone(r, me)
                    in_promo_to = _in_promotion_zone(tr, me)
                    must = _must_promote(piece, tr, me)

                    if promotable and (in_promo_from or in_promo_to):
                        # Promotion move
                        actions.append(((r, c), (tr + BOARD_SIZE, tc)))
                        if not must:
                            # Also allow non-promotion
                            actions.append(((r, c), (tr, tc)))
                    else:
                        actions.append(((r, c), (tr, tc)))

        # --- Drop moves ---
        for pt in range(1, 6):  # PAWN=1, SILVER=2, GOLD=3, BISHOP=4, ROOK=5
            if self.hand[me][pt] <= 0:
                continue
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    if my_board[r][c] != EMPTY or opp_board[r][c] != EMPTY:
                        continue
                    # Pawn drop restrictions
                    if pt == PAWN:
                        # Cannot drop pawn on last rank
                        if (me == 0 and r == 0) or (me == 1 and r == BOARD_SIZE - 1):
                            continue
                        # Two-pawn restriction: no column already has an unpromoted pawn
                        has_pawn_in_col = False
                        for rr in range(BOARD_SIZE):
                            if my_board[rr][c] == PAWN:
                                has_pawn_in_col = True
                                break
                        if has_pawn_in_col:
                            continue
                    actions.append(((BOARD_SIZE, pt), (r, c)))

        self.legal_actions = actions

    # ------------------------------------------------------------------ #
    # Next state
    # ------------------------------------------------------------------ #

    def next_state(self, move):
        """Return a new MiniShogiState after applying move."""
        frm, to = move
        fr, fc = frm
        tr, tc = to

        new_board = _deep_copy_board(self.board)
        new_hand = _deep_copy_hand(self.hand)
        me = self.player
        opp = 1 - me

        if fr == BOARD_SIZE:
            # Drop move: fc = piece_type
            piece_type = fc
            new_hand[me][piece_type] -= 1
            new_board[me][tr][tc] = piece_type
        else:
            # Board move
            promoting = tr >= BOARD_SIZE
            actual_tr = tr - BOARD_SIZE if promoting else tr

            moved_piece = new_board[me][fr][fc]

            # Handle capture
            captured = new_board[opp][actual_tr][tc]
            if captured != EMPTY:
                new_board[opp][actual_tr][tc] = EMPTY
                # Demote captured piece if promoted, then add to hand
                base = _DEMOTE_MAP.get(captured, captured)
                if base != KING:
                    new_hand[me][base] += 1

            # Move piece
            new_board[me][fr][fc] = EMPTY
            if promoting:
                new_board[me][actual_tr][tc] = _PROMOTE_MAP[moved_piece]
            else:
                new_board[me][actual_tr][tc] = moved_piece

        ns = MiniShogiState(new_board, new_hand, opp, self.step + 1)
        ns.last_move = move

        if self.game_state != "win":
            ns.get_legal_actions()

        return ns

    # ------------------------------------------------------------------ #
    # Game-over check
    # ------------------------------------------------------------------ #

    def check_game_over(self):
        """Check if the game ended.

        Returns:
            ("win", winner_player) -- if king can be captured.
            ("draw", None) -- if material is equal after MAX_STEP.
            (None, None) -- game is not over.
        """
        if self.game_state == "win":
            return ("win", self.player)

        if self.step > MAX_STEP:
            mat = [0, 0]
            for p in range(2):
                for r in range(BOARD_SIZE):
                    for c in range(BOARD_SIZE):
                        piece = self.board[p][r][c]
                        mat[p] += _MATERIAL_TABLE.get(piece, 0)
                # Add hand material
                for pt in range(1, 6):
                    mat[p] += self.hand[p][pt] * _MATERIAL_TABLE.get(pt, 0)

            if mat[0] > mat[1]:
                return ("win", 0)
            elif mat[1] > mat[0]:
                return ("win", 1)
            else:
                return ("draw", None)

        return (None, None)

    # ------------------------------------------------------------------ #
    # State encoding for UBGI engine communication
    # ------------------------------------------------------------------ #

    def encode_state(self):
        """Encode state for the C++ engine.

        Format:
            player
            sente_board (5 rows of 5 ints)
            <blank>
            gote_board (5 rows of 5 ints)
            <blank>
            sente_hand (5 ints: P S G B R counts)
            gote_hand (5 ints: P S G B R counts)
        """
        lines = []
        lines.append(str(self.player))
        for pl in range(2):
            for r in range(BOARD_SIZE):
                lines.append(
                    " ".join(str(self.board[pl][r][c]) for c in range(BOARD_SIZE)) + " "
                )
            lines.append("")
        for pl in range(2):
            lines.append(" ".join(str(self.hand[pl][pt]) for pt in range(1, 6)))
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------ #
    # Deep copy
    # ------------------------------------------------------------------ #

    def copy(self):
        """Return a deep copy of this state."""
        s = MiniShogiState.__new__(MiniShogiState)
        s.board = _deep_copy_board(self.board)
        s.hand = _deep_copy_hand(self.hand)
        s.player = self.player
        s.step = self.step
        s.game_state = self.game_state
        s.legal_actions = list(self.legal_actions)
        s.last_move = self.last_move
        return s

    def __repr__(self):
        return (
            f"MiniShogiState(player={self.player}, step={self.step}, "
            f"game_state={self.game_state!r}, "
            f"legal_actions={len(self.legal_actions)})"
        )


# ---------------------------------------------------------------------------
# Move formatting
# ---------------------------------------------------------------------------

def format_move(move):
    """Format move as a display string.

    Drop: 'P*C3'
    Board move: 'A1->B2' or 'A1->B2+' (promotion)
    """
    (fr, fc), (tr, tc) = move
    col_labels = "ABCDE"
    row_labels = "54321"

    if fr == BOARD_SIZE:
        # Drop move: fc = piece_type
        piece_char = _DROP_PIECE_CHAR.get(fc, "?")
        return f"{piece_char}*{col_labels[tc]}{row_labels[tr]}"

    promoting = tr >= BOARD_SIZE
    actual_tr = tr - BOARD_SIZE if promoting else tr
    result = f"{col_labels[fc]}{row_labels[fr]}->{col_labels[tc]}{row_labels[actual_tr]}"
    if promoting:
        result += "+"
    return result
