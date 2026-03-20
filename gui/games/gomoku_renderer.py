"""Gomoku board renderer — stones as filled/open circles."""

import pygame

try:
    import gui.config as cfg
except ImportError:
    import config as cfg


class GomokuRenderer:
    """Renders Gomoku board with filled circles for stones."""

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

                if val == 1:
                    pygame.draw.circle(self.surface, (20, 20, 20), (sx, sy), radius)
                    pygame.draw.circle(self.surface, (60, 60, 60), (sx, sy), radius, 2)
                elif val == 2:
                    pygame.draw.circle(self.surface, (240, 240, 240), (sx, sy), radius)
                    pygame.draw.circle(
                        self.surface, (100, 100, 100), (sx, sy), radius, 2
                    )

    def draw_pv(self, state, pv_moves):
        """Draw semi-transparent ghost stones for the principal variation."""
        if not pv_moves:
            return

        col_map = {chr(ord("a") + i): i for i in range(cfg.BOARD_W)}
        row_map = {str(cfg.BOARD_H - i): i for i in range(cfg.BOARD_H)}

        radius = max(10, cfg.SQUARE_SIZE // 2 - 6)
        current_player = state.current_player

        max_pv = min(len(pv_moves), 8)
        for i in range(max_pv):
            uci = pv_moves[i]

            # Parse placement move (2-char like "e5") or board move destination
            if len(uci) == 2:
                c_idx = col_map.get(uci[0])
                r_idx = row_map.get(uci[1])
            elif len(uci) >= 4:
                c_idx = col_map.get(uci[2])
                r_idx = row_map.get(uci[3])
            else:
                continue

            if c_idx is None or r_idx is None:
                continue

            sx = cfg.BOARD_X + c_idx * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2
            sy = cfg.BOARD_Y + r_idx * cfg.SQUARE_SIZE + cfg.SQUARE_SIZE // 2

            # Alternate: current player places first, then opponent, etc.
            player_turn = (current_player + i) % 2
            alpha = max(80, 180 - i * 15)

            # Semi-transparent ghost stone
            ghost = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
            cx, cy = radius + 2, radius + 2

            if player_turn == 0:  # Black stone
                pygame.draw.circle(ghost, (20, 20, 20, alpha), (cx, cy), radius)
                pygame.draw.circle(ghost, (60, 60, 60, alpha), (cx, cy), radius, 2)
            else:  # White stone
                pygame.draw.circle(ghost, (240, 240, 240, alpha), (cx, cy), radius)
                pygame.draw.circle(ghost, (100, 100, 100, alpha), (cx, cy), radius, 2)

            self.surface.blit(ghost, (sx - cx, sy - cy))

            # Move number label (contrasting color)
            fg = (255, 255, 255) if player_turn == 0 else (0, 0, 0)
            num_surf = self._num_font.render(str(i + 1), True, fg)
            self.surface.blit(
                num_surf,
                (sx - num_surf.get_width() // 2, sy - num_surf.get_height() // 2),
            )
