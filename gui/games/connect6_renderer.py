"""Connect6 board renderer — stones as filled/open circles."""

import pygame

try:
    import gui.config as cfg
except ImportError:
    import config as cfg


def _parse_c6_uci(uci):
    """Parse a Connect6 UCI move string into list of (row, col) placements.

    Formats:
    - "h8" — single placement (degenerate)
    - "g8h7" — two placements (letter+digits+letter+digits)
    """
    col_map = {chr(ord("a") + i): i for i in range(cfg.BOARD_W)}
    row_map = {str(cfg.BOARD_H - i): i for i in range(cfg.BOARD_H)}

    squares = []
    pos = 0
    while pos < len(uci):
        if not uci[pos].isalpha():
            break
        c_idx = col_map.get(uci[pos])
        pos += 1
        num_start = pos
        while pos < len(uci) and uci[pos].isdigit():
            pos += 1
        if num_start == pos or c_idx is None:
            break
        r_idx = row_map.get(uci[num_start:pos])
        if r_idx is None:
            break
        squares.append((r_idx, c_idx))
    return squares


class Connect6Renderer:
    """Renders Connect6 board with filled circles for stones."""

    def __init__(self, surface):
        self.surface = surface
        self._num_font = pygame.font.SysFont("Arial", 14, bold=True)

    def draw_pieces(self, state):
        radius = max(10, cfg.SQUARE_SIZE // 2 - 6)
        for row in range(cfg.BOARD_H):
            for col in range(cfg.BOARD_W):
                try:
                    val = state.board[row][col]
                except (TypeError, IndexError):
                    continue
                if val == 0:
                    continue

                sx = cfg.BOARD_X + col * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
                sy = cfg.BOARD_Y + row * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2

                if val == 1:  # black
                    pygame.draw.circle(self.surface, (20, 20, 20), (sx, sy), radius)
                    pygame.draw.circle(self.surface, (60, 60, 60), (sx, sy), radius, 2)
                elif val == 2:  # white
                    pygame.draw.circle(self.surface, (240, 240, 240), (sx, sy), radius)
                    pygame.draw.circle(
                        self.surface, (100, 100, 100), (sx, sy), radius, 2
                    )

    def _draw_ghost_stone(self, r, c, player_turn, alpha, label=None, border_color=None):
        """Draw a semi-transparent ghost stone at (r, c)."""
        radius = max(10, cfg.SQUARE_SIZE // 2 - 6)
        sx = cfg.BOARD_X + c * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
        sy = cfg.BOARD_Y + r * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2

        ghost = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
        cx, cy = radius + 2, radius + 2

        if player_turn == 1:  # black
            pygame.draw.circle(ghost, (20, 20, 20, alpha), (cx, cy), radius)
        else:  # white
            pygame.draw.circle(ghost, (240, 240, 240, alpha), (cx, cy), radius)

        if border_color:
            pygame.draw.circle(
                ghost,
                (border_color[0], border_color[1], border_color[2], alpha),
                (cx, cy), radius, 3,
            )
        else:
            border = (60, 60, 60, alpha) if player_turn == 1 else (100, 100, 100, alpha)
            pygame.draw.circle(ghost, border, (cx, cy), radius, 2)

        self.surface.blit(ghost, (sx - cx, sy - cy))

        if label:
            fg = (255, 255, 255) if player_turn == 1 else (0, 0, 0)
            num_surf = self._num_font.render(str(label), True, fg)
            self.surface.blit(
                num_surf,
                (sx - num_surf.get_width() // 2, sy - num_surf.get_height() // 2),
            )

    def draw_pv(self, state, pv_moves):
        """Draw ghost stones for the principal variation.
        Each PV move is a single stone placement. Player switches every 2 stones."""
        if not pv_moves:
            return

        player_turn = state.current_player
        stones_left = getattr(state, "stones_left", 2)

        for i, uci in enumerate(pv_moves[:16]):
            squares = _parse_c6_uci(uci)
            alpha = max(80, 180 - i * 10)

            for r, c in squares:
                self._draw_ghost_stone(r, c, player_turn, alpha, label=i + 1)

            # Advance turn counter
            stones_left -= 1
            if stones_left == 0:
                player_turn = 1 - player_turn
                stones_left = 2

    def draw_pv_multi(self, state, pv_multi):
        """Draw ghost stones for multiple PV lines."""
        if not pv_multi:
            return

        current_player = state.current_player

        pv_border_colors = {
            1: (80, 220, 80),
            2: (80, 160, 230),
        }
        default_border = (120, 180, 240)

        for mpv_idx in sorted(pv_multi.keys()):
            pv_moves = pv_multi[mpv_idx]
            if not pv_moves:
                continue

            base_alpha = max(110, 200 - (mpv_idx - 1) * 50)
            border_color = pv_border_colors.get(mpv_idx, default_border)

            player_turn = current_player
            stones_left = getattr(state, "stones_left", 2)

            for i, uci in enumerate(pv_moves):
                squares = _parse_c6_uci(uci)
                alpha = max(60, base_alpha - i * 10)

                for r, c in squares:
                    label = str(mpv_idx) if i == 0 else str(i + 1)
                    self._draw_ghost_stone(r, c, player_turn, alpha, label=label, border_color=border_color)

                stones_left -= 1
                if stones_left == 0:
                    player_turn = 1 - player_turn
                    stones_left = 2
