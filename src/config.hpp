#pragma once

/*Board Size, Don't change!*/
#define BOARD_H 6
#define BOARD_W 5

/*You can modify these things in development for fast testing*/
/*When TA run your program, we will use default settings (123, 10, 50)*/
#define RANDOM_SEED 123
#define timeout 2
#define MAX_STEP 100


/*
 * Evaluation and search options (uncomment to enable)
 *
 * USE_KP_EVAL: King-Piece evaluation with piece-square tables + king tropism
 *   For games with a "king" piece (MiniChess, Chess, Shogi).
 *   Pieces are valued based on their position AND their relation to kings.
 *
 * USE_MOVE_ORDERING: Sort moves before search (captures first via MVV-LVA)
 *   Essential for PVS to be effective. Also helps plain alpha-beta.
 *
 * Note: USE_KP_EVAL and USE_PP_EVAL are mutually exclusive.
 */
#define USE_KP_EVAL
#define USE_MOVE_ORDERING

/*
 * USE_QUIESCENCE: Continue searching captures at depth 0 until the position
 *   is "quiet". Prevents the horizon effect (e.g., evaluating mid-capture).
 *   Pairs naturally with PVS. Max quiescence depth is capped for safety.
 */
#define USE_QUIESCENCE
#define QUIESCENCE_MAX_DEPTH 16

/*
 * USE_TRANSPOSITION_TABLE: Cache searched positions to avoid redundant work.
 *   Positions reached via different move orders share results.
 *   Also provides best-move hints for move ordering (huge for PVS).
 *   TT_SIZE_BITS controls table size: 2^N entries (~24 bytes each).
 *   18 = 256K entries (~6MB), 20 = 1M entries (~24MB).
 */
#define USE_TRANSPOSITION_TABLE
#define TT_SIZE_BITS 18

/*
 * USE_BITBOARD: Use bitboard-based move generation (uint32_t for 6x5=30 bits).
 *   Precomputed attack tables for leapers (knight, king, pawn).
 *   Bit-scan iteration instead of nested loops.
 *   ~2-4x faster than naive array-based generation on this board size.
 */
#define USE_BITBOARD

/*
 * USE_KILLER_MOVES: Store quiet moves that caused beta cutoffs, 2 slots per ply.
 *   Killers rank below captures but above other quiet moves in move ordering.
 *   Requires USE_MOVE_ORDERING to have any effect.
 */
// #define USE_KILLER_MOVES
#define KILLER_SLOTS 2

/*
 * USE_NULL_MOVE: Skip a turn (pass) with reduced depth; if still >= beta, prune.
 *   Based on the assumption that doing nothing is rarely better than the best move.
 *   NULL_MOVE_R controls the depth reduction for the null move search.
 */
// #define USE_NULL_MOVE
#define NULL_MOVE_R 2

/*
 * USE_LMR: Late Move Reduction — reduce depth for late quiet moves that are
 *   unlikely to be good. Saves search time on moves ordered near the end.
 *   LMR_FULL_DEPTH: search first N moves at full depth before reducing.
 *   LMR_DEPTH_LIMIT: only apply LMR when remaining depth >= this value.
 */
// #define USE_LMR
#define LMR_FULL_DEPTH 3
#define LMR_DEPTH_LIMIT 3

/*
 * Additional evaluation features (additive, each independent)
 * All require USE_KP_EVAL as the base. Values are added on top of KP score.
 *
 * USE_EVAL_MOBILITY: Bonus for having more legal moves than opponent.
 *   More moves = more flexibility = stronger position.
 */
#define USE_EVAL_MOBILITY


/*Which character/words for pieces*/
/* By default, the pieces are '♟', '♜', '♞', '♝', '♛', '♚' from unicode*/
// #define PIECE_STR_LEN 1
// const char piece_table[2][7][5] = {
//   {" ", "♟", "♜", "♞", "♝", "♛", "♚"},
//   {" ", "♙", "♖", "♘", "♗", "♕", "♔"},
// };
#define PIECE_STR_LEN 2
const char PIECE_TABLE[2][7][5] = {
  {"  ", "wP", "wR", "wn", "wB", "wQ", "wK"},
  {"  ", "bP", "bR", "bn", "bB", "bQ", "bK"},
};