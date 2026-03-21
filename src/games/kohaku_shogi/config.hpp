#pragma once
#include "../../config.hpp"

#ifndef BOARD_H
#define BOARD_H 7
#endif
#ifndef BOARD_W
#define BOARD_W 6
#endif

#define MAX_STEP 300

/* Piece types (unpromoted) */
#define EMPTY   0
#define PAWN    1
#define SILVER  2
#define GOLD    3
#define LANCE   4
#define KNIGHT  5
#define BISHOP  6
#define ROOK    7
#define KING    8

/* Promoted pieces */
#define P_PAWN    9   /* tokin = promoted pawn, moves like gold */
#define P_SILVER  10  /* promoted silver, moves like gold */
#define P_LANCE   11  /* promoted lance, moves like gold */
#define P_KNIGHT  12  /* promoted knight, moves like gold */
#define P_BISHOP  13  /* horse = promoted bishop (bishop + 1-step orthogonal) */
#define P_ROOK    14  /* dragon = promoted rook (rook + 1-step diagonal) */

#define NUM_PIECE_TYPES 15  /* 0-14 */
#define NUM_PT_NO_KING  14  /* all except king (gap at index 8) */
#define KING_ID         8
#undef  NUM_HAND_TYPES
#define NUM_HAND_TYPES  7   /* pawn, silver, gold, lance, knight, bishop, rook (indices 1-7) */

/* Drop piece letters for UBGI protocol (index 0 unused, 1-7 = P S G L N B R) */
static const char DROP_LETTERS[] = " PSGLNBR";

/* Default NNUE model path */
#undef NNUE_FILE
#define NNUE_FILE "models/nnue.bin"

/* Drop moves use sentinel row = BOARD_H in the from-point */
#define DROP_ROW BOARD_H

/* Piece display */
#define PIECE_STR_LEN 3
const char PIECE_TABLE[2][NUM_PIECE_TYPES][4] = {
    {"  ", " P", " S", " G", " L", " N", " B", " R", " K", "+P", "+S", "+L", "+N", "+B", "+R"},
    {"  ", " p", " s", " g", " l", " n", " b", " r", " k", "+p", "+s", "+l", "+n", "+b", "+r"},
};
