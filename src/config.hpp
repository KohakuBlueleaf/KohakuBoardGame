#pragma once

/* === Global settings === */
#define RANDOM_SEED 123
#define TIMEOUT_LIMIT 2

/* === TT === */
#define DEFAULT_TT_SIZE_BITS 18

/* === NNUE === */
#ifndef NO_NNUE
#define USE_NNUE
#endif
#define NNUE_FILE "models/nnue.bin"
#define USE_NNUE_SIMD

/* === Drop pieces (for games without drops, defaults to 0) === */
#ifndef NUM_HAND_TYPES
#define NUM_HAND_TYPES 0
#endif
