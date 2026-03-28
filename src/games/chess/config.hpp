#pragma once
#include "../../config.hpp"

/* === Standard Chess Board (8x8) === */
#ifndef BOARD_H
#define BOARD_H 8
#endif
#ifndef BOARD_W
#define BOARD_W 8
#endif

#define MAX_STEP 300
#define USE_BITBOARD

/* === Piece types === */
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
    0,    /* EMPTY=0 */
    10,   /* PAWN=1 */
    50,   /* ROOK=2 */
    30,   /* KNIGHT=3 */
    30,   /* BISHOP=4 */
    90,   /* QUEEN=5 */
    900,  /* KING=6 */
};

/* === Piece display === */
#define PIECE_STR_LEN 2
static const char PIECE_TABLE[2][7][5] = {
    {"  ", "wP", "wR", "wN", "wB", "wQ", "wK"},
    {"  ", "bP", "bR", "bN", "bB", "bQ", "bK"},
};

/* Unicode piece chars for encode_output */
static const char PIECE_UNICODE[2][7][5] = {
    {" ", "♙", "♖", "♘", "♗", "♕", "♔"},
    {" ", "♟", "♜", "♞", "♝", "♛", "♚"},
};
