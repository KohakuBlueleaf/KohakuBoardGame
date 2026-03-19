"""MiniChess CLI - Run AI vs AI or Human vs AI matches via UCI protocol."""

import argparse
import sys
import os
import time
import subprocess

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.game_engine import MiniChessState, format_move
from gui.uci_client import UCIEngine
from gui.config import (
    BOARD_H,
    BOARD_W,
    MAX_STEP,
    PIECE_UNICODE,
    COL_LABELS,
    ROW_LABELS,
)

ALGO_CHOICES = ["pvs", "alphabeta", "minimax", "random"]


def print_board(state):
    """Print board with Unicode chess pieces from White's perspective."""
    print()
    print("    " + "  ".join(COL_LABELS))
    for r in range(BOARD_H):
        rank_label = ROW_LABELS[r]
        row_chars = []
        for c in range(BOARD_W):
            w_piece = state.board[0][r][c]
            b_piece = state.board[1][r][c]
            if w_piece:
                row_chars.append(PIECE_UNICODE[0][w_piece])
            elif b_piece:
                row_chars.append(PIECE_UNICODE[1][b_piece])
            else:
                row_chars.append(".")
        print(f" {rank_label}  " + "  ".join(row_chars) + f"  {rank_label}")
    print("    " + "  ".join(COL_LABELS))
    print()


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


def get_engine_move(engine_path, algo, params, uci_moves, time_limit, depth=0):
    """Spawn engine, send commands, kill after timeout, parse output.

    Returns (bestmove_uci_str, last_info_dict) or (None, None).
    """
    # Build all commands
    commands = ["uci"]
    commands.append(f"setoption name Algorithm value {algo}")
    for p in (params or []):
        if "=" in p:
            k, v = p.split("=", 1)
            commands.append(f"setoption name {k} value {v}")
    if uci_moves:
        commands.append("position startpos moves " + " ".join(uci_moves))
    else:
        commands.append("position startpos")
    if depth > 0:
        commands.append(f"go depth {depth}")
    else:
        commands.append(f"go movetime {time_limit}")

    stdin_data = "\n".join(commands) + "\n"
    timeout_sec = (time_limit / 1000.0) + 1.5 if depth == 0 else 300.0

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

    # Write commands
    try:
        proc.stdin.write(stdin_data.encode())
        proc.stdin.flush()
    except Exception:
        proc.kill()
        return None, None

    # Wait, then kill and read whatever was produced
    time.sleep(timeout_sec)
    proc.kill()
    stdout = proc.stdout.read()

    # Parse output — find last info and bestmove
    bestmove = None
    last_info = None
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("info ") and "depth" in line:
            last_info = UCIEngine.parse_info(line)
        elif line.startswith("bestmove"):
            parts = line.split()
            bestmove = parts[1] if len(parts) >= 2 else None

    # If no bestmove but we have info with currmove, use that
    if bestmove is None and last_info and last_info.get("currmove"):
        bestmove = last_info["currmove"]

    return bestmove, last_info


def get_human_move(state):
    """Prompt human player for a move via numbered list or algebraic notation."""
    legal = state.legal_actions
    player_name = "White" if state.player == 0 else "Black"

    print(f"  {player_name}'s legal moves:")
    entries = [f"{i + 1:>3}. {format_move(mv)}" for i, mv in enumerate(legal)]
    cols = 4
    for i in range(0, len(entries), cols):
        row = entries[i : i + cols]
        print("  " + "    ".join(f"{e:<16}" for e in row))
    print()

    while True:
        try:
            raw = input(f"  Enter move number (or algebraic e.g. b2b3): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGame aborted.")
            sys.exit(0)

        if not raw:
            continue

        try:
            num = int(raw)
            if 1 <= num <= len(legal):
                return legal[num - 1]
            print(f"  Invalid number. Enter 1-{len(legal)}.")
            continue
        except ValueError:
            pass

        uci_str = raw.replace("-", "").replace(">", "").lower()
        if len(uci_str) == 4:
            try:
                move = UCIEngine.uci_to_move(uci_str)
                if move in legal:
                    return move
                print(f"  '{raw}' is not a legal move.")
                continue
            except (ValueError, IndexError, KeyError):
                pass

        print(
            f"  Could not parse '{raw}'. Enter a move number or algebraic (e.g. b2b3)."
        )


