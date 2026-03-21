"""UBGI GUI -- entry point and game loop."""

import sys
import time
import argparse

import pygame

try:
    from gui.board_renderer import BoardRenderer
    from gui.ui_panels import SidePanel
    from gui.ubgi_client import UBGIEngine, discover_engines
    import gui.config as _cfg
except ImportError:
    from board_renderer import BoardRenderer
    from ui_panels import SidePanel
    from ubgi_client import UBGIEngine, discover_engines
    import config as _cfg


def _get_game_module(game_name):
    """Return (StateClass, format_move, RendererClass, player_labels, player_colors) for the given game."""
    # Default: no drops (overridden by shogi games)
    _cfg.DROP_PIECE_CHAR = {}
    _cfg.CHAR_TO_DROP_PIECE = {}

    if game_name in ("Gomoku", "gomoku"):
        try:
            from gui.games.gomoku_engine import (
                GomokuState,
                format_move,
                PLAYER_LABELS,
                PLAYER_COLORS,
            )
            from gui.games.gomoku_renderer import GomokuRenderer
        except ImportError:
            from games.gomoku_engine import (
                GomokuState,
                format_move,
                PLAYER_LABELS,
                PLAYER_COLORS,
            )
            from games.gomoku_renderer import GomokuRenderer
        return GomokuState, format_move, GomokuRenderer, PLAYER_LABELS, PLAYER_COLORS
    if game_name in ("MiniShogi", "minishogi"):
        try:
            from gui.games.minishogi_engine import (
                MiniShogiState,
                format_move,
                PLAYER_LABELS,
                PLAYER_COLORS,
                DROP_PIECE_CHAR,
                CHAR_TO_DROP_PIECE,
            )
            from gui.games.minishogi_renderer import MiniShogiRenderer
        except ImportError:
            from games.minishogi_engine import (
                MiniShogiState,
                format_move,
                PLAYER_LABELS,
                PLAYER_COLORS,
                DROP_PIECE_CHAR,
                CHAR_TO_DROP_PIECE,
            )
            from games.minishogi_renderer import MiniShogiRenderer
        _cfg.DROP_PIECE_CHAR = DROP_PIECE_CHAR
        _cfg.CHAR_TO_DROP_PIECE = CHAR_TO_DROP_PIECE
        return (
            MiniShogiState,
            format_move,
            MiniShogiRenderer,
            PLAYER_LABELS,
            PLAYER_COLORS,
        )
    if game_name in ("KohakuShogi", "kohaku_shogi"):
        try:
            from gui.games.kohaku_shogi_engine import (
                KohakuShogiState,
                format_move,
                PLAYER_LABELS,
                PLAYER_COLORS,
                DROP_PIECE_CHAR,
                CHAR_TO_DROP_PIECE,
                PROMOTE_MAP,
            )
            from gui.games.kohaku_shogi_renderer import KohakuShogiRenderer
        except ImportError:
            from games.kohaku_shogi_engine import (
                KohakuShogiState,
                format_move,
                PLAYER_LABELS,
                PLAYER_COLORS,
                DROP_PIECE_CHAR,
                CHAR_TO_DROP_PIECE,
                PROMOTE_MAP,
            )
            from games.kohaku_shogi_renderer import KohakuShogiRenderer
        _cfg.DROP_PIECE_CHAR = DROP_PIECE_CHAR
        _cfg.CHAR_TO_DROP_PIECE = CHAR_TO_DROP_PIECE
        _cfg.PROMOTE_MAP = PROMOTE_MAP
        return (
            KohakuShogiState,
            format_move,
            KohakuShogiRenderer,
            PLAYER_LABELS,
            PLAYER_COLORS,
        )
    if game_name in ("KohakuChess", "kohaku_chess"):
        try:
            from gui.games.kohaku_chess_engine import (
                KohakuChessState,
                format_move,
                PLAYER_LABELS,
                PLAYER_COLORS,
            )
            from gui.games.kohaku_chess_renderer import KohakuChessRenderer
        except ImportError:
            from games.kohaku_chess_engine import (
                KohakuChessState,
                format_move,
                PLAYER_LABELS,
                PLAYER_COLORS,
            )
            from games.kohaku_chess_renderer import KohakuChessRenderer
        return (
            KohakuChessState,
            format_move,
            KohakuChessRenderer,
            PLAYER_LABELS,
            PLAYER_COLORS,
        )
    try:
        from gui.games.minichess_engine import (
            MiniChessState,
            format_move,
            PLAYER_LABELS,
            PLAYER_COLORS,
        )
        from gui.games.minichess_renderer import MiniChessRenderer
    except ImportError:
        from games.minichess_engine import (
            MiniChessState,
            format_move,
            PLAYER_LABELS,
            PLAYER_COLORS,
        )
        from games.minichess_renderer import MiniChessRenderer
    return MiniChessState, format_move, MiniChessRenderer, PLAYER_LABELS, PLAYER_COLORS


def _configure_board_size(game_name):
    """Set config board dimensions based on game type."""
    if game_name in ("Gomoku", "gomoku"):
        _cfg.BOARD_H = 15
        _cfg.BOARD_W = 15
        _cfg.SQUARE_SIZE = 36  # smaller squares for 15x15 board
        _cfg.MAX_STEP = _cfg.BOARD_H * _cfg.BOARD_W
        _cfg.SCORE_PLOT_MAX_CP = 10000  # gomoku threats score large
        _cfg.SCORE_DISPLAY_DIV = 2000  # normalize to ±5 range for display
    elif game_name in ("MiniShogi", "minishogi"):
        _cfg.BOARD_H = 5
        _cfg.BOARD_W = 5
        _cfg.SQUARE_SIZE = 70  # larger squares for kanji
        _cfg.MAX_STEP = 200
        _cfg.SCORE_PLOT_MAX_CP = 2000
        _cfg.SCORE_DISPLAY_DIV = 100
        _cfg.HAND_ROW_H = 60  # height of each hand row (gote top, sente bottom)
    elif game_name in ("KohakuShogi", "kohaku_shogi"):
        _cfg.BOARD_H = 7
        _cfg.BOARD_W = 6
        _cfg.SQUARE_SIZE = 64  # medium squares for 7x6 board with kanji
        _cfg.MAX_STEP = 300
        _cfg.SCORE_PLOT_MAX_CP = 2000
        _cfg.SCORE_DISPLAY_DIV = 100
        _cfg.HAND_ROW_H = 60  # height of each hand row (gote top, sente bottom)
    elif game_name in ("KohakuChess", "kohaku_chess"):
        _cfg.BOARD_H = 7
        _cfg.BOARD_W = 6
        _cfg.SQUARE_SIZE = 72  # medium squares for 7x6 chess board
        _cfg.MAX_STEP = 150
        _cfg.SCORE_PLOT_MAX_CP = 500
        _cfg.SCORE_DISPLAY_DIV = 100
    else:
        _cfg.BOARD_H = 6
        _cfg.BOARD_W = 5
        _cfg.SQUARE_SIZE = 80
        _cfg.MAX_STEP = 100
        _cfg.SCORE_PLOT_MAX_CP = 500  # chess centipawns
        _cfg.SCORE_DISPLAY_DIV = 100  # centipawns → pawns
    _cfg.BOARD_PIXEL_W = _cfg.BOARD_W * _cfg.SQUARE_SIZE
    _cfg.BOARD_PIXEL_H = _cfg.BOARD_H * _cfg.SQUARE_SIZE
    _cfg.COL_LABELS = "".join(chr(65 + i) for i in range(_cfg.BOARD_W))
    _cfg.ROW_LABELS = "".join(str(_cfg.BOARD_H - i) for i in range(_cfg.BOARD_H))
    # Hand rows for games with captured pieces (e.g. MiniShogi)
    hand_h = getattr(_cfg, "HAND_ROW_H", 0)
    _cfg.HAND_TOP_Y = _cfg.BOARD_Y  # gote hand row above board
    if hand_h:
        _cfg.BOARD_Y += hand_h  # push board down below gote hand
    # Sente hand goes BELOW the column labels (LABEL_MARGIN below board)
    _cfg.HAND_BOTTOM_Y = _cfg.BOARD_Y + _cfg.BOARD_PIXEL_H + _cfg.LABEL_MARGIN
    total_h = hand_h + _cfg.BOARD_PIXEL_H + _cfg.LABEL_MARGIN + hand_h
    _cfg.PANEL_X = _cfg.BOARD_X + _cfg.BOARD_PIXEL_W + 16
    _cfg.PANEL_Y = _cfg.HAND_TOP_Y
    _cfg.PANEL_H = max(getattr(_cfg, "PANEL_H", total_h), total_h)
    _cfg.BOTTOM_Y = _cfg.HAND_TOP_Y + total_h + 4
    _cfg.WINDOW_W = _cfg.PANEL_X + _cfg.PANEL_WIDTH + 12
    _cfg.WINDOW_H = _cfg.BOTTOM_Y + _cfg.BOTTOM_H + 8


