#pragma once
#include "../../config.hpp"

#ifndef BOARD_H
#define BOARD_H 15
#endif
#ifndef BOARD_W
#define BOARD_W 15
#endif

#define WIN_LENGTH 5
#define MAX_STEP (BOARD_H * BOARD_W)

/* Piece type counts (used by NNUE if enabled) */
#define NUM_PIECE_TYPES 2   /* 1=X, 2=O */
#define NUM_PT_NO_KING  2   /* no king in gomoku */
#define KING_ID         0   /* no king */
