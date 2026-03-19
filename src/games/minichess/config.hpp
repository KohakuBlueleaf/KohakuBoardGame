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

/* === Piece display === */
#define PIECE_STR_LEN 2
const char PIECE_TABLE[2][7][5] = {
    {"  ", "wP", "wR", "wn", "wB", "wQ", "wK"},
    {"  ", "bP", "bR", "bn", "bB", "bQ", "bK"},
};
