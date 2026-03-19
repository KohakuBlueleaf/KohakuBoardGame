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
        self._analyze_gen = 0  # generation counter to ignore stale bestmove
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
            or (self._available_engines[0][1] if self._available_engines else None)
        )
        if exe_path is None:
            return

        self._algo_options = {}   # algo_name -> [option_dicts]
        self._algo_defaults = {}  # algo_name -> {name: default_val}

        try:
            probe = UCIEngine(exe_path)
            initial_options = list(probe.options)
        except RuntimeError:
            return

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
                    probe._send("uci")
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
        # Just send position + go. Engine handles superseding the old search.
        # Client's persistent reader thread dispatches to current callbacks.
        if self.uci_moves:
            engine.set_position(moves=list(self.uci_moves))
        else:
            engine.set_position()
        self._analyze_gen += 1
        my_gen = self._analyze_gen
        engine.go(
            infinite=True,
            info_callback=self._on_analyze_info,
            done_callback=lambda bm: self._on_analyze_done(bm, my_gen),
        )
        self._analyzing = True

    def _stop_analysis(self):
        if self._analyze_engine is not None:
            try:
                self._analyze_engine.stop()
            except Exception:
                pass
        # Don't set _analyzing = False here — let _on_analyze_done handle it
        # via generation check. This prevents the race where stop's bestmove
        # arrives after a new go was already sent.

    def _on_analyze_info(self, info_dict):
        """Normalize score to white's perspective for the score bar."""
        if "score_cp" in info_dict and self.game_state.player == 1:
            info_dict["score_cp"] = -info_dict["score_cp"]
        # Preserve last known PV if new info doesn't have one
        if "pv" not in info_dict and "pv" in self.search_info:
            info_dict["pv"] = self.search_info["pv"]
        self.search_info = info_dict

    def _on_analyze_done(self, bestmove_str, gen):
        # Only clear _analyzing if this is from the current generation
        if gen == self._analyze_gen:
            self._analyzing = False

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

        action = self.side_panel.handle_click(x, y)
        if action == "new_game":
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
                self.selected_piece = None
                self.legal_moves_for_selected = []
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
        move_str = f"{step}. {prefix}: {format_move(move)}"

        new_state = self.game_state.next_state(move)
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

        if self.analyze["enabled"] and not self._is_gaming():
            self._stop_analysis()
            self.search_info = {}
            self._start_analysis()
        elif self._is_gaming():
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
        if "score_cp" in info_dict and self.game_state.player == 1:
            info_dict["score_cp"] = -info_dict["score_cp"]
        if "pv" not in info_dict and "pv" in self.search_info:
            info_dict["pv"] = self.search_info["pv"]
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
                self.game_result = "black_wins" if loser == 0 else "white_wins"
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
            gaming=self._is_gaming(),
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

        # Mark game as explicitly started
        self._game_started = True

        for attr in ("white_uci_engine", "black_uci_engine"):
            engine = getattr(self, attr, None)
            if engine is not None and engine.is_alive():
                try:
                    engine.new_game()
                except Exception:
                    pass

        self._trigger_ai_if_needed()

    def open_new_game_dialog(self):
        """Player setup dialog → starts a new game on OK."""
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
        dialog.title("New Game")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.attributes("-topmost", True)
        pad = {"padx": 10, "pady": 4}

        white_engine_var = tk.StringVar(value=engine_names[_engine_index(self.white["engine"])])
        black_engine_var = tk.StringVar(value=engine_names[_engine_index(self.black["engine"])])
        w_algo_var = tk.StringVar(value=self.white["algo"])
        b_algo_var = tk.StringVar(value=self.black["algo"])
        w_depth_var = tk.IntVar(value=self.white["depth"])
        b_depth_var = tk.IntVar(value=self.black["depth"])
        time_var = tk.IntVar(value=self.time_limit)
        white_params = dict(self.white["params"])
        black_params = dict(self.black["params"])
        applied = [False]

        def _build_side_frame(parent, row, label, engine_var, algo_var, depth_var, params):
            frame = ttk.LabelFrame(parent, text=label)
            frame.grid(row=row, column=0, columnspan=2, sticky="ew", **pad)
            ttk.Label(frame, text="Player:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
            combo = ttk.Combobox(frame, textvariable=engine_var, values=engine_names, state="readonly", width=22)
            combo.grid(row=0, column=1, columnspan=4, sticky="ew", padx=4, pady=2)
            ttk.Label(frame, text="Algorithm:").grid(row=1, column=0, sticky="w", padx=4, pady=2)
            algo_cb = ttk.Combobox(frame, textvariable=algo_var, values=algo_list, state="readonly", width=10)
            algo_cb.grid(row=1, column=1, sticky="w", padx=4, pady=2)
            pbtn = ttk.Button(frame, text="Params...", command=lambda: self._open_params_dialog(dialog, algo_var.get(), params), width=8)
            pbtn.grid(row=1, column=2, sticky="w", padx=4, pady=2)
            ttk.Label(frame, text="Depth:").grid(row=1, column=3, sticky="w", padx=4, pady=2)
            dspin = ttk.Spinbox(frame, from_=0, to=20, textvariable=depth_var, width=4)
            dspin.grid(row=1, column=4, sticky="w", padx=4, pady=2)
            ai_widgets = [algo_cb, pbtn, dspin]
            def _on_algo_change(e=None):
                new_algo = algo_var.get()
                params.clear()
                params.update(self._algo_defaults.get(new_algo, {}))
            algo_cb.bind("<<ComboboxSelected>>", _on_algo_change)
            return combo, ai_widgets

        w_combo, w_widgets = _build_side_frame(dialog, 0, "White", white_engine_var, w_algo_var, w_depth_var, white_params)
        b_combo, b_widgets = _build_side_frame(dialog, 1, "Black", black_engine_var, b_algo_var, b_depth_var, black_params)

        ttk.Label(dialog, text="Time limit (s):").grid(row=2, column=0, sticky="w", **pad)
        ttk.Spinbox(dialog, from_=1, to=30, textvariable=time_var, width=5).grid(row=2, column=1, sticky="w", **pad)

        def _update():
            for w in w_widgets:
                st = ("readonly" if isinstance(w, ttk.Combobox) else "normal") if white_engine_var.get() != "Human" else "disabled"
                w.configure(state=st)
            for w in b_widgets:
                st = ("readonly" if isinstance(w, ttk.Combobox) else "normal") if black_engine_var.get() != "Human" else "disabled"
                w.configure(state=st)
        w_combo.bind("<<ComboboxSelected>>", lambda e: _update())
        b_combo.bind("<<ComboboxSelected>>", lambda e: _update())
        _update()

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="Start", command=lambda: [applied.__setitem__(0, True), dialog.destroy()], width=10).grid(row=0, column=0, padx=8)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=10).grid(row=0, column=1, padx=8)
        dialog.bind("<Return>", lambda e: [applied.__setitem__(0, True), dialog.destroy()])
        dialog.bind("<Escape>", lambda e: dialog.destroy())

        dialog.update_idletasks()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        sw, sh = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
        dialog.geometry(f"+{(sw - dw) // 2}+{(sh - dh) // 2}")
        dialog.wait_window()
        root.destroy()

        if not applied[0]:
            return

        w_idx = engine_names.index(white_engine_var.get()) if white_engine_var.get() in engine_names else 0
        b_idx = engine_names.index(black_engine_var.get()) if black_engine_var.get() in engine_names else 0

        if engine_paths[w_idx] != self.white["engine"] or w_algo_var.get() != self.white["algo"] or white_params != self.white["params"]:
            self._quit_engine("white_uci_engine")
        if engine_paths[b_idx] != self.black["engine"] or b_algo_var.get() != self.black["algo"] or black_params != self.black["params"]:
            self._quit_engine("black_uci_engine")

        self.white.update({"engine": engine_paths[w_idx], "algo": w_algo_var.get(), "params": white_params, "depth": max(0, min(20, w_depth_var.get()))})
        self.black.update({"engine": engine_paths[b_idx], "algo": b_algo_var.get(), "params": black_params, "depth": max(0, min(20, b_depth_var.get()))})
        self.time_limit = max(1, min(30, time_var.get()))
        self.new_game()

    def open_settings(self):
        """Settings dialog: analyze engine config + time limit. Saves without starting game."""
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

        analyze_engine_names = [name for name, _path in self._available_engines] or ["(none)"]
        analyze_engine_var = tk.StringVar(value="(auto)" if self.analyze["engine"] is None else engine_names[_engine_index(self.analyze["engine"])])
        analyze_algo_var = tk.StringVar(value=self.analyze["algo"])
        time_var = tk.IntVar(value=self.time_limit)
        analyze_params = dict(self.analyze["params"])
        applied = [False]

        # Analyze engine
        af = ttk.LabelFrame(dialog, text="Analyze Engine")
        af.grid(row=0, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Label(af, text="Engine:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Combobox(af, textvariable=analyze_engine_var, values=["(auto)"] + analyze_engine_names, state="readonly", width=22).grid(row=0, column=1, columnspan=3, sticky="ew", padx=4, pady=2)
        ttk.Label(af, text="Algorithm:").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        a_algo_cb = ttk.Combobox(af, textvariable=analyze_algo_var, values=algo_list, state="readonly", width=10)
        a_algo_cb.grid(row=1, column=1, sticky="w", padx=4, pady=2)
        ttk.Button(af, text="Params...", command=lambda: self._open_params_dialog(dialog, analyze_algo_var.get(), analyze_params), width=8).grid(row=1, column=2, sticky="w", padx=4, pady=2)

        def _on_a_algo(e=None):
            new_algo = analyze_algo_var.get()
            analyze_params.clear()
            analyze_params.update(self._algo_defaults.get(new_algo, {}))
        a_algo_cb.bind("<<ComboboxSelected>>", _on_a_algo)

        # Time limit
        ttk.Label(dialog, text="Time limit (s):").grid(row=1, column=0, sticky="w", **pad)
        ttk.Spinbox(dialog, from_=1, to=30, textvariable=time_var, width=5).grid(row=1, column=1, sticky="w", **pad)

        # Buttons
        bf = ttk.Frame(dialog)
        bf.grid(row=2, column=0, columnspan=2, pady=10)
        ttk.Button(bf, text="Save", command=lambda: [applied.__setitem__(0, True), dialog.destroy()], width=10).grid(row=0, column=0, padx=8)
        ttk.Button(bf, text="Cancel", command=dialog.destroy, width=10).grid(row=0, column=1, padx=8)
        dialog.bind("<Return>", lambda e: [applied.__setitem__(0, True), dialog.destroy()])
        dialog.bind("<Escape>", lambda e: dialog.destroy())

        dialog.update_idletasks()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        sw, sh = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
        dialog.geometry(f"+{(sw - dw) // 2}+{(sh - dh) // 2}")
        dialog.wait_window()
        root.destroy()

        if not applied[0]:
            return

        a_name = analyze_engine_var.get()
        new_analyze_engine = None if a_name in ("(auto)", "(none)") else engine_paths[engine_names.index(a_name)] if a_name in engine_names else None

        if new_analyze_engine != self.analyze["engine"] or analyze_algo_var.get() != self.analyze["algo"] or analyze_params != self.analyze["params"]:
            self._quit_engine("_analyze_engine")

        self.analyze["engine"] = new_analyze_engine
        self.analyze["algo"] = analyze_algo_var.get()
        self.analyze["params"] = analyze_params
        self.time_limit = max(1, min(30, time_var.get()))

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
    app = GameApp()
    app.run()


if __name__ == "__main__":
    main()
