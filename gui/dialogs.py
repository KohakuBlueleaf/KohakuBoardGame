"""Dialog mixin for GameApp — New Game, Settings, Params."""

import os
import glob

try:
    from gui.ubgi_client import discover_engines
    import gui.config as _cfg
except ImportError:
    from ubgi_client import discover_engines
    import config as _cfg


def _discover_nnue_models(game_name):
    """Scan models/ for .bin files matching the current game.

    Tries multiple naming conventions: CamelCase, snake_case, lowercase,
    with/without -models suffix. Returns list of relative paths sorted.
    """
    # Generate all plausible directory names
    names = {game_name}
    names.add(game_name.lower())
    names.add(game_name.replace(" ", ""))
    names.add(game_name.replace(" ", "").lower())
    # CamelCase → snake_case: "KohakuShogi" → "kohakushogi"
    import re
    snake = re.sub(r'(?<!^)(?=[A-Z])', '_', game_name).lower()
    names.add(snake)
    # Also strip underscores: "kohakushogi" → "kohakushogi"
    names.add(game_name.lower().replace("_", ""))

    patterns = []
    for n in names:
        patterns.append(f"models/{n}/*.bin")
        patterns.append(f"models/{n}-models/*.bin")

    found = set()
    for pat in patterns:
        for p in glob.glob(pat):
            found.add(p.replace("\\", "/"))
    return sorted(found)


class DialogsMixin:

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

        # MultiPV and PV display settings
        pv_frame = ttk.LabelFrame(dialog, text="PV Display")
        pv_frame.grid(row=2, column=0, columnspan=2, sticky="ew", **pad)

        multi_pv_var = tk.IntVar(value=self.multi_pv)
        ttk.Label(pv_frame, text="MultiPV:").grid(
            row=0, column=0, sticky="w", padx=4, pady=2
        )
        ttk.Spinbox(pv_frame, from_=1, to=10, increment=1,
                     textvariable=multi_pv_var, width=5).grid(
            row=0, column=1, sticky="w", padx=4, pady=2
        )

        pv_steps_var = tk.IntVar(value=self.pv_display_steps)
        ttk.Label(pv_frame, text="PV Steps:").grid(
            row=1, column=0, sticky="w", padx=4, pady=2
        )
        ttk.Spinbox(pv_frame, from_=1, to=20, increment=1,
                     textvariable=pv_steps_var, width=5).grid(
            row=1, column=1, sticky="w", padx=4, pady=2
        )

        # Buttons
        bf = ttk.Frame(dialog)
        bf.grid(row=3, column=0, columnspan=2, pady=10)
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

        # Update MultiPV and PV display steps
        new_multi_pv = max(1, min(10, multi_pv_var.get()))
        self.pv_display_steps = max(1, min(20, pv_steps_var.get()))
        multi_pv_changed = new_multi_pv != self.multi_pv
        self.multi_pv = new_multi_pv

        # Send MultiPV option to running analyze engine if changed
        if multi_pv_changed and self._analyze_engine is not None and self._analyze_engine.is_alive():
            self._analyze_engine.set_option("MultiPV", str(self.multi_pv))


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

                if name == "NNUEFile":
                    models = _discover_nnue_models(self._game_name)
                    if models:
                        # Select current if it exists, otherwise first model
                        if current not in models:
                            var.set(models[0])
                        ttk.Combobox(
                            sub_f,
                            textvariable=var,
                            values=models,
                            state="readonly",
                            width=max(20, max(len(m) for m in models) + 2),
                        ).pack(side="left", padx=(4, 0))
                    else:
                        ttk.Entry(sub_f, textvariable=var, width=30).pack(
                            side="left", padx=(4, 0)
                        )
                else:
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
