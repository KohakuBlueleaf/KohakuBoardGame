#pragma once

/* === Board === */
#define BOARD_H 6
#define BOARD_W 5

/* === Game rules === */
#define RANDOM_SEED 123
#define TIMEOUT_LIMIT 2
#define MAX_STEP 100

/* === Compile-time features === */

// Bitboard move generation (~2-4x faster than naive)
#define USE_BITBOARD

// Default TT size (can be changed at runtime via UCI "Hash" option)
#define DEFAULT_TT_SIZE_BITS 18

/* === NNUE (compile-time: controls whether nnue code is included) === */
#ifndef NO_NNUE
#define USE_NNUE
#endif
// #define NNUE_EMBEDDED
#define NNUE_FILE "models/nnue_v1.bin"
#define USE_NNUE_SIMD

/* === Piece display === */
#define PIECE_STR_LEN 2
const char PIECE_TABLE[2][7][5] = {
    {"  ", "wP", "wR", "wn", "wB", "wQ", "wK"},
    {"  ", "bP", "bR", "bn", "bB", "bQ", "bK"},
};
