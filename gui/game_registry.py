"""Game registry — module-level imports and board configuration for all games."""

try:
    import gui.config as _cfg
except ImportError:
    import config as _cfg

# ---------------------------------------------------------------------------
# Module-level imports for each game (dual import path: gui.games.X / games.X)
# ---------------------------------------------------------------------------

try:
    from gui.games.connect6_engine import (
        Connect6State,
        format_move as _connect6_format_move,
        PLAYER_LABELS as _connect6_labels,
        PLAYER_COLORS as _connect6_colors,
    )
    from gui.games.connect6_renderer import Connect6Renderer
except ImportError:
    from games.connect6_engine import (
        Connect6State,
        format_move as _connect6_format_move,
        PLAYER_LABELS as _connect6_labels,
        PLAYER_COLORS as _connect6_colors,
    )
    from games.connect6_renderer import Connect6Renderer

try:
    from gui.games.minishogi_engine import (
        MiniShogiState,
        format_move as _minishogi_format_move,
        PLAYER_LABELS as _minishogi_labels,
        PLAYER_COLORS as _minishogi_colors,
        DROP_PIECE_CHAR as _minishogi_drop_char,
        CHAR_TO_DROP_PIECE as _minishogi_char_to_drop,
        PROMOTE_MAP as _minishogi_promote_map,
    )
    from gui.games.minishogi_renderer import MiniShogiRenderer
except ImportError:
    from games.minishogi_engine import (
        MiniShogiState,
        format_move as _minishogi_format_move,
        PLAYER_LABELS as _minishogi_labels,
        PLAYER_COLORS as _minishogi_colors,
        DROP_PIECE_CHAR as _minishogi_drop_char,
        CHAR_TO_DROP_PIECE as _minishogi_char_to_drop,
        PROMOTE_MAP as _minishogi_promote_map,
    )
    from games.minishogi_renderer import MiniShogiRenderer

try:
    from gui.games.kohakushogi_engine import (
        KohakuShogiState,
        format_move as _kohakushogi_format_move,
        PLAYER_LABELS as _kohakushogi_labels,
        PLAYER_COLORS as _kohakushogi_colors,
        DROP_PIECE_CHAR as _kohakushogi_drop_char,
        CHAR_TO_DROP_PIECE as _kohakushogi_char_to_drop,
        PROMOTE_MAP as _kohakushogi_promote_map,
    )
    from gui.games.kohakushogi_renderer import KohakuShogiRenderer
except ImportError:
    from games.kohakushogi_engine import (
        KohakuShogiState,
        format_move as _kohakushogi_format_move,
        PLAYER_LABELS as _kohakushogi_labels,
        PLAYER_COLORS as _kohakushogi_colors,
        DROP_PIECE_CHAR as _kohakushogi_drop_char,
        CHAR_TO_DROP_PIECE as _kohakushogi_char_to_drop,
        PROMOTE_MAP as _kohakushogi_promote_map,
    )
    from games.kohakushogi_renderer import KohakuShogiRenderer

try:
    from gui.games.shogi_engine import (
        ShogiState,
        format_move as _shogi_format_move,
        PLAYER_LABELS as _shogi_labels,
        PLAYER_COLORS as _shogi_colors,
        DROP_PIECE_CHAR as _shogi_drop_char,
        CHAR_TO_DROP_PIECE as _shogi_char_to_drop,
        PROMOTE_MAP as _shogi_promote_map,
    )
    from gui.games.shogi_renderer import ShogiRenderer
except ImportError:
    from games.shogi_engine import (
        ShogiState,
        format_move as _shogi_format_move,
        PLAYER_LABELS as _shogi_labels,
        PLAYER_COLORS as _shogi_colors,
        DROP_PIECE_CHAR as _shogi_drop_char,
        CHAR_TO_DROP_PIECE as _shogi_char_to_drop,
        PROMOTE_MAP as _shogi_promote_map,
    )
    from games.shogi_renderer import ShogiRenderer

