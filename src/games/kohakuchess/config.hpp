#pragma once
#include "../../config.hpp"

/* === Kohaku Chess Board (6x7) === */
#ifndef BOARD_H
#define BOARD_H 7
#endif
#ifndef BOARD_W
#define BOARD_W 6
#endif

#define MAX_STEP 200
#define USE_BITBOARD

/* === Piece types (same IDs as minichess) === */
#define EMPTY   0
#define PAWN    1
#define ROOK    2
#define KNIGHT  3
#define BISHOP  4
#define QUEEN   5
#define KING    6

/* === Piece type counts (used by NNUE) === */
#define NUM_PIECE_TYPES 6
#define NUM_PT_NO_KING  5
#define KING_ID         6

/* MVV-LVA piece values for move ordering (indexed by piece type) */
static const int PIECE_VALUES[] = {
    0,   /* EMPTY=0 */
    10,  /* PAWN=1 */
    50,  /* ROOK=2 */
    30,  /* KNIGHT=3 */
    30,  /* BISHOP=4 */
    90,  /* QUEEN=5 */
    900, /* KING=6 */
};

/* === Piece display === */
#define PIECE_STR_LEN 2
const char PIECE_TABLE[2][7][5] = {
    {"  ", "wP", "wR", "wn", "wB", "wQ", "wK"},
    {"  ", "bP", "bR", "bn", "bB", "bQ", "bK"},
};
