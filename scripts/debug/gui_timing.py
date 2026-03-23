"""Run the GUI with timing instrumentation to find hangs.

Usage:
    python scripts/debug/gui_timing.py --game KohakuShogi
    python scripts/debug/gui_timing.py --game MiniShogi

Logs any main-loop frame or method call that takes >50ms.
When the GUI hangs, the console will show which call is blocking.
"""
import sys
import os
import time
import threading
import argparse

sys.path.insert(0, ".")

import gui.main as gui_main

THRESHOLD_MS = 50


def _log(msg):
    t = time.monotonic()
    tid = threading.current_thread().name
    print(f"[{t:.3f}] [{tid}] {msg}", flush=True)


def _timed_wrap(name, orig):
    def wrapper(self, *args, **kwargs):
        t0 = time.monotonic()
        result = orig(self, *args, **kwargs)
        dt = (time.monotonic() - t0) * 1000
        if dt > THRESHOLD_MS:
            _log(f"SLOW {name}: {dt:.1f}ms")
        return result
    return wrapper


# Patch all potentially-blocking methods
for name in [
    "update",
    "handle_events",
    "draw",
    "execute_move",
    "trigger_ai_move",
    "_start_analysis",
    "_stop_analysis",
    "_kill_analyze_engine",
    "_get_or_create_uci_engine",
    "_shutdown_uci_engines",
    "_force_kill_ai_engine",
]:
    orig = getattr(gui_main.GameApp, name, None)
    if orig is not None:
        setattr(gui_main.GameApp, name, _timed_wrap(name, orig))


_orig_run = gui_main.GameApp.run

def patched_run(self):
    import pygame
    try:
        frame = 0
        while self._running:
            t0 = time.monotonic()
            self.handle_events()
            t1 = time.monotonic()
            self.update()
            t2 = time.monotonic()
            self.draw()
            t3 = time.monotonic()
            self.clock.tick(60)
            t4 = time.monotonic()

            total = (t4 - t0) * 1000
            if total > 200:
                _log(
                    f"SLOW FRAME #{frame}: {total:.0f}ms "
                    f"(events={1000*(t1-t0):.0f} update={1000*(t2-t1):.0f} "
                    f"draw={1000*(t3-t2):.0f} tick={1000*(t4-t3):.0f})"
                )
            frame += 1
    finally:
        self._shutdown_uci_engines()
        pygame.quit()
        try:
            self._tk_root.destroy()
        except Exception:
            pass

gui_main.GameApp.run = patched_run


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", default="KohakuShogi")
    args = parser.parse_args()

    _log(f"Starting GUI with game={args.game}")
    app = gui_main.GameApp(game_name=args.game)
    _log("App created, starting main loop")
    app.run()