try:
    from gui.games.kohakuchess_engine import (
        KohakuChessState,
        format_move as _kohakuchess_format_move,
        PLAYER_LABELS as _kohakuchess_labels,
        PLAYER_COLORS as _kohakuchess_colors,
    )
    from gui.games.kohakuchess_renderer import KohakuChessRenderer
except ImportError:
    from games.kohakuchess_engine import (
        KohakuChessState,
        format_move as _kohakuchess_format_move,
        PLAYER_LABELS as _kohakuchess_labels,
        PLAYER_COLORS as _kohakuchess_colors,
    )
    from games.kohakuchess_renderer import KohakuChessRenderer

try:
    from gui.games.chess_engine import (
        ChessState,
        format_move as _chess_format_move,
        PLAYER_LABELS as _chess_labels,
        PLAYER_COLORS as _chess_colors,
    )
    from gui.games.chess_renderer import ChessRenderer
except ImportError:
    from games.chess_engine import (
        ChessState,
        format_move as _chess_format_move,
        PLAYER_LABELS as _chess_labels,
        PLAYER_COLORS as _chess_colors,
    )
    from games.chess_renderer import ChessRenderer

try:
    from gui.games.minichess_engine import (
        MiniChessState,
        format_move as _minichess_format_move,
        PLAYER_LABELS as _minichess_labels,
        PLAYER_COLORS as _minichess_colors,
    )
    from gui.games.minichess_renderer import MiniChessRenderer
except ImportError:
    from games.minichess_engine import (
        MiniChessState,
        format_move as _minichess_format_move,
        PLAYER_LABELS as _minichess_labels,
        PLAYER_COLORS as _minichess_colors,
    )
    from games.minichess_renderer import MiniChessRenderer


# ---------------------------------------------------------------------------
# Game registry — maps canonical names to tuples of game components.
# Each entry: (StateClass, format_move, RendererClass, labels, colors,
#              drop_char | None, char_to_drop | None, promote_map | None)
# ---------------------------------------------------------------------------

_GAME_REGISTRY: dict[str, tuple] = {
    "connect6": (
        Connect6State,
        _connect6_format_move,
        Connect6Renderer,
        _connect6_labels,
        _connect6_colors,
        None,
        None,
        None,
    ),
    "minishogi": (
        MiniShogiState,
        _minishogi_format_move,
        MiniShogiRenderer,
        _minishogi_labels,
        _minishogi_colors,
        _minishogi_drop_char,
        _minishogi_char_to_drop,
        _minishogi_promote_map,
    ),
    "kohakushogi": (
        KohakuShogiState,
        _kohakushogi_format_move,
        KohakuShogiRenderer,
        _kohakushogi_labels,
        _kohakushogi_colors,
        _kohakushogi_drop_char,
        _kohakushogi_char_to_drop,
        _kohakushogi_promote_map,
    ),
    "shogi": (
        ShogiState,
        _shogi_format_move,
        ShogiRenderer,
        _shogi_labels,
        _shogi_colors,
        _shogi_drop_char,
        _shogi_char_to_drop,
        _shogi_promote_map,
    ),
    "kohakuchess": (
        KohakuChessState,
        _kohakuchess_format_move,
        KohakuChessRenderer,
        _kohakuchess_labels,
        _kohakuchess_colors,
        None,
        None,
        None,
    ),
    "chess": (
        ChessState,
        _chess_format_move,
        ChessRenderer,
        _chess_labels,
        _chess_colors,
        None,
        None,
        None,
    ),
    "minichess": (
        MiniChessState,
        _minichess_format_move,
        MiniChessRenderer,
        _minichess_labels,
        _minichess_colors,
        None,
        None,
        None,
    ),
}


