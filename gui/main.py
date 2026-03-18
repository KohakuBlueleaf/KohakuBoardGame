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

        # Discover engines
        self._available_engines = discover_uci_engines(BUILD_DIR)

        # Engine option definitions (list of dicts from UCIEngine.options)
        self._engine_options = []
        # Algorithm list read from engine's combo option
        self._engine_algorithms = []

        # Per-side state
        self.white = {
            "engine": None,  # path or None for human
            "algo": DEFAULT_ALGORITHM,
            "params": {},  # algo-specific search params
            "depth": 0,  # 0 = use time limit
        }
        self.black = {
            "engine": (
                self._available_engines[0][1] if self._available_engines else None
            ),
            "algo": DEFAULT_ALGORITHM,
            "params": {},
            "depth": 0,
        }
        self.analyze = {
            "enabled": False,
            "engine": None,  # auto-select first available
            "algo": DEFAULT_ALGORITHM,
            "params": {},
        }

        self.time_limit = DEFAULT_TIMEOUT

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
        self._undo_stack = []

        # AI vs AI pacing
        self._last_ai_time = 0.0
        self._paused = False

        self._running = True

        self._trigger_ai_if_needed()

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

    def _probe_engine_options(self):
        """Launch a temporary engine to read its UCI options, then quit it.

        Populates self._engine_options, self._engine_algorithms, and
        default params for each side from the engine's option lines.
        """
        exe_path = (
            self.white["engine"]
            or self.black["engine"]
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
                self._engine_algorithms = list(opt.get("vars", []))
                # Use the engine's default algorithm
                if opt.get("default") in self._engine_algorithms:
                    self.white["algo"] = opt["default"]
                    self.black["algo"] = opt["default"]
                    self.analyze["algo"] = opt["default"]
                break

        # Build default params dict (skip Algorithm and Hash-like globals)
        default_params = {}
        for opt in self._engine_options:
            if opt["name"] == "Algorithm":
                continue
            default_params[opt["name"]] = opt.get("default", "")

        # Initialize each side's params with defaults
        self.white["params"] = dict(default_params)
        self.black["params"] = dict(default_params)
        self.analyze["params"] = dict(default_params)

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
            engine = UCIEngine(side_config["engine"])
            engine.set_option("Algorithm", side_config["algo"])
            for name, value in side_config["params"].items():
                engine.set_option(name, str(value))
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
        # Use explicit analyze engine path, or fall back to any available
        exe_path = (
            self.analyze["engine"]
            or self.white["engine"]
            or self.black["engine"]
            or (self._available_engines[0][1] if self._available_engines else None)
        )
        if exe_path is None:
            return None
        try:
            engine = UCIEngine(exe_path)
            engine.set_option("Algorithm", self.analyze["algo"])
            for name, value in self.analyze["params"].items():
                engine.set_option(name, str(value))
            self._analyze_engine = engine
            return engine
        except RuntimeError:
            return None

    def _start_analysis(self):
        if self.game_result is not None:
            return
        if not self.analyze["enabled"]:
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
        elif self.analyze["enabled"]:
            if self._analyzing:
                self._stop_analysis()
            else:
                self._start_analysis()

    def undo_move(self):
        if not self._undo_stack:
            return
        if self.analyze["enabled"]:
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

        action = self.side_panel.handle_click(
            x, y, mode=self.mode, analyze_enabled=self.analyze["enabled"]
        )
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
        if self.game_result is not None:
            return False
        if self.ai_thinking:
            return False
        player = self.game_state.player
        side = self.white if player == 0 else self.black
        return side["engine"] is None

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
        if self.analyze["enabled"]:
            self._stop_analysis()

        if self.analyze["enabled"] or self.mode == "ai_vs_ai":
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

        if self.analyze["enabled"] and self._is_human_turn():
            self.search_info = {}
            self._start_analysis()
        else:
            self._trigger_ai_if_needed()

    def _trigger_ai_if_needed(self):
        if self.game_result is not None or self.ai_thinking or self._paused:
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

        pv = self.search_info.get("pv") if self.analyze["enabled"] or self.ai_thinking else None
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
            paused=self._paused or (self.analyze["enabled"] and not self._analyzing),
            analyze_enabled=self.analyze["enabled"],
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

        if self.analyze["enabled"]:
            self._start_analysis()
        else:
            self._trigger_ai_if_needed()

    def open_settings(self):
        import tkinter as tk
        from tkinter import ttk

        self._available_engines = discover_uci_engines(BUILD_DIR)

        engine_names = ["Human"] + [name for name, _path in self._available_engines]
        engine_paths = [None] + [path for _name, path in self._available_engines]

        algo_list = self._engine_algorithms or [DEFAULT_ALGORITHM]

        def _engine_index(exe_path):
            if exe_path is None:
                return 0
            for idx, path in enumerate(engine_paths):
                if path == exe_path:
                    return idx
            return 0

        root = tk.Tk()
        root.withdraw()

        dialog = tk.Toplevel(root)
        dialog.title("Settings")
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

        analyze_enabled_var = tk.BooleanVar(value=self.analyze["enabled"])
        analyze_engine_var = tk.StringVar(
            value=engine_names[_engine_index(self.analyze["engine"])]
        )
        analyze_algo_var = tk.StringVar(value=self.analyze["algo"])

        time_var = tk.IntVar(value=self.time_limit)

        # Mutable copies of per-side params for editing via sub-dialogs
        white_params = dict(self.white["params"])
        black_params = dict(self.black["params"])
        analyze_params = dict(self.analyze["params"])

        applied = [False]

        # ---- White frame ----
        white_frame = ttk.LabelFrame(dialog, text="White")
        white_frame.grid(row=0, column=0, columnspan=2, sticky="ew", **pad)

        ttk.Label(white_frame, text="Player:").grid(
            row=0, column=0, sticky="w", padx=4, pady=2
        )
        white_combo = ttk.Combobox(
            white_frame,
            textvariable=white_engine_var,
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

        w_params_btn = ttk.Button(
            white_frame,
            text="Params...",
            command=lambda: self._open_params_dialog(
                dialog, w_algo_var.get(), white_params
            ),
            width=8,
        )
        w_params_btn.grid(row=1, column=2, sticky="w", padx=4, pady=2)

        ttk.Label(white_frame, text="Depth:").grid(
            row=1, column=3, sticky="w", padx=4, pady=2
        )
        w_depth_spin = ttk.Spinbox(
            white_frame, from_=0, to=20, textvariable=w_depth_var, width=4
        )
        w_depth_spin.grid(row=1, column=4, sticky="w", padx=4, pady=2)

        # ---- Black frame ----
        black_frame = ttk.LabelFrame(dialog, text="Black")
        black_frame.grid(row=1, column=0, columnspan=2, sticky="ew", **pad)

        ttk.Label(black_frame, text="Player:").grid(
            row=0, column=0, sticky="w", padx=4, pady=2
        )
        black_combo = ttk.Combobox(
            black_frame,
            textvariable=black_engine_var,
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

        b_params_btn = ttk.Button(
            black_frame,
            text="Params...",
            command=lambda: self._open_params_dialog(
                dialog, b_algo_var.get(), black_params
            ),
            width=8,
        )
        b_params_btn.grid(row=1, column=2, sticky="w", padx=4, pady=2)

        ttk.Label(black_frame, text="Depth:").grid(
            row=1, column=3, sticky="w", padx=4, pady=2
        )
        b_depth_spin = ttk.Spinbox(
            black_frame, from_=0, to=20, textvariable=b_depth_var, width=4
        )
        b_depth_spin.grid(row=1, column=4, sticky="w", padx=4, pady=2)

        # ---- Analyze frame ----
        analyze_frame = ttk.LabelFrame(dialog, text="Analyze")
        analyze_frame.grid(row=2, column=0, columnspan=2, sticky="ew", **pad)

        analyze_check = ttk.Checkbutton(
            analyze_frame,
            text="Enable background analysis",
            variable=analyze_enabled_var,
            command=lambda: _update_analyze_widgets(),
        )
        analyze_check.grid(row=0, column=0, columnspan=5, sticky="w", padx=4, pady=2)

        ttk.Label(analyze_frame, text="Engine:").grid(
            row=1, column=0, sticky="w", padx=4, pady=2
        )
        # Analyze engine choices: only actual engines (no Human)
        analyze_engine_names = [name for name, _path in self._available_engines]
        if not analyze_engine_names:
            analyze_engine_names = ["(none)"]
        analyze_engine_combo = ttk.Combobox(
            analyze_frame,
            textvariable=analyze_engine_var,
            values=["(auto)"] + analyze_engine_names,
            state="readonly",
            width=22,
        )
        # Default to (auto) if analyze engine was None
        if self.analyze["engine"] is None:
            analyze_engine_var.set("(auto)")
        analyze_engine_combo.grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=4, pady=2
        )

        ttk.Label(analyze_frame, text="Algorithm:").grid(
            row=2, column=0, sticky="w", padx=4, pady=2
        )
        analyze_algo_combo = ttk.Combobox(
            analyze_frame,
            textvariable=analyze_algo_var,
            values=algo_list,
            state="readonly",
            width=10,
        )
        analyze_algo_combo.grid(row=2, column=1, sticky="w", padx=4, pady=2)

        a_params_btn = ttk.Button(
            analyze_frame,
            text="Params...",
            command=lambda: self._open_params_dialog(
                dialog, analyze_algo_var.get(), analyze_params
            ),
            width=8,
        )
        a_params_btn.grid(row=2, column=2, sticky="w", padx=4, pady=2)

        analyze_widgets = [analyze_engine_combo, analyze_algo_combo, a_params_btn]

        def _update_analyze_widgets():
            enabled = analyze_enabled_var.get()
            for w in analyze_widgets:
                if isinstance(w, ttk.Combobox):
                    w.configure(state="readonly" if enabled else "disabled")
                else:
                    w.configure(state="normal" if enabled else "disabled")

        _update_analyze_widgets()

        # ---- Time limit ----
        ttk.Label(dialog, text="Time limit (s):").grid(
            row=3, column=0, sticky="w", **pad
        )
        time_spin = ttk.Spinbox(dialog, from_=1, to=30, textvariable=time_var, width=5)
        time_spin.grid(row=3, column=1, sticky="w", **pad)

        # ---- Widget enable/disable based on player selection ----
        w_ai_widgets = [w_algo_combo, w_params_btn, w_depth_spin]
        b_ai_widgets = [b_algo_combo, b_params_btn, b_depth_spin]

        def _update_side_widgets():
            w_is_engine = white_engine_var.get() != "Human"
            b_is_engine = black_engine_var.get() != "Human"
            for w in w_ai_widgets:
                if isinstance(w, ttk.Combobox):
                    w.configure(state="readonly" if w_is_engine else "disabled")
                elif isinstance(w, ttk.Spinbox):
                    w.configure(state="normal" if w_is_engine else "disabled")
                else:
                    w.configure(state="normal" if w_is_engine else "disabled")
            for w in b_ai_widgets:
                if isinstance(w, ttk.Combobox):
                    w.configure(state="readonly" if b_is_engine else "disabled")
                elif isinstance(w, ttk.Spinbox):
                    w.configure(state="normal" if b_is_engine else "disabled")
                else:
                    w.configure(state="normal" if b_is_engine else "disabled")

        white_combo.bind("<<ComboboxSelected>>", lambda e: _update_side_widgets())
        black_combo.bind("<<ComboboxSelected>>", lambda e: _update_side_widgets())

        # Reset params to defaults when algorithm changes
        def _on_w_algo_change(event=None):
            new_algo = w_algo_var.get()
            # Reset white params to defaults
            for opt in self._engine_options:
                if opt["name"] == "Algorithm":
                    continue
                white_params[opt["name"]] = opt.get("default", "")

        def _on_b_algo_change(event=None):
            new_algo = b_algo_var.get()
            # Reset black params to defaults
            for opt in self._engine_options:
                if opt["name"] == "Algorithm":
                    continue
                black_params[opt["name"]] = opt.get("default", "")

        def _on_a_algo_change(event=None):
            new_algo = analyze_algo_var.get()
            # Reset analyze params to defaults
            for opt in self._engine_options:
                if opt["name"] == "Algorithm":
                    continue
                analyze_params[opt["name"]] = opt.get("default", "")

        w_algo_combo.bind("<<ComboboxSelected>>", _on_w_algo_change)
        b_algo_combo.bind("<<ComboboxSelected>>", _on_b_algo_change)
        analyze_algo_combo.bind("<<ComboboxSelected>>", _on_a_algo_change)

        _update_side_widgets()

        # ---- Buttons ----
        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=10)

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

        # ---- Read back values ----
        new_time = max(1, min(30, time_var.get()))
        new_w_algo = w_algo_var.get()
        new_b_algo = b_algo_var.get()
        new_w_depth = max(0, min(20, w_depth_var.get()))
        new_b_depth = max(0, min(20, b_depth_var.get()))
        new_analyze_algo = analyze_algo_var.get()
        new_analyze_enabled = analyze_enabled_var.get()

        w_name = white_engine_var.get()
        b_name = black_engine_var.get()
        w_idx = engine_names.index(w_name) if w_name in engine_names else 0
        b_idx = engine_names.index(b_name) if b_name in engine_names else 0
        new_white_engine = engine_paths[w_idx]
        new_black_engine = engine_paths[b_idx]

        # Resolve analyze engine
        a_name = analyze_engine_var.get()
        if a_name == "(auto)" or a_name == "(none)":
            new_analyze_engine = None
        else:
            a_idx = engine_names.index(a_name) if a_name in engine_names else 0
            new_analyze_engine = engine_paths[a_idx]

        # ---- Detect changes and shutdown engines as needed ----
        w_changed = (
            new_white_engine != self.white["engine"]
            or new_w_algo != self.white["algo"]
            or white_params != self.white["params"]
        )
        b_changed = (
            new_black_engine != self.black["engine"]
            or new_b_algo != self.black["algo"]
            or black_params != self.black["params"]
        )
        a_changed = (
            new_analyze_engine != self.analyze["engine"]
            or new_analyze_algo != self.analyze["algo"]
            or analyze_params != self.analyze["params"]
            or new_analyze_enabled != self.analyze["enabled"]
        )

        if w_changed:
            self._quit_engine("white_uci_engine")
        if b_changed:
            self._quit_engine("black_uci_engine")
        if a_changed:
            self._quit_engine("_analyze_engine")

        # ---- Apply new settings ----
        self.white["engine"] = new_white_engine
        self.white["algo"] = new_w_algo
        self.white["params"] = white_params
        self.white["depth"] = new_w_depth

        self.black["engine"] = new_black_engine
        self.black["algo"] = new_b_algo
        self.black["params"] = black_params
        self.black["depth"] = new_b_depth

        self.analyze["enabled"] = new_analyze_enabled
        self.analyze["engine"] = new_analyze_engine
        self.analyze["algo"] = new_analyze_algo
        self.analyze["params"] = analyze_params

        self.time_limit = new_time

        self.new_game()

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

        # Build options from engine options, skipping "Algorithm"
        opts = [o for o in self._engine_options if o["name"] != "Algorithm"]

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
    app = GameApp()
    app.run()


if __name__ == "__main__":
    main()
