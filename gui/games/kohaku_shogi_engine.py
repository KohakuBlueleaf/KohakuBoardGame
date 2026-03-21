"""Kohaku Shogi game engine -- Python state tracking for GUI."""

try:
    import gui.config as cfg
except ImportError:
    import config as cfg

BOARD_H = 7
BOARD_W = 6

# Piece types
EMPTY = 0
PAWN = 1
SILVER = 2
GOLD = 3
LANCE = 4
KNIGHT = 5
BISHOP = 6
ROOK = 7
KING = 8
P_PAWN = 9
P_SILVER = 10
P_LANCE = 11
P_KNIGHT = 12
P_BISHOP = 13
P_ROOK = 14

NUM_HAND_TYPES = 7  # P, S, G, L, N, B, R (indices 1-7)

PLAYER_LABELS = {0: "Sente", 1: "Gote"}
PLAYER_COLORS = {0: (200, 160, 80), 1: (80, 60, 40)}  # wood-like

PIECE_NAMES = {
    PAWN: "P",
    SILVER: "S",
    GOLD: "G",
    LANCE: "L",
    KNIGHT: "N",
    BISHOP: "B",
    ROOK: "R",
    KING: "K",
    P_PAWN: "+P",
    P_SILVER: "+S",
    P_LANCE: "+L",
    P_KNIGHT: "+N",
    P_BISHOP: "+B",
    P_ROOK: "+R",
}

# Kanji/symbol for rendering
PIECE_SYMBOLS = {
    0: {
        PAWN: "\u6b69",  # 歩
        SILVER: "\u9280",  # 銀
        GOLD: "\u91d1",  # 金
        LANCE: "\u9999",  # 香
        KNIGHT: "\u6842",  # 桂
        BISHOP: "\u89d2",  # 角
        ROOK: "\u98db",  # 飛
        KING: "\u738b",  # 王
        P_PAWN: "\u3068",  # と
        P_SILVER: "\u5168",  # 全
        P_LANCE: "\u674f",  # 杏
        P_KNIGHT: "\u572d",  # 圭
        P_BISHOP: "\u99ac",  # 馬
        P_ROOK: "\u9f8d",  # 龍
    },
    1: {
        PAWN: "\u6b69",
        SILVER: "\u9280",
        GOLD: "\u91d1",
        LANCE: "\u9999",
        KNIGHT: "\u6842",
        BISHOP: "\u89d2",
        ROOK: "\u98db",
        KING: "\u7389",  # 玉
        P_PAWN: "\u3068",
        P_SILVER: "\u5168",
        P_LANCE: "\u674f",
        P_KNIGHT: "\u572d",
        P_BISHOP: "\u99ac",
        P_ROOK: "\u9f8d",
    },
}

# Drop piece name abbreviations (for UCI-style notation)
_DROP_PIECE_CHAR = {
    PAWN: "P",
    SILVER: "S",
    GOLD: "G",
    LANCE: "L",
    KNIGHT: "N",
    BISHOP: "B",
    ROOK: "R",
}
_CHAR_TO_DROP_PIECE = {
    "P": PAWN,
    "S": SILVER,
    "G": GOLD,
    "L": LANCE,
    "N": KNIGHT,
    "B": BISHOP,
    "R": ROOK,
}

# Promotable pieces and their promoted forms
_PROMOTE_MAP = {
    PAWN: P_PAWN,
    SILVER: P_SILVER,
    LANCE: P_LANCE,
    KNIGHT: P_KNIGHT,
    BISHOP: P_BISHOP,
    ROOK: P_ROOK,
}

# Reverse: promoted piece -> base piece (for captures going to hand)
_DEMOTE_MAP = {
    P_PAWN: PAWN,
    P_SILVER: SILVER,
    P_LANCE: LANCE,
    P_KNIGHT: KNIGHT,
    P_BISHOP: BISHOP,
    P_ROOK: ROOK,
}

