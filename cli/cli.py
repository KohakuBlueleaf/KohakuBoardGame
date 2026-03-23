"""UBGI CLI - Run AI vs AI or Human vs AI matches via UBGI protocol (backward compatible with UCI).

Supports multiple game types via --game flag. Board display and move input
adapt to the chosen game. When --game is not specified, defaults to minichess.
"""

import argparse
import sys
import os
import time
import subprocess

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Game-agnostic UCI info parsing (no game-specific imports needed)
# ---------------------------------------------------------------------------

try:
    from gui.ubgi_client import UBGIEngine as _UBGIEngineStatic

    _parse_info = _UBGIEngineStatic.parse_info
except ImportError:
    _parse_info = lambda line: {}  # fallback: no info parsing

# ---------------------------------------------------------------------------
# Game context -- populated once by _init_game(), replaces per-module globals
# ---------------------------------------------------------------------------

_game_ctx = {}  # populated by _init_game()


def _init_game(game_name, board_size=None):
    """Initialize game-specific context. Called once from main()."""
    if game_name == "minichess":
        from cli.games.minichess import get_context

        _game_ctx.update(get_context())
    elif game_name == "connect6":
        from cli.games.connect6 import get_context

        _game_ctx.update(get_context(board_size or 15))
    elif game_name == "minishogi":
        from cli.games.minishogi import get_context

        _game_ctx.update(get_context())
    elif game_name == "kohakushogi":
        from cli.games.kohakushogi import get_context

        _game_ctx.update(get_context())
    elif game_name == "kohakuchess":
        from cli.games.kohakuchess import get_context

        _game_ctx.update(get_context())
    else:
        _game_ctx.update({"name": "generic"})


ALGO_CHOICES = ["pvs", "alphabeta", "minimax", "random"]

# ---------------------------------------------------------------------------
# Board display (game-specific)
# ---------------------------------------------------------------------------


def print_board(state):
    """Dispatch to the appropriate board printer via _game_ctx."""
    printer = _game_ctx.get("print_board")
    if printer is not None:
        printer(state, _game_ctx)
    # Generic: no board display


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_nodes(n):
    """Format node count: 1234 -> '1.2K', 1234567 -> '1.2M'."""
    if n is None:
        return "?"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def format_search_info(info):
    """Format search info dict for display."""
    if not info:
        return ""

    parts = []

    depth = info.get("depth")
    seldepth = info.get("seldepth")
    if depth is not None:
        d = f"depth={depth}/{seldepth}" if seldepth is not None else f"depth={depth}"
        parts.append(d)

    score_cp = info.get("score_cp")
    if score_cp is not None:
        parts.append(f"score={score_cp / 100.0:+.2f}")
    elif info.get("score_mate") is not None:
        parts.append(f"mate={info['score_mate']}")

    nodes = info.get("nodes")
    if nodes is not None:
        parts.append(f"nodes={format_nodes(nodes)}")

    nps = info.get("nps")
    if nps is not None:
        parts.append(f"{format_nodes(nps)} nps")
    elif nodes is not None and info.get("time") and info["time"] > 0:
        calc_nps = int(nodes / (info["time"] / 1000.0))
        parts.append(f"{format_nodes(calc_nps)} nps")

    elapsed = info.get("time")
    if elapsed is not None:
        parts.append(f"{elapsed}ms")

    return ", ".join(parts)


def format_move_display(move_or_uci, state=None):
    """Format a move for display, adapting to the active game type.

    For minichess: uses the algebraic format_move (e.g. 'B2->B3').
    For connect6: shows the coordinate (e.g. 'E5').
    For generic: shows the raw UCI string.
    """
    game_name = _game_ctx.get("name", "generic")
    if game_name in ("minichess", "kohakuchess") and not isinstance(move_or_uci, str):
        return _game_ctx["format_move"](move_or_uci)
    elif game_name in ("minishogi", "kohakushogi") and not isinstance(move_or_uci, str):
        return _game_ctx["format_move"](move_or_uci)
    elif game_name in ("minishogi", "kohakushogi") and isinstance(move_or_uci, str):
        return move_or_uci.upper()
    elif game_name == "connect6" and isinstance(move_or_uci, str):
        # Connect6 UCI move is like "e5" (column letter + row number)
        return move_or_uci.upper()
    else:
        if isinstance(move_or_uci, str):
            return move_or_uci
        return str(move_or_uci)


# ---------------------------------------------------------------------------
# Engine communication (game-agnostic)
# ---------------------------------------------------------------------------


