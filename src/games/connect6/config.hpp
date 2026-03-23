#pragma once
#include "../../config.hpp"

#ifndef BOARD_H
#define BOARD_H 15
#endif
#ifndef BOARD_W
#define BOARD_W 15
#endif

#define WIN_LENGTH 6
#define MAX_STEP (BOARD_H * BOARD_W)

/* Piece type counts (used by NNUE if enabled) */
#define NUM_PIECE_TYPES 2   /* 1=Black, 2=White */
#define NUM_PT_NO_KING  2   /* no king in connect6 */
#define KING_ID         0   /* no king */

/* MVV-LVA piece values for move ordering (indexed by piece type) */
static const int PIECE_VALUES[] = {
    0,  /* EMPTY=0 */
    1,  /* Black=1 */
    1,  /* White=2 */
};
