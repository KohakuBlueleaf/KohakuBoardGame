#pragma once
#include "../../config.hpp"

/* === Standard Shogi Board (9x9) === */
#ifndef BOARD_H
#define BOARD_H 9
#endif
#ifndef BOARD_W
#define BOARD_W 9
#endif

#define MAX_STEP 512

/* === Piece types === */
#define EMPTY     0
#define PAWN      1
#define SILVER    2
#define GOLD      3
#define LANCE     4
#define KNIGHT    5
#define BISHOP    6
#define ROOK      7
#define KING      8
#define P_PAWN    9
#define P_SILVER  10
#define P_LANCE   11
#define P_KNIGHT  12
#define P_BISHOP  13   /* Horse (馬) */
#define P_ROOK    14   /* Dragon (龍) */

#define NUM_PIECE_TYPES 15
#define NUM_HAND_TYPES  7   /* PAWN..ROOK (indices 1-7) */
#define KING_ID         8
#define NUM_PT_NO_KING  13  /* piece types excluding KING (for NNUE) */

/* Drop row sentinel (must be >= BOARD_H) */
#define DROP_ROW BOARD_H

/* Drop piece letters for UCI notation: index 1-7 = P S G L N B R */
static const char DROP_LETTERS[] = " PSGLNBR";

/* MVV-LVA piece values for move ordering */
static const int PIECE_VALUES[] = {
    0,     /* EMPTY */
    10,    /* PAWN */
    40,    /* SILVER */
    50,    /* GOLD */
    30,    /* LANCE */
    35,    /* KNIGHT */
    70,    /* BISHOP */
    90,    /* ROOK */
    900,   /* KING */
    50,    /* P_PAWN */
    50,    /* P_SILVER */
    50,    /* P_LANCE */
    50,    /* P_KNIGHT */
    120,   /* P_BISHOP */
    130,   /* P_ROOK */
};

/* === Piece display === */
#define PIECE_STR_LEN 3
static const char PIECE_TABLE[2][NUM_PIECE_TYPES][5] = {
    {"  ", "sP", "sS", "sG", "sL", "sN", "sB", "sR", "sK",
     "s+P","s+S","s+L","s+N","s+B","s+R"},
    {"  ", "gP", "gS", "gG", "gL", "gN", "gB", "gR", "gK",
     "g+P","g+S","g+L","g+N","g+B","g+R"},
};

/* Unicode piece chars for display */
static const char PIECE_UNICODE[2][NUM_PIECE_TYPES][5] = {
    {" ", "歩", "銀", "金", "香", "桂", "角", "飛", "王",
     "と", "全", "杏", "圭", "馬", "龍"},
    {" ", "歩", "銀", "金", "香", "桂", "角", "飛", "玉",
     "と", "全", "杏", "圭", "馬", "龍"},
};