def get_engine_move(engine_path, algo, params, uci_moves, time_limit, depth=0):
    """Spawn engine, send UBGI/UCI commands, kill after timeout, parse output.

    Returns (bestmove_uci_str, last_info_dict) or (None, None).
    """
    kwargs = {
        "args": [os.path.abspath(engine_path)],
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        proc = subprocess.Popen(**kwargs)
    except OSError:
        return None, None

    def send(cmd):
        proc.stdin.write((cmd + "\n").encode())
        proc.stdin.flush()

    # Setup phase -- blocking communicate for handshake (UBGI, backward compatible with UCI)
    setup_cmds = ["ubgi"]
    setup_cmds.append(f"setoption name Algorithm value {algo}")
    for p in params or []:
        if "=" in p:
            k, v = p.split("=", 1)
            setup_cmds.append(f"setoption name {k} value {v}")
    if uci_moves:
        setup_cmds.append("position startpos moves " + " ".join(uci_moves))
    else:
        setup_cmds.append("position startpos")
    setup_cmds.append("isready")

    for cmd in setup_cmds:
        send(cmd)

    # Wait for readyok or ubgiok (engine is ready to search)
    while True:
        raw = proc.stdout.readline()
        if not raw:
            break
        line_str = raw.decode("utf-8", errors="replace").strip()
        if line_str in ("readyok", "ubgiok", "uciok"):
            break

    # Now send go -- timer starts HERE
    bestmove = None
    last_info = None

    if depth > 0:
        send(f"go depth {depth}")
        # Wait for engine to finish (no time limit for depth search)
        while True:
            raw = proc.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if line.startswith("info ") and "depth" in line:
                last_info = _parse_info(line)
            elif line.startswith("bestmove"):
                parts = line.split()
                bestmove = parts[1] if len(parts) >= 2 else None
                break
        proc.kill()
        return bestmove, last_info
    else:
        send(f"go movetime {time_limit}")
        # Wait exactly the time limit, then kill and read
        time.sleep(time_limit / 1000.0)
        proc.kill()
        stdout = proc.stdout.read()

    # Parse killed output -- iterate from last to first for robustness
    # (last line may be truncated by kill)
    lines = stdout.decode("utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        line = line.strip()
        if bestmove is None and line.startswith("bestmove"):
            parts = line.split()
            if len(parts) >= 2:
                bestmove = parts[1]
        if last_info is None and line.startswith("info ") and "depth" in line:
            parsed = _parse_info(line)
            if parsed and "depth" in parsed:
                last_info = parsed
        if bestmove is not None and last_info is not None:
            break

    # If no bestmove, extract from last info (pv or currmove)
    if bestmove is None and last_info:
        pv = last_info.get("pv")
        if pv and len(pv) > 0:
            bestmove = pv[0]
        elif last_info.get("currmove"):
            bestmove = last_info["currmove"]

    # Debug: dump raw output if no move found
    if bestmove is None:
        print(f"  [DEBUG] No bestmove found. stdout lines={len(lines)}")
        for i, l in enumerate(lines[-10:]):
            print(f"  [DEBUG]   {i}: {l.strip()}")

    return bestmove, last_info


# ---------------------------------------------------------------------------
# Human move input (generic fallback)
# ---------------------------------------------------------------------------


def get_human_move_generic(uci_moves):
    """Prompt human player for a raw UCI move string (generic game)."""
    side_name = "Player 1" if len(uci_moves) % 2 == 0 else "Player 2"
    print(f"  {side_name}'s turn.")

    while True:
        try:
            raw = input("  Enter move (UCI format): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGame aborted.")
            sys.exit(0)

        if raw:
            return raw


# ---------------------------------------------------------------------------
# Game loop
# ---------------------------------------------------------------------------


def _quit_engine(engine):
    """Quit a UBGI/UCI engine, ignoring errors."""
    if engine is not None:
        try:
            engine.quit()
        except Exception:
            pass


def run_game(
    white_path,
    black_path,
    time_limit,
    white_algo,
    black_algo,
    verbose=True,
    game_num=None,
    total_games=None,
    depth=0,
    params=None,
    white_params=None,
    black_params=None,
):
    """Run a single game between two players.

    Returns "white", "black", or "draw".
    params: shared params for both sides.
    white_params/black_params: per-side overrides (merged after shared).
    """
    game_name = _game_ctx.get("name", "generic")
    has_state = game_name != "generic"
    uci_moves = []
    move_number = 0

    # Initialize game state based on game type
    if has_state:
        if "make_state" in _game_ctx:
            state = _game_ctx["make_state"](_game_ctx.get("board_size", 15))
        else:
            state = _game_ctx["state_class"].initial()
    else:
        state = None  # generic: no local state

    if verbose:
        if game_num is not None and total_games is not None:
            print(f"=== Game {game_num}/{total_games} ===")
        else:
            print("=== New Game ===")
        print(f"  White: {'Human' if white_path == 'human' else white_algo}")
        print(f"  Black: {'Human' if black_path == 'human' else black_algo}")
        print(f"  Time limit: {time_limit}ms per move")
        if has_state:
            print_board(state)

    while True:
        # --- Check game over ---
        if has_state:
            check_fn = _game_ctx.get("check_game_over")
            result, winner = check_fn(state)
            if result in ("win", "checkmate", "perpetual_check", "stalemate_loss"):
                if game_name in ("minichess", "kohakuchess"):
                    winner_str = "White" if winner == 0 else "Black"
                    color = "white" if winner == 0 else "black"
                elif game_name in ("minishogi", "kohakushogi"):
                    winner_str = "Sente" if winner == 0 else "Gote"
                    color = "white" if winner == 0 else "black"
                elif game_name == "connect6":
                    winner_str = "Player 1 (X)" if winner == 1 else "Player 2 (O)"
                    color = "white" if winner == 1 else "black"
                else:
                    winner_str = str(winner)
                    color = "white" if winner in (0, 1) else "black"
                if verbose:
                    if result == "checkmate":
                        print(f"  >> Checkmate! {winner_str} wins!")
                    elif result == "perpetual_check":
                        print(f"  >> Perpetual check! {winner_str} wins!")
                    elif result == "stalemate_loss":
                        loser_str = "Sente" if winner == 1 else "Gote"
                        print(f"  >> {loser_str} has no legal moves! {winner_str} wins!")
                    else:
                        print(f"  >> {winner_str} wins!")
                return color
            elif result == "draw":
                if verbose:
                    print(f"  >> Draw!")
                return "draw"
            elif result == "no_moves":
                if verbose:
                    if game_name in ("minishogi", "kohakushogi"):
                        loser = "Sente" if winner == 1 else "Gote"
                    else:
                        loser = "White" if winner == 1 else "Black"
                    print(f"  >> {loser} has no legal moves!")
                # winner value is the winning side
                if game_name in ("minichess", "minishogi", "kohakuchess", "kohakushogi"):
                    return "white" if winner == 0 else "black"
                else:
                    return "white" if winner == 1 else "black"

            # Determine which side to move
            if game_name in ("minichess", "minishogi", "kohakuchess", "kohakushogi"):
                is_white = state.player == 0
            elif game_name == "connect6":
                is_white = state["player"] == 1  # player 1 = "white" (first player)
            else:
                is_white = len(uci_moves) % 2 == 0
        else:
            # Generic: no game-over detection, rely on engine
            is_white = len(uci_moves) % 2 == 0

        engine_path = white_path if is_white else black_path
        algo_name = white_algo if is_white else black_algo
        side_name = "White" if is_white else "Black"

        if is_white:
            move_number += 1

        bestmove_uci = None
        info = None

        if engine_path == "human":
            # Human move input
            human_fn = _game_ctx.get("get_human_move")
            if human_fn is not None:
                if game_name in ("minichess", "minishogi", "kohakuchess", "kohakushogi") and verbose:
                    print(f"  Step {state.step}/{_game_ctx['max_step']}")
                result = human_fn(state, _game_ctx)
                # For chess/shogi variants, result is a move tuple; for connect6, a UCI string
                if game_name in ("minichess", "minishogi", "kohakuchess", "kohakushogi"):
                    bestmove_uci = _game_ctx["move_to_uci"](result)
                else:
                    bestmove_uci = result
            else:
                bestmove_uci = get_human_move_generic(uci_moves)
        else:
            side_params = list(params or [])
            extra = white_params if is_white else black_params
            if extra:
                side_params.extend(extra)
            bestmove_uci, info = get_engine_move(
                engine_path, algo_name, side_params, uci_moves, time_limit, depth=depth
            )

            if bestmove_uci is None:
                if verbose:
                    print(
                        f"  >> {side_name} engine failed to return a move! {side_name} loses."
                    )
                    print(
                        f"     algo={algo_name}, moves={len(uci_moves)}, last_info={info}"
                    )
                return "black" if is_white else "white"

            # Move validation (for games with state)
            if has_state:
                try:
                    move = _game_ctx["uci_to_move"](bestmove_uci)
                except (ValueError, IndexError, KeyError):
                    if verbose:
                        print(
                            f"  >> {side_name} engine returned invalid move '{bestmove_uci}'! {side_name} loses."
                        )
                    return "black" if is_white else "white"

                if game_name in ("minichess", "minishogi", "kohakuchess", "kohakushogi"):
                    if move not in state.legal_actions:
                        if verbose:
                            print(
                                f"  >> {side_name} engine returned illegal move {_game_ctx['format_move'](move)}! {side_name} loses."
                            )
                        return "black" if is_white else "white"
                elif game_name == "connect6":
                    # Validate placement is on an empty square and in bounds
                    _, (r, c) = move
                    size = state["size"]
                    if r < 0 or r >= size or c < 0 or c >= size:
                        if verbose:
                            print(
                                f"  >> {side_name} engine returned out-of-bounds move '{bestmove_uci}'! {side_name} loses."
                            )
                        return "black" if is_white else "white"
                    if state["board"][r][c] != 0:
                        if verbose:
                            print(
                                f"  >> {side_name} engine returned move to occupied square '{bestmove_uci}'! {side_name} loses."
                            )
                        return "black" if is_white else "white"

        # For generic games, if engine returns "none" or "(none)", it means no moves
        if game_name == "generic" and bestmove_uci in ("none", "(none)", "0000"):
            if verbose:
                print(f"  >> {side_name} has no moves. Game over.")
            return "black" if is_white else "white"

        uci_moves.append(bestmove_uci)

        # Display move
        if verbose:
            prefix = f"{move_number}." if is_white else f"{move_number}..."
            info_str = format_search_info(info)
            display_move = format_move_display(bestmove_uci)
            line = f"  {prefix} {side_name}: {display_move}"
            if info_str:
                line += f" ({info_str})"
            print(line)

        # Advance local state
        if has_state:
            apply_fn = _game_ctx.get("apply_move")
            if apply_fn is not None:
                state, _ = apply_fn(state, bestmove_uci, _game_ctx)

        if verbose and has_state:
            print_board(state)


def run_tournament(
    engine1_path,
    engine2_path,
    time_limit,
    algo1,
    algo2,
    num_games,
    verbose,
    depth=0,
    params=None,
    engine1_params=None,
    engine2_params=None,
):
    """Run a tournament of N games, alternating colors."""
    engine1_wins = 0
    engine2_wins = 0
    draws = 0
    white_wins = 0
    black_wins = 0
    color_draws = 0

    try:
        for game_idx in range(num_games):
            if game_idx % 2 == 0:
                w_path, w_algo = engine1_path, algo1
                b_path, b_algo = engine2_path, algo2
                engine1_is_white = True
            else:
                w_path, w_algo = engine2_path, algo2
                b_path, b_algo = engine1_path, algo1
                engine1_is_white = False

            w_label = "Human" if w_path == "human" else w_algo
            b_label = "Human" if b_path == "human" else b_algo

            if not verbose:
                e1_color = "White" if engine1_is_white else "Black"
                e2_color = "Black" if engine1_is_white else "White"
                print(
                    f"Game {game_idx + 1}/{num_games}: "
                    f"Engine1({algo1})={e1_color} vs Engine2({algo2})={e2_color}",
                    end="",
                    flush=True,
                )

            # Per-side params follow the engine, not the color
            if engine1_is_white:
                w_params, b_params = engine1_params, engine2_params
            else:
                w_params, b_params = engine2_params, engine1_params

            result = run_game(
                w_path,
                b_path,
                time_limit,
                w_label,
                b_label,
                verbose=verbose,
                game_num=game_idx + 1,
                total_games=num_games,
                depth=depth,
                params=params,
                white_params=w_params,
                black_params=b_params,
            )

            if result == "white":
                white_wins += 1
                if engine1_is_white:
                    engine1_wins += 1
                else:
                    engine2_wins += 1
            elif result == "black":
                black_wins += 1
                if engine1_is_white:
                    engine2_wins += 1
                else:
                    engine1_wins += 1
            else:
                draws += 1
                color_draws += 1

            if not verbose:
                winner_str = {"white": "1-0", "black": "0-1", "draw": "1/2"}[result]
                print(f" {winner_str}")

            total_played = game_idx + 1
            print(
                f"  Score after {total_played} game(s): "
                f"Engine1({algo1}) +{engine1_wins} -{engine2_wins} ={draws}"
            )

    except KeyboardInterrupt:
        print("\n\nTournament interrupted!")

    finally:
        pass  # engines are killed per-move, nothing to clean up

    total = engine1_wins + engine2_wins + draws
    print()
    print("=" * 50)
    print(f"  Tournament Results ({total} games)")
    print("=" * 50)
    print(f"  Engine1 ({algo1}): +{engine1_wins} -{engine2_wins} ={draws}")
    print(f"  Engine2 ({algo2}): +{engine2_wins} -{engine1_wins} ={draws}")
    print(f"  White wins: {white_wins}  Black wins: {black_wins}  Draws: {color_draws}")
    if total > 0:
        e1_score = engine1_wins + draws * 0.5
        print(f"  Engine1 score: {e1_score}/{total} ({e1_score / total * 100:.1f}%)")
    print("=" * 50)


def main():
    """Parse arguments and run UBGI CLI."""

    parser = argparse.ArgumentParser(
        description="UBGI CLI - Run AI vs AI or Human vs AI matches via UBGI protocol (backward compatible with UCI).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s --white build/minichess-uci.exe --black build/minichess-uci.exe --time 2000 --games 10
  %(prog)s --white human --black build/minichess-uci.exe --time 2000
  %(prog)s --game connect6 --white build/connect6.exe --black build/connect6.exe --depth 6
  %(prog)s --game generic --white build/engine.exe --black build/engine.exe --time 5000
""",
    )

    parser.add_argument(
        "--game",
        default="minichess",
        help="Game type for board display and move input (default: minichess). "
        "Built-in: minichess, minishogi, kohakuchess, kohakushogi, connect6. Use 'generic' for any other UBGI engine.",
    )
    parser.add_argument(
        "--white", required=True, help='Path to UBGI/UCI engine for White, or "human".'
    )
    parser.add_argument(
        "--black", required=True, help='Path to UBGI/UCI engine for Black, or "human".'
    )
    parser.add_argument(
        "--time", type=int, default=2000, help="Time per move in ms (default: 2000)."
    )
    parser.add_argument(
        "--games", type=int, default=1, help="Number of games (default: 1)."
    )
    parser.add_argument(
        "--white-algo",
        default="pvs",
        choices=ALGO_CHOICES,
        help="Algorithm for White (default: pvs).",
    )
    parser.add_argument(
        "--black-algo",
        default="pvs",
        choices=ALGO_CHOICES,
        help="Algorithm for Black (default: pvs).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=None,
        help="Show board after each move (default: on for single game).",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Minimal output, just results."
    )
    parser.add_argument(
        "--depth", type=int, default=0, help="Fixed search depth (0 = use time limit)."
    )
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="Set engine param for both sides: --param UseNNUE=true. Can repeat.",
    )
    parser.add_argument(
        "--white-param",
        action="append",
        default=[],
        help="Set engine param for white only: --white-param NNUEFile=models/v2.bin",
    )
    parser.add_argument(
        "--black-param",
        action="append",
        default=[],
        help="Set engine param for black only: --black-param NNUEFile=models/v3.bin",
    )
    parser.add_argument(
        "--board-size",
        type=int,
        default=15,
        help="Board size for connect6 (default: 15).",
    )

    args = parser.parse_args()

    _init_game(args.game.lower(), board_size=args.board_size)

    if args.quiet:
        verbose = False
    elif args.verbose is not None:
        verbose = args.verbose
    else:
        verbose = args.games == 1

    for label, path in [("--white", args.white), ("--black", args.black)]:
        if path != "human" and not os.path.isfile(path):
            print(f"Error: {label} engine not found: {path}", file=sys.stderr)
            sys.exit(1)

    if args.games < 1:
        print("Error: --games must be >= 1", file=sys.stderr)
        sys.exit(1)

    if args.time < 100:
        print("Error: --time must be >= 100ms", file=sys.stderr)
        sys.exit(1)

    wp = args.white_param or None
    bp = args.black_param or None

    if args.games > 1:
        run_tournament(
            args.white,
            args.black,
            args.time,
            args.white_algo,
            args.black_algo,
            args.games,
            verbose,
            depth=args.depth,
            params=args.param,
            engine1_params=wp,
            engine2_params=bp,
        )
        return

    try:
        result = run_game(
            args.white,
            args.black,
            args.time,
            args.white_algo if args.white != "human" else "Human",
            args.black_algo if args.black != "human" else "Human",
            verbose=verbose,
            depth=args.depth,
            params=args.param,
            white_params=wp,
            black_params=bp,
        )

        result_map = {"white": "1-0", "black": "0-1", "draw": "1/2-1/2"}
        print(f"Result: {result_map[result]}")

    except KeyboardInterrupt:
        print("\nGame aborted.")


if __name__ == "__main__":
    main()
