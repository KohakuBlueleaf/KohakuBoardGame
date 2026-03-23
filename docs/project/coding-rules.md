# Coding Rules & Style Guide

## Architecture Principles

1. **Game-agnostic core**: Everything outside `src/games/` is game-agnostic. Search algorithms, NNUE, UBGI protocol, TT, move ordering — NONE of these should reference game-specific types or constants.

2. **Game module boundary**: Each game lives in `src/games/<name>/` and exposes ONLY through `config.hpp` (constants) and `state.hpp/cpp` (State class inheriting BaseState). If more structure is needed, add files within the game directory (e.g. `eval.cpp`, `movegen.cpp`).

3. **Minimal BaseState interface**: Games implement the virtual interface. The search only calls BaseState methods. No downcasting, no game-specific hooks in search code.

## C++ Style

1. **C-style C++**: Write C with classes and useful STL. No templates (except STL containers), no RAII patterns beyond simple cases, no smart pointers, no exceptions, no CRTP, no metaprogramming.

2. **Includes**: Sorted and grouped:
   ```cpp
   /* Standard library */
   #include <cstdint>
   #include <cstring>
   #include <vector>

   /* Project headers */
   #include "config.hpp"
   #include "state.hpp"

   /* Optional/conditional */
   #ifdef USE_NNUE
   #include "../../nnue/nnue.hpp"
   #endif
   ```

3. **Naming**: `snake_case` for functions/variables, `PascalCase` for classes/structs, `UPPER_CASE` for macros/constants.

4. **Functions**: Keep under 80 lines. If longer, split into helpers.

5. **Memory**: `new`/`delete` paired. Caller or callee owns — document which. Search's `eval_ctx` takes ownership of the state pointer.

6. **No globals except**: TT (inline in header), search history (inline in header), Zobrist tables (static in .cpp).

## Python Style

1. **black** formatter, always.
2. Game engines export public names without underscore prefix.
3. Config values stored in `gui/config.py`, not hardcoded.
4. GUI main.py should be split: dialogs, engine management, rendering are separate concerns.

## Game Module Contract

Each game in `src/games/<name>/` must provide:

- `config.hpp`: BOARD_H, BOARD_W, piece type constants, MAX_STEP, NUM_PIECE_TYPES, NUM_HAND_TYPES, DROP_LETTERS (if drops), KING_ID, material values for MVV-LVA
- `state.hpp`: Board struct, State class
- `state.cpp`: All BaseState virtual methods implemented

The game module may also provide:
- `eval.cpp`: Evaluation function (if large)
- `movegen.cpp`: Move generation (if large)
- Game-specific MVV-LVA values via a `PIECE_VALUES` array in config.hpp

## MVV-LVA Contract

Each game's `config.hpp` must define:
```cpp
static const int PIECE_VALUES[NUM_PIECE_TYPES] = { ... };
```
The search's move ordering reads `PIECE_VALUES[captured]` — array must cover ALL piece type IDs.
