"""Side panel and bottom panel rendering for the MiniChess GUI."""

import pygame

try:
    from gui.config import *
except ImportError:
    from config import *


def _make_font(size, bold=False):
    for name in ("Segoe UI", "Arial", None):
        font = pygame.font.SysFont(name, size, bold=bold)
        if font is not None:
            return font


def _draw_rounded_rect(surface, rect, color, radius=10):
    x, y, w, h = rect
    radius = min(radius, w // 2, h // 2)
    pygame.draw.rect(surface, color, (x + radius, y, w - 2 * radius, h))
    pygame.draw.rect(surface, color, (x, y + radius, w, h - 2 * radius))
    corners = [
        (x + radius, y + radius),
        (x + w - radius, y + radius),
        (x + radius, y + h - radius),
        (x + w - radius, y + h - radius),
    ]
    for cx, cy in corners:
        pygame.draw.circle(surface, color, (cx, cy), radius)


class Button:
    def __init__(self, x, y, width, height, text, font):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.font = font
        self.enabled = True
        self.active = False  # "on" state — different color

    def draw(self, surface, mouse_pos):
        if not self.enabled:
            bg = (45, 45, 50)
            fg = (90, 90, 90)
        elif self.active:
            bg = (40, 100, 60) if not self.rect.collidepoint(mouse_pos) else (50, 120, 70)
            fg = (200, 255, 200)
        elif self.rect.collidepoint(mouse_pos):
            bg = COLOR_BTN_HOVER
            fg = COLOR_BTN_TEXT
        else:
            bg = COLOR_BTN
            fg = COLOR_BTN_TEXT
        pygame.draw.rect(surface, bg, self.rect, border_radius=6)
        pygame.draw.rect(surface, COLOR_TEXT_DIM, self.rect, width=1, border_radius=6)
        label = self.font.render(self.text, True, fg)
        lx = self.rect.x + (self.rect.width - label.get_width()) // 2
        ly = self.rect.y + (self.rect.height - label.get_height()) // 2
        surface.blit(label, (lx, ly))

    def is_clicked(self, x, y):
        return self.enabled and self.rect.collidepoint(x, y)


class SidePanel:
    _PAD_TOP = 12
    _PAD_LEFT = 14
    _LINE_GAP = 6
    _SECTION_GAP = 10
    _SEPARATOR_INSET = 8
    _BTN_HEIGHT = 36
    _BTN_GAP = 10
    _BTN_BOTTOM_MARGIN = 14
    _DOT_RADIUS = 12
    _SCORE_PLOT_MAX_CP = 500
    _HISTORY_LINE_H = 20

    def __init__(self, surface):
        self.surface = surface

        self.font_title = _make_font(FONT_SIZE_STATUS, bold=True)
        self.font_normal = _make_font(FONT_SIZE_PANEL)
        self.font_btn = _make_font(FONT_SIZE_BTN, bold=True)
        self.font_bold = _make_font(FONT_SIZE_PANEL, bold=True)
        self.font_small = _make_font(FONT_SIZE_PANEL - 2)

        btn2_w = (PANEL_WIDTH - 2 * self._PAD_LEFT - self._BTN_GAP) // 2
        btn3_w = (PANEL_WIDTH - 2 * self._PAD_LEFT - 2 * self._BTN_GAP) // 3
        bx = PANEL_X + self._PAD_LEFT

        # Bottom row: New Game | Settings
        btn_y2 = PANEL_Y + PANEL_H - self._BTN_BOTTOM_MARGIN - self._BTN_HEIGHT
        self.btn_new_game = Button(bx, btn_y2, btn2_w, self._BTN_HEIGHT, "New Game", self.font_btn)
        self.btn_settings = Button(bx + btn2_w + self._BTN_GAP, btn_y2, btn2_w, self._BTN_HEIGHT, "Settings", self.font_btn)

        # Top row: Undo | Analyze | Stop
        btn_y1 = btn_y2 - self._BTN_HEIGHT - self._BTN_GAP
        self.btn_undo = Button(bx, btn_y1, btn3_w, self._BTN_HEIGHT, "Undo", self.font_btn)
        self.btn_analyze = Button(bx + btn3_w + self._BTN_GAP, btn_y1, btn3_w, self._BTN_HEIGHT, "Analyze", self.font_btn)
        self.btn_stop = Button(bx + 2 * (btn3_w + self._BTN_GAP), btn_y1, btn3_w, self._BTN_HEIGHT, "Stop", self.font_btn)

        self._scroll_offset = 0
        self._frame = 0

    # ==================================================================
    # Right panel (status / controls)
    # ==================================================================

    def draw(
        self,
        state,
        ai_thinking=False,
        game_result=None,
        ai_depth=None,
        mode="human_vs_human",
        time_limit=DEFAULT_TIMEOUT,
        search_info=None,
        paused=False,
        analyze_enabled=False,
        gaming=False,
    ):
        self._frame += 1
        mouse_pos = pygame.mouse.get_pos()
        if search_info is None:
            search_info = {}

        _draw_rounded_rect(
            self.surface,
            (PANEL_X, PANEL_Y, PANEL_WIDTH, PANEL_H),
            COLOR_PANEL_BG,
            radius=10,
        )

        cx = PANEL_X + self._PAD_LEFT
        cy = PANEL_Y + self._PAD_TOP

        # Title: mode + gaming state indicator
        mode_labels = {
            "human_vs_human": "Human vs Human",
            "human_vs_ai": "Human vs AI",
            "ai_vs_ai": "AI vs AI",
        }
        if gaming:
            title_label = mode_labels.get(mode, mode)
            title_color = (100, 220, 100)  # green = game in progress
        elif analyze_enabled:
            title_label = "Analyze"
            title_color = (100, 200, 220)  # cyan
        elif game_result is not None and game_result != "stopped":
            title_label = mode_labels.get(mode, mode)
            title_color = COLOR_TEXT_DIM  # dimmed = game over
        else:
            title_label = "Free Play"
            title_color = COLOR_TEXT
        surf = self.font_title.render(title_label, True, title_color)
        self.surface.blit(surf, (cx, cy))
        cy += surf.get_height() + self._SECTION_GAP

        if game_result is not None:
            text, color = self._result_info(game_result)
            surf = self.font_bold.render(text, True, color)
            self.surface.blit(surf, (cx, cy))
            cy += surf.get_height() + self._LINE_GAP
        else:
            dot_color = (
                COLOR_WHITE_PIECE if state.current_player == 0 else COLOR_BLACK_PIECE
            )
            dot_cx = cx + self._DOT_RADIUS
            dot_cy = cy + self._DOT_RADIUS
            pygame.draw.circle(
                self.surface, dot_color, (dot_cx, dot_cy), self._DOT_RADIUS
            )
            pygame.draw.circle(
                self.surface,
                COLOR_TEXT_DIM,
                (dot_cx, dot_cy),
                self._DOT_RADIUS,
                width=1,
            )
            who = "White to move" if state.current_player == 0 else "Black to move"
            surf = self.font_normal.render(who, True, COLOR_TEXT)
            self.surface.blit(surf, (cx + self._DOT_RADIUS * 2 + 8, cy + 2))
            cy += max(surf.get_height(), self._DOT_RADIUS * 2) + self._LINE_GAP

        surf = self.font_normal.render(
            f"Step {state.step} / {MAX_STEP}", True, COLOR_TEXT_DIM
        )
        self.surface.blit(surf, (cx, cy))
        cy += surf.get_height() + self._SECTION_GAP

        status_text = None
        status_color = COLOR_TEXT
        if analyze_enabled and paused:
            status_text = "Paused"
            status_color = (200, 200, 100)
        elif analyze_enabled and search_info.get("depth") is not None:
            n_dots = (self._frame // (FPS // 3)) % 3 + 1
            status_text = "Analyzing" + "." * n_dots
            status_color = (100, 200, 220)
        elif analyze_enabled:
            n_dots = (self._frame // (FPS // 3)) % 3 + 1
            status_text = "Loading" + "." * n_dots
            status_color = (180, 180, 100)
        elif paused:
            status_text = "Paused"
            status_color = (200, 200, 100)
        elif ai_thinking:
            n_dots = (self._frame // (FPS // 3)) % 3 + 1
            status_text = "AI thinking" + "." * n_dots
        if status_text:
            surf = self.font_normal.render(status_text, True, status_color)
            self.surface.blit(surf, (cx, cy))
            cy += surf.get_height() + self._LINE_GAP

        cy = self._draw_search_stats(cx, cy, search_info, ai_depth, time_limit)

        if search_info.get("pv"):
            cy = self._draw_pv(cx, cy, search_info["pv"])

        # Undo: disabled during gaming
        self.btn_undo.enabled = not gaming
        self.btn_undo.draw(self.surface, mouse_pos)

        # Analyze: disabled during gaming, green when active
        self.btn_analyze.enabled = not gaming
        self.btn_analyze.active = analyze_enabled
        self.btn_analyze.draw(self.surface, mouse_pos)

        # Stop: only enabled during gaming
        self.btn_stop.enabled = gaming
        self.btn_stop.draw(self.surface, mouse_pos)

        top_btn = self.btn_undo
        sep_y = top_btn.rect.y - self._SECTION_GAP - 2
        x1 = PANEL_X + self._SEPARATOR_INSET
        x2 = PANEL_X + PANEL_WIDTH - self._SEPARATOR_INSET
        pygame.draw.line(self.surface, COLOR_TEXT_DIM, (x1, sep_y), (x2, sep_y), 1)

        self.btn_new_game.draw(self.surface, mouse_pos)
        self.btn_settings.draw(self.surface, mouse_pos)

    # ==================================================================
    # Bottom panel (eval bar | score plot | move table)
    # ==================================================================

    def draw_bottom(self, score_cp, score_history, move_history):
        bx = BOTTOM_X
        by = BOTTOM_Y
        bw = WINDOW_W - 2 * BOTTOM_X
        bh = BOTTOM_H
        pad = 8

        _draw_rounded_rect(self.surface, (bx, by, bw, bh), COLOR_PANEL_BG, radius=8)

        inner_x = bx + pad
        inner_y = by + pad
        inner_h = bh - 2 * pad

        eval_w = BOTTOM_EVAL_W
        self._draw_eval_bar(inner_x, inner_y, eval_w, inner_h, score_cp)

        plot_x = inner_x + eval_w + BOTTOM_GAP
        remaining_w = bw - 2 * pad - eval_w - BOTTOM_GAP
        plot_w = remaining_w // 2
        self._draw_score_plot(plot_x, inner_y, score_history, plot_w, inner_h)

        table_x = plot_x + plot_w + BOTTOM_GAP
        table_w = bw - (table_x - bx) - pad
        self._draw_move_table(table_x, inner_y, table_w, inner_h, move_history)

    def _draw_eval_bar(self, x, y, w, h, score_cp):
        """Vertical eval bar. White on bottom, black on top.
        Positive score = white better = white section grows upward."""
        max_cp = self._SCORE_PLOT_MAX_CP

        if score_cp is not None:
            clamped = max(-max_cp, min(max_cp, score_cp))
            white_pct = 50 + clamped * 50 / max_cp
        else:
            white_pct = 50

        white_h = int(h * white_pct / 100)
        black_h = h - white_h

        # Black on top
        if black_h > 0:
            pygame.draw.rect(self.surface, (50, 50, 50), (x, y, w, black_h))
        # White on bottom
        if white_h > 0:
            pygame.draw.rect(self.surface, (230, 230, 230), (x, y + black_h, w, white_h))

        pygame.draw.rect(self.surface, COLOR_TEXT_DIM, (x, y, w, h), 1)

        if score_cp is not None:
            score_pawns = score_cp / 100.0
            sign = "+" if score_cp >= 0 else ""
            text = f"{sign}{score_pawns:.1f}"
        else:
            text = "0.0"
        surf = self.font_small.render(text, True, (180, 180, 0))
        tx = x + (w - surf.get_width()) // 2
        ty = y + (h - surf.get_height()) // 2
        bg_rect = pygame.Rect(tx - 1, ty, surf.get_width() + 2, surf.get_height())
        pygame.draw.rect(self.surface, (40, 40, 44), bg_rect)
        self.surface.blit(surf, (tx, ty))

    def _draw_score_plot(self, cx, cy, score_history, plot_w, plot_h):
        max_cp = self._SCORE_PLOT_MAX_CP

        pygame.draw.rect(self.surface, (30, 30, 34), (cx, cy, plot_w, plot_h))

        mid_y = cy + plot_h // 2
        pygame.draw.line(
            self.surface, (80, 80, 80), (cx, mid_y), (cx + plot_w, mid_y), 1
        )

        for frac in (0.25, 0.75):
            ref_y = cy + int(plot_h * frac)
            pygame.draw.line(
                self.surface, (45, 45, 50), (cx, ref_y), (cx + plot_w, ref_y), 1
            )

        points = [
            (i, player, score)
            for i, (player, score) in enumerate(score_history)
            if score is not None
        ]

        if not points:
            pygame.draw.rect(self.surface, COLOR_TEXT_DIM, (cx, cy, plot_w, plot_h), 1)
            return

        n_total = len(score_history)

        def to_screen(idx, score):
            if n_total <= 1:
                sx = cx + plot_w // 2
            else:
                sx = cx + int(idx / (n_total - 1) * (plot_w - 1))
            clamped = max(-max_cp, min(max_cp, score))
            sy = mid_y - int(clamped / max_cp * (plot_h // 2 - 2))
            return (sx, sy)

        if len(points) >= 2:
            screen_pts = [to_screen(idx, score) for idx, _, score in points]
            pygame.draw.lines(self.surface, (100, 100, 110), False, screen_pts, 2)

        for idx, player, score in points:
            sx, sy = to_screen(idx, score)
            if player == 0:
                pygame.draw.circle(self.surface, (230, 230, 230), (sx, sy), 3)
                pygame.draw.circle(self.surface, (80, 80, 80), (sx, sy), 3, 1)
            else:
                pygame.draw.circle(self.surface, (40, 40, 40), (sx, sy), 3)
                pygame.draw.circle(self.surface, (160, 160, 160), (sx, sy), 3, 1)

        pygame.draw.rect(self.surface, COLOR_TEXT_DIM, (cx, cy, plot_w, plot_h), 1)

        label_top = self.font_small.render(f"+{max_cp/100:.0f}", True, (90, 90, 90))
        label_bot = self.font_small.render(f"-{max_cp/100:.0f}", True, (90, 90, 90))
        self.surface.blit(label_top, (cx + 2, cy + 1))
        self.surface.blit(label_bot, (cx + 2, cy + plot_h - label_bot.get_height() - 1))

    def _draw_move_table(self, x, y, w, h, move_history):
        pygame.draw.rect(self.surface, (30, 30, 34), (x, y, w, h))
        pygame.draw.rect(self.surface, COLOR_TEXT_DIM, (x, y, w, h), 1)

        header = self.font_small.render("Moves", True, COLOR_TEXT_DIM)
        self.surface.blit(header, (x + 4, y + 2))
        header_h = header.get_height() + 4
        pygame.draw.line(
            self.surface, (60, 60, 64), (x, y + header_h), (x + w, y + header_h), 1
        )

        line_h = self._HISTORY_LINE_H
        avail_h = h - header_h - 2
        max_lines = max(1, avail_h // line_h)

        total = len(move_history)
        if total <= max_lines:
            self._scroll_offset = 0
        else:
            max_scroll = total - max_lines
            self._scroll_offset = max(0, min(self._scroll_offset, max_scroll))

        start = self._scroll_offset
        end = start + max_lines
        visible = move_history[start:end]

        ly = y + header_h + 2
        color_even = COLOR_TEXT
        color_odd = tuple(min(c + 15, 255) for c in COLOR_TEXT)

        for idx, line in enumerate(visible):
            color = color_even if idx % 2 == 0 else color_odd
            surf = self.font_small.render(line, True, color)
            self.surface.blit(surf, (x + 4, ly), area=(0, 0, w - 8, surf.get_height()))
            ly += line_h

        if total > end:
            dots = self.font_small.render("...", True, COLOR_TEXT_DIM)
            self.surface.blit(dots, (x + 4, ly))

    # ==================================================================
    # Interaction
    # ==================================================================

    def handle_click(self, x, y, **_kw):
        if self.btn_new_game.is_clicked(x, y):
            return "new_game"
        if self.btn_settings.is_clicked(x, y):
            return "settings"
        if self.btn_undo.is_clicked(x, y):
            return "undo"
        if self.btn_analyze.is_clicked(x, y):
            return "analyze"
        if self.btn_stop.is_clicked(x, y):
            return "stop"
        return None

    def set_scroll(self, direction):
        self._scroll_offset = max(0, self._scroll_offset + direction)

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _result_info(game_result):
        if game_result == "white_wins":
            return "White wins!", (100, 220, 100)
        if game_result == "black_wins":
            return "Black wins!", (220, 80, 80)
        if game_result == "stopped":
            return "Game stopped", (180, 180, 180)
        return "Draw!", (200, 200, 100)

    def _draw_search_stats(self, cx, cy, search_info, ai_depth, time_limit):
        depth = search_info.get("depth")
        seldepth = search_info.get("seldepth")
        nodes = search_info.get("nodes")
        nps = search_info.get("nps")
        elapsed = search_info.get("time")

        if depth is not None:
            dt = f"Depth: {depth}/{seldepth}" if seldepth else f"Depth: {depth}"
            surf = self.font_normal.render(dt, True, COLOR_TEXT_DIM)
            self.surface.blit(surf, (cx, cy))
            cy += surf.get_height() + self._LINE_GAP
        elif ai_depth is not None:
            surf = self.font_normal.render(f"Depth: {ai_depth}", True, COLOR_TEXT_DIM)
            self.surface.blit(surf, (cx, cy))
            cy += surf.get_height() + self._LINE_GAP

        parts = []
        if nodes is not None:
            parts.append(f"Nodes: {self._fmt(nodes)}")
        if nps is not None:
            parts.append(f"NPS: {self._fmt(nps)}")
        if parts:
            surf = self.font_normal.render("  ".join(parts), True, COLOR_TEXT_DIM)
            self.surface.blit(surf, (cx, cy))
            cy += surf.get_height() + self._LINE_GAP

        if elapsed is not None:
            tt = f"Time: {elapsed / 1000.0:.2f}s"
        else:
            tt = f"Time: {time_limit}s"
        surf = self.font_normal.render(tt, True, COLOR_TEXT_DIM)
        self.surface.blit(surf, (cx, cy))
        cy += surf.get_height() + self._SECTION_GAP
        return cy

    def _draw_pv(self, cx, cy, pv_moves):
        max_text_w = PANEL_WIDTH - 2 * self._PAD_LEFT
        pv_str = "PV: " + " ".join(pv_moves)
        surf = self.font_normal.render(pv_str, True, COLOR_TEXT_DIM)
        if surf.get_width() > max_text_w:
            for n in range(len(pv_moves), 0, -1):
                pv_str = "PV: " + " ".join(pv_moves[:n]) + " ..."
                surf = self.font_normal.render(pv_str, True, COLOR_TEXT_DIM)
                if surf.get_width() <= max_text_w:
                    break
        self.surface.blit(surf, (cx, cy))
        cy += surf.get_height() + self._LINE_GAP
        return cy

    @staticmethod
    def _fmt(value):
        if value >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        if value >= 1_000:
            return f"{value / 1_000:.1f}K"
        return str(value)
