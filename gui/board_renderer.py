"""Board renderer for MiniChess GUI using Pygame."""

import pygame
import pygame.freetype

try:
    from gui.config import *
except ImportError:
    from config import *


class BoardRenderer:
    """Renders the MiniChess board on a Pygame surface."""

    # Font candidates in preference order
    _FONT_CANDIDATES = ("Segoe UI Symbol", "DejaVu Sans", "Arial Unicode MS", None)

    def __init__(self, surface):
        """Initialize fonts and pre-render piece glyphs.

        Uses pygame.freetype for Unicode chess pieces. Tries fonts in order:
        "Segoe UI Symbol", "DejaVu Sans", "Arial Unicode MS", None (default).
        Pre-renders all 12 piece glyphs (2 players x 6 piece types) for
        performance.
        """
        self.surface = surface

        # --- resolve a font that can render chess Unicode glyphs ----------
        self.piece_font = None
        for name in self._FONT_CANDIDATES:
            try:
                font = pygame.freetype.SysFont(name, FONT_SIZE_PIECE)
                # Quick sanity check: try rendering a white king glyph
                font.render(PIECE_UNICODE[0][KING], fgcolor=(255, 255, 255))
                self.piece_font = font
                break
            except Exception:
                continue
        if self.piece_font is None:
            # Absolute fallback – use the freetype default font
            self.piece_font = pygame.freetype.Font(None, FONT_SIZE_PIECE)

        # Label font
        self.label_font = None
        for name in self._FONT_CANDIDATES:
            try:
                self.label_font = pygame.freetype.SysFont(name, FONT_SIZE_LABEL)
                break
            except Exception:
                continue
        if self.label_font is None:
            self.label_font = pygame.freetype.Font(None, FONT_SIZE_LABEL)

        # --- pre-render piece glyphs -------------------------------------
        # _glyphs[player][piece_type] = (main_surface, shadow_surface, rect)
        self._glyphs = {0: {}, 1: {}}
        self._pre_render_glyphs()

    # -----------------------------------------------------------------
    # Pre-rendering helpers
    # -----------------------------------------------------------------

    def _pre_render_glyphs(self):
        """Pre-render all 12 chess piece glyphs with shadow for contrast."""
        shadow_color = (0, 0, 0)
        piece_colors = {0: COLOR_WHITE_PIECE, 1: COLOR_BLACK_PIECE}

        for player in (0, 1):
            for piece_type in (PAWN, ROOK, KNIGHT, BISHOP, QUEEN, KING):
                char = PIECE_UNICODE[player][piece_type]
                fg = piece_colors[player]

                main_surf, main_rect = self.piece_font.render(char, fgcolor=fg)
                shadow_surf, _ = self.piece_font.render(char, fgcolor=shadow_color)

                self._glyphs[player][piece_type] = (main_surf, shadow_surf, main_rect)

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def draw(self, state, selected=None, legal_moves=None, last_move=None, pv_arrows=None):
        self._draw_squares()
        self._draw_last_move(last_move)
        self._draw_selected(selected)
        self._draw_legal_moves(state, selected, legal_moves)
        self._draw_pieces(state)
        if pv_arrows:
            self._draw_pv_arrows(pv_arrows)
        self._draw_labels()

    def screen_to_board(self, x, y):
        """Convert screen (x, y) to board (row, col).

        Returns (row, col) or None if the click is outside the board area.
        """
        if (
            x < BOARD_X
            or x >= BOARD_X + BOARD_PIXEL_W
            or y < BOARD_Y
            or y >= BOARD_Y + BOARD_PIXEL_H
        ):
            return None

        col = (x - BOARD_X) // SQUARE_SIZE
        row = (y - BOARD_Y) // SQUARE_SIZE

        # Clamp to valid range (defensive)
        col = max(0, min(col, BOARD_W - 1))
        row = max(0, min(row, BOARD_H - 1))

        return (row, col)

    def board_to_screen(self, row, col):
        """Convert board (row, col) to the top-left pixel (x, y) of that square."""
        x = BOARD_X + col * SQUARE_SIZE
        y = BOARD_Y + row * SQUARE_SIZE
        return (x, y)

    # -----------------------------------------------------------------
    # Internal drawing helpers
    # -----------------------------------------------------------------

    def _draw_squares(self):
        """Draw the alternating light/dark board squares."""
        for row in range(BOARD_H):
            for col in range(BOARD_W):
                x, y = self.board_to_screen(row, col)
                color = COLOR_LIGHT_SQ if (row + col) % 2 == 0 else COLOR_DARK_SQ
                pygame.draw.rect(self.surface, color, (x, y, SQUARE_SIZE, SQUARE_SIZE))

    def _draw_overlay(self, row, col, color_with_alpha):
        """Draw a semi-transparent overlay on a single square."""
        overlay = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
        overlay.fill(color_with_alpha)
        x, y = self.board_to_screen(row, col)
        self.surface.blit(overlay, (x, y))

    def _draw_last_move(self, last_move):
        """Highlight the from/to squares of the last move with a blue tint."""
        if last_move is None:
            return
        (fr, fc), (tr, tc) = last_move
        self._draw_overlay(fr, fc, COLOR_LAST_MOVE)
        self._draw_overlay(tr, tc, COLOR_LAST_MOVE)

    def _draw_selected(self, selected):
        """Highlight the currently selected piece square with a yellow tint."""
        if selected is None:
            return
        row, col = selected
        self._draw_overlay(row, col, COLOR_HIGHLIGHT)

    def _draw_legal_moves(self, state, selected, legal_moves):
        """Draw green indicators on each legal destination square.

        A filled green circle is drawn for empty destination squares.
        A green ring (hollow circle) is drawn if the destination contains an
        opponent piece.
        """
        if selected is None or legal_moves is None:
            return

        src = selected
        opponent = 1 - state.current_player
        radius = 12
        ring_width = 3

        for move in legal_moves:
            (fr, fc), (tr, tc) = move
            if (fr, fc) != src:
                continue

            cx, cy = self.board_to_screen(tr, tc)
            cx += SQUARE_SIZE // 2
            cy += SQUARE_SIZE // 2

            # Check whether the destination has an opponent piece
            opponent_piece = self._get_piece(state, opponent, tr, tc)
            has_opponent = opponent_piece is not None

            # Use a per-pixel alpha surface for the indicator
            overlay = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
            local_cx = SQUARE_SIZE // 2
            local_cy = SQUARE_SIZE // 2

            if has_opponent:
                pygame.draw.circle(
                    overlay,
                    COLOR_LEGAL,
                    (local_cx, local_cy),
                    SQUARE_SIZE // 2 - 4,
                    ring_width,
                )
            else:
                pygame.draw.circle(overlay, COLOR_LEGAL, (local_cx, local_cy), radius)

            sq_x, sq_y = self.board_to_screen(tr, tc)
            self.surface.blit(overlay, (sq_x, sq_y))

    def _draw_pieces(self, state):
        """Draw all pieces on the board using pre-rendered glyphs.

        The board layout ``state.board[player][row][col]`` stores the piece
        type at each square for each player (0 = empty).

        Pieces are drawn with a subtle shadow for contrast: the shadow glyph
        is blitted at slight offsets first, then the main-color glyph on top.
        """
        shadow_offsets = [(-1, -1), (1, -1), (-1, 1), (1, 1)]

        for player in (0, 1):
            for row in range(BOARD_H):
                for col in range(BOARD_W):
                    piece_type = self._get_piece(state, player, row, col)
                    if piece_type is None or piece_type == EMPTY:
                        continue

                    main_surf, shadow_surf, glyph_rect = self._glyphs[player][
                        piece_type
                    ]

                    sx, sy = self.board_to_screen(row, col)
                    # Center the glyph in the square
                    cx = sx + (SQUARE_SIZE - glyph_rect.width) // 2
                    cy = sy + (SQUARE_SIZE - glyph_rect.height) // 2

                    # Shadow pass
                    for dx, dy in shadow_offsets:
                        self.surface.blit(shadow_surf, (cx + dx, cy + dy))

                    # Main colour pass
                    self.surface.blit(main_surf, (cx, cy))

    def _get_piece(self, state, player, row, col):
        """Return the piece type for *player* at (row, col), or None.

        Supports two common board representations:
        A) state.board[player][row][col] -> piece_type int
        B) state.board[player][piece_type][row][col] -> 0/1 bitboard style
        """
        try:
            val = state.board[player][row][col]
            # Representation A: value is the piece type directly
            if isinstance(val, (int, float)):
                return int(val) if int(val) != EMPTY else None
            # Might be a nested array (representation B row)
        except (TypeError, IndexError, KeyError):
            pass

        # Representation B: iterate piece types
        for pt in (PAWN, ROOK, KNIGHT, BISHOP, QUEEN, KING):
            try:
                if state.board[player][pt][row][col]:
                    return pt
            except (TypeError, IndexError, KeyError):
                continue

        return None

    def _draw_pv_arrows(self, pv_moves):
        """Draw numbered arrows on the board for the principal variation."""
        import math

        if not pv_moves:
            return

        col_map = {"a": 0, "b": 1, "c": 2, "d": 3, "e": 4}
        row_map = {"6": 0, "5": 1, "4": 2, "3": 3, "2": 4, "1": 5}

        overlay = pygame.Surface(
            (BOARD_PIXEL_W + 2 * LABEL_MARGIN, BOARD_PIXEL_H + 2 * LABEL_MARGIN),
            pygame.SRCALPHA,
        )

        num_font = pygame.font.SysFont("Arial", 14, bold=True)

        max_arrows = min(len(pv_moves), 6)
        for i in range(max_arrows):
            uci = pv_moves[i]
            if len(uci) < 4:
                continue

            fc = col_map.get(uci[0])
            fr = row_map.get(uci[1])
            tc = col_map.get(uci[2])
            tr = row_map.get(uci[3])
            if any(v is None for v in (fc, fr, tc, tr)):
                continue

            alpha = max(60, 220 - i * 30)
            if i == 0:
                color = (80, 220, 80, alpha)
            else:
                color = (80, 160, 230, alpha)

            fx, fy = self.board_to_screen(fr, fc)
            tx, ty = self.board_to_screen(tr, tc)
            fx += SQUARE_SIZE // 2
            fy += SQUARE_SIZE // 2
            tx += SQUARE_SIZE // 2
            ty += SQUARE_SIZE // 2

            dx = tx - fx
            dy = ty - fy
            length = math.sqrt(dx * dx + dy * dy)
            if length < 1:
                continue
            ux, uy = dx / length, dy / length

            shaft_w = max(3, 7 - i)
            head_len = min(20, length * 0.3)
            head_w = head_len * 0.65

            # Shaft ends at the base of the arrowhead (not the tip)
            sx2 = tx - ux * head_len
            sy2 = ty - uy * head_len
            pygame.draw.line(overlay, color, (fx, fy), (sx2, sy2), shaft_w)

            # Arrowhead triangle
            px, py = -uy, ux
            points = [
                (tx, ty),
                (sx2 + px * head_w, sy2 + py * head_w),
                (sx2 - px * head_w, sy2 - py * head_w),
            ]
            pygame.draw.polygon(overlay, color, points)

            # Step number at midpoint of the arrow
            mid_x = (fx + tx) / 2
            mid_y = (fy + ty) / 2
            # Offset perpendicular to arrow so number doesn't sit on the shaft
            off = 10
            num_x = mid_x + px * off
            num_y = mid_y + py * off
            num_surf = num_font.render(str(i + 1), True, (255, 255, 255))
            # Background circle for readability
            nr = max(num_surf.get_width(), num_surf.get_height()) // 2 + 3
            pygame.draw.circle(
                overlay, (0, 0, 0, min(200, alpha)),
                (int(num_x), int(num_y)), nr,
            )
            overlay.blit(
                num_surf,
                (num_x - num_surf.get_width() / 2, num_y - num_surf.get_height() / 2),
            )

        self.surface.blit(overlay, (0, 0))

    def _draw_labels(self):
        """Draw row labels (6-1) on the left and column labels (A-E) below."""
        for row in range(BOARD_H):
            label = ROW_LABELS[row]
            sx, sy = self.board_to_screen(row, 0)
            # Position to the left of the first column, vertically centred
            lx = BOARD_X - LABEL_MARGIN
            ly = sy + SQUARE_SIZE // 2

            surf, rect = self.label_font.render(label, fgcolor=COLOR_TEXT_DIM)
            self.surface.blit(
                surf, (lx + (LABEL_MARGIN - rect.width) // 2, ly - rect.height // 2)
            )

        for col in range(BOARD_W):
            label = COL_LABELS[col]
            sx, sy = self.board_to_screen(BOARD_H - 1, col)
            # Position below the last row, horizontally centred
            lx = sx + SQUARE_SIZE // 2
            ly = BOARD_Y + BOARD_PIXEL_H

            surf, rect = self.label_font.render(label, fgcolor=COLOR_TEXT_DIM)
            self.surface.blit(
                surf, (lx - rect.width // 2, ly + (LABEL_MARGIN - rect.height) // 2)
            )
