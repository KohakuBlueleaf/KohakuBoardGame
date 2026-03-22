"""Board renderer for UBGI games."""

import pygame
import pygame.freetype

try:
    import gui.config as cfg
except ImportError:
    import config as cfg


class BoardRenderer:
    """Renders game boards on a Pygame surface."""

    # Font candidates in preference order
    _FONT_CANDIDATES = (
        "Segoe UI Symbol",
        "Apple Symbols",
        "DejaVu Sans",
        "Arial Unicode MS",
        "Helvetica",
        None,
    )

    def __init__(self, surface, game_renderer=None):
        self.surface = surface
        self.game_renderer = game_renderer

        self.label_font = None
        for name in self._FONT_CANDIDATES:
            try:
                font = pygame.freetype.SysFont(name, cfg.FONT_SIZE_LABEL)
                if name is not None and "freesansbold" in getattr(font, "path", ""):
                    continue
                self.label_font = font
                break
            except Exception:
                continue
        if self.label_font is None:
            self.label_font = pygame.freetype.Font(None, cfg.FONT_SIZE_LABEL)

        self._num_font = pygame.font.SysFont("Arial", 14, bold=True)

    # -----------------------------------------------------------------
    # Piece lookup (handles both chess and placement game board layouts)
    # -----------------------------------------------------------------

    def _get_piece(self, state, player, row, col):
        """Return the piece value for *player* at (row, col), or None."""
        try:
            piece = state.board[player][row][col]
            return piece if piece else None
        except (TypeError, IndexError):
            return None

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def draw(
        self, state, selected=None, legal_moves=None, last_move=None,
        pv_arrows=None, pv_multi=None,
    ):
        self._draw_squares()
        self._draw_last_move(last_move)
        self._draw_selected(selected)
        self._draw_legal_moves(state, selected, legal_moves)
        if self.game_renderer:
            self.game_renderer.draw_pieces(state)
        if pv_multi and len(pv_multi) > 1:
            # Multi-PV rendering
            if self.game_renderer and hasattr(self.game_renderer, "draw_pv_multi"):
                self.game_renderer.draw_pv_multi(state, pv_multi)
            else:
                self._draw_pv_multi(pv_multi)
        elif pv_arrows:
            if self.game_renderer and hasattr(self.game_renderer, "draw_pv"):
                self.game_renderer.draw_pv(state, pv_arrows)
            else:
                self._draw_pv_arrows(pv_arrows)
        self._draw_labels()

    def screen_to_board(self, x, y):
        """Convert screen (x, y) to board (row, col).

        Returns (row, col) or None if the click is outside the board area.
        """
        if (
            x < cfg.BOARD_X
            or x >= cfg.BOARD_X + cfg.BOARD_PIXEL_W
            or y < cfg.BOARD_Y
            or y >= cfg.BOARD_Y + cfg.BOARD_PIXEL_H
        ):
            return None

        col = (x - cfg.BOARD_X) // cfg.SQUARE_SIZE
        row = (y - cfg.BOARD_Y) // cfg.SQUARE_SIZE

        # Clamp to valid range (defensive)
        col = max(0, min(col, cfg.BOARD_W - 1))
        row = max(0, min(row, cfg.BOARD_H - 1))

        return (row, col)

    def board_to_screen(self, row, col):
        """Convert board (row, col) to the top-left pixel (x, y) of that square."""
        x = cfg.BOARD_X + col * cfg.SQUARE_SIZE
        y = cfg.BOARD_Y + row * cfg.SQUARE_SIZE
        return (x, y)

    # -----------------------------------------------------------------
    # Internal drawing helpers
    # -----------------------------------------------------------------

    def _draw_squares(self):
        """Draw the alternating light/dark board squares."""
        for row in range(cfg.BOARD_H):
            for col in range(cfg.BOARD_W):
                x, y = self.board_to_screen(row, col)
                color = (
                    cfg.COLOR_LIGHT_SQ if (row + col) % 2 == 0 else cfg.COLOR_DARK_SQ
                )
                pygame.draw.rect(
                    self.surface, color, (x, y, cfg.SQUARE_SIZE, cfg.SQUARE_SIZE)
                )

    def _draw_overlay(self, row, col, color_with_alpha):
        """Draw a semi-transparent overlay on a single square."""
        overlay = pygame.Surface((cfg.SQUARE_SIZE, cfg.SQUARE_SIZE), pygame.SRCALPHA)
        overlay.fill(color_with_alpha)
        x, y = self.board_to_screen(row, col)
        self.surface.blit(overlay, (x, y))

    def _draw_last_move(self, last_move):
        """Highlight the from/to squares of the last move with a blue tint."""
        if last_move is None:
            return
        (fr, fc), (tr, tc) = last_move
        # Skip out-of-bounds squares (drop source or promotion encoding)
        if 0 <= fr < cfg.BOARD_H and 0 <= fc < cfg.BOARD_W:
            self._draw_overlay(fr, fc, cfg.COLOR_LAST_MOVE)
        actual_tr = tr - cfg.BOARD_H if tr >= cfg.BOARD_H else tr
        if 0 <= actual_tr < cfg.BOARD_H and 0 <= tc < cfg.BOARD_W:
            self._draw_overlay(actual_tr, tc, cfg.COLOR_LAST_MOVE)

    def _draw_selected(self, selected):
        """Highlight the currently selected piece square with a yellow tint."""
        if selected is None:
            return
        row, col = selected
        # Skip if out of bounds (e.g. hand piece selection in MiniShogi)
        if 0 <= row < cfg.BOARD_H and 0 <= col < cfg.BOARD_W:
            self._draw_overlay(row, col, cfg.COLOR_HIGHLIGHT)

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
        drawn = set()  # avoid drawing duplicate indicators for promotion variants

        for move in legal_moves:
            (fr, fc), (tr, tc) = move
            if (fr, fc) != src:
                continue

            # Decode actual destination (promotion moves encode to_r += BOARD_H)
            actual_tr = tr - cfg.BOARD_H if tr >= cfg.BOARD_H else tr
            if actual_tr < 0 or actual_tr >= cfg.BOARD_H or tc < 0 or tc >= cfg.BOARD_W:
                continue
            if (actual_tr, tc) in drawn:
                continue
            drawn.add((actual_tr, tc))

            cx, cy = self.board_to_screen(actual_tr, tc)
            cx += cfg.SQUARE_SIZE // 2
            cy += cfg.SQUARE_SIZE // 2

            # Check whether the destination has an opponent piece
            opponent_piece = self._get_piece(state, opponent, actual_tr, tc)
            has_opponent = opponent_piece is not None

            # Use a per-pixel alpha surface for the indicator
            overlay = pygame.Surface(
                (cfg.SQUARE_SIZE, cfg.SQUARE_SIZE), pygame.SRCALPHA
            )
            local_cx = cfg.SQUARE_SIZE // 2
            local_cy = cfg.SQUARE_SIZE // 2

            if has_opponent:
                pygame.draw.circle(
                    overlay,
                    cfg.COLOR_LEGAL,
                    (local_cx, local_cy),
                    cfg.SQUARE_SIZE // 2 - 4,
                    ring_width,
                )
            else:
                pygame.draw.circle(
                    overlay, cfg.COLOR_LEGAL, (local_cx, local_cy), radius
                )

            sq_x, sq_y = self.board_to_screen(actual_tr, tc)
            self.surface.blit(overlay, (sq_x, sq_y))

    def _draw_pv_arrows(self, pv_moves):
        """Draw numbered arrows on the board for the principal variation."""
        import math

        if not pv_moves:
            return

        col_map = {chr(ord("a") + i): i for i in range(cfg.BOARD_W)}
        row_map = {str(cfg.BOARD_H - i): i for i in range(cfg.BOARD_H)}

        overlay = pygame.Surface(
            (cfg.WINDOW_W, cfg.WINDOW_H),
            pygame.SRCALPHA,
        )

        num_font = self._num_font

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
            fx += cfg.SQUARE_SIZE // 2
            fy += cfg.SQUARE_SIZE // 2
            tx += cfg.SQUARE_SIZE // 2
            ty += cfg.SQUARE_SIZE // 2

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
                overlay,
                (0, 0, 0, min(200, alpha)),
                (int(num_x), int(num_y)),
                nr,
            )
            overlay.blit(
                num_surf,
                (num_x - num_surf.get_width() / 2, num_y - num_surf.get_height() / 2),
            )

        self.surface.blit(overlay, (0, 0))

    def _draw_pv_multi(self, pv_multi):
        """Draw numbered arrows for multiple PV lines with distinct colors.

        Args:
            pv_multi: dict mapping multipv index (1, 2, ...) to list of UCI move strings.
        """
        import math

        if not pv_multi:
            return

        col_map = {chr(ord("a") + i): i for i in range(cfg.BOARD_W)}
        row_map = {str(cfg.BOARD_H - i): i for i in range(cfg.BOARD_H)}

        overlay = pygame.Surface(
            (cfg.WINDOW_W, cfg.WINDOW_H),
            pygame.SRCALPHA,
        )

        num_font = self._num_font

        # PV style per multipv index:
        # PV 1: green, wide shaft
        # PV 2: blue, medium shaft
        # PV 3+: lighter blue, thin shaft
        for mpv_idx in sorted(pv_multi.keys()):
            pv_moves = pv_multi[mpv_idx]
            if not pv_moves:
                continue

            if mpv_idx == 1:
                base_color = (80, 220, 80)
                base_alpha = 220
                shaft_w = 6
            elif mpv_idx == 2:
                base_color = (80, 160, 230)
                base_alpha = 178  # ~70%
                shaft_w = 4
            else:
                base_color = (120, 180, 240)
                base_alpha = 128  # ~50%
                shaft_w = 3

            for i, uci in enumerate(pv_moves):
                if len(uci) < 4:
                    continue

                fc = col_map.get(uci[0])
                fr = row_map.get(uci[1])
                tc = col_map.get(uci[2])
                tr = row_map.get(uci[3])
                if any(v is None for v in (fc, fr, tc, tr)):
                    continue

                alpha = max(60, base_alpha - i * 25)
                color = (base_color[0], base_color[1], base_color[2], alpha)

                fx, fy = self.board_to_screen(fr, fc)
                tx, ty = self.board_to_screen(tr, tc)
                fx += cfg.SQUARE_SIZE // 2
                fy += cfg.SQUARE_SIZE // 2
                tx += cfg.SQUARE_SIZE // 2
                ty += cfg.SQUARE_SIZE // 2

                dx = tx - fx
                dy = ty - fy
                length = math.sqrt(dx * dx + dy * dy)
                if length < 1:
                    continue
                ux, uy = dx / length, dy / length

                cur_shaft_w = max(2, shaft_w - i)
                head_len = min(20, length * 0.3)
                head_w = head_len * 0.65

                sx2 = tx - ux * head_len
                sy2 = ty - uy * head_len
                pygame.draw.line(overlay, color, (fx, fy), (sx2, sy2), cur_shaft_w)

                px, py = -uy, ux
                points = [
                    (tx, ty),
                    (sx2 + px * head_w, sy2 + py * head_w),
                    (sx2 - px * head_w, sy2 - py * head_w),
                ]
                pygame.draw.polygon(overlay, color, points)

                # Draw numbered circle on the first move of each PV line
                if i == 0:
                    mid_x = (fx + tx) / 2
                    mid_y = (fy + ty) / 2
                    off = 10
                    num_x = mid_x + px * off
                    num_y = mid_y + py * off
                    label = str(mpv_idx)
                    num_surf = num_font.render(label, True, (255, 255, 255))
                    nr = max(num_surf.get_width(), num_surf.get_height()) // 2 + 3
                    pygame.draw.circle(
                        overlay,
                        (0, 0, 0, min(200, alpha)),
                        (int(num_x), int(num_y)),
                        nr,
                    )
                    overlay.blit(
                        num_surf,
                        (num_x - num_surf.get_width() / 2,
                         num_y - num_surf.get_height() / 2),
                    )

        self.surface.blit(overlay, (0, 0))

    def _draw_labels(self):
        """Draw row labels (6-1) on the left and column labels (A-E) below."""
        for row in range(cfg.BOARD_H):
            label = cfg.ROW_LABELS[row]
            sx, sy = self.board_to_screen(row, 0)
            # Position to the left of the first column, vertically centred
            lx = cfg.BOARD_X - cfg.LABEL_MARGIN
            ly = sy + cfg.SQUARE_SIZE // 2

            surf, rect = self.label_font.render(label, fgcolor=cfg.COLOR_TEXT_DIM)
            self.surface.blit(
                surf, (lx + (cfg.LABEL_MARGIN - rect.width) // 2, ly - rect.height // 2)
            )

        for col in range(cfg.BOARD_W):
            label = cfg.COL_LABELS[col]
            sx, sy = self.board_to_screen(cfg.BOARD_H - 1, col)
            # Position below the last row, horizontally centred
            lx = sx + cfg.SQUARE_SIZE // 2
            ly = cfg.BOARD_Y + cfg.BOARD_PIXEL_H

            surf, rect = self.label_font.render(label, fgcolor=cfg.COLOR_TEXT_DIM)
            self.surface.blit(
                surf, (lx - rect.width // 2, ly + (cfg.LABEL_MARGIN - rect.height) // 2)
            )