# Material values for MAX_STEP game-over
_MATERIAL_TABLE = {
    EMPTY: 0,
    PAWN: 1,
    SILVER: 5,
    GOLD: 5,
    LANCE: 3,
    KNIGHT: 4,
    BISHOP: 8,
    ROOK: 10,
    KING: 100,
    P_PAWN: 5,
    P_SILVER: 5,
    P_LANCE: 5,
    P_KNIGHT: 5,
    P_BISHOP: 12,
    P_ROOK: 14,
}

MAX_STEP = 300

# ---------------------------------------------------------------------------
# Movement tables
# ---------------------------------------------------------------------------

# Gold moves: one step in 6 directions (orthogonal + forward-diagonals)
_GOLD_MOVES_SENTE = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0)]
_GOLD_MOVES_GOTE = [(1, -1), (1, 0), (1, 1), (0, -1), (0, 1), (-1, 0)]

_SILVER_MOVES_SENTE = [(-1, -1), (-1, 0), (-1, 1), (1, -1), (1, 1)]
_SILVER_MOVES_GOTE = [(1, -1), (1, 0), (1, 1), (-1, -1), (-1, 1)]

_KING_MOVES = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

# Knight moves: 2 forward, 1 sideways (jump, not sliding)
_KNIGHT_MOVES_SENTE = [(-2, -1), (-2, 1)]
_KNIGHT_MOVES_GOTE = [(2, -1), (2, 1)]

# Rook: 4 orthogonal sliding directions
_ROOK_DIRS = [(0, 1), (0, -1), (1, 0), (-1, 0)]
# Bishop: 4 diagonal sliding directions
_BISHOP_DIRS = [(1, 1), (1, -1), (-1, 1), (-1, -1)]


# ---------------------------------------------------------------------------
# Promotion zone helpers
# ---------------------------------------------------------------------------


def _in_promotion_zone(row, player):
    """Return True if (row) is in the promotion zone for player.

    Promotion zone is the last 2 ranks.
    """
    if player == 0:
        return row <= 1  # sente promotes on rows 0-1
    else:
        return row >= BOARD_H - 2  # gote promotes on rows 5-6


def _can_promote(piece_type):
    """Return True if piece_type can promote."""
    return piece_type in _PROMOTE_MAP


def _is_promoted(piece_type):
    """Return True if piece_type is already promoted."""
    return piece_type in _DEMOTE_MAP


def _must_promote(piece_type, to_row, player):
    """Return True if the piece MUST promote.

    Pawn/Lance: last rank.
    Knight: last 2 ranks.
    """
    if piece_type == PAWN or piece_type == LANCE:
        if player == 0 and to_row == 0:
            return True
        if player == 1 and to_row == BOARD_H - 1:
            return True
    if piece_type == KNIGHT:
        if player == 0 and to_row <= 1:
            return True
        if player == 1 and to_row >= BOARD_H - 2:
            return True
    return False


# ---------------------------------------------------------------------------
# Initial board layout
# ---------------------------------------------------------------------------


def _make_initial_board():
    """Return the starting position as board[2][BOARD_H][BOARD_W].

    Sente (player 0) -- bottom of board:
      Row 6 (rank 1): K  G  S  L  R  B
      Row 5 (rank 2): N  S  P  P  P  P
      Row 4 (rank 3): P  P  .  .  .  .

    Gote (player 1) -- top of board (180 degree rotated):
      Row 0 (rank 7): B  R  L  S  G  K
      Row 1 (rank 6): P  P  P  P  S  N
      Row 2 (rank 5): .  .  .  .  P  P
    """
    board = [[[EMPTY] * BOARD_W for _ in range(BOARD_H)] for _ in range(2)]

    # Sente (player 0) -- bottom rows
    # Row 6: K G S L R B
    board[0][6][0] = KING
    board[0][6][1] = GOLD
    board[0][6][2] = SILVER
    board[0][6][3] = LANCE
    board[0][6][4] = ROOK
    board[0][6][5] = BISHOP
    # Row 5: N S P P P P
    board[0][5][0] = KNIGHT
    board[0][5][1] = SILVER
    board[0][5][2] = PAWN
    board[0][5][3] = PAWN
    board[0][5][4] = PAWN
    board[0][5][5] = PAWN
    # Row 4: P P . . . .
    board[0][4][0] = PAWN
    board[0][4][1] = PAWN

    # Gote (player 1) -- top rows (180 degree rotation)
    # Row 0: B R L S G K
    board[1][0][0] = BISHOP
    board[1][0][1] = ROOK
    board[1][0][2] = LANCE
    board[1][0][3] = SILVER
    board[1][0][4] = GOLD
    board[1][0][5] = KING
    # Row 1: P P P P S N
    board[1][1][0] = PAWN
    board[1][1][1] = PAWN
    board[1][1][2] = PAWN
    board[1][1][3] = PAWN
    board[1][1][4] = SILVER
    board[1][1][5] = KNIGHT
    # Row 2: . . . . P P
    board[1][2][4] = PAWN
    board[1][2][5] = PAWN

    return board


