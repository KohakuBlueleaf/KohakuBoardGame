"""Kohaku Shogi board renderer -- kanji pieces with direction indicators."""

import math
import pygame
import pygame.freetype

try:
    import gui.config as cfg
except ImportError:
    import config as cfg

try:
    from gui.games.kohakushogi_engine import (
        EMPTY,
        PAWN,
        SILVER,
        GOLD,
        LANCE,
        KNIGHT,
        BISHOP,
        ROOK,
        KING,
        P_PAWN,
        P_SILVER,
        P_LANCE,
        P_KNIGHT,
        P_BISHOP,
        P_ROOK,
        BOARD_H,
        BOARD_W,
        PIECE_SYMBOLS,
        PIECE_NAMES,
        DROP_PIECE_CHAR,
        CHAR_TO_DROP_PIECE,
    )
except ImportError:
    from games.kohakushogi_engine import (
        EMPTY,
        PAWN,
        SILVER,
        GOLD,
        LANCE,
        KNIGHT,
        BISHOP,
        ROOK,
        KING,
        P_PAWN,
        P_SILVER,
        P_LANCE,
        P_KNIGHT,
        P_BISHOP,
        P_ROOK,
        BOARD_H,
        BOARD_W,
        PIECE_SYMBOLS,
        PIECE_NAMES,
        DROP_PIECE_CHAR,
        CHAR_TO_DROP_PIECE,
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
    LANCE,
    KNIGHT,
    BISHOP,
    ROOK,
    KING,
    P_PAWN,
    P_SILVER,
    P_LANCE,
    P_KNIGHT,
    P_BISHOP,
    P_ROOK,
)

# Promoted piece types (drawn in red)
_PROMOTED_TYPES = {P_PAWN, P_SILVER, P_LANCE, P_KNIGHT, P_BISHOP, P_ROOK}

# Pieces that can appear in hand (base types only), display order
_HAND_PIECES = [ROOK, BISHOP, GOLD, SILVER, KNIGHT, LANCE, PAWN]


def _pentagon_points(cx, cy, w, h, pointing_up):
    """Return vertices for a shogi-piece-shaped pentagon.

    Traditional shogi piece shape: narrow tip (top for sente),
    wide flat base (bottom for sente). All interior angles > 90°.
    The base is wider than the shoulders.
    """
    # Base (bottom for sente) is the widest part
    base_hw = w * 0.50       # half-width of base
    shoulder_hw = w * 0.42   # half-width at shoulder
    tip_y_frac = 0.0         # tip at the very top
    shoulder_y_frac = 0.28   # shoulder ~28% from tip
    hh = h / 2

    if pointing_up:
        top = cy - hh
        bot = cy + hh
        points = [
            (cx, top),                                     # tip (narrow top)
            (cx + shoulder_hw, top + shoulder_y_frac * h),  # right shoulder
            (cx + base_hw, bot),                            # right base (widest)
            (cx - base_hw, bot),                            # left base (widest)
            (cx - shoulder_hw, top + shoulder_y_frac * h),  # left shoulder
        ]
    else:
        top = cy - hh
        bot = cy + hh
        points = [
            (cx, bot),                                     # tip (narrow bottom)
            (cx - shoulder_hw, bot - shoulder_y_frac * h),  # left shoulder
            (cx - base_hw, top),                            # left base (widest)
            (cx + base_hw, top),                            # right base (widest)
            (cx + shoulder_hw, bot - shoulder_y_frac * h),  # right shoulder
        ]
    return points