class GameApp:
    """Main application class."""

    def __init__(self, game_name="minichess"):
        # Configure board size BEFORE creating the window
        _configure_board_size(game_name)

        # Initialize Tk BEFORE pygame to avoid NSApplication conflict on macOS.
        # SDL and Tk both register their own NSApplication subclass; whichever
        # comes second crashes.  Keeping a hidden Tk root alive lets us reuse
        # it for settings dialogs later.
        import tkinter as tk

        self._tk_root = tk.Tk()
        self._tk_root.withdraw()

        pygame.init()
        pygame.display.set_caption(game_name.capitalize())

        self.screen = pygame.display.set_mode((_cfg.WINDOW_W, _cfg.WINDOW_H))
        self.clock = pygame.time.Clock()

        # Select game module (state class, move formatter, renderer, labels, colors)
        state_cls, fmt_move, renderer_cls, player_labels, player_colors = (
            _get_game_module(game_name)
        )
        self._state_class = state_cls
        self._format_move = fmt_move
        self._game_name = game_name
        self._player_labels = player_labels  # {0: "White"/"Black", 1: "Black"/"White"}
        self._player_colors = player_colors  # {0: (r,g,b), 1: (r,g,b)}

        game_renderer = renderer_cls(self.screen)
        self.board_renderer = BoardRenderer(self.screen, game_renderer=game_renderer)
        self.side_panel = SidePanel(self.screen)

        self.game_state = state_cls.initial()

        # Discover engines
        self._available_engines = discover_engines(_cfg.BUILD_DIR)

        # Engine option definitions
        self._engine_options = []
        self._engine_algorithms = []
        self._board_width = _cfg.BOARD_W
        self._board_height = _cfg.BOARD_H

        # Per-side state
        self.white = {
            "engine": None,  # path or None for human
            "algo": _cfg.DEFAULT_ALGORITHM,
            "params": {},  # algo-specific search params
            "depth": 0,  # 0 = use time limit
        }
        self.black = {
            "engine": self._best_engine_for_game(),
            "algo": _cfg.DEFAULT_ALGORITHM,
            "params": {},
            "depth": 0,
        }
        self.analyze = {
            "enabled": False,
            "engine": None,  # auto-select first available
            "algo": _cfg.DEFAULT_ALGORITHM,
            "params": {},
        }

        self.time_limit = _cfg.DEFAULT_TIMEOUT

        self._probe_engine_options()

        # Selection / interaction
        self.selected_piece = None
        self.legal_moves_for_selected = []
        self.last_move = None
        self._promotion_dialog = None

        # History
        self.move_history = []
        self.score_history = []

        self.game_result = None

        # AI state
        self.ai_thinking = False
        self.ai_result = {"move": None, "depth": 0, "ready": False}
        self.ai_depth = None

        # UCI state
        self.uci_moves = []
        self.search_info = {}
        self.white_uci_engine = None
        self.black_uci_engine = None

        # Analyze mode
        self._analyze_engine = None
        self._analyze_active = False  # True when we expect info lines
        self._undo_stack = []

        # AI vs AI pacing
        self._last_ai_time = 0.0
        self._paused = False
        self._game_started = False  # only True after explicit New Game + OK

        self._running = True

    # ------------------------------------------------------------------
    # Mode property -- derived from engine selections
    # ------------------------------------------------------------------

    @property
    def mode(self):
        w_is_ai = self.white["engine"] is not None
        b_is_ai = self.black["engine"] is not None
        if w_is_ai and b_is_ai:
            return "ai_vs_ai"
        elif w_is_ai or b_is_ai:
            return "human_vs_ai"
        else:
            return "human_vs_human"

    # ------------------------------------------------------------------
    # Engine auto-selection / probing
    # ------------------------------------------------------------------

    def _best_engine_for_game(self):
        """Return the best engine path for the current game.

        Prefers engines whose name starts with the game name
        (e.g. 'minishogi-ubgi' for game 'minishogi'), then falls back
        to the first available engine.
        """
        if not self._available_engines:
            return None
        game = self._game_name.lower().replace(" ", "")
        for name, path in self._available_engines:
            if name.lower().startswith(game):
                return path
        return self._available_engines[0][1]

    def _probe_engine_options(self):
        """Probe engine to get per-algorithm option sets.

        Launches a temp engine, reads default algo's options, then
        switches to each algorithm to read its specific options.
        Stores: _engine_algorithms, _algo_options[algo] = [opt_dicts],
        _algo_defaults[algo] = {name: default_val}.
        """
        exe_path = (
            self.white["engine"]
            or self.black["engine"]
            or self._best_engine_for_game()
        )
        if exe_path is None:
            return

        self._algo_options = {}  # algo_name -> [option_dicts]
        self._algo_defaults = {}  # algo_name -> {name: default_val}

        try:
            probe = UBGIEngine(exe_path)
            initial_options = list(probe.options)
        except RuntimeError:
            return

        # Extract game description from UBGI handshake
        self._game_name = probe.game_name
        self._board_width = probe.board_width
        self._board_height = probe.board_height

        # Extract algorithm list
        for opt in initial_options:
            if opt["name"] == "Algorithm" and opt["type"] == "combo":
                self._engine_algorithms = list(opt.get("vars", []))
                if opt.get("default") in self._engine_algorithms:
                    default_algo = opt["default"]
                    self.white["algo"] = default_algo
                    self.black["algo"] = default_algo
                    self.analyze["algo"] = default_algo
                break

        # Store options for the default algo (already loaded)
        if self._engine_algorithms:
            default_algo = self._engine_algorithms[0]
            algo_opts = [o for o in initial_options if o["name"] != "Algorithm"]
            self._algo_options[default_algo] = algo_opts
            self._algo_defaults[default_algo] = {
                o["name"]: o.get("default", "") for o in algo_opts
            }

            # Probe each other algorithm by switching and re-reading options
            for algo in self._engine_algorithms[1:]:
                try:
                    probe.set_option("Algorithm", algo)
                    # Re-handshake to get new options
                    probe._send("ubgi")
                    probe.options = []
                    probe._wait_for_uciok(timeout=3.0)
                    algo_opts = [o for o in probe.options if o["name"] != "Algorithm"]
                    self._algo_options[algo] = algo_opts
                    self._algo_defaults[algo] = {
                        o["name"]: o.get("default", "") for o in algo_opts
                    }
                except Exception:
                    self._algo_options[algo] = []
                    self._algo_defaults[algo] = {}

        try:
            probe.quit()
        except Exception:
            pass

        # Keep _engine_options as the default algo's options for backward compat
        self._engine_options = initial_options

        # Initialize each side's params with their algo's defaults
        for side in (self.white, self.black, self.analyze):
            algo = side["algo"]
            side["params"] = dict(self._algo_defaults.get(algo, {}))

    def _probe_engine_options_from(self, exe_path):
        """Re-probe engine options from a specific engine path."""
        old_white = self.white["engine"]
        old_black = self.black["engine"]
        # Temporarily set engine path so _probe_engine_options picks it up
        self.white["engine"] = exe_path
        self._probe_engine_options()
        self.white["engine"] = old_white

    def _get_or_create_uci_engine(self, side_config, attr_name):
        """Create or reuse a UCI engine for a given side configuration.

        Args:
            side_config: dict with 'engine', 'algo', 'params' keys.
            attr_name: attribute name on self to store the engine instance.
        """
        existing = getattr(self, attr_name, None)
        if existing is not None and existing.is_alive():
            return existing
        try:
            # Build initial options: Algorithm + all params (including NNUEFile)
            # These are sent before isready so the engine can load NNUE correctly.
            init_opts = {"Algorithm": side_config["algo"]}
            init_opts.update({k: str(v) for k, v in side_config["params"].items()})
            engine = UBGIEngine(side_config["engine"], initial_options=init_opts)
            setattr(self, attr_name, engine)
            return engine
        except RuntimeError:
            return None

    def _quit_engine(self, attr):
        """Quit a single UCI engine by attribute name and clear it."""
        engine = getattr(self, attr, None)
        if engine is not None:
            try:
                engine.quit()
            except Exception:
                pass
            setattr(self, attr, None)

    def _shutdown_uci_engines(self):
        """Quit all active UCI engine instances."""
        self._stop_analysis()
        for attr in ("_analyze_engine", "white_uci_engine", "black_uci_engine"):
            self._quit_engine(attr)

    # ------------------------------------------------------------------
    # Analyze mode
    # ------------------------------------------------------------------

    def _get_or_create_analyze_engine(self):
        if self._analyze_engine is not None and self._analyze_engine.is_alive():
            return self._analyze_engine
        # Use explicit analyze engine path, or fall back to game-matched engine
        exe_path = (
            self.analyze["engine"]
            or self.white["engine"]
            or self.black["engine"]
            or self._best_engine_for_game()
        )
        if exe_path is None:
            return None
        try:
            init_opts = {"Algorithm": self.analyze["algo"]}
            init_opts.update({k: str(v) for k, v in self.analyze["params"].items()})
            engine = UBGIEngine(exe_path, initial_options=init_opts)
            self._analyze_engine = engine
            return engine
        except RuntimeError:
            return None

    def _start_analysis(self):
        if self.game_result is not None:
            return
        if not self.analyze["enabled"]:
            return
        # Kill old engine and create fresh — instant stop, no races
        self._kill_analyze_engine()
        engine = self._get_or_create_analyze_engine()
        if engine is None:
            return
        self.search_info = {}
        if self.uci_moves:
            engine.set_position(moves=list(self.uci_moves))
        else:
            engine.set_position()
        engine.go(
            infinite=True,
            info_callback=self._on_analyze_info,
            done_callback=self._on_analyze_done,
        )
        self._analyze_active = True

    def _stop_analysis(self):
        self._kill_analyze_engine()
        self._analyze_active = False
        self.search_info = {}

    def _kill_analyze_engine(self):
        if self._analyze_engine is not None:
            try:
                self._analyze_engine.quit()
            except Exception:
                pass
            self._analyze_engine = None

    def _on_analyze_info(self, info_dict):
        """Normalize score to White-labeled player's perspective for the score bar."""
        if "score_cp" in info_dict and self.game_state.player == 1:
            info_dict["score_cp"] = -info_dict["score_cp"]
        # Preserve last known PV if new info doesn't have one
        if "pv" not in info_dict and "pv" in self.search_info:
            info_dict["pv"] = self.search_info["pv"]
        self.search_info = info_dict

    def _on_analyze_done(self, bestmove_str):
        # Engine stopped (either by our stop or by completing depth limit).
        # Don't clear _analyze_active here — a new go may already be in flight.
        pass

    # ------------------------------------------------------------------
    # Pause / Undo
    # ------------------------------------------------------------------

    def toggle_analyze(self):
        """Toggle analyze mode on/off. Only allowed when not gaming."""
        if self._is_gaming():
            return
        self.analyze["enabled"] = not self.analyze["enabled"]
        if self.analyze["enabled"]:
            self._start_analysis()
        else:
            self._stop_analysis()
            self.search_info = {}

    def stop_game(self):
        """Stop the current game. Declares it over so user can analyze."""
        if not self._is_gaming():
            return
        self._paused = False
        if self.ai_thinking:
            # Force stop current search
            for attr in ("white_uci_engine", "black_uci_engine"):
                eng = getattr(self, attr, None)
                if eng is not None:
                    try:
                        eng.stop()
                    except Exception:
                        pass
            self.ai_thinking = False
            self.ai_result = {"move": None, "depth": 0, "ready": False}
        self.game_result = "stopped"
        self._game_started = False

    def _is_gaming(self):
        """True when a game was explicitly started and not yet finished/stopped."""
        return self._game_started and self.game_result is None

    def undo_move(self):
        if not self._undo_stack or self._is_gaming():
            return
        if self.analyze["enabled"]:
            self._stop_analysis()
        snap = self._undo_stack.pop()
        self.game_state = snap["game_state"]
        self.uci_moves = snap["uci_moves"]
        self.move_history = snap["move_history"]
        self.score_history = snap["score_history"]
        self.last_move = snap["last_move"]
        self.game_result = None
        self.search_info = {}
        self.selected_piece = None
        self.legal_moves_for_selected = []
        self._sync_hand_highlight(None)
        if self.analyze["enabled"]:
            self._start_analysis()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        try:
            while self._running:
                self.handle_events()
                self.update()
                self.draw()
                self.clock.tick(_cfg.FPS)
        finally:
            self._shutdown_uci_engines()
            pygame.quit()
            try:
                self._tk_root.destroy()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    self._handle_left_click(event.pos)
                elif event.button == 3:  # Right click -- deselect
                    self._deselect_piece()

            elif event.type == pygame.MOUSEWHEEL:
                self.side_panel.set_scroll(-event.y)

            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event.key)

    def _handle_left_click(self, pos):
        x, y = pos

        # Promotion dialog intercepts all clicks when active
        if self._handle_promotion_click(x, y):
            return

        board_pos = self.board_renderer.screen_to_board(x, y)
        if board_pos is not None:
            if self._is_human_turn():
                self.handle_board_click(board_pos[0], board_pos[1])
            return

        # Check hand piece click (MiniShogi drop support)
        gr = self.board_renderer.game_renderer
        if gr is not None and hasattr(gr, "screen_to_hand") and self._is_human_turn():
            hand_sel = gr.screen_to_hand(x, y, self.game_state)
            if hand_sel is not None:
                self._select_hand_piece(hand_sel)
                return

        action = self.side_panel.handle_click(x, y)
        if action == "reset":
            self.reset()
        elif action == "new_game":
            self.open_new_game_dialog()
        elif action == "settings":
            self.open_settings()
        elif action == "undo":
            self.undo_move()
        elif action == "analyze":
            self.toggle_analyze()
        elif action == "stop":
            self.stop_game()

    def _handle_keydown(self, key):
        if key == pygame.K_n:
            self.open_new_game_dialog()
        elif key == pygame.K_s:
            self.open_settings()
        elif key == pygame.K_ESCAPE:
            if self.selected_piece is not None:
                self._deselect_piece()
            else:
                self._running = False
        elif key == pygame.K_SPACE:
            if self.mode == "ai_vs_ai":
                self._paused = not self._paused
        elif key == pygame.K_z:
            self.undo_move()
        elif key == pygame.K_a:
            self.toggle_analyze()
        elif key == pygame.K_q:
            self.stop_game()

    # ------------------------------------------------------------------
    # Board interaction
    # ------------------------------------------------------------------

    def _is_human_turn(self):
        if self.ai_thinking:
            return False
        # Not gaming (stopped, game over, or no engines) → always allow clicks
        if not self._is_gaming():
            return True
        # During a game, only human side can click
        player = self.game_state.player
        side = self.white if player == 0 else self.black
        return side["engine"] is None

    def handle_board_click(self, row, col):
        player = self.game_state.player

        # Get the clicked piece; board layout differs per game
        try:
            clicked_piece = self.game_state.board[player][row][col]
        except (TypeError, IndexError):
            # Non-chess games (e.g. Gomoku) use board[row][col]
            clicked_piece = _cfg.EMPTY

        if self.selected_piece is None:
            # For placement games (Gomoku), check if any legal move targets (row,col)
            placement_move = None
            for m in self.game_state.legal_actions:
                if m[1] == (row, col):
                    placement_move = m
                    break
            if placement_move is not None and clicked_piece == _cfg.EMPTY:
                self.execute_move(placement_move)
            elif clicked_piece != _cfg.EMPTY:
                self._select_piece(row, col)
        else:
            target_move = self._find_legal_move(row, col)
            if target_move is not None:
                self.execute_move(target_move)
            elif clicked_piece != _cfg.EMPTY and (row, col) != self.selected_piece:
                self._select_piece(row, col)
            else:
                self._deselect_piece()

    def _select_piece(self, row, col):
        self.selected_piece = (row, col)
        self.legal_moves_for_selected = [
            m for m in self.game_state.legal_actions if m[0] == (row, col)
        ]
        self._sync_hand_highlight(None)

    def _select_hand_piece(self, hand_key):
        """Select a hand piece for dropping.

        Args:
            hand_key: (BOARD_SIZE, piece_type) tuple from the renderer.
        """
        self.selected_piece = hand_key
        self.legal_moves_for_selected = [
            m for m in self.game_state.legal_actions if m[0] == hand_key
        ]
        self._sync_hand_highlight(hand_key)

    def _deselect_piece(self):
        """Clear selection and hand highlight."""
        self.selected_piece = None
        self.legal_moves_for_selected = []
        self._sync_hand_highlight(None)

    def _sync_hand_highlight(self, hand_key):
        """Update the renderer's hand highlight if it supports it."""
        gr = self.board_renderer.game_renderer
        if gr is not None and hasattr(gr, "set_selected_hand"):
            gr.set_selected_hand(hand_key)

    def _find_legal_move(self, dest_row, dest_col):
        """Find a legal move to (dest_row, dest_col) from the current selection.

        If both promotion and non-promotion moves exist, show a promotion
        choice dialog instead of auto-promoting.
        """
        bh = _cfg.BOARD_H
        matches = []
        for move in self.legal_moves_for_selected:
            (_, _), (tr, tc) = move
            actual_tr = tr - bh if tr >= bh else tr
            if actual_tr == dest_row and tc == dest_col:
                matches.append(move)

        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]

        # Multiple matches: separate promotion and non-promotion
        promo_move = None
        normal_move = None
        for m in matches:
            if m[1][0] >= bh:
                promo_move = m
            else:
                normal_move = m

        if promo_move and normal_move:
            # Show promotion choice dialog
            self._show_promotion_dialog(dest_row, dest_col, promo_move, normal_move)
            return None  # don't execute yet — dialog handles it
        return promo_move or normal_move

    def _show_promotion_dialog(self, row, col, promo_move, normal_move):
        """Show an inline promotion choice overlay on the board."""
        self._promotion_dialog = {
            "row": row,
            "col": col,
            "promo_move": promo_move,
            "normal_move": normal_move,
        }

    def _draw_promotion_dialog(self):
        """Draw the promotion choice overlay if active."""
        dlg = getattr(self, "_promotion_dialog", None)
        if dlg is None:
            return

        # Semi-transparent overlay
        overlay = pygame.Surface(
            (self.board_renderer.surface.get_width(),
             self.board_renderer.surface.get_height()),
            pygame.SRCALPHA,
        )
        overlay.fill((0, 0, 0, 100))
        self.board_renderer.surface.blit(overlay, (0, 0))

        row, col = dlg["row"], dlg["col"]
        sq = _cfg.SQUARE_SIZE

        # Position: two boxes side by side centered on the destination square
        cx = _cfg.BOARD_X + col * sq + sq // 2
        cy = _cfg.BOARD_Y + row * sq + sq // 2
        box_w = int(sq * 1.2)
        box_h = int(sq * 1.4)
        gap = 8

        # Promote box (left), Keep box (right)
        left_x = cx - box_w - gap // 2
        right_x = cx + gap // 2

        # Clamp to screen bounds
        if left_x < 4:
            left_x = 4
            right_x = left_x + box_w + gap
        max_x = self.board_renderer.surface.get_width() - box_w - 4
        if right_x > max_x:
            right_x = max_x
            left_x = right_x - box_w - gap

        top_y = cy - box_h // 2
        if top_y < 4:
            top_y = 4
        max_y = self.board_renderer.surface.get_height() - box_h - 4
        if top_y > max_y:
            top_y = max_y

        # Draw "Promote" box
        promo_rect = pygame.Rect(left_x, top_y, box_w, box_h)
        pygame.draw.rect(self.board_renderer.surface, (220, 180, 120), promo_rect, border_radius=6)
        pygame.draw.rect(self.board_renderer.surface, (80, 50, 20), promo_rect, 2, border_radius=6)

        # Draw "Keep" box
        keep_rect = pygame.Rect(right_x, top_y, box_w, box_h)
        pygame.draw.rect(self.board_renderer.surface, (200, 200, 190), keep_rect, border_radius=6)
        pygame.draw.rect(self.board_renderer.surface, (80, 50, 20), keep_rect, 2, border_radius=6)

        # Draw piece previews inside boxes
        gr = self.board_renderer.game_renderer
        player = self.game_state.player
        if gr is not None and hasattr(gr, "_piece_cache"):
            fr, fc = dlg["promo_move"][0]
            bh = _cfg.BOARD_H
            base_piece = self.game_state.board[player][fr][fc] if fr < bh else fc

            promote_map = getattr(_cfg, "PROMOTE_MAP", {})
            promoted_piece = promote_map.get(base_piece)

            cache = gr._piece_cache
            if promoted_piece and (player, promoted_piece) in cache:
                s = cache[(player, promoted_piece)]
                self.board_renderer.surface.blit(
                    s,
                    (promo_rect.centerx - s.get_width() // 2,
                     promo_rect.centery - s.get_height() // 2 - 8),
                )
            if (player, base_piece) in cache:
                s = cache[(player, base_piece)]
                self.board_renderer.surface.blit(
                    s,
                    (keep_rect.centerx - s.get_width() // 2,
                     keep_rect.centery - s.get_height() // 2 - 8),
                )

        # Labels
        try:
            label_font = pygame.font.SysFont("Arial", 14, bold=True)
            promo_label = label_font.render("Promote", True, (180, 30, 30))
            keep_label = label_font.render("Keep", True, (40, 40, 40))
            self.board_renderer.surface.blit(
                promo_label,
                (promo_rect.centerx - promo_label.get_width() // 2,
                 promo_rect.bottom - promo_label.get_height() - 4),
            )
            self.board_renderer.surface.blit(
                keep_label,
                (keep_rect.centerx - keep_label.get_width() // 2,
                 keep_rect.bottom - keep_label.get_height() - 4),
            )
        except Exception:
            pass

        # Store rects for click handling
        dlg["promo_rect"] = promo_rect
        dlg["keep_rect"] = keep_rect

    def _handle_promotion_click(self, x, y):
        """Handle click during promotion dialog. Returns True if handled."""
        dlg = getattr(self, "_promotion_dialog", None)
        if dlg is None:
            return False

        promo_rect = dlg.get("promo_rect")
        keep_rect = dlg.get("keep_rect")

        if promo_rect and promo_rect.collidepoint(x, y):
            self._promotion_dialog = None
            self.execute_move(dlg["promo_move"])
            return True
        elif keep_rect and keep_rect.collidepoint(x, y):
            self._promotion_dialog = None
            self.execute_move(dlg["normal_move"])
            return True
        else:
            # Click outside — cancel promotion
            self._promotion_dialog = None
            self._deselect_piece()
            return True

    # ------------------------------------------------------------------
    # Move execution
    # ------------------------------------------------------------------

    def execute_move(self, move):

        # Clear "stopped" state so user can keep exploring
        if self.game_result == "stopped":
            self.game_result = None

        # Save undo snapshot (always — user may want to explore/replay)
        if not self._is_gaming():
            self._undo_stack.append(
                {
                    "game_state": self.game_state,
                    "uci_moves": list(self.uci_moves),
                    "move_history": list(self.move_history),
                    "score_history": list(self.score_history),
                    "last_move": self.last_move,
                }
            )

        mover = self.game_state.player
        prefix = "W" if mover == 0 else "B"
        step = self.game_state.step
        move_str = f"{step}. {prefix}: {self._format_move(move)}"

        new_state = self.game_state.next_state(move)
        self.game_state = new_state

        self.move_history.append(move_str)
        self.last_move = move
        self.uci_moves.append(UBGIEngine.move_to_uci(move))
        # Determine score source
        score_cp = self.search_info.get("score_cp")
        if self.analyze["enabled"]:
            source = "analyze"
        elif mover == 0 and self.white["engine"] is not None:
            source = "p0"
        elif mover == 1 and self.black["engine"] is not None:
            source = "p1"
        else:
            source = "human"
        self.score_history.append((mover, score_cp, source))

        self.side_panel._scroll_offset = max(0, len(self.move_history))
        self.selected_piece = None
        self.legal_moves_for_selected = []
        self._sync_hand_highlight(None)

        result, winner = self.game_state.check_game_over()
        if result in ("win", "checkmate"):
            self.game_result = ("p0_checkmate" if winner == 0 else "p1_checkmate") \
                if result == "checkmate" \
                else ("p0_wins" if winner == 0 else "p1_wins")
            return
        if result == "draw":
            self.game_result = "draw"
            return

        if self.analyze["enabled"] and not self._is_gaming():
            self._start_analysis()  # sends position+go, engine supersedes old search
        elif self._is_gaming():
            self._trigger_ai_if_needed()

    def _trigger_ai_if_needed(self):
        if not self._game_started or self.game_result is not None or self.ai_thinking or self._paused:
            return
        player = self.game_state.player
        side = self.white if player == 0 else self.black
        if side["engine"] is None:
            return  # human's turn
        self.trigger_ai_move()

    # ------------------------------------------------------------------
    # AI management
    # ------------------------------------------------------------------

    def trigger_ai_move(self):
        player = self.game_state.player
        side = self.white if player == 0 else self.black

        if side["engine"] is None:
            return  # human's turn

        self.ai_thinking = True
        self.ai_result = {"move": None, "depth": 0, "ready": False}
        self.search_info = {}
        self._ai_start_time = time.time()

        attr = "white_uci_engine" if player == 0 else "black_uci_engine"
        uci = self._get_or_create_uci_engine(side, attr)

        if uci is None:
            # Engine failed to start
            self.ai_result = {"move": None, "depth": 0, "ready": True}
            return

        if self.uci_moves:
            uci.set_position(moves=list(self.uci_moves))
        else:
            uci.set_position()

        max_depth = side["depth"]
        if max_depth > 0:
            uci.go(
                depth=max_depth,
                info_callback=self._on_uci_info,
                done_callback=self._on_uci_bestmove,
            )
        else:
            movetime_ms = int(self.time_limit * 1000)
            uci.go(
                movetime=movetime_ms,
                info_callback=self._on_uci_info,
                done_callback=self._on_uci_bestmove,
            )

    def _force_kill_ai_engine(self):
        """Kill the AI engine after timeout; use last known best move."""
        player = self.game_state.player
        attr = "white_uci_engine" if player == 0 else "black_uci_engine"
        engine = getattr(self, attr, None)

        # Extract best move from last search info (currmove or pv[0])
        bestmove = None
        info = self.search_info
        if info.get("pv"):
            bestmove = UBGIEngine.uci_to_move(info["pv"][0])
        elif info.get("currmove"):
            bestmove = UBGIEngine.uci_to_move(info["currmove"])

        # Kill engine process
        if engine is not None:
            try:
                engine.quit()
            except Exception:
                pass
            setattr(self, attr, None)

        depth = info.get("depth", 0)
        self.ai_result = {"move": bestmove, "depth": depth, "ready": True}

    def _on_uci_info(self, info_dict):
        if "score_cp" in info_dict and self.game_state.player == 1:
            info_dict["score_cp"] = -info_dict["score_cp"]
        # Preserve last known PV and currmove for timeout fallback
        if "pv" not in info_dict and "pv" in self.search_info:
            info_dict["pv"] = self.search_info["pv"]
        if "currmove" not in info_dict and "currmove" in self.search_info:
            info_dict["currmove"] = self.search_info["currmove"]
        self.search_info = info_dict

    def _on_uci_bestmove(self, bestmove_str):
        if bestmove_str is None:
            self.ai_result = {"move": None, "depth": 0, "ready": True}
            return

        move = UBGIEngine.uci_to_move(bestmove_str)
        depth = self.search_info.get("depth", 0)
        self.ai_result = {"move": move, "depth": depth, "ready": True}

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def update(self):
        # Force-kill engine if it exceeds the timeout
        if self.ai_thinking and not self.ai_result.get("ready"):
            elapsed = time.time() - getattr(self, "_ai_start_time", 0)
            kill_after = self.time_limit + 1.0  # 1s grace period
            if elapsed > kill_after:
                self._force_kill_ai_engine()

        if self.ai_result.get("ready"):
            move = self.ai_result["move"]
            depth = self.ai_result["depth"]
            self.ai_result = {"move": None, "depth": 0, "ready": False}
            self.ai_thinking = False

            # Discard stale results if game was reset/stopped
            if not self._game_started:
                return

            if move is not None and move in self.game_state.legal_actions:
                self.ai_depth = depth
                self.execute_move(move)
                self._last_ai_time = time.time()
            else:
                loser = self.game_state.player
                self.game_result = "p1_wins" if loser == 0 else "p0_wins"
            return

        # AI vs AI auto-trigger
        if (
            self.mode == "ai_vs_ai"
            and self.game_result is None
            and not self.ai_thinking
            and not self._paused
        ):
            elapsed = time.time() - self._last_ai_time
            if elapsed >= _cfg.AI_VS_AI_DELAY:
                self._trigger_ai_if_needed()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self):
        self.screen.fill(_cfg.COLOR_BG)

        # Only show PV arrows in analyze mode, NOT during gaming
        pv = (
            self.search_info.get("pv")
            if self.analyze["enabled"] and not self._is_gaming()
            else None
        )
        self.board_renderer.draw(
            self.game_state,
            selected=self.selected_piece,
            legal_moves=self.legal_moves_for_selected,
            last_move=self.last_move,
            pv_arrows=pv,
        )

        self.side_panel.draw(
            self.game_state,
            ai_thinking=self.ai_thinking,
            game_result=self.game_result,
            ai_depth=self.ai_depth,
            mode=self.mode,
            time_limit=self.time_limit,
            search_info=self.search_info,
            paused=self._paused,
            analyze_enabled=self.analyze["enabled"],
            gaming=self._is_gaming(),
            player_labels=self._player_labels,
            player_colors=self._player_colors,
        )

        self.side_panel.draw_bottom(
            score_cp=self.search_info.get("score_cp"),
            score_history=self.score_history,
            move_history=self.move_history,
            player_colors=self._player_colors,
        )

        # Draw promotion dialog overlay if active
        self._draw_promotion_dialog()

        pygame.display.flip()

    # ------------------------------------------------------------------
    # New game / settings
    # ------------------------------------------------------------------

    def reset(self):
        """Reset to initial position, clear history, close engines."""
        # Stop any in-progress search first
        for attr in ("white_uci_engine", "black_uci_engine"):
            eng = getattr(self, attr, None)
            if eng is not None:
                try:
                    eng.stop()
                except Exception:
                    pass
        self._stop_analysis()
        self._kill_analyze_engine()
        # Now quit engines
        for attr in ("white_uci_engine", "black_uci_engine"):
            self._quit_engine(attr)

        self.game_state = self._state_class.initial()
        self.selected_piece = None
        self.legal_moves_for_selected = []
        self.last_move = None
        self._promotion_dialog = None
        self.move_history = []
        self.score_history = []
        self.game_result = None
        self.ai_thinking = False
        self.ai_result = {"move": None, "depth": 0, "ready": False}
        self.ai_depth = None
        self.uci_moves = []
        self.search_info = {}
        self._last_ai_time = 0.0
        self._paused = False
        self._undo_stack = []
        self._game_started = False

    def new_game(self):
        """Reset + start game (trigger AI if needed)."""
        self.reset()
        self._game_started = True
        self._trigger_ai_if_needed()

    def open_new_game_dialog(self):
        """Player setup dialog → starts a new game on OK."""
        import tkinter as tk
        from tkinter import ttk

        self._available_engines = discover_engines(_cfg.BUILD_DIR)
        engine_names = ["Human"] + [name for name, _path in self._available_engines]
        engine_paths = [None] + [path for _name, path in self._available_engines]
        # Re-probe if we haven't probed yet
        if not self._engine_algorithms:
            best = self._best_engine_for_game()
            if best:
                self._probe_engine_options_from(best)
        algo_list = self._engine_algorithms or [_cfg.DEFAULT_ALGORITHM]

        def _engine_index(exe_path):
            if exe_path is None:
                return 0
            for idx, path in enumerate(engine_paths):
                if path == exe_path:
                    return idx
            return 0

        dialog = tk.Toplevel(self._tk_root)
        dialog.title("New Game")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.attributes("-topmost", True)
        pad = {"padx": 10, "pady": 4}

        white_engine_var = tk.StringVar(
            value=engine_names[_engine_index(self.white["engine"])]
        )
        black_engine_var = tk.StringVar(
            value=engine_names[_engine_index(self.black["engine"])]
        )
        w_algo_var = tk.StringVar(value=self.white["algo"])
        b_algo_var = tk.StringVar(value=self.black["algo"])
        w_depth_var = tk.IntVar(value=self.white["depth"])
        b_depth_var = tk.IntVar(value=self.black["depth"])
        time_var = tk.DoubleVar(value=self.time_limit)
        white_params = dict(self.white["params"])
        black_params = dict(self.black["params"])
        applied = [False]

        def _build_side_frame(
            parent, row, label, engine_var, algo_var, depth_var, params
        ):
            frame = ttk.LabelFrame(parent, text=label)
            frame.grid(row=row, column=0, columnspan=2, sticky="ew", **pad)
            ttk.Label(frame, text="Player:").grid(
                row=0, column=0, sticky="w", padx=4, pady=2
            )
            combo = ttk.Combobox(
                frame,
                textvariable=engine_var,
                values=engine_names,
                state="readonly",
                width=22,
            )
            combo.grid(row=0, column=1, columnspan=4, sticky="ew", padx=4, pady=2)
            ttk.Label(frame, text="Algorithm:").grid(
                row=1, column=0, sticky="w", padx=4, pady=2
            )
            algo_cb = ttk.Combobox(
                frame,
                textvariable=algo_var,
                values=algo_list,
                state="readonly",
                width=10,
            )
            algo_cb.grid(row=1, column=1, sticky="w", padx=4, pady=2)
            pbtn = ttk.Button(
                frame,
                text="Params...",
                command=lambda: self._open_params_dialog(
                    dialog, algo_var.get(), params
                ),
                width=8,
            )
            pbtn.grid(row=1, column=2, sticky="w", padx=4, pady=2)
            ttk.Label(frame, text="Depth:").grid(
                row=1, column=3, sticky="w", padx=4, pady=2
            )
            dspin = ttk.Spinbox(frame, from_=0, to=20, textvariable=depth_var, width=4)
            dspin.grid(row=1, column=4, sticky="w", padx=4, pady=2)
            ai_widgets = [algo_cb, pbtn, dspin]

            def _on_algo_change(e=None):
                new_algo = algo_var.get()
                params.clear()
                params.update(self._algo_defaults.get(new_algo, {}))

            algo_cb.bind("<<ComboboxSelected>>", _on_algo_change)
            return combo, ai_widgets

        w_combo, w_widgets = _build_side_frame(
            dialog, 0, "White", white_engine_var, w_algo_var, w_depth_var, white_params
        )
        b_combo, b_widgets = _build_side_frame(
            dialog, 1, "Black", black_engine_var, b_algo_var, b_depth_var, black_params
        )

        ttk.Label(dialog, text="Time limit (s):").grid(
            row=2, column=0, sticky="w", **pad
        )
        ttk.Spinbox(dialog, from_=0.1, to=30, increment=0.1, textvariable=time_var, width=5).grid(
            row=2, column=1, sticky="w", **pad
        )

        def _update():
            for w in w_widgets:
                st = (
                    ("readonly" if isinstance(w, ttk.Combobox) else "normal")
                    if white_engine_var.get() != "Human"
                    else "disabled"
                )
                w.configure(state=st)
            for w in b_widgets:
                st = (
                    ("readonly" if isinstance(w, ttk.Combobox) else "normal")
                    if black_engine_var.get() != "Human"
                    else "disabled"
                )
                w.configure(state=st)

        def _on_engine_change(e=None):
            _update()
            # Re-probe if an engine is selected and we haven't probed yet
            for var in (white_engine_var, black_engine_var):
                name = var.get()
                if name != "Human":
                    idx = engine_names.index(name) if name in engine_names else 0
                    path = engine_paths[idx]
                    if path and not self._engine_algorithms:
                        self._probe_engine_options_from(path)
                        # Update algo comboboxes with new list
                        new_algos = self._engine_algorithms or [_cfg.DEFAULT_ALGORITHM]
                        for cb in (w_widgets[0], b_widgets[0]):
                            cb.configure(values=new_algos)
                    break

        w_combo.bind("<<ComboboxSelected>>", _on_engine_change)
        b_combo.bind("<<ComboboxSelected>>", _on_engine_change)
        _update()

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(
            btn_frame,
            text="Start",
            command=lambda: [applied.__setitem__(0, True), dialog.destroy()],
            width=10,
        ).grid(row=0, column=0, padx=8)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=10).grid(
            row=0, column=1, padx=8
        )
        dialog.bind(
            "<Return>", lambda e: [applied.__setitem__(0, True), dialog.destroy()]
        )
        dialog.bind("<Escape>", lambda e: dialog.destroy())

        dialog.update_idletasks()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        sw, sh = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
        dialog.geometry(f"+{(sw - dw) // 2}+{(sh - dh) // 2}")
        dialog.wait_window()

        if not applied[0]:
            return

        w_idx = (
            engine_names.index(white_engine_var.get())
            if white_engine_var.get() in engine_names
            else 0
        )
        b_idx = (
            engine_names.index(black_engine_var.get())
            if black_engine_var.get() in engine_names
            else 0
        )

        if (
            engine_paths[w_idx] != self.white["engine"]
            or w_algo_var.get() != self.white["algo"]
            or white_params != self.white["params"]
        ):
            self._quit_engine("white_uci_engine")
        if (
            engine_paths[b_idx] != self.black["engine"]
            or b_algo_var.get() != self.black["algo"]
            or black_params != self.black["params"]
        ):
            self._quit_engine("black_uci_engine")

        self.white.update(
            {
                "engine": engine_paths[w_idx],
                "algo": w_algo_var.get(),
                "params": white_params,
                "depth": max(0, min(20, w_depth_var.get())),
            }
        )
        self.black.update(
            {
                "engine": engine_paths[b_idx],
                "algo": b_algo_var.get(),
                "params": black_params,
                "depth": max(0, min(20, b_depth_var.get())),
            }
        )
        self.time_limit = max(0.1, min(30, time_var.get()))
        self.new_game()

    def open_settings(self):
        """Settings dialog: analyze engine config + time limit. Saves without starting game."""
        import tkinter as tk
        from tkinter import ttk

        self._available_engines = discover_engines(_cfg.BUILD_DIR)
        engine_names = ["Human"] + [name for name, _path in self._available_engines]
        engine_paths = [None] + [path for _name, path in self._available_engines]
        # Re-probe if we haven't probed yet
        if not self._engine_algorithms:
            best = self._best_engine_for_game()
            if best:
                self._probe_engine_options_from(best)
        algo_list = self._engine_algorithms or [_cfg.DEFAULT_ALGORITHM]

        def _engine_index(exe_path):
            if exe_path is None:
                return 0
            for idx, path in enumerate(engine_paths):
                if path == exe_path:
                    return idx
            return 0

        dialog = tk.Toplevel(self._tk_root)
        dialog.title("Settings")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.attributes("-topmost", True)
        pad = {"padx": 10, "pady": 4}

        analyze_engine_names = [name for name, _path in self._available_engines] or [
            "(none)"
        ]
        analyze_engine_var = tk.StringVar(
            value=(
                "(auto)"
                if self.analyze["engine"] is None
                else engine_names[_engine_index(self.analyze["engine"])]
            )
        )
        analyze_algo_var = tk.StringVar(value=self.analyze["algo"])
        time_var = tk.DoubleVar(value=self.time_limit)
        analyze_params = dict(self.analyze["params"])
        applied = [False]

        # Analyze engine
        af = ttk.LabelFrame(dialog, text="Analyze Engine")
        af.grid(row=0, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Label(af, text="Engine:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Combobox(
            af,
            textvariable=analyze_engine_var,
            values=["(auto)"] + analyze_engine_names,
            state="readonly",
            width=22,
        ).grid(row=0, column=1, columnspan=3, sticky="ew", padx=4, pady=2)
        ttk.Label(af, text="Algorithm:").grid(
            row=1, column=0, sticky="w", padx=4, pady=2
        )
        a_algo_cb = ttk.Combobox(
            af,
            textvariable=analyze_algo_var,
            values=algo_list,
            state="readonly",
            width=10,
        )
        a_algo_cb.grid(row=1, column=1, sticky="w", padx=4, pady=2)
        ttk.Button(
            af,
            text="Params...",
            command=lambda: self._open_params_dialog(
                dialog, analyze_algo_var.get(), analyze_params
            ),
            width=8,
        ).grid(row=1, column=2, sticky="w", padx=4, pady=2)

        def _on_a_algo(e=None):
            new_algo = analyze_algo_var.get()
            analyze_params.clear()
            analyze_params.update(self._algo_defaults.get(new_algo, {}))

        a_algo_cb.bind("<<ComboboxSelected>>", _on_a_algo)

        # Time limit
        ttk.Label(dialog, text="Time limit (s):").grid(
            row=1, column=0, sticky="w", **pad
        )
        ttk.Spinbox(dialog, from_=0.1, to=30, increment=0.1, textvariable=time_var, width=5).grid(
            row=1, column=1, sticky="w", **pad
        )

        # Buttons
        bf = ttk.Frame(dialog)
        bf.grid(row=2, column=0, columnspan=2, pady=10)
        ttk.Button(
            bf,
            text="Save",
            command=lambda: [applied.__setitem__(0, True), dialog.destroy()],
            width=10,
        ).grid(row=0, column=0, padx=8)
        ttk.Button(bf, text="Cancel", command=dialog.destroy, width=10).grid(
            row=0, column=1, padx=8
        )
        dialog.bind(
            "<Return>", lambda e: [applied.__setitem__(0, True), dialog.destroy()]
        )
        dialog.bind("<Escape>", lambda e: dialog.destroy())

        dialog.update_idletasks()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        sw, sh = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
        dialog.geometry(f"+{(sw - dw) // 2}+{(sh - dh) // 2}")
        dialog.wait_window()

        if not applied[0]:
            return

        a_name = analyze_engine_var.get()
        new_analyze_engine = (
            None
            if a_name in ("(auto)", "(none)")
            else (
                engine_paths[engine_names.index(a_name)]
                if a_name in engine_names
                else None
            )
        )

        if (
            new_analyze_engine != self.analyze["engine"]
            or analyze_algo_var.get() != self.analyze["algo"]
            or analyze_params != self.analyze["params"]
        ):
            self._quit_engine("_analyze_engine")

        self.analyze["engine"] = new_analyze_engine
        self.analyze["algo"] = analyze_algo_var.get()
        self.analyze["params"] = analyze_params
        self.time_limit = max(0.1, min(30, time_var.get()))

        # Restart analysis if it was running
        if self.analyze["enabled"]:
            self._start_analysis()

    def _open_params_dialog(self, parent, algo_name, params_dict):
        """Open a modal sub-dialog to edit search parameters for a specific side.

        Args:
            parent: The parent tk window (the settings dialog).
            algo_name: The currently selected algorithm name.
            params_dict: Mutable dict of param_name -> value_string.
                         Modified in-place if OK is clicked.
        """
        import tkinter as tk
        from tkinter import ttk

        sub = tk.Toplevel(parent)
        sub.title(f"Search Parameters ({algo_name})")
        sub.resizable(False, False)
        sub.grab_set()
        sub.attributes("-topmost", True)

        # Build options for this specific algorithm
        opts = self._algo_options.get(algo_name, [])

        if not opts:
            ttk.Label(sub, text="No parameters available.").grid(
                row=0, column=0, padx=20, pady=20
            )
            ttk.Button(sub, text="OK", command=sub.destroy, width=10).grid(
                row=1, column=0, pady=10
            )
            sub.update_idletasks()
            sw, sh = sub.winfo_screenwidth(), sub.winfo_screenheight()
            dw, dh = sub.winfo_width(), sub.winfo_height()
            sub.geometry(f"+{(sw - dw) // 2}+{(sh - dh) // 2}")
            sub.wait_window()
            return

        sp_vars = {}
        sp_meta = {}

        # Separate by type: checks first, then others
        check_opts = [o for o in opts if o["type"] == "check"]
        other_opts = [o for o in opts if o["type"] != "check"]

        content_frame = ttk.Frame(sub, padding=10)
        content_frame.grid(row=0, column=0, sticky="nsew")

        # Checkboxes -- two columns
        for i, opt in enumerate(check_opts):
            name = opt["name"]
            current = params_dict.get(name, opt.get("default", "false"))
            var = tk.BooleanVar(value=(str(current).lower() == "true"))
            sp_vars[name] = var
            sp_meta[name] = opt
            r, c = divmod(i, 2)
            ttk.Checkbutton(content_frame, text=name, variable=var).grid(
                row=r, column=c, sticky="w", padx=8, pady=1
            )

        # Other option types below checkboxes
        row_start = (len(check_opts) + 1) // 2
        for j, opt in enumerate(other_opts):
            name = opt["name"]
            current = params_dict.get(name, opt.get("default", ""))
            sp_meta[name] = opt
            r = row_start + j

            if opt["type"] == "spin":
                lo = int(opt.get("min", 0))
                hi = int(opt.get("max", 9999))
                try:
                    val = int(current)
                except (ValueError, TypeError):
                    val = int(opt.get("default", 0))
                var = tk.IntVar(value=val)
                sp_vars[name] = var
                sub_f = ttk.Frame(content_frame)
                sub_f.grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=1)
                ttk.Label(sub_f, text=f"{name}:").pack(side="left")
                ttk.Spinbox(sub_f, from_=lo, to=hi, textvariable=var, width=6).pack(
                    side="left", padx=(4, 0)
                )

            elif opt["type"] == "combo":
                choices = opt.get("vars", [])
                var = tk.StringVar(value=current)
                sp_vars[name] = var
                sub_f = ttk.Frame(content_frame)
                sub_f.grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=1)
                ttk.Label(sub_f, text=f"{name}:").pack(side="left")
                ttk.Combobox(
                    sub_f,
                    textvariable=var,
                    values=choices,
                    state="readonly",
                    width=max(8, max((len(v) for v in choices), default=8)),
                ).pack(side="left", padx=(4, 0))

            elif opt["type"] == "string":
                var = tk.StringVar(value=current)
                sp_vars[name] = var
                sub_f = ttk.Frame(content_frame)
                sub_f.grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=1)
                ttk.Label(sub_f, text=f"{name}:").pack(side="left")
                ttk.Entry(sub_f, textvariable=var, width=12).pack(
                    side="left", padx=(4, 0)
                )

        # OK / Cancel
        applied = [False]

        def _on_ok():
            applied[0] = True
            sub.destroy()

        def _on_cancel():
            sub.destroy()

        btn_frame = ttk.Frame(sub)
        btn_frame.grid(row=1, column=0, pady=10)
        ttk.Button(btn_frame, text="OK", command=_on_ok, width=10).grid(
            row=0, column=0, padx=8
        )
        ttk.Button(btn_frame, text="Cancel", command=_on_cancel, width=10).grid(
            row=0, column=1, padx=8
        )

        sub.bind("<Return>", lambda e: _on_ok())
        sub.bind("<Escape>", lambda e: _on_cancel())

        sub.update_idletasks()
        sw, sh = sub.winfo_screenwidth(), sub.winfo_screenheight()
        dw, dh = sub.winfo_width(), sub.winfo_height()
        sub.geometry(f"+{(sw - dw) // 2}+{(sh - dh) // 2}")

        sub.wait_window()

        if not applied[0]:
            return

        # Write back into params_dict
        for name, var in sp_vars.items():
            opt = sp_meta[name]
            if opt["type"] == "check":
                params_dict[name] = "true" if var.get() else "false"
            elif opt["type"] == "spin":
                lo = int(opt.get("min", 0))
                hi = int(opt.get("max", 9999))
                params_dict[name] = str(max(lo, min(hi, var.get())))
            else:
                params_dict[name] = str(var.get())


def main():
    parser = argparse.ArgumentParser(description="UBGI GUI")
    parser.add_argument(
        "--game",
        default="minichess",
        help="Game type: minichess, minishogi, gomoku, kohaku_shogi, kohaku_chess (default: minichess)",
    )
    args = parser.parse_args()

    app = GameApp(game_name=args.game)
    app.run()


if __name__ == "__main__":
    main()
