#pragma once
#include "../../config.hpp"

/* === MiniChess Board === */
#ifndef BOARD_H
#define BOARD_H 6
#endif
#ifndef BOARD_W
#define BOARD_W 5
#endif

#define MAX_STEP 100
#define USE_BITBOARD

/* === NNUE feature layout === */
#define NNUE_NUM_PIECE_TYPES 6
#define NNUE_NUM_PT_NO_KING 5

/* === MVV-LVA piece values for move ordering === */
#define NUM_PIECE_VALS 7
static const int PIECE_VAL[NUM_PIECE_VALS] = {
    /* EMPTY */ 0, /* PAWN */ 2, /* ROOK */ 6, /* KNIGHT */ 7,
    /* BISHOP */ 8, /* QUEEN */ 20, /* KING */ 100,
};

/* === Piece display === */
#define PIECE_STR_LEN 2
const char PIECE_TABLE[2][7][5] = {
    {"  ", "wP", "wR", "wn", "wB", "wQ", "wK"},
    {"  ", "bP", "bR", "bn", "bB", "bQ", "bK"},
};
