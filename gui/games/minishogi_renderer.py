"""MiniShogi board renderer -- kanji pieces with direction indicators."""

import math
import pygame
import pygame.freetype

try:
    import gui.config as cfg
except ImportError:
    import config as cfg

try:
    from gui.games.minishogi_engine import (
        EMPTY,
        PAWN,
        SILVER,
        GOLD,
        BISHOP,
        ROOK,
        KING,
        P_PAWN,
        P_SILVER,
        P_BISHOP,
        P_ROOK,
        BOARD_SIZE,
        PIECE_SYMBOLS,
        PIECE_NAMES,
        _DROP_PIECE_CHAR,
    )
except ImportError:
    from games.minishogi_engine import (
        EMPTY,
        PAWN,
        SILVER,
        GOLD,
        BISHOP,
        ROOK,
        KING,
        P_PAWN,
        P_SILVER,
        P_BISHOP,
        P_ROOK,
        BOARD_SIZE,
        PIECE_SYMBOLS,
        PIECE_NAMES,
        _DROP_PIECE_CHAR,
    )

# Colors for pieces
_SENTE_BG = (240, 210, 150)  # light wood
_GOTE_BG = (190, 150, 100)  # darker wood
_PIECE_OUTLINE = (60, 40, 20)  # dark brown outline
_NORMAL_TEXT = (20, 20, 20)  # black text
_PROMOTED_TEXT = (180, 30, 30)  # red text for promoted pieces
_HAND_HIGHLIGHT = (255, 255, 100, 140)  # selected hand piece highlight

# All piece types used on the board
_ALL_PIECE_TYPES = (
    PAWN,
    SILVER,
    GOLD,
    BISHOP,
    ROOK,
    KING,
    P_PAWN,
    P_SILVER,
    P_BISHOP,
    P_ROOK,
)

# Promoted piece types (drawn in red)
_PROMOTED_TYPES = {P_PAWN, P_SILVER, P_BISHOP, P_ROOK}

# Pieces that can appear in hand (base types only), display order
_HAND_PIECES = [ROOK, BISHOP, GOLD, SILVER, PAWN]


def _pentagon_points(cx, cy, w, h, pointing_up):
    """Return vertices for a shogi-piece-shaped pentagon.

    The piece is a pointed pentagon:
      - If pointing_up: narrow top, wide bottom (sente).
      - If pointing_down: narrow bottom, wide top (gote).

    Args:
        cx, cy: center of the bounding box.
        w, h: width and height of the bounding box.
        pointing_up: True for sente, False for gote.
    """
    hw = w / 2
    hh = h / 2
    shoulder = hw * 0.85  # half-width at shoulder

    if pointing_up:
        top = cy - hh
        bot = cy + hh
        points = [
            (cx, top),  # tip
            (cx + shoulder, top + 0.3 * h),  # right shoulder
            (cx + hw * 0.82, bot),  # right base
            (cx - hw * 0.82, bot),  # left base
            (cx - shoulder, top + 0.3 * h),  # left shoulder
        ]
    else:
        top = cy - hh
        bot = cy + hh
        points = [
            (cx, bot),  # tip (bottom)
            (cx - shoulder, bot - 0.3 * h),  # left shoulder
            (cx - hw * 0.82, top),  # left base (top)
            (cx + hw * 0.82, top),  # right base (top)
            (cx + shoulder, bot - 0.3 * h),  # right shoulder
        ]
    return points