class KohakuShogiRenderer:
    """Renders Kohaku Shogi board with kanji pieces in pentagon shapes."""

    # Bundled font path (relative to gui/ directory)
    _BUNDLED_FONT = None  # set in __init__

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

        self._piece_w = int(cfg.SQUARE_SIZE * 0.78)
        self._piece_h = int(cfg.SQUARE_SIZE * 0.88)

        self._hand_small_w = int(self._piece_w * 0.65)
        self._hand_small_h = int(self._piece_h * 0.65)
        self._hand_spacing_x = self._hand_small_w + 16

        self._hand_rects = {}
        self._selected_hand = None

        kanji_size = int(cfg.SQUARE_SIZE * 0.44)
        self._piece_font = None

        # Try bundled Zen Old Mincho font first
        import os
        font_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fonts")
        bundled_path = os.path.join(font_dir, "ZenOldMincho-Bold.ttf")
        if os.path.isfile(bundled_path):
            try:
                font = pygame.freetype.Font(bundled_path, kanji_size)
                surf, rect = font.render("\u738b", fgcolor=(0, 0, 0))
                if rect.width > 2 and rect.height > 2:
                    self._piece_font = font
                    self._use_kanji = True
                    self._bundled_font = bundled_path
            except Exception:
                pass

        # Fallback: try system fonts
        if self._piece_font is None:
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

        hand_size = int(cfg.SQUARE_SIZE * 0.30)
        self._hand_font = None
        # Try bundled font for hand pieces too
        if self._bundled_font:
            try:
                self._hand_font = pygame.freetype.Font(self._bundled_font, hand_size)
            except Exception:
                pass
        if self._hand_font is None and self._use_kanji and self._piece_font is not None:
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

        self._num_font = pygame.font.SysFont("Arial", 14, bold=True)

        self._piece_cache = {}
        self._pre_render_pieces()

    def _pre_render_pieces(self):
        for player in (0, 1):
            for pt in _ALL_PIECE_TYPES:
                self._piece_cache[(player, pt)] = self._render_piece(player, pt, 255)

    def _render_piece(self, player, piece_type, alpha=255):
        # Render at 2x then downscale for anti-aliasing
        scale = 2
        w = self._piece_w * scale
        h = self._piece_h * scale
        surf_big = pygame.Surface((w + 4 * scale, h + 4 * scale), pygame.SRCALPHA)
        cx = (w + 4 * scale) / 2
        cy = (h + 4 * scale) / 2

        pointing_up = player == 0
        pts = _pentagon_points(cx, cy, w, h, pointing_up)

        bg = _SENTE_BG if player == 0 else _GOTE_BG
        bg_alpha = (bg[0], bg[1], bg[2], alpha)
        pygame.draw.polygon(surf_big, bg_alpha, pts)
        outline_alpha = (_PIECE_OUTLINE[0], _PIECE_OUTLINE[1], _PIECE_OUTLINE[2], alpha)
        pygame.draw.polygon(surf_big, outline_alpha, pts, max(2, scale))

        is_promoted = piece_type in _PROMOTED_TYPES
        text_color = _PROMOTED_TEXT if is_promoted else _NORMAL_TEXT
        text_color_alpha = (text_color[0], text_color[1], text_color[2], alpha)

        if self._use_kanji:
            char = PIECE_SYMBOLS.get(player, {}).get(piece_type, "?")
        else:
            char = PIECE_NAMES.get(piece_type, "?")

        # Render text at 2x size for the big surface
        try:
            if self._bundled_font:
                big_font = pygame.freetype.Font(self._bundled_font, int(self._piece_font.size * scale))
            else:
                big_font = pygame.freetype.SysFont(
                    self._piece_font.name if hasattr(self._piece_font, 'name') else None,
                    int(self._piece_font.size * scale),
                )
            text_surf, text_rect = big_font.render(char, fgcolor=text_color_alpha)
        except Exception:
            try:
                text_surf, text_rect = self._piece_font.render(
                    char, fgcolor=text_color_alpha
                )
            except Exception:
                text_surf, text_rect = self._piece_font.render(
                    "?", fgcolor=text_color_alpha
                )

        # Rotate text 180° for gote (player 1)
        if player == 1:
            text_surf = pygame.transform.rotate(text_surf, 180)

        # Position text slightly toward base (down for sente, up for gote)
        base_offset = h * 0.06 if player == 0 else -h * 0.06
        tx = cx - text_rect.width / 2
        ty = cy - text_rect.height / 2 + base_offset

        surf_big.blit(text_surf, (tx, ty))

        # Downscale 2x → 1x with smoothing for anti-aliased result
        final_w = self._piece_w + 4
        final_h = self._piece_h + 4
        surf = pygame.transform.smoothscale(surf_big, (final_w, final_h))
        return surf

    # ------------------------------------------------------------------ #
    # Public drawing API
    # ------------------------------------------------------------------ #

    def draw_pieces(self, state):
        self._draw_board_pieces(state)
        self._draw_hand_pieces(state)

    def set_selected_hand(self, selected):
        self._selected_hand = selected

    # ------------------------------------------------------------------ #
    # Board pieces
    # ------------------------------------------------------------------ #

    def _draw_board_pieces(self, state):
        for player in (0, 1):
            for row in range(BOARD_H):
                for col in range(BOARD_W):
                    piece = state.board[player][row][col]
                    if piece == EMPTY:
                        continue

                    surf = self._piece_cache.get((player, piece))
                    if surf is None:
                        continue

                    sx = cfg.BOARD_X + col * cfg.SQUARE_SIZE
                    sy = cfg.BOARD_Y + row * cfg.SQUARE_SIZE
                    px = sx + (cfg.SQUARE_SIZE - surf.get_width()) // 2
                    py = sy + (cfg.SQUARE_SIZE - surf.get_height()) // 2

                    self.surface.blit(surf, (px, py))

    # ------------------------------------------------------------------ #
    # Hand pieces
    # ------------------------------------------------------------------ #

    def _draw_hand_pieces(self, state):
        if not hasattr(state, "hand"):
            return

        self._hand_rects.clear()
        sw = self._hand_small_w
        sh = self._hand_small_h
        spacing_x = self._hand_spacing_x
        hand_h = getattr(cfg, "HAND_ROW_H", 36)

        for player in (0, 1):
            if player == 1:
                base_y = getattr(cfg, "HAND_TOP_Y", cfg.BOARD_Y - hand_h)
            else:
                base_y = getattr(cfg, "HAND_BOTTOM_Y", cfg.BOARD_Y + cfg.BOARD_PIXEL_H)

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

                if (
                    self._selected_hand is not None
                    and self._selected_hand == (BOARD_H, pt)
                    and player == state.current_player
                ):
                    hl = pygame.Surface((sw + 8, sh + 8), pygame.SRCALPHA)
                    hl.fill(_HAND_HIGHLIGHT)
                    self.surface.blit(hl, (draw_x - 2, draw_y - 2))

                small_surf = pygame.Surface((sw + 4, sh + 4), pygame.SRCALPHA)
                scx = (sw + 4) / 2
                scy_local = (sh + 4) / 2
                pointing_up = player == 0
                pts = _pentagon_points(scx, scy_local, sw, sh, pointing_up)

                if count > 0:
                    bg = _SENTE_BG if player == 0 else _GOTE_BG
                else:
                    bg = (120, 110, 100)
                pygame.draw.polygon(small_surf, bg, pts)
                pygame.draw.polygon(small_surf, _PIECE_OUTLINE, pts, 1)

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

                if count > 0:
                    try:
                        cnt_text = str(count)
                        cnt_surf, cnt_rect = self._hand_font.render(
                            cnt_text, fgcolor=cfg.COLOR_TEXT
                        )
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
        if not hasattr(state, "hand"):
            return None
        player = state.current_player
        for pt in _HAND_PIECES:
            rect = self._hand_rects.get((player, pt))
            if rect is not None and rect.collidepoint(x, y):
                if state.hand[player][pt] > 0:
                    return (BOARD_H, pt)
        return None

    # ------------------------------------------------------------------ #
    # PV visualization
    # ------------------------------------------------------------------ #

    def draw_pv(self, state, pv_moves):
        if not pv_moves:
            return

        col_map = {chr(ord("a") + i): i for i in range(BOARD_W)}
        row_map = {str(BOARD_H - i): i for i in range(BOARD_H)}

        current_player = state.current_player

        max_pv = min(len(pv_moves), 6)
        for i in range(max_pv):
            uci = pv_moves[i]
            if not uci:
                continue

            player_turn = (current_player + i) % 2
            alpha = max(80, 180 - i * 20)

            if len(uci) >= 3 and uci[1] == "*":
                tc = col_map.get(uci[2])
                tr = row_map.get(uci[3]) if len(uci) > 3 else None
                if tc is None or tr is None:
                    continue
                drop_map = {
                    "P": PAWN,
                    "S": SILVER,
                    "G": GOLD,
                    "L": LANCE,
                    "N": KNIGHT,
                    "B": BISHOP,
                    "R": ROOK,
                }
                drop_pt = drop_map.get(uci[0].upper(), PAWN)

                hand_rect = self._hand_rects.get((player_turn, drop_pt))
                if hand_rect is not None:
                    fx = hand_rect.centerx
                    fy = hand_rect.centery
                else:
                    fx = cfg.BOARD_X - 20
                    fy = cfg.BOARD_Y + cfg.BOARD_PIXEL_H // 2

                tx = cfg.BOARD_X + tc * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                ty = cfg.BOARD_Y + tr * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2

                color = (80, 220, 80, alpha) if i == 0 else (80, 160, 230, alpha)
                self._draw_arrow(fx, fy, tx, ty, color, i)
                self._draw_pv_number(tx, ty, i + 1, player_turn, alpha)

            elif len(uci) >= 4:
                fc = col_map.get(uci[0])
                fr = row_map.get(uci[1])
                tc = col_map.get(uci[2])
                tr = row_map.get(uci[3])
                if any(v is None for v in (fc, fr, tc, tr)):
                    continue

                fx = cfg.BOARD_X + fc * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                fy = cfg.BOARD_Y + fr * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                tx = cfg.BOARD_X + tc * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                ty = cfg.BOARD_Y + tr * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2

                color = (80, 220, 80, alpha) if i == 0 else (80, 160, 230, alpha)
                self._draw_arrow(fx, fy, tx, ty, color, i)

                mid_x = (fx + tx) // 2
                mid_y = (fy + ty) // 2
                self._draw_pv_number(mid_x, mid_y, i + 1, player_turn, alpha)

    def draw_pv_multi(self, state, pv_multi):
        """Draw multiple PV lines with distinct colors and numbered markers.

        Args:
            state: Current game state.
            pv_multi: dict mapping multipv index (1, 2, ...) to list of UCI move strings.
        """
        if not pv_multi:
            return

        col_map = {chr(ord("a") + i): i for i in range(BOARD_W)}
        row_map = {str(BOARD_H - i): i for i in range(BOARD_H)}
        current_player = state.current_player
        drop_map = {
            "P": PAWN, "S": SILVER, "G": GOLD,
            "L": LANCE, "N": KNIGHT, "B": BISHOP, "R": ROOK,
        }

        # Draw secondary PVs first (behind best), then best PV on top
        for mpv_idx in sorted(pv_multi.keys(), reverse=True):
            pv_moves = pv_multi[mpv_idx]
            if not pv_moves:
                continue

            # All green, different width/alpha
            if mpv_idx == 1:
                base_alpha = 220
                shaft_base = 6
            elif mpv_idx == 2:
                base_alpha = 150
                shaft_base = 4
            elif mpv_idx == 3:
                base_alpha = 110
                shaft_base = 3
            else:
                base_alpha = 80
                shaft_base = 2

            # Best PV: show full sequence. Others: first move only.
            max_moves = len(pv_moves) if mpv_idx == 1 else 1

            for i in range(min(max_moves, len(pv_moves))):
                uci = pv_moves[i]
                if not uci:
                    continue

                player_turn = (current_player + i) % 2
                alpha = max(40, base_alpha - i * 25)
                color = (80, 220, 80, alpha)

                if len(uci) >= 3 and uci[1] == "*":
                    tc = col_map.get(uci[2])
                    tr = row_map.get(uci[3]) if len(uci) > 3 else None
                    if tc is None or tr is None:
                        continue
                    drop_pt = drop_map.get(uci[0].upper(), PAWN)
                    hand_rect = self._hand_rects.get((player_turn, drop_pt))
                    if hand_rect is not None:
                        fx, fy = hand_rect.centerx, hand_rect.centery
                    else:
                        fx = cfg.BOARD_X - 20
                        fy = cfg.BOARD_Y + cfg.BOARD_PIXEL_H // 2
                    tx = cfg.BOARD_X + tc * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                    ty = cfg.BOARD_Y + tr * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                    self._draw_arrow(fx, fy, tx, ty, color, i)
                    # Step numbers only on best PV sequence (skip first move)
                    if mpv_idx == 1 and i > 0:
                        self._draw_pv_number(tx, ty, i + 1, player_turn, alpha)

                elif len(uci) >= 4:
                    fc = col_map.get(uci[0])
                    fr = row_map.get(uci[1])
                    tc = col_map.get(uci[2])
                    tr = row_map.get(uci[3])
                    if any(v is None for v in (fc, fr, tc, tr)):
                        continue
                    fx = cfg.BOARD_X + fc * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                    fy = cfg.BOARD_Y + fr * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                    tx = cfg.BOARD_X + tc * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                    ty = cfg.BOARD_Y + tr * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                    self._draw_arrow(fx, fy, tx, ty, color, i)
                    if mpv_idx == 1 and i > 0:
                        mid_x = (fx + tx) // 2
                        mid_y = (fy + ty) // 2
                        self._draw_pv_number(mid_x, mid_y, i + 1, player_turn, alpha)

    def _draw_arrow(self, fx, fy, tx, ty, color, idx):
        dx = tx - fx
        dy = ty - fy
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1:
            return

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
