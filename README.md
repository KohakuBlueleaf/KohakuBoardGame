# KohakuBoardGame

A multi-game board game engine framework with UBGI protocol, NNUE evaluation, and multiple search algorithms.

## Supported Games

| Game | Board | Pieces | Special Rules |
|------|-------|--------|---------------|
| **MiniChess** | 6x5 | P, R, N, B, Q, K | King capture wins. Pawn promotes on back rank. |
| **MiniShogi** | 5x5 | P, S, G, B, R, K + promoted | Captured pieces go to hand and can be dropped. |
| **Gomoku** | 9x9 | Black / White stones | 5-in-a-row wins. |

## Build

```bash
make all              # builds all game engines + tools
make minichess        # MiniChess UBGI engine (with NNUE)
make minishogi        # MiniShogi UBGI engine
make gomoku           # Gomoku UBGI engine
```

Requires `g++` with C++20 support. Builds with `-O3 -march=native` for SIMD.

### Tools

Per-game tool targets:

```bash
make minichess-datagen    # data generation for NNUE training
make minishogi-datagen
make gomoku-datagen

make minichess-selfplay   # self-play
make minichess-benchmark  # search benchmark
```

## Engine

```bash
./build/minichess-ubgi
./build/minishogi-ubgi
./build/gomoku-ubgi
```

All engines use the UBGI protocol and support `go depth/movetime/infinite`, `stop`, `setoption`, algorithm switching.

### Search Algorithms

| Algorithm | Description |
|-----------|-------------|
| **PVS** | Principal variation search with TT, null-move, LMR, quiescence, killer moves |
| **AlphaBeta** | Basic alpha-beta pruning |
| **MiniMax** | Exhaustive negamax |
| **Random** | Random legal move |

All features are independently toggled at runtime via UBGI options.

### Multi-PV

Set `MultiPV` option (1-10) to get top-K candidate moves with scores:

```
setoption name MultiPV value 3
```

### Evaluation

| Strategy | Flag | Description |
|----------|------|-------------|
| NNUE | `UseNNUE` | HalfKP features, 128-unit accumulator, SCReLU. AVX2/NEON SIMD. |
| KP Eval | `UseKPEval` | Material + piece-square tables |
| Material | (default) | Simple piece value sum |

NNUE feature extraction is per-game — each game's State class implements its own feature encoding via `extract_nnue_features()`.

## GUI

```bash
python gui/main.py                    # MiniChess (default)
python gui/main.py --game minishogi   # MiniShogi
python gui/main.py --game gomoku      # Gomoku
```

- Per-side engine + algorithm + search param configuration
- Multi-PV display: top-3 candidates shown as colored arrows (green/blue/orange)
- Background analysis with live PV, score, depth
- Score history plot + eval bar + move table
- Undo (Z), Pause/Resume (Space), Stop (Q)

## CLI

```bash
# Human vs AI
python cli/cli.py --game minichess --white human --black build/minichess-ubgi --time 2000

# AI vs AI
python cli/cli.py --game minishogi --white build/minishogi-ubgi --black build/minishogi-ubgi --depth 8

# Tournament
python cli/cli.py --white build/minichess-ubgi --black build/minichess-ubgi \
    --white-algo pvs --black-algo alphabeta --games 100 --time 2000
```

## NNUE Training Pipeline

### Data Generation

```bash
# Generate training data (all games supported)
./build/minichess-datagen -n 10000 -d 6 -o data/minichess_train.bin
./build/minishogi-datagen -n 10000 -d 6 -o data/minishogi_train.bin
./build/gomoku-datagen -n 10000 -d 6 -o data/gomoku_train.bin

# With NNUE model for stronger play
./build/minichess-datagen -n 10000 -d 6 -m models/nnue_v2.bin -o data/train.bin

# Parallel generation
bash scripts/gen_data.sh -g minichess -n 100000 -d 6 -j 8 -o data/
```

### Training

```bash
# Auto-detects game from data file header (v4 format)
python scripts/train_nnue.py --data "data/minichess_train.bin" --features halfkp --epochs 100

# Explicit game selection
python scripts/train_nnue.py --game minishogi --data "data/minishogi_train.bin" --features halfkp --epochs 100
python scripts/train_nnue.py --game gomoku --data "data/gomoku_train.bin" --features ps --epochs 100
```

### Inspect Data

```bash
python scripts/read_data.py --game minichess data/train.bin
```

## Project Structure

```
src/
  config.hpp                  # global settings (TT size, NNUE path)
  search_types.hpp            # SearchContext, SearchResult, RankedMove (Multi-PV)
  search_params.hpp           # ParamMap, ParamDef
  state/
    base_state.hpp            # BaseState — virtual interface for all games
  games/
    minichess/                # 6x5 chess: state, config, NNUE features
    minishogi/                # 5x5 shogi: state, config, drops, promotions
    gomoku/                   # 9x9 gomoku: state, config, threat eval
  policy/
    registry.hpp              # algorithm registry
    pvs.hpp/cpp               # PVS with 14 tunable features
    alphabeta.hpp/cpp         # alpha-beta
    minimax.hpp/cpp           # minimax
    random.hpp/cpp            # random
    pvs/
      tt.hpp                  # transposition table
      killer_moves.hpp        # killer move heuristic
      move_ordering.hpp       # MVV-LVA (per-game PIECE_VAL)
      quiescence.hpp          # quiescence search
  ubgi/
    ubgi.hpp/cpp              # UBGI protocol + MultiPV
  nnue/                       # NNUE: model, scalar/SIMD/quantized compute
gui/                          # Pygame GUI (all games)
cli/                          # CLI runner
scripts/                      # training pipeline (all games)
```

## Architecture

The multi-game framework compiles each game separately with different `-I` paths. `#include "config.hpp"` and `#include "state.hpp"` resolve to game-specific files at compile time. Search algorithms, UBGI protocol, and training tools are fully game-agnostic.

```
Game config (compile-time)    Search (game-agnostic)
    |                              |
    v                              v
  State : BaseState ───────> PVS / AB / MM / Random
    |                              |
    v                              v
  evaluate()                 SearchResult + Multi-PV
  extract_nnue_features()    RootUpdate callback
  get_legal_actions()        UBGI protocol
```

Each game defines:
- Board representation and legal move generation
- Evaluation function (material, PST, game-specific heuristics)
- NNUE feature extraction (optional, via `extract_nnue_features()` override)
- Per-game `PIECE_VAL[]` for MVV-LVA move ordering