class MiniShogiRenderer:
    """Renders MiniShogi board with kanji pieces in pentagon shapes."""

    # Font preference: Japanese fonts first, then fallback
    _KANJI_FONT_CANDIDATES = (
        "Noto Sans JP",
        "Noto Sans CJK JP",
        "Yu Mincho",
        "YuMincho",
        "MS Mincho",
        "MS Gothic",
        "Meiryo",
        "Arial Unicode MS",
        "Apple Symbols",
        "Segoe UI Symbol",
    )
    _FALLBACK_FONT_CANDIDATES = (
        "Apple Symbols",
        "Segoe UI Symbol",
        "DejaVu Sans",
        "Arial",
        "Menlo",
        None,
    )

    def __init__(self, surface):
        self.surface = surface
        self._use_kanji = False

        # Piece size (slightly smaller than square to leave margin)
        self._piece_w = int(cfg.SQUARE_SIZE * 0.78)
        self._piece_h = int(cfg.SQUARE_SIZE * 0.88)

        # Hand piece layout metrics
        self._hand_small_w = int(self._piece_w * 0.65)
        self._hand_small_h = int(self._piece_h * 0.65)
        self._hand_spacing_x = self._hand_small_w + 16  # horizontal spacing

        # Hand piece hit-test rects: (player, piece_type) -> pygame.Rect
        self._hand_rects = {}

        # Currently selected hand piece for highlighting: (BOARD_SIZE, piece_type) or None
        self._selected_hand = None

        # Try to find a font that can render kanji
        self._piece_font = None
        kanji_size = int(cfg.SQUARE_SIZE * 0.44)
        for name in self._KANJI_FONT_CANDIDATES:
            try:
                font = pygame.freetype.SysFont(name, kanji_size)
                if "freesansbold" in getattr(font, "path", ""):
                    continue
                surf, rect = font.render("\u738b", fgcolor=(0, 0, 0))
                if rect.width > 2 and rect.height > 2:
                    self._piece_font = font
                    self._use_kanji = True
                    break
            except Exception:
                continue

        # Fallback: use Latin abbreviations
        if self._piece_font is None:
            for name in self._FALLBACK_FONT_CANDIDATES:
                try:
                    font = pygame.freetype.SysFont(name, kanji_size)
                    if name is not None and "freesansbold" in getattr(font, "path", ""):
                        continue
                    self._piece_font = font
                    break
                except Exception:
                    continue
            if self._piece_font is None:
                self._piece_font = pygame.freetype.Font(None, kanji_size)

        # Hand font: same font family as pieces, just smaller
        hand_size = int(cfg.SQUARE_SIZE * 0.30)
        self._hand_font = None
        if self._use_kanji and self._piece_font is not None:
            # Re-create the same kanji font at hand size
            for name in self._KANJI_FONT_CANDIDATES:
                try:
                    font = pygame.freetype.SysFont(name, hand_size)
                    if "freesansbold" in getattr(font, "path", ""):
                        continue
                    surf, rect = font.render("\u738b", fgcolor=(0, 0, 0))
                    if rect.width > 2 and rect.height > 2:
                        self._hand_font = font
                        break
                except Exception:
                    continue
        if self._hand_font is None:
            for name in self._FALLBACK_FONT_CANDIDATES:
                try:
                    self._hand_font = pygame.freetype.SysFont(name, hand_size)
                    break
                except Exception:
                    continue
            if self._hand_font is None:
                self._hand_font = pygame.freetype.Font(None, hand_size)

        # Number font for PV labels
        self._num_font = pygame.font.SysFont("Arial", 14, bold=True)

        # Pre-render piece surfaces
        self._piece_cache = {}  # (player, piece_type) -> Surface
        self._pre_render_pieces()

    def _pre_render_pieces(self):
        """Pre-render all piece shapes with text."""
        for player in (0, 1):
            for pt in _ALL_PIECE_TYPES:
                self._piece_cache[(player, pt)] = self._render_piece(player, pt, 255)

    def _render_piece(self, player, piece_type, alpha=255):
        """Render a single piece as a surface with transparent background."""
        w = self._piece_w
        h = self._piece_h
        surf = pygame.Surface((w + 4, h + 4), pygame.SRCALPHA)
        cx = (w + 4) / 2
        cy = (h + 4) / 2

        pointing_up = player == 0
        pts = _pentagon_points(cx, cy, w, h, pointing_up)

        # Background fill
        bg = _SENTE_BG if player == 0 else _GOTE_BG
        bg_alpha = (bg[0], bg[1], bg[2], alpha)
        pygame.draw.polygon(surf, bg_alpha, pts)
        # Outline
        outline_alpha = (_PIECE_OUTLINE[0], _PIECE_OUTLINE[1], _PIECE_OUTLINE[2], alpha)
        pygame.draw.polygon(surf, outline_alpha, pts, 2)

        # Text
        is_promoted = piece_type in _PROMOTED_TYPES
        text_color = _PROMOTED_TEXT if is_promoted else _NORMAL_TEXT
        text_color_alpha = (text_color[0], text_color[1], text_color[2], alpha)

        if self._use_kanji:
            char = PIECE_SYMBOLS.get(player, {}).get(piece_type, "?")
        else:
            char = PIECE_NAMES.get(piece_type, "?")

        try:
            text_surf, text_rect = self._piece_font.render(
                char, fgcolor=text_color_alpha
            )
        except Exception:
            text_surf, text_rect = self._piece_font.render(
                "?", fgcolor=text_color_alpha
            )

        tx = cx - text_rect.width / 2
        ty = cy - text_rect.height / 2
        surf.blit(text_surf, (tx, ty))

        return surf

    # ------------------------------------------------------------------ #
    # Public drawing API
    # ------------------------------------------------------------------ #

    def draw_pieces(self, state):
        """Draw all pieces on the board and hand pieces in sidebars."""
        self._draw_board_pieces(state)
        self._draw_hand_pieces(state)

    def set_selected_hand(self, selected):
        """Set the currently selected hand piece for highlighting.

        Args:
            selected: (BOARD_SIZE, piece_type) tuple or None.
        """
        self._selected_hand = selected

    # ------------------------------------------------------------------ #
    # Board pieces
    # ------------------------------------------------------------------ #

    def _draw_board_pieces(self, state):
        """Draw pieces on the 5x5 board."""
        for player in (0, 1):
            for row in range(BOARD_SIZE):
                for col in range(BOARD_SIZE):
                    piece = state.board[player][row][col]
                    if piece == EMPTY:
                        continue

                    surf = self._piece_cache.get((player, piece))
                    if surf is None:
                        continue

                    sx = cfg.BOARD_X + col * cfg.SQUARE_SIZE
                    sy = cfg.BOARD_Y + row * cfg.SQUARE_SIZE
                    # Center the piece in the square
                    px = sx + (cfg.SQUARE_SIZE - surf.get_width()) // 2
                    py = sy + (cfg.SQUARE_SIZE - surf.get_height()) // 2

                    self.surface.blit(surf, (px, py))

    # ------------------------------------------------------------------ #
    # Hand pieces
    # ------------------------------------------------------------------ #

    def _draw_hand_pieces(self, state):
        """Draw captured pieces in horizontal rows above/below the board.

        Gote's hand: row above board.  Sente's hand: row below board.
        Each piece is a small pentagon with count in bottom-right.
        """
        if not hasattr(state, "hand"):
            return

        self._hand_rects.clear()
        sw = self._hand_small_w
        sh = self._hand_small_h
        spacing_x = self._hand_spacing_x
        hand_h = getattr(cfg, "HAND_ROW_H", 36)

        for player in (0, 1):
            if player == 1:
                # Gote's hand: above board
                base_y = getattr(cfg, "HAND_TOP_Y", cfg.BOARD_Y - hand_h)
            else:
                # Sente's hand: below board
                base_y = getattr(cfg, "HAND_BOTTOM_Y", cfg.BOARD_Y + cfg.BOARD_PIXEL_H)

            # Center the row horizontally within the board width
            total_w = len(_HAND_PIECES) * spacing_x
            start_x = cfg.BOARD_X + (cfg.BOARD_PIXEL_W - total_w) // 2
            cy = base_y + hand_h // 2

            for idx, pt in enumerate(_HAND_PIECES):
                count = state.hand[player][pt]
                draw_x = start_x + idx * spacing_x
                draw_y = int(cy - sh / 2)

                self._hand_rects[(player, pt)] = pygame.Rect(
                    draw_x, draw_y, sw + 4, sh + 4
                )

                # Highlight if selected
                if (
                    self._selected_hand is not None
                    and self._selected_hand == (BOARD_SIZE, pt)
                    and player == state.current_player
                ):
                    hl = pygame.Surface((sw + 8, sh + 8), pygame.SRCALPHA)
                    hl.fill(_HAND_HIGHLIGHT)
                    self.surface.blit(hl, (draw_x - 2, draw_y - 2))

                # Draw piece shape (dimmed if count == 0)
                small_surf = pygame.Surface((sw + 4, sh + 4), pygame.SRCALPHA)
                scx = (sw + 4) / 2
                scy_local = (sh + 4) / 2
                pointing_up = player == 0
                pts = _pentagon_points(scx, scy_local, sw, sh, pointing_up)

                if count > 0:
                    bg = _SENTE_BG if player == 0 else _GOTE_BG
                else:
                    bg = (120, 110, 100)  # dimmed for empty hand slot
                pygame.draw.polygon(small_surf, bg, pts)
                pygame.draw.polygon(small_surf, _PIECE_OUTLINE, pts, 1)

                # Piece character
                char = (
                    PIECE_SYMBOLS.get(player, {}).get(pt, "?")
                    if self._use_kanji
                    else PIECE_NAMES.get(pt, "?")
                )
                try:
                    fg = _NORMAL_TEXT if count > 0 else (100, 90, 80)
                    text_surf, text_rect = self._hand_font.render(char, fgcolor=fg)
                    small_surf.blit(
                        text_surf,
                        (scx - text_rect.width / 2, scy_local - text_rect.height / 2),
                    )
                except Exception:
                    pass

                self.surface.blit(small_surf, (draw_x, draw_y))

                # Count badge in bottom-right
                if count > 0:
                    try:
                        cnt_text = str(count)
                        cnt_surf, cnt_rect = self._hand_font.render(
                            cnt_text, fgcolor=cfg.COLOR_TEXT
                        )
                        # Small background circle for readability
                        badge_r = max(cnt_rect.width, cnt_rect.height) // 2 + 2
                        bx = draw_x + sw + 2
                        by = draw_y + sh - 2
                        pygame.draw.circle(
                            self.surface, (40, 40, 44), (bx, by), badge_r
                        )
                        self.surface.blit(
                            cnt_surf,
                            (bx - cnt_rect.width // 2, by - cnt_rect.height // 2),
                        )
                    except Exception:
                        pass

    def screen_to_hand(self, x, y, state):
        """Check if screen coordinates (x, y) hit a hand piece.

        Returns:
            (BOARD_SIZE, piece_type) if a hand piece for the current player
            was clicked and has count > 0, else None.
        """
        if not hasattr(state, "hand"):
            return None
        player = state.current_player
        for pt in _HAND_PIECES:
            rect = self._hand_rects.get((player, pt))
            if rect is not None and rect.collidepoint(x, y):
                if state.hand[player][pt] > 0:
                    return (BOARD_SIZE, pt)
        return None

    # ------------------------------------------------------------------ #
    # PV visualization
    # ------------------------------------------------------------------ #

    def draw_pv(self, state, pv_moves):
        """Draw semi-transparent ghost pieces for the principal variation."""
        if not pv_moves:
            return

        col_map = {chr(ord("a") + i): i for i in range(BOARD_SIZE)}
        row_map = {str(BOARD_SIZE - i): i for i in range(BOARD_SIZE)}

        current_player = state.current_player

        max_pv = min(len(pv_moves), 6)
        for i in range(max_pv):
            uci = pv_moves[i]
            if not uci:
                continue

            player_turn = (current_player + i) % 2
            alpha = max(80, 180 - i * 20)

            # Parse move format
            if len(uci) >= 3 and uci[1] == "*":
                # Drop move: e.g. "P*c3" — arrow from hand to target
                tc = col_map.get(uci[2])
                tr = row_map.get(uci[3]) if len(uci) > 3 else None
                if tc is None or tr is None:
                    continue
                drop_map = {"P": PAWN, "S": SILVER, "G": GOLD, "B": BISHOP, "R": ROOK}
                drop_pt = drop_map.get(uci[0].upper(), PAWN)

                # Find the hand piece rect as arrow source
                hand_rect = self._hand_rects.get((player_turn, drop_pt))
                if hand_rect is not None:
                    fx = hand_rect.centerx
                    fy = hand_rect.centery
                else:
                    # Fallback: arrow starts from side of board
                    fx = cfg.BOARD_X - 20 if player_turn == 0 else cfg.BOARD_X - 20
                    fy = cfg.BOARD_Y + cfg.BOARD_PIXEL_H // 2

                tx = cfg.BOARD_X + tc * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                ty = cfg.BOARD_Y + tr * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2

                if i == 0:
                    color = (80, 220, 80, alpha)
                else:
                    color = (80, 160, 230, alpha)

                self._draw_arrow(fx, fy, tx, ty, color, i)
                self._draw_pv_number(tx, ty, i + 1, player_turn, alpha)

            elif len(uci) >= 4:
                # Board move: e.g. "a1b2" or "a1b2+"
                fc = col_map.get(uci[0])
                fr = row_map.get(uci[1])
                tc = col_map.get(uci[2])
                tr = row_map.get(uci[3])
                if any(v is None for v in (fc, fr, tc, tr)):
                    continue

                # Draw arrow from source to destination
                fx = cfg.BOARD_X + fc * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                fy = cfg.BOARD_Y + fr * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                tx = cfg.BOARD_X + tc * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                ty = cfg.BOARD_Y + tr * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2

                if i == 0:
                    color = (80, 220, 80, alpha)
                else:
                    color = (80, 160, 230, alpha)

                self._draw_arrow(fx, fy, tx, ty, color, i)

                # Move number at midpoint
                mid_x = (fx + tx) // 2
                mid_y = (fy + ty) // 2
                self._draw_pv_number(mid_x, mid_y, i + 1, player_turn, alpha)

    def _draw_arrow(self, fx, fy, tx, ty, color, idx):
        """Draw a directional arrow directly on the surface."""
        dx = tx - fx
        dy = ty - fy
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1:
            return

        # Use a full-window overlay so arrows are never clipped
        overlay = pygame.Surface(
            (cfg.WINDOW_W, cfg.WINDOW_H),
            pygame.SRCALPHA,
        )

        ux, uy = dx / length, dy / length
        shaft_w = max(3, 6 - idx)
        head_len = min(18, length * 0.3)
        head_w = head_len * 0.6

        sx2 = tx - ux * head_len
        sy2 = ty - uy * head_len
        pygame.draw.line(overlay, color, (fx, fy), (sx2, sy2), shaft_w)

        px, py = -uy, ux
        points = [
            (tx, ty),
            (sx2 + px * head_w, sy2 + py * head_w),
            (sx2 - px * head_w, sy2 - py * head_w),
        ]
        pygame.draw.polygon(overlay, color, points)

        self.surface.blit(overlay, (0, 0))

    def _draw_pv_number(self, cx, cy, number, player, alpha):
        """Draw a numbered circle for PV move ordering."""
        fg = (255, 255, 255) if player == 0 else (0, 0, 0)
        num_surf = self._num_font.render(str(number), True, fg)
        nr = max(num_surf.get_width(), num_surf.get_height()) // 2 + 3
        bg_surf = pygame.Surface((nr * 2 + 2, nr * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(bg_surf, (0, 0, 0, min(200, alpha)), (nr + 1, nr + 1), nr)
        self.surface.blit(bg_surf, (cx - nr - 1, cy - nr - 1))
        self.surface.blit(
            num_surf,
            (cx - num_surf.get_width() // 2, cy - num_surf.get_height() // 2),
        )