def get_game_module(game_name: str) -> tuple:
    """Return (StateClass, format_move, RendererClass, player_labels, player_colors).

    Also sets _cfg.DROP_PIECE_CHAR, _cfg.CHAR_TO_DROP_PIECE, _cfg.PROMOTE_MAP
    for shogi-family games.
    """
    # Reset drop config (overridden by shogi games)
    _cfg.DROP_PIECE_CHAR = {}
    _cfg.CHAR_TO_DROP_PIECE = {}

    key = game_name.lower().replace(" ", "")
    entry = _GAME_REGISTRY.get(key, _GAME_REGISTRY["minichess"])

    (
        state_cls,
        fmt_move,
        renderer_cls,
        labels,
        colors,
        drop_char,
        char_to_drop,
        promote_map,
    ) = entry

    if drop_char is not None:
        _cfg.DROP_PIECE_CHAR = drop_char
    if char_to_drop is not None:
        _cfg.CHAR_TO_DROP_PIECE = char_to_drop
    if promote_map is not None:
        _cfg.PROMOTE_MAP = promote_map

    return state_cls, fmt_move, renderer_cls, labels, colors


# ---------------------------------------------------------------------------
# Board size configuration — data-driven via match/case
# ---------------------------------------------------------------------------


def configure_board_size(game_name: str) -> None:
    """Set config board dimensions based on game type."""
    key = game_name.lower().replace(" ", "")

    # Reset hand row height (only shogi variants use it)
    _cfg.HAND_ROW_H = 0

    match key:
        case "connect6":
            _cfg.BOARD_H = 15
            _cfg.BOARD_W = 15
            _cfg.SQUARE_SIZE = 36
            _cfg.MAX_STEP = _cfg.BOARD_H * _cfg.BOARD_W
            _cfg.SCORE_PLOT_MAX_CP = 10000
            _cfg.SCORE_DISPLAY_DIV = 2000
        case "minishogi":
            _cfg.BOARD_H = 5
            _cfg.BOARD_W = 5
            _cfg.SQUARE_SIZE = 70
            _cfg.MAX_STEP = 200
            _cfg.SCORE_PLOT_MAX_CP = 2000
            _cfg.SCORE_DISPLAY_DIV = 100
            _cfg.HAND_ROW_H = 60
        case "kohakushogi":
            _cfg.BOARD_H = 7
            _cfg.BOARD_W = 6
            _cfg.SQUARE_SIZE = 64
            _cfg.MAX_STEP = 300
            _cfg.SCORE_PLOT_MAX_CP = 2000
            _cfg.SCORE_DISPLAY_DIV = 100
            _cfg.HAND_ROW_H = 60
        case "shogi":
            _cfg.BOARD_H = 9
            _cfg.BOARD_W = 9
            _cfg.SQUARE_SIZE = 56
            _cfg.MAX_STEP = 512
            _cfg.SCORE_PLOT_MAX_CP = 2000
            _cfg.SCORE_DISPLAY_DIV = 100
            _cfg.HAND_ROW_H = 60
        case "kohakuchess":
            _cfg.BOARD_H = 6
            _cfg.BOARD_W = 6
            _cfg.SQUARE_SIZE = 80
            _cfg.MAX_STEP = 150
            _cfg.SCORE_PLOT_MAX_CP = 500
            _cfg.SCORE_DISPLAY_DIV = 100
        case "chess":
            _cfg.BOARD_H = 8
            _cfg.BOARD_W = 8
            _cfg.SQUARE_SIZE = 60
            _cfg.MAX_STEP = 300
            _cfg.SCORE_PLOT_MAX_CP = 500
            _cfg.SCORE_DISPLAY_DIV = 100
        case _:  # minichess (default)
            _cfg.BOARD_H = 6
            _cfg.BOARD_W = 5
            _cfg.SQUARE_SIZE = 80
            _cfg.MAX_STEP = 100
            _cfg.SCORE_PLOT_MAX_CP = 500
            _cfg.SCORE_DISPLAY_DIV = 100

    _cfg.BOARD_PIXEL_W = _cfg.BOARD_W * _cfg.SQUARE_SIZE
    _cfg.BOARD_PIXEL_H = _cfg.BOARD_H * _cfg.SQUARE_SIZE
    _cfg.COL_LABELS = "".join(chr(65 + i) for i in range(_cfg.BOARD_W))
    _cfg.ROW_LABELS = [str(_cfg.BOARD_H - i) for i in range(_cfg.BOARD_H)]

    # Hand rows for games with captured pieces (e.g. shogi variants)
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
