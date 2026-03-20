#pragma once
#include "../../config.hpp"

#ifndef BOARD_H
#define BOARD_H 5
#endif
#ifndef BOARD_W
#define BOARD_W 5
#endif

#define MAX_STEP 200

/* Piece types (unpromoted) */
#define EMPTY   0
#define PAWN    1
#define SILVER  2
#define GOLD    3
#define BISHOP  4
#define ROOK    5
#define KING    6

/* Promoted pieces */
#define P_PAWN   7   /* tokin = promoted pawn, moves like gold */
#define P_SILVER 8   /* promoted silver, moves like gold */
#define P_BISHOP 9   /* horse = promoted bishop (bishop + king) */
#define P_ROOK   10  /* dragon = promoted rook (rook + king) */

#define NUM_PIECE_TYPES 11  /* 0-10 */
#define NUM_PT_NO_KING  10  /* all except king (gap at index 5) */
#define NUM_HAND_TYPES 5    /* pawn, silver, gold, bishop, rook (indices 1-5) */

/* Default NNUE model path */
#undef NNUE_FILE
#define NNUE_FILE "models/minishogi-nnue_v1.bin"

/* Drop moves use sentinel row = BOARD_H in the from-point */
#define DROP_ROW BOARD_H

/* Piece display */
#define PIECE_STR_LEN 3
const char PIECE_TABLE[2][NUM_PIECE_TYPES][4] = {
    {"  ", " P", " S", " G", " B", " R", " K", "+P", "+S", "+B", "+R"},
    {"  ", " p", " s", " g", " b", " r", " k", "+p", "+s", "+b", "+r"},
};