def _make_initial_hand():
    """Return hand[2][8] -- all zeros. Index 0 unused, 1-7 = P,S,G,L,N,B,R."""
    return [[0] * (NUM_HAND_TYPES + 1) for _ in range(2)]


def _deep_copy_board(board):
    """Deep-copy a board[2][BOARD_H][BOARD_W] list."""
    return [[row[:] for row in player_board] for player_board in board]


def _deep_copy_hand(hand):
    """Deep-copy a hand[2][8] list."""
    return [counts[:] for counts in hand]


# ---------------------------------------------------------------------------
# KohakuShogiState
# ---------------------------------------------------------------------------


class KohakuShogiState:
    """Game state for Kohaku Shogi (7x6)."""

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
        self.hash_counts = {}  # position_key -> count for repetition detection

    @property
    def current_player(self):
        return self.player

    @staticmethod
    def initial():
        """Return the starting-position state with legal actions computed."""
        s = KohakuShogiState()
        s.get_legal_actions()
        return s

    # ------------------------------------------------------------------ #
    # Legal move generation
    # ------------------------------------------------------------------ #

    def get_legal_actions(self):
        """Populate self.legal_actions and set self.game_state.

        Move encoding:
          Board move: ((from_r, from_c), (to_r, to_c))
          Board move with promotion: ((from_r, from_c), (to_r + BOARD_H, to_c))
          Drop move: ((BOARD_H, piece_type), (to_r, to_c))
        """
        self.game_state = "none"
        actions = []
        me = self.player
        opp = 1 - me
        my_board = self.board[me]
        opp_board = self.board[opp]

        # --- Board moves ---
        for r in range(BOARD_H):
            for c in range(BOARD_W):
                piece = my_board[r][c]
                if piece == EMPTY:
                    continue

                dests = []  # list of (to_r, to_c)

                if piece == PAWN:
                    # Pawn moves one step forward
                    dr = -1 if me == 0 else 1
                    nr = r + dr
                    if 0 <= nr < BOARD_H:
                        if my_board[nr][c] == EMPTY:
                            dests.append((nr, c))

                elif piece == LANCE:
                    # Lance slides forward (no diagonal, no backward)
                    dr = -1 if me == 0 else 1
                    nr = r + dr
                    while 0 <= nr < BOARD_H:
                        if my_board[nr][c] != EMPTY:
                            break
                        dests.append((nr, c))
                        if opp_board[nr][c] != EMPTY:
                            break
                        nr += dr

                elif piece == KNIGHT:
                    # Knight: 2 forward, 1 sideways (jump)
                    moves = _KNIGHT_MOVES_SENTE if me == 0 else _KNIGHT_MOVES_GOTE
                    for dr, dc in moves:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < BOARD_H and 0 <= nc < BOARD_W:
                            if my_board[nr][nc] == EMPTY:
                                dests.append((nr, nc))

                elif piece == SILVER:
                    moves = _SILVER_MOVES_SENTE if me == 0 else _SILVER_MOVES_GOTE
                    for dr, dc in moves:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < BOARD_H and 0 <= nc < BOARD_W:
                            if my_board[nr][nc] == EMPTY:
                                dests.append((nr, nc))

                elif piece in (GOLD, P_PAWN, P_SILVER, P_LANCE, P_KNIGHT):
                    moves = _GOLD_MOVES_SENTE if me == 0 else _GOLD_MOVES_GOTE
                    for dr, dc in moves:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < BOARD_H and 0 <= nc < BOARD_W:
                            if my_board[nr][nc] == EMPTY:
                                dests.append((nr, nc))

                elif piece == KING:
                    for dr, dc in _KING_MOVES:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < BOARD_H and 0 <= nc < BOARD_W:
                            if my_board[nr][nc] == EMPTY:
                                dests.append((nr, nc))

                elif piece == BISHOP:
                    for dr, dc in _BISHOP_DIRS:
                        nr, nc = r + dr, c + dc
                        while 0 <= nr < BOARD_H and 0 <= nc < BOARD_W:
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
                        while 0 <= nr < BOARD_H and 0 <= nc < BOARD_W:
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
                        while 0 <= nr < BOARD_H and 0 <= nc < BOARD_W:
                            if my_board[nr][nc] != EMPTY:
                                break
                            dests.append((nr, nc))
                            if opp_board[nr][nc] != EMPTY:
                                break
                            nr += dr
                            nc += dc
                    for dr, dc in _ROOK_DIRS:  # orthogonal one-step
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < BOARD_H and 0 <= nc < BOARD_W:
                            if my_board[nr][nc] == EMPTY:
                                dests.append((nr, nc))

                elif piece == P_ROOK:
                    # Dragon: rook sliding + diagonal one-step
                    for dr, dc in _ROOK_DIRS:
                        nr, nc = r + dr, c + dc
                        while 0 <= nr < BOARD_H and 0 <= nc < BOARD_W:
                            if my_board[nr][nc] != EMPTY:
                                break
                            dests.append((nr, nc))
                            if opp_board[nr][nc] != EMPTY:
                                break
                            nr += dr
                            nc += dc
                    for dr, dc in _BISHOP_DIRS:  # diagonal one-step
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < BOARD_H and 0 <= nc < BOARD_W:
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
                        actions.append(((r, c), (tr + BOARD_H, tc)))
                        if not must:
                            # Also allow non-promotion
                            actions.append(((r, c), (tr, tc)))
                    else:
                        actions.append(((r, c), (tr, tc)))

        # --- Drop moves ---
        for pt in range(1, NUM_HAND_TYPES + 1):  # PAWN=1 through ROOK=7
            if self.hand[me][pt] <= 0:
                continue
            for r in range(BOARD_H):
                for c in range(BOARD_W):
                    if my_board[r][c] != EMPTY or opp_board[r][c] != EMPTY:
                        continue
                    # Pawn drop restrictions
                    if pt == PAWN:
                        # Cannot drop pawn on last rank
                        if (me == 0 and r == 0) or (me == 1 and r == BOARD_H - 1):
                            continue
                        # Two-pawn restriction: no column already has an unpromoted pawn
                        has_pawn_in_col = False
                        for rr in range(BOARD_H):
                            if my_board[rr][c] == PAWN:
                                has_pawn_in_col = True
                                break
                        if has_pawn_in_col:
                            continue
                    # Lance drop restriction: cannot drop on last rank
                    if pt == LANCE:
                        if (me == 0 and r == 0) or (me == 1 and r == BOARD_H - 1):
                            continue
                    # Knight drop restriction: cannot drop on last 2 ranks
                    if pt == KNIGHT:
                        if (me == 0 and r <= 1) or (me == 1 and r >= BOARD_H - 2):
                            continue
                    actions.append(((BOARD_H, pt), (r, c)))

        self.legal_actions = actions

    def position_key(self):
        """Hashable key for the current board + hand + side-to-move."""
        return (
            self.player,
            tuple(
                self.board[p][r][c]
                for p in range(2)
                for r in range(BOARD_H)
                for c in range(BOARD_W)
            ),
            tuple(
                self.hand[p][pt] for p in range(2) for pt in range(len(self.hand[0]))
            ),
        )

    # ------------------------------------------------------------------ #
    # Next state
    # ------------------------------------------------------------------ #

    def next_state(self, move):
        """Return a new KohakuShogiState after applying move."""
        frm, to = move
        fr, fc = frm
        tr, tc = to

        new_board = _deep_copy_board(self.board)
        new_hand = _deep_copy_hand(self.hand)
        me = self.player
        opp = 1 - me

        if fr == BOARD_H:
            # Drop move: fc = piece_type
            piece_type = fc
            new_hand[me][piece_type] -= 1
            new_board[me][tr][tc] = piece_type
        else:
            # Board move
            promoting = tr >= BOARD_H
            actual_tr = tr - BOARD_H if promoting else tr

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

        ns = KohakuShogiState(new_board, new_hand, opp, self.step + 1)
        ns.last_move = move
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
            mat = [0, 0]
            for p in range(2):
                for r in range(BOARD_H):
                    for c in range(BOARD_W):
                        piece = self.board[p][r][c]
                        mat[p] += _MATERIAL_TABLE.get(piece, 0)
                # Add hand material
                for pt in range(1, NUM_HAND_TYPES + 1):
                    mat[p] += self.hand[p][pt] * _MATERIAL_TABLE.get(pt, 0)

            if mat[0] > mat[1]:
                return ("win", 0)
            elif mat[1] > mat[0]:
                return ("win", 1)
            else:
                return ("draw", None)

        # Checkmate: current player is in check and every move
        # still leaves king capturable.
        probe = KohakuShogiState(self.board, self.hand, 1 - self.player, self.step)
        probe.get_legal_actions()
        if probe.game_state == "win":  # we are in check
            for move in self.legal_actions:
                child = self.next_state(move)
                if child.game_state != "win":
                    return (None, None)  # at least one escape
            return ("checkmate", 1 - self.player)

        return (None, None)

    # ------------------------------------------------------------------ #
    # State encoding for UBGI engine communication
    # ------------------------------------------------------------------ #

    def encode_state(self):
        """Encode state for the C++ engine.

        Format:
            player
            sente_board (7 rows of 6 ints)
            <blank>
            gote_board (7 rows of 6 ints)
            <blank>
            sente_hand (7 ints: P S G L N B R counts)
            gote_hand (7 ints: P S G L N B R counts)
        """
        lines = []
        lines.append(str(self.player))
        for pl in range(2):
            for r in range(BOARD_H):
                lines.append(
                    " ".join(str(self.board[pl][r][c]) for c in range(BOARD_W)) + " "
                )
            lines.append("")
        for pl in range(2):
            lines.append(
                " ".join(str(self.hand[pl][pt]) for pt in range(1, NUM_HAND_TYPES + 1))
            )
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------ #
    # Deep copy
    # ------------------------------------------------------------------ #

    def copy(self):
        """Return a deep copy of this state."""
        s = KohakuShogiState.__new__(KohakuShogiState)
        s.board = _deep_copy_board(self.board)
        s.hand = _deep_copy_hand(self.hand)
        s.player = self.player
        s.step = self.step
        s.game_state = self.game_state
        s.legal_actions = list(self.legal_actions)
        s.last_move = self.last_move
        s.hash_counts = dict(self.hash_counts)
        return s

    def __repr__(self):
        return (
            f"KohakuShogiState(player={self.player}, step={self.step}, "
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
    col_labels = "ABCDEF"
    row_labels = "7654321"

    if fr == BOARD_H:
        # Drop move: fc = piece_type
        piece_char = _DROP_PIECE_CHAR.get(fc, "?")
        return f"{piece_char}*{col_labels[tc]}{row_labels[tr]}"

    promoting = tr >= BOARD_H
    actual_tr = tr - BOARD_H if promoting else tr
    result = (
        f"{col_labels[fc]}{row_labels[fr]}->{col_labels[tc]}{row_labels[actual_tr]}"
    )
    if promoting:
        result += "+"
    return result
