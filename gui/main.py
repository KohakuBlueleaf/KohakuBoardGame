"""MiniChess GUI -- entry point and game loop."""

import time

import pygame

try:
    from gui.config import *
    from gui.game_engine import MiniChessState, format_move
    from gui.board_renderer import BoardRenderer
    from gui.ui_panels import SidePanel
    from gui.uci_client import UCIEngine, discover_uci_engines
except ImportError:
    from config import *
    from game_engine import MiniChessState, format_move
    from board_renderer import BoardRenderer
    from ui_panels import SidePanel
    from uci_client import UCIEngine, discover_uci_engines


def _sync_current_player(state):
    """Bridge .player to .current_player for the renderer and panel."""
    state.current_player = state.player
    return state


class GameApp:
    """Main application class."""

    def __init__(self):
        pygame.init()
        pygame.display.set_caption("MiniChess")

        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()

        self.board_renderer = BoardRenderer(self.screen)
        self.side_panel = SidePanel(self.screen)

        self.game_state = MiniChessState.initial()
        _sync_current_player(self.game_state)

        # Mode / settings
        self.mode = "human_vs_ai"
        self.human_player = 0
        self.time_limit = DEFAULT_TIMEOUT
        self.white_algorithm = DEFAULT_ALGORITHM
        self.black_algorithm = DEFAULT_ALGORITHM
        self.white_max_depth = DEFAULT_MAX_DEPTH
        self.black_max_depth = DEFAULT_MAX_DEPTH

        # search_params: {option_name: current_value_string}
        # Populated from engine options during first engine creation.
        self.search_params = {}
        # Engine option definitions (list of dicts from UCIEngine.options)
        self._engine_options = []
        # Algorithm list read from engine's combo option
        self._engine_algorithms = list(ALGORITHMS_FALLBACK)

        self.white_engine = None
        self.black_engine = None

        self._available_engines = discover_uci_engines(BUILD_DIR)
        self._auto_select_engine()
        self._probe_engine_options()

        # Selection / interaction
        self.selected_piece = None
        self.legal_moves_for_selected = []
        self.last_move = None

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
        self._analyzing = False
        self.analyze_algorithm = DEFAULT_ALGORITHM
        self._undo_stack = []

        # AI vs AI pacing
        self._last_ai_time = 0.0
        self._paused = False

        self._running = True

        if self.mode == "ai_vs_ai" or (
            self.mode == "human_vs_ai" and self.game_state.player != self.human_player
        ):
            self._trigger_ai_if_needed()

    # ------------------------------------------------------------------
    # Engine auto-selection
    # ------------------------------------------------------------------

    def _auto_select_engine(self):
        """Pick the first available UCI engine for Black."""
        if self._available_engines:
            self.black_engine = self._available_engines[0][1]

    def _probe_engine_options(self):
        """Launch a temporary engine to read its UCI options, then quit it.

        Populates self._engine_options, self._engine_algorithms, and
        self.search_params (with defaults) from the engine's option lines.
        """
        exe_path = (
            self.white_engine
            or self.black_engine
            or (self._available_engines[0][1] if self._available_engines else None)
        )
        if exe_path is None:
            return
        try:
            probe = UCIEngine(exe_path)
            self._engine_options = list(probe.options)
            probe.quit()
        except RuntimeError:
            return

        # Extract algorithm list from the combo option named "Algorithm"
        for opt in self._engine_options:
            if opt["name"] == "Algorithm" and opt["type"] == "combo":
                self._engine_algorithms = list(opt.get("vars", ALGORITHMS_FALLBACK))
                if not self._engine_algorithms:
                    self._engine_algorithms = list(ALGORITHMS_FALLBACK)
                # Use the engine's default algorithm
                if opt.get("default") in self._engine_algorithms:
                    self.white_algorithm = opt["default"]
                    self.black_algorithm = opt["default"]
                    self.analyze_algorithm = opt["default"]
                break

        # Populate search_params from engine defaults (skip Algorithm)
        self.search_params = {}
        for opt in self._engine_options:
            if opt["name"] == "Algorithm":
                continue
            self.search_params[opt["name"]] = opt.get("default", "")

    def _get_or_create_uci_engine(self, exe_path, attr_name):
        existing = getattr(self, attr_name, None)
        if existing is not None and existing.is_alive():
            return existing
        algo = (
            self.white_algorithm
            if attr_name == "white_uci_engine"
            else self.black_algorithm
        )
        try:
            engine = UCIEngine(exe_path)
            engine.set_option("Algorithm", algo)
            self._send_search_params(engine)
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

    def _send_search_params(self, engine):
        """Send all search parameter options to a UCI engine."""
        for name, value in self.search_params.items():
            engine.set_option(name, str(value))

    # ------------------------------------------------------------------
    # Analyze mode
    # ------------------------------------------------------------------

    def _get_or_create_analyze_engine(self):
        if self._analyze_engine is not None and self._analyze_engine.is_alive():
            return self._analyze_engine
        # Use whichever engine path is available
        exe_path = (
            self.white_engine
            or self.black_engine
            or (self._available_engines[0][1] if self._available_engines else None)
        )
        if exe_path is None:
            return None
        try:
            engine = UCIEngine(exe_path)
            engine.set_option("Algorithm", self.analyze_algorithm)
            self._send_search_params(engine)
            self._analyze_engine = engine
            return engine
        except RuntimeError:
            return None

    def _start_analysis(self):
        if self.game_result is not None:
            return
        engine = self._get_or_create_analyze_engine()
        if engine is None:
            return
        self._stop_analysis()
        if self.uci_moves:
            engine.set_position(moves=list(self.uci_moves))
        else:
            engine.set_position()
        engine.go(
            infinite=True,
            info_callback=self._on_analyze_info,
            done_callback=self._on_analyze_done,
        )
        self._analyzing = True

    def _stop_analysis(self):
        if self._analyzing and self._analyze_engine is not None:
            try:
                self._analyze_engine.stop()
            except Exception:
                pass
            self._analyzing = False

    def _on_analyze_info(self, info_dict):
        """Normalize score to white's perspective for the score bar."""
        if "score_cp" in info_dict and self.game_state.player == 1:
            info_dict["score_cp"] = -info_dict["score_cp"]
        self.search_info = info_dict

    def _on_analyze_done(self, bestmove_str):
        self._analyzing = False

    # ------------------------------------------------------------------
    # Pause / Undo
    # ------------------------------------------------------------------

    def _toggle_pause(self):
        if self.mode == "ai_vs_ai":
            self._paused = not self._paused
        elif self.mode == "analyze":
            if self._analyzing:
                self._stop_analysis()
            else:
                self._start_analysis()

    def undo_move(self):
        if not self._undo_stack:
            return
        if self.mode == "analyze":
            self._stop_analysis()
        snap = self._undo_stack.pop()
        self.game_state = snap["game_state"]
        _sync_current_player(self.game_state)
        self.uci_moves = snap["uci_moves"]
        self.move_history = snap["move_history"]
        self.score_history = snap["score_history"]
        self.last_move = snap["last_move"]
        self.game_result = None
        self.search_info = {}
        self.selected_piece = None
        self.legal_moves_for_selected = []
        if self.mode == "analyze":
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
                self.clock.tick(FPS)
        finally:
            self._shutdown_uci_engines()
            pygame.quit()

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
                    self.selected_piece = None
                    self.legal_moves_for_selected = []

            elif event.type == pygame.MOUSEWHEEL:
                self.side_panel.set_scroll(-event.y)

            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event.key)

    def _handle_left_click(self, pos):
        x, y = pos
        board_pos = self.board_renderer.screen_to_board(x, y)
        if board_pos is not None:
            if self._is_human_turn():
                self.handle_board_click(board_pos[0], board_pos[1])
            return

        action = self.side_panel.handle_click(x, y, mode=self.mode)
        if action == "new_game":
            self.new_game()
        elif action == "settings":
            self.open_settings()
        elif action == "undo":
            self.undo_move()
        elif action == "pause":
            self._toggle_pause()

    def _handle_keydown(self, key):
        if key == pygame.K_n:
            self.new_game()
        elif key == pygame.K_s:
            self.open_settings()
        elif key == pygame.K_ESCAPE:
            if self.selected_piece is not None:
                self.selected_piece = None
                self.legal_moves_for_selected = []
            else:
                self._running = False
        elif key == pygame.K_SPACE:
            self._toggle_pause()
        elif key == pygame.K_z:
            self.undo_move()

    # ------------------------------------------------------------------
    # Board interaction
    # ------------------------------------------------------------------

    def _is_human_turn(self):
        if self.game_result is not None or self.ai_thinking:
            return False
        if self.mode == "ai_vs_ai":
            return False
        if self.mode == "analyze":
            return True
        return self.game_state.player == self.human_player

    def handle_board_click(self, row, col):
        player = self.game_state.player
        clicked_piece = self.game_state.board[player][row][col]

        if self.selected_piece is None:
            if clicked_piece != EMPTY:
                self._select_piece(row, col)
        else:
            target_move = self._find_legal_move(row, col)
            if target_move is not None:
                self.execute_move(target_move)
            elif clicked_piece != EMPTY and (row, col) != self.selected_piece:
                self._select_piece(row, col)
            else:
                self.selected_piece = None
                self.legal_moves_for_selected = []

    def _select_piece(self, row, col):
        self.selected_piece = (row, col)
        self.legal_moves_for_selected = [
            m for m in self.game_state.legal_actions if m[0] == (row, col)
        ]

    def _find_legal_move(self, dest_row, dest_col):
        for move in self.legal_moves_for_selected:
            if move[1] == (dest_row, dest_col):
                return move
        return None

    # ------------------------------------------------------------------
    # Move execution
    # ------------------------------------------------------------------

    def execute_move(self, move):
        if self.mode == "analyze":
            self._stop_analysis()

        if self.mode in ("analyze", "ai_vs_ai"):
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
        move_str = f"{step}. {prefix}: {format_move(move)}"

        new_state = self.game_state.next_state(move)
        _sync_current_player(new_state)
        self.game_state = new_state

        self.move_history.append(move_str)
        self.last_move = move
        self.uci_moves.append(UCIEngine.move_to_uci(move))
        self.score_history.append((mover, self.search_info.get("score_cp")))

        self.side_panel._scroll_offset = max(0, len(self.move_history))
        self.selected_piece = None
        self.legal_moves_for_selected = []

        result, winner = self.game_state.check_game_over()
        if result == "win":
            self.game_result = "white_wins" if winner == 0 else "black_wins"
            return
        if result == "draw":
            self.game_result = "draw"
            return

        if self.mode == "analyze":
            self.search_info = {}
            self._start_analysis()
        else:
            self._trigger_ai_if_needed()

    def _trigger_ai_if_needed(self):
        if self.game_result is not None or self.ai_thinking or self._paused:
            return
        if self.mode == "human_vs_ai" and self.game_state.player == self.human_player:
            return

        player = self.game_state.player
        engine = self.white_engine if player == 0 else self.black_engine

        if engine is not None:
            self.trigger_ai_move()

    # ------------------------------------------------------------------
    # AI management
    # ------------------------------------------------------------------

    def trigger_ai_move(self):
        player = self.game_state.player
        engine_path = self.white_engine if player == 0 else self.black_engine

        if engine_path is None:
            return

        self.ai_thinking = True
        self.ai_result = {"move": None, "depth": 0, "ready": False}
        self.search_info = {}

        attr = "white_uci_engine" if player == 0 else "black_uci_engine"
        uci = self._get_or_create_uci_engine(engine_path, attr)

        if uci is None:
            # Engine failed to start
            self.ai_result = {"move": None, "depth": 0, "ready": True}
            return

        if self.uci_moves:
            uci.set_position(moves=list(self.uci_moves))
        else:
            uci.set_position()

        max_depth = self.white_max_depth if player == 0 else self.black_max_depth
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

    def _on_uci_info(self, info_dict):
        """Normalize score to white's perspective for the score bar."""
        if "score_cp" in info_dict and self.game_state.player == 1:
            info_dict["score_cp"] = -info_dict["score_cp"]
        self.search_info = info_dict

    def _on_uci_bestmove(self, bestmove_str):
        if bestmove_str is None:
            self.ai_result = {"move": None, "depth": 0, "ready": True}
            return

        move = UCIEngine.uci_to_move(bestmove_str)
        depth = self.search_info.get("depth", 0)
        self.ai_result = {"move": move, "depth": depth, "ready": True}

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def update(self):
        if self.ai_result.get("ready"):
            move = self.ai_result["move"]
            depth = self.ai_result["depth"]
            self.ai_result = {"move": None, "depth": 0, "ready": False}
            self.ai_thinking = False

            if move is not None and move in self.game_state.legal_actions:
                self.ai_depth = depth
                self.execute_move(move)
                self._last_ai_time = time.time()
            else:
                loser = self.game_state.player
                self.game_result = "white_wins" if loser == 0 else "black_wins"
            return

        # AI vs AI auto-trigger
        if (
            self.mode == "ai_vs_ai"
            and self.game_result is None
            and not self.ai_thinking
            and not self._paused
        ):
            elapsed = time.time() - self._last_ai_time
            if elapsed >= AI_VS_AI_DELAY:
                self._trigger_ai_if_needed()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self):
        self.screen.fill(COLOR_BG)

        self.board_renderer.draw(
            self.game_state,
            selected=self.selected_piece,
            legal_moves=self.legal_moves_for_selected,
            last_move=self.last_move,
        )

        self.side_panel.draw(
            self.game_state,
            ai_thinking=self.ai_thinking,
            game_result=self.game_result,
            ai_depth=self.ai_depth,
            mode=self.mode,
            time_limit=self.time_limit,
            search_info=self.search_info,
            paused=self._paused or (self.mode == "analyze" and not self._analyzing),
        )

        self.side_panel.draw_bottom(
            score_cp=self.search_info.get("score_cp"),
            score_history=self.score_history,
            move_history=self.move_history,
        )

        pygame.display.flip()

    # ------------------------------------------------------------------
    # New game / settings
    # ------------------------------------------------------------------

    def new_game(self):
        self.game_state = MiniChessState.initial()
        _sync_current_player(self.game_state)

        self.selected_piece = None
        self.legal_moves_for_selected = []
        self.last_move = None
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
        self._stop_analysis()

        for attr in ("white_uci_engine", "black_uci_engine"):
            engine = getattr(self, attr, None)
            if engine is not None and engine.is_alive():
                try:
                    engine.new_game()
                except Exception:
                    pass

        if self.mode == "analyze":
            self._start_analysis()
        else:
            self._trigger_ai_if_needed()

    def open_settings(self):
        import tkinter as tk
        from tkinter import ttk

        self._available_engines = discover_uci_engines(BUILD_DIR)

        engine_names = ["Human"] + [name for name, _path in self._available_engines]
        engine_paths = [None] + [path for _name, path in self._available_engines]

        algo_list = self._engine_algorithms or ALGORITHMS_FALLBACK

        def _engine_index(exe_path):
            if exe_path is None:
                return 0
            for idx, path in enumerate(engine_paths):
                if path == exe_path:
                    return idx
            return 0

        first_engine_name = engine_names[1] if len(engine_names) > 1 else "Human"

        root = tk.Tk()
        root.withdraw()

        dialog = tk.Toplevel(root)
        dialog.title("Settings")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.attributes("-topmost", True)

        pad = {"padx": 10, "pady": 4}

        mode_var = tk.StringVar(value=self.mode)
        human_var = tk.IntVar(value=self.human_player)
        white_var = tk.StringVar(value=engine_names[_engine_index(self.white_engine)])
        black_var = tk.StringVar(value=engine_names[_engine_index(self.black_engine)])
        time_var = tk.IntVar(value=self.time_limit)
        w_algo_var = tk.StringVar(value=self.white_algorithm)
        b_algo_var = tk.StringVar(value=self.black_algorithm)
        w_depth_var = tk.IntVar(value=self.white_max_depth)
        b_depth_var = tk.IntVar(value=self.black_max_depth)
        analyze_algo_var = tk.StringVar(value=self.analyze_algorithm)

        applied = [False]

        mode_frame = ttk.LabelFrame(dialog, text="Mode")
        mode_frame.grid(row=0, column=0, columnspan=2, sticky="ew", **pad)

        rb_hva = ttk.Radiobutton(
            mode_frame,
            text="Human vs AI",
            variable=mode_var,
            value="human_vs_ai",
            command=lambda: _on_mode_change(),
        )
        rb_ava = ttk.Radiobutton(
            mode_frame,
            text="AI vs AI",
            variable=mode_var,
            value="ai_vs_ai",
            command=lambda: _on_mode_change(),
        )
        rb_analyze = ttk.Radiobutton(
            mode_frame,
            text="Analyze",
            variable=mode_var,
            value="analyze",
            command=lambda: _on_mode_change(),
        )
        rb_hva.grid(row=0, column=0, sticky="w", padx=8, pady=2)
        rb_ava.grid(row=0, column=1, sticky="w", padx=8, pady=2)
        rb_analyze.grid(row=0, column=2, sticky="w", padx=8, pady=2)

        human_frame = ttk.LabelFrame(dialog, text="Human plays as")
        human_frame.grid(row=1, column=0, columnspan=2, sticky="ew", **pad)

        rb_white = ttk.Radiobutton(
            human_frame, text="White", variable=human_var, value=0
        )
        rb_black = ttk.Radiobutton(
            human_frame, text="Black", variable=human_var, value=1
        )
        rb_white.grid(row=0, column=0, sticky="w", padx=8, pady=2)
        rb_black.grid(row=0, column=1, sticky="w", padx=8, pady=2)
        human_radios = [rb_white, rb_black]

        white_frame = ttk.LabelFrame(dialog, text="White")
        white_frame.grid(row=2, column=0, columnspan=2, sticky="ew", **pad)

        ttk.Label(white_frame, text="Engine:").grid(
            row=0, column=0, sticky="w", padx=4, pady=2
        )
        white_combo = ttk.Combobox(
            white_frame,
            textvariable=white_var,
            values=engine_names,
            state="readonly",
            width=22,
        )
        white_combo.grid(row=0, column=1, columnspan=3, sticky="ew", padx=4, pady=2)

        ttk.Label(white_frame, text="Algorithm:").grid(
            row=1, column=0, sticky="w", padx=4, pady=2
        )
        w_algo_combo = ttk.Combobox(
            white_frame,
            textvariable=w_algo_var,
            values=algo_list,
            state="readonly",
            width=10,
        )
        w_algo_combo.grid(row=1, column=1, sticky="w", padx=4, pady=2)

        ttk.Label(white_frame, text="Depth:").grid(
            row=1, column=2, sticky="w", padx=4, pady=2
        )
        w_depth_spin = ttk.Spinbox(
            white_frame, from_=0, to=20, textvariable=w_depth_var, width=4
        )
        w_depth_spin.grid(row=1, column=3, sticky="w", padx=4, pady=2)

        black_frame = ttk.LabelFrame(dialog, text="Black")
        black_frame.grid(row=3, column=0, columnspan=2, sticky="ew", **pad)

        ttk.Label(black_frame, text="Engine:").grid(
            row=0, column=0, sticky="w", padx=4, pady=2
        )
        black_combo = ttk.Combobox(
            black_frame,
            textvariable=black_var,
            values=engine_names,
            state="readonly",
            width=22,
        )
        black_combo.grid(row=0, column=1, columnspan=3, sticky="ew", padx=4, pady=2)

        ttk.Label(black_frame, text="Algorithm:").grid(
            row=1, column=0, sticky="w", padx=4, pady=2
        )
        b_algo_combo = ttk.Combobox(
            black_frame,
            textvariable=b_algo_var,
            values=algo_list,
            state="readonly",
            width=10,
        )
        b_algo_combo.grid(row=1, column=1, sticky="w", padx=4, pady=2)

        ttk.Label(black_frame, text="Depth:").grid(
            row=1, column=2, sticky="w", padx=4, pady=2
        )
        b_depth_spin = ttk.Spinbox(
            black_frame, from_=0, to=20, textvariable=b_depth_var, width=4
        )
        b_depth_spin.grid(row=1, column=3, sticky="w", padx=4, pady=2)

        w_ai_widgets = [w_algo_combo, w_depth_spin]
        b_ai_widgets = [b_algo_combo, b_depth_spin]

        def _update_side_widgets():
            w_is_engine = white_var.get() != "Human"
            b_is_engine = black_var.get() != "Human"
            for w in w_ai_widgets:
                w.configure(state="readonly" if w_is_engine else "disabled")
            w_depth_spin.configure(state="normal" if w_is_engine else "disabled")
            for w in b_ai_widgets:
                w.configure(state="readonly" if b_is_engine else "disabled")
            b_depth_spin.configure(state="normal" if b_is_engine else "disabled")

        white_combo.bind("<<ComboboxSelected>>", lambda e: _update_side_widgets())
        black_combo.bind("<<ComboboxSelected>>", lambda e: _update_side_widgets())

        def _on_mode_change():
            mode = mode_var.get()
            is_human_choice = mode == "human_vs_ai"
            state = "!disabled" if is_human_choice else "disabled"
            for rb in human_radios:
                rb.state([state])
            if mode == "ai_vs_ai":
                if white_var.get() == "Human":
                    white_var.set(first_engine_name)
                if black_var.get() == "Human":
                    black_var.set(first_engine_name)
            _update_side_widgets()

        _on_mode_change()
        _update_side_widgets()

        ttk.Label(dialog, text="Time limit (s):").grid(
            row=4, column=0, sticky="w", **pad
        )
        time_spin = ttk.Spinbox(dialog, from_=1, to=30, textvariable=time_var, width=5)
        time_spin.grid(row=4, column=1, sticky="w", **pad)

        analyze_frame = ttk.LabelFrame(dialog, text="Analyze Engine")
        analyze_frame.grid(row=5, column=0, columnspan=2, sticky="ew", **pad)

        ttk.Label(analyze_frame, text="Algorithm:").grid(
            row=0, column=0, sticky="w", padx=4, pady=2
        )
        analyze_algo_combo = ttk.Combobox(
            analyze_frame,
            textvariable=analyze_algo_var,
            values=algo_list,
            state="readonly",
            width=10,
        )
        analyze_algo_combo.grid(row=0, column=1, sticky="w", padx=4, pady=2)

        # -- Search Parameters (built dynamically from engine options) ----------
        # Separate options into search params and global params.
        # Skip "Algorithm" (handled above). Show "Hash" in a "Global" section.
        search_opts = []
        global_opts = []
        for opt in self._engine_options:
            if opt["name"] == "Algorithm":
                continue
            if opt["name"] == "Hash":
                global_opts.append(opt)
            else:
                search_opts.append(opt)

        sp_vars = {}  # {option_name: tk variable}
        sp_meta = {}  # {option_name: opt dict} for reading back values

        if search_opts:
            search_frame = ttk.LabelFrame(dialog, text="Search Parameters")
            search_frame.grid(row=6, column=0, columnspan=2, sticky="ew", **pad)

            # Separate by type for layout: checks first, then others
            check_opts = [o for o in search_opts if o["type"] == "check"]
            other_opts = [o for o in search_opts if o["type"] != "check"]

            # Checkboxes -- two columns
            for i, opt in enumerate(check_opts):
                name = opt["name"]
                current = self.search_params.get(name, opt.get("default", "false"))
                var = tk.BooleanVar(value=(current.lower() == "true"))
                sp_vars[name] = var
                sp_meta[name] = opt
                r, c = divmod(i, 2)
                ttk.Checkbutton(search_frame, text=name, variable=var).grid(
                    row=r, column=c, sticky="w", padx=8, pady=1
                )

            # Other option types -- two columns below checkboxes
            row_start = (len(check_opts) + 1) // 2
            for j, opt in enumerate(other_opts):
                name = opt["name"]
                current = self.search_params.get(name, opt.get("default", ""))
                sp_meta[name] = opt
                r, c = divmod(j, 2)
                r += row_start

                if opt["type"] == "spin":
                    lo = int(opt.get("min", 0))
                    hi = int(opt.get("max", 9999))
                    try:
                        val = int(current)
                    except (ValueError, TypeError):
                        val = int(opt.get("default", 0))
                    var = tk.IntVar(value=val)
                    sp_vars[name] = var
                    sub = ttk.Frame(search_frame)
                    sub.grid(row=r, column=c, sticky="w", padx=8, pady=1)
                    ttk.Label(sub, text=f"{name}:").pack(side="left")
                    ttk.Spinbox(
                        sub, from_=lo, to=hi, textvariable=var, width=4
                    ).pack(side="left", padx=(4, 0))

                elif opt["type"] == "combo":
                    choices = opt.get("vars", [])
                    var = tk.StringVar(value=current)
                    sp_vars[name] = var
                    sub = ttk.Frame(search_frame)
                    sub.grid(row=r, column=c, sticky="w", padx=8, pady=1)
                    ttk.Label(sub, text=f"{name}:").pack(side="left")
                    ttk.Combobox(
                        sub,
                        textvariable=var,
                        values=choices,
                        state="readonly",
                        width=max(8, max((len(v) for v in choices), default=8)),
                    ).pack(side="left", padx=(4, 0))

                elif opt["type"] == "string":
                    var = tk.StringVar(value=current)
                    sp_vars[name] = var
                    sub = ttk.Frame(search_frame)
                    sub.grid(row=r, column=c, sticky="w", padx=8, pady=1)
                    ttk.Label(sub, text=f"{name}:").pack(side="left")
                    ttk.Entry(sub, textvariable=var, width=12).pack(
                        side="left", padx=(4, 0)
                    )

        # -- Global Parameters (e.g. Hash) ------------------------------------
        global_vars = {}
        if global_opts:
            global_frame = ttk.LabelFrame(dialog, text="Global")
            global_frame.grid(row=7, column=0, columnspan=2, sticky="ew", **pad)

            for i, opt in enumerate(global_opts):
                name = opt["name"]
                current = self.search_params.get(name, opt.get("default", ""))
                sp_meta[name] = opt

                if opt["type"] == "spin":
                    lo = int(opt.get("min", 0))
                    hi = int(opt.get("max", 9999))
                    try:
                        val = int(current)
                    except (ValueError, TypeError):
                        val = int(opt.get("default", 0))
                    var = tk.IntVar(value=val)
                    global_vars[name] = var
                    sub = ttk.Frame(global_frame)
                    sub.grid(row=i, column=0, sticky="w", padx=8, pady=1)
                    ttk.Label(sub, text=f"{name}:").pack(side="left")
                    ttk.Spinbox(
                        sub, from_=lo, to=hi, textvariable=var, width=4
                    ).pack(side="left", padx=(4, 0))

                elif opt["type"] == "check":
                    var = tk.BooleanVar(value=(current.lower() == "true"))
                    global_vars[name] = var
                    ttk.Checkbutton(
                        global_frame, text=name, variable=var
                    ).grid(row=i, column=0, sticky="w", padx=8, pady=1)

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=8, column=0, columnspan=2, pady=10)

        def _on_ok():
            applied[0] = True
            dialog.destroy()

        def _on_cancel():
            dialog.destroy()

        ttk.Button(btn_frame, text="OK", command=_on_ok, width=10).grid(
            row=0, column=0, padx=8
        )
        ttk.Button(btn_frame, text="Cancel", command=_on_cancel, width=10).grid(
            row=0, column=1, padx=8
        )

        dialog.bind("<Return>", lambda e: _on_ok())
        dialog.bind("<Escape>", lambda e: _on_cancel())

        dialog.update_idletasks()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        sw, sh = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
        dialog.geometry(f"+{(sw - dw) // 2}+{(sh - dh) // 2}")

        dialog.wait_window()
        root.destroy()

        if not applied[0]:
            return

        new_mode = mode_var.get()
        new_human = human_var.get()
        new_time = max(1, min(30, time_var.get()))
        new_w_algo = w_algo_var.get()
        new_b_algo = b_algo_var.get()
        new_w_depth = max(0, min(20, w_depth_var.get()))
        new_b_depth = max(0, min(20, b_depth_var.get()))
        new_analyze_algo = analyze_algo_var.get()

        # Collect search params as strings (the UCI wire format)
        new_search_params = {}
        for name, var in sp_vars.items():
            opt = sp_meta[name]
            if opt["type"] == "check":
                new_search_params[name] = "true" if var.get() else "false"
            elif opt["type"] == "spin":
                lo = int(opt.get("min", 0))
                hi = int(opt.get("max", 9999))
                new_search_params[name] = str(max(lo, min(hi, var.get())))
            else:
                new_search_params[name] = str(var.get())

        # Also collect global params (Hash etc.) into search_params so they
        # get sent via _send_search_params.  Store under a separate key
        # only for the change-detection below.
        for name, var in global_vars.items():
            opt = sp_meta[name]
            if opt["type"] == "spin":
                lo = int(opt.get("min", 0))
                hi = int(opt.get("max", 9999))
                new_search_params[name] = str(max(lo, min(hi, var.get())))
            elif opt["type"] == "check":
                new_search_params[name] = "true" if var.get() else "false"
            else:
                new_search_params[name] = str(var.get())

        search_params_changed = new_search_params != self.search_params

        w_name = white_var.get()
        b_name = black_var.get()
        w_idx = engine_names.index(w_name) if w_name in engine_names else 0
        b_idx = engine_names.index(b_name) if b_name in engine_names else 0
        new_white_engine = engine_paths[w_idx]
        new_black_engine = engine_paths[b_idx]

        if new_mode == "ai_vs_ai" and (
            new_white_engine is None or new_black_engine is None
        ):
            new_mode = "human_vs_ai"
            if new_white_engine is None and new_black_engine is not None:
                new_human = 0
            elif new_black_engine is None and new_white_engine is not None:
                new_human = 1

        if new_mode == "human_vs_ai":
            ai_side = 1 - new_human
            ai_engine = new_white_engine if ai_side == 0 else new_black_engine
            if ai_engine is None and self._available_engines:
                fallback = self._available_engines[0][1]
                if ai_side == 0:
                    new_white_engine = fallback
                else:
                    new_black_engine = fallback

        if search_params_changed:
            self._shutdown_uci_engines()
        else:
            if new_w_algo != self.white_algorithm or new_white_engine != self.white_engine:
                self._quit_engine("white_uci_engine")
            if new_b_algo != self.black_algorithm or new_black_engine != self.black_engine:
                self._quit_engine("black_uci_engine")
            if new_analyze_algo != self.analyze_algorithm:
                self._quit_engine("_analyze_engine")

        self.mode = new_mode
        self.human_player = new_human
        self.time_limit = new_time
        self.white_algorithm = new_w_algo
        self.black_algorithm = new_b_algo
        self.white_max_depth = new_w_depth
        self.black_max_depth = new_b_depth
        self.white_engine = new_white_engine
        self.black_engine = new_black_engine
        self.analyze_algorithm = new_analyze_algo
        self.search_params = new_search_params

        self.new_game()


def main():
    app = GameApp()
    app.run()


if __name__ == "__main__":
    main()