def _quit_engine(engine):
    """Quit a UCI engine, ignoring errors."""
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
):
    """Run a single game between two players.

    Returns "white", "black", or "draw".
    """
    state = MiniChessState.initial()
    uci_moves = []
    move_number = 0

    if verbose:
        if game_num is not None and total_games is not None:
            print(f"=== Game {game_num}/{total_games} ===")
        else:
            print("=== New Game ===")
        print(f"  White: {'Human' if white_path == 'human' else white_algo}")
        print(f"  Black: {'Human' if black_path == 'human' else black_algo}")
        print(f"  Time limit: {time_limit}ms per move")
        print_board(state)

    while True:
        result, winner = state.check_game_over()
        if result == "win":
            winner_str = "White" if winner == 0 else "Black"
            if verbose:
                print(f"  >> {winner_str} wins! (king capture available)")
            return "white" if winner == 0 else "black"
        elif result == "draw":
            if verbose:
                print(f"  >> Draw! (step limit reached, equal material)")
            return "draw"

        if not state.legal_actions:
            if verbose:
                side = "White" if state.player == 0 else "Black"
                print(f"  >> {side} has no legal moves!")
            return "black" if state.player == 0 else "white"

        is_white = state.player == 0
        engine_path = white_path if is_white else black_path
        algo_name = white_algo if is_white else black_algo
        side_name = "White" if is_white else "Black"

        if is_white:
            move_number += 1

        move = None
        info = None

        if engine_path == "human":
            if verbose:
                print(f"  Step {state.step}/{MAX_STEP}")
            move = get_human_move(state)
        else:
            bestmove_uci, info = get_engine_move(
                engine_path, algo_name, params, uci_moves, time_limit, depth=depth
            )

            if bestmove_uci is None:
                if verbose:
                    print(
                        f"  >> {side_name} engine failed to return a move! {side_name} loses."
                    )
                return "black" if is_white else "white"

            try:
                move = UCIEngine.uci_to_move(bestmove_uci)
            except (ValueError, IndexError, KeyError):
                if verbose:
                    print(
                        f"  >> {side_name} engine returned invalid move '{bestmove_uci}'! {side_name} loses."
                    )
                return "black" if is_white else "white"

            if move not in state.legal_actions:
                if verbose:
                    print(
                        f"  >> {side_name} engine returned illegal move {format_move(move)}! {side_name} loses."
                    )
                return "black" if is_white else "white"

        uci_str = UCIEngine.move_to_uci(move)
        uci_moves.append(uci_str)

        if verbose:
            prefix = f"{move_number}." if is_white else f"{move_number}..."
            info_str = format_search_info(info)
            line = f"  {prefix} {side_name}: {format_move(move)}"
            if info_str:
                line += f" ({info_str})"
            print(line)

        state = state.next_state(move)

        if verbose:
            print_board(state)


def run_tournament(
    engine1_path, engine2_path, time_limit, algo1, algo2, num_games, verbose, depth=0, params=None
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
    """Parse arguments and run MiniChess CLI."""
    parser = argparse.ArgumentParser(
        description="MiniChess CLI - Run AI vs AI or Human vs AI matches via UCI protocol.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s --white build/minichess-uci.exe --black build/minichess-uci.exe --time 2000 --games 10
  %(prog)s --white human --black build/minichess-uci.exe --time 2000
  %(prog)s --white build/minichess-uci.exe --black build/minichess-uci.exe --white-algo pvs --black-algo alphabeta --time 2000
""",
    )

    parser.add_argument(
        "--white", required=True, help='Path to UCI engine for White, or "human".'
    )
    parser.add_argument(
        "--black", required=True, help='Path to UCI engine for Black, or "human".'
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
        "--param", action="append", default=[],
        help="Set engine param: --param UseNNUE=false. Can repeat.",
    )

    args = parser.parse_args()

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
        )

        result_map = {"white": "1-0", "black": "0-1", "draw": "1/2-1/2"}
        print(f"Result: {result_map[result]}")

    except KeyboardInterrupt:
        print("\nGame aborted.")


if __name__ == "__main__":
    main()
