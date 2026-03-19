# MiniChess

A 6x5 chess variant engine with UBGI protocol, NNUE evaluation, and multiple search algorithms. Also supports Gomoku (9x9, 5-in-a-row).

## Build

```bash
make all        # builds minichess ubgi engine + selfplay, benchmark, datagen, nnue_bench
make ubgi       # UBGI engine only
```

Requires `g++` with C++20 support. Builds with `-O3 -march=native` for SIMD.

Without NNUE:
```bash
make CXXFLAGS="-std=c++2a -O3 -DNO_NNUE" ubgi
```

## Board

```
  A  B  C  D  E
6 bR bn bB bQ bK
5 bP bP bP bP bP
4  .  .  .  .  .
3  .  .  .  .  .
2 wP wP wP wP wP
1 wR wn wB wQ wK
```

6x5 board. King capture wins. Pawns promote on back rank. Draw after 100 steps with equal material.

## Engine

```bash
./build/minichess-ubgi
```

Supports `go depth/movetime/infinite`, `stop`, `setoption`, algorithm switching via UBGI protocol.

### Runtime Parameters

Each algorithm defines its own parameter set. Switching algorithm loads its defaults:

```
setoption name Algorithm value pvs
```

**PVS** (14 params):
```
UseNNUE, UseKPEval, UseEvalMobility, UseMoveOrdering,
UseQuiescence (QuiescenceMaxDepth), UseTT,
UseKillerMoves (KillerSlots), UseNullMove (NullMoveR),
UseLMR (LMRFullDepth, LMRDepthLimit)
```

**AlphaBeta / MiniMax** (3 params): `UseNNUE, UseKPEval, UseEvalMobility`

**Random**: no params.

**Global**: `Hash` (TT size in bits, 2^N entries).

Parameters are advertised dynamically via UBGI protocol based on the current algorithm.

## GUI

```bash
python gui/main.py
```

- Per-side engine + algorithm + search param configuration
- [Params...] button opens modal editor with algo-specific options (read from engine)
- Mode derived from selections: Human/Human, Human/AI, AI/AI
- Background analysis toggle with live PV, score, depth display
- Score history plot with white/black move markers
- Vertical eval bar + move table in bottom panel
- Undo (Z), Pause/Resume (Space)

## CLI

```bash
# Human vs AI
python cli/cli.py --white human --black build/minichess-ubgi.exe --time 2000

# AI vs AI tournament
python cli/cli.py --white build/minichess-ubgi.exe --black build/minichess-ubgi.exe \
    --white-algo pvs --black-algo alphabeta --games 100 --time 2000

# Fixed depth
python cli/cli.py --white build/minichess-ubgi.exe --black build/minichess-ubgi.exe --depth 8
```

## Evaluation

Three strategies, selectable at runtime per algorithm:

| Strategy | Flag | Description |
|----------|------|-------------|
| NNUE | `UseNNUE` | HalfKP features, 128-unit accumulator, SCReLU. AVX2/NEON SIMD. |
| KP Eval | `UseKPEval` | Material (10x) + piece-square tables + king tropism |
| Material | (default when KP off) | Simple piece value sum |

Mobility bonus (`UseEvalMobility`) adds points per legal move advantage.

## Search

PVS combines:
- Iterative deepening with TT seeding across depths
- Null-window re-search (PVS framework)
- Transposition table (Zobrist, dynamic size, always-replace)
- Quiescence search (captures only at depth 0)
- Move ordering: TT best move > MVV-LVA captures > killer moves > quiet
- Null move pruning (pass at reduced depth)
- Late move reductions (reduce late quiet moves)

All features toggled independently at runtime.

## NNUE Training

```bash
./build/datagen -n 10000 -d 6 -o data/train.bin
python scripts/train_nnue.py --data "data/train_*.bin" --features halfkp --epochs 100
```

Binary format: 66 bytes/record (board + player + score + result + ply).

## Project Structure

```
src/
  config.hpp                # board size, compile-time flags (NNUE, bitboard)
  search_params.hpp         # ParamMap (generic key-value), ParamDef, helpers
  search_types.hpp          # SearchContext, SearchResult
  policy/
    registry.hpp            # algorithm registry (name, defaults, param_defs, search)
    pvs.hpp/cpp             # PVS — PVSParams, 14 tunable features
    alphabeta.hpp/cpp       # alpha-beta — ABParams
    minimax.hpp/cpp         # minimax — MMParams
    random.hpp/cpp          # random move
    pvs/
      tt.hpp                # transposition table (dynamic allocation)
      killer_moves.hpp      # killer move heuristic
      move_ordering.hpp     # MVV-LVA + killer ordering
      quiescence.hpp        # quiescence search
  ubgi/
    ubgi.hpp/cpp            # UBGI protocol, dynamic option advertisement
  games/
    minichess/              # MiniChess state, move gen (bitboard), eval
    gomoku/                 # Gomoku state, threat-based eval
  nnue/                     # NNUE: model, scalar/SIMD/quantized kernels
gui/                        # Pygame GUI
cli/                        # CLI tournament runner
scripts/                    # training pipeline
```

## Architecture

```
UBGI setoption ──> ParamMap (map<string,string>)
                       |
           ┌───────────┼───────────┐
           v           v           v
     PVS::search   AB::search   MM::search
           |           |           |
     PVSParams     ABParams     MMParams
     ::from_map()  ::from_map() ::from_map()
```

Each algorithm owns its typed params struct, default values, and UBGI option definitions. The registry maps names to search functions and defaults. The engine dynamically advertises options based on the selected algorithm.
