#include <iostream>
#include <sstream>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <algorithm>

#include "./state.hpp"
#include "config.hpp"
#include "../../policy/game_history.hpp"
#ifdef USE_NNUE
#include "../../nnue/nnue.hpp"
#endif


/* ================================================================
 * Constants & Tables
 * ================================================================ */

/* === Material values (centipawn-ish scale) ===
 *
 * Kohaku Shogi piece values (adjusted for 6x7 board):
 *   - Pawn is baseline
 *   - Lance ~ 3 pawns (forward-only slider, limited on 7-rank board)
 *   - Knight ~ 3.5 pawns (jumping piece, but restricted movement)
 *   - Silver ~ 4 pawns (good forward moves, can retreat diagonally)
 *   - Gold ~ 5 pawns (strong defensive/attacking, no diagonal backward)
 *   - Bishop ~ 7 pawns (strong diagonal)
 *   - Rook ~ 9 pawns (dominant, controls whole rank/file)
 *   - Promoted bishop (Horse) ~ 12 (bishop + 1-step orthogonal)
 *   - Promoted rook (Dragon) ~ 13 (rook + 1-step diagonal)
 *   - Promoted pawn/silver/lance/knight = gold equivalent ~ 5
 */
static const int material_value[NUM_PIECE_TYPES] = {
    /* EMPTY */ 0,
    /* PAWN  */ 10, /* SILVER */ 40, /* GOLD   */ 50,
    /* LANCE */ 30, /* KNIGHT */ 35, /* BISHOP */ 70, /* ROOK */ 90,
    /* KING  */ 0,
    /* P_PAWN*/ 50, /* P_SILVER*/ 50, /* P_LANCE*/ 50, /* P_KNIGHT*/ 50,
    /* P_BISHOP */ 120, /* P_ROOK */ 130,
};

/* Hand pieces are more valuable than board pieces (drop flexibility) */
static const int hand_value[NUM_HAND_TYPES + 1] = {
    /* 0 */ 0,
    /* PAWN  */ 12, /* SILVER */ 45, /* GOLD */ 55,
    /* LANCE */ 35, /* KNIGHT */ 40, /* BISHOP */ 80, /* ROOK */ 100,
};

/* === Piece-Square Tables (sente perspective, row 0 = top/opponent side) ===
 * Scale: roughly +/-15 centipawns. Forward = aggressive = bonus.
 * Board is 7 rows x 6 columns. */
static const int pst_pawn[BOARD_H][BOARD_W] = {
    /* row 0: deep in promotion zone */
    {15, 15, 15, 15, 15, 15},
    {12, 14, 14, 14, 14, 12},
    { 8, 10, 12, 12, 10,  8},
    { 4,  6,  8,  8,  6,  4},
    { 2,  2,  4,  4,  2,  2},
    { 0,  0,  0,  0,  0,  0},
    { 0,  0,  0,  0,  0,  0},
};
static const int pst_silver[BOARD_H][BOARD_W] = {
    { 6,  8, 10, 10,  8,  6},
    { 4,  6,  8,  8,  6,  4},
    { 2,  4,  6,  6,  4,  2},
    { 0,  2,  4,  4,  2,  0},
    {-2,  0,  2,  2,  0, -2},
    {-2, -2,  0,  0, -2, -2},
    {-4, -2, -2, -2, -2, -4},
};
static const int pst_gold[BOARD_H][BOARD_W] = {
    { 6,  8, 10, 10,  8,  6},
    { 4,  6,  8,  8,  6,  4},
    { 2,  4,  6,  6,  4,  2},
    { 0,  2,  4,  4,  2,  0},
    {-2,  0,  2,  2,  0, -2},
    {-2, -2,  0,  0, -2, -2},
    {-4, -2, -2, -2, -2, -4},
};
static const int pst_lance[BOARD_H][BOARD_W] = {
    {12, 12, 14, 14, 12, 12},
    { 8, 10, 12, 12, 10,  8},
    { 4,  6,  8,  8,  6,  4},
    { 2,  2,  4,  4,  2,  2},
    { 0,  0,  2,  2,  0,  0},
    { 0,  0,  0,  0,  0,  0},
    { 0,  0,  0,  0,  0,  0},
};
static const int pst_knight[BOARD_H][BOARD_W] = {
    { 8, 10, 12, 12, 10,  8},
    { 6,  8, 10, 10,  8,  6},
    { 4,  6,  8,  8,  6,  4},
    { 2,  4,  6,  6,  4,  2},
    { 0,  2,  4,  4,  2,  0},
    {-2,  0,  0,  0,  0, -2},
    {-4, -2, -2, -2, -2, -4},
};
static const int pst_bishop[BOARD_H][BOARD_W] = {
    { 2,  2,  4,  4,  2,  2},
    { 2,  6,  6,  6,  6,  2},
    { 4,  6,  8,  8,  6,  4},
    { 4,  6,  8,  8,  6,  4},
    { 2,  6,  6,  6,  6,  2},
    { 2,  2,  4,  4,  2,  2},
    { 0,  2,  2,  2,  2,  0},
};
static const int pst_rook[BOARD_H][BOARD_W] = {
    { 6,  6,  8,  8,  6,  6},
    { 4,  4,  6,  6,  4,  4},
    { 2,  2,  4,  4,  2,  2},
    { 0,  0,  2,  2,  0,  0},
    { 0,  0,  0,  0,  0,  0},
    { 0,  0,  0,  0,  0,  0},
    { 0,  0,  0,  0,  0,  0},
};
static const int pst_king[BOARD_H][BOARD_W] = {
    {-15,-15,-15,-15,-15,-15},
    {-12,-12,-12,-12,-12,-12},
    { -8, -8, -8, -8, -8, -8},
    { -4, -4, -4, -4, -4, -4},
    {  0,  0,  0,  0,  0,  0},
    {  4,  4,  2,  2,  4,  4},
    {  6,  8,  4,  4,  8,  6},
};
/* Promoted bishop (horse): wants to be aggressive, near enemy */
static const int pst_horse[BOARD_H][BOARD_W] = {
    {10, 10, 12, 12, 10, 10},
    { 8,  8, 10, 10,  8,  8},
    { 4,  6,  8,  8,  6,  4},
    { 2,  4,  6,  6,  4,  2},
    { 0,  2,  4,  4,  2,  0},
    { 0,  0,  0,  0,  0,  0},
    { 0,  0,  0,  0,  0,  0},
};
/* Promoted rook (dragon): wants to be aggressive, near enemy */
static const int pst_dragon[BOARD_H][BOARD_W] = {
    {10, 10, 12, 12, 10, 10},
    { 8,  8, 10, 10,  8,  8},
    { 4,  6,  8,  8,  6,  4},
    { 2,  4,  6,  6,  4,  2},
    { 0,  2,  4,  4,  2,  0},
    { 0,  0,  0,  0,  0,  0},
    { 0,  0,  0,  0,  0,  0},
};

/* Pointers for indexing by piece type */
static const int (*pst_table[NUM_PIECE_TYPES])[BOARD_W] = {
    /* EMPTY    */ nullptr,
    /* PAWN     */ pst_pawn,
    /* SILVER   */ pst_silver,
    /* GOLD     */ pst_gold,
    /* LANCE    */ pst_lance,
    /* KNIGHT   */ pst_knight,
    /* BISHOP   */ pst_bishop,
    /* ROOK     */ pst_rook,
    /* KING     */ pst_king,
    /* P_PAWN   */ pst_gold,     /* tokin moves like gold */
    /* P_SILVER */ pst_gold,     /* narigin moves like gold */
    /* P_LANCE  */ pst_gold,     /* narikyo moves like gold */
    /* P_KNIGHT */ pst_gold,     /* narikei moves like gold */
    /* P_BISHOP */ pst_horse,    /* horse = aggressive */
    /* P_ROOK   */ pst_dragon,   /* dragon = aggressive */
};

/* King tropism: bonus for pieces near enemy king */
static const int tropism_w[NUM_PIECE_TYPES] = {
    0,  /* EMPTY */
    0,  /* PAWN -- too weak for tropism */
    3,  /* SILVER */
    4,  /* GOLD */
    2,  /* LANCE */
    2,  /* KNIGHT */
    3,  /* BISHOP */
    5,  /* ROOK */
    0,  /* KING */
    4,  /* P_PAWN (tokin) */
    4,  /* P_SILVER */
    4,  /* P_LANCE */
    4,  /* P_KNIGHT */
    5,  /* P_BISHOP (horse) */
    6,  /* P_ROOK (dragon) */
};

static int king_tropism(
    int piece_type,
    int pr, int pc,
    int ekr, int ekc
){
    int dist = std::max(std::abs(pr - ekr), std::abs(pc - ekc));
    if(dist <= 2){
        return tropism_w[piece_type] * (3 - dist);
    }
    return 0;
}


/* === Direction tables === */

/* 8 directions: 0-3 orthogonal, 4-7 diagonal */
static const int dir8_dr[8] = { -1,  1,  0,  0, -1, -1,  1,  1 };
static const int dir8_dc[8] = {  0,  0, -1,  1, -1,  1, -1,  1 };

/* Gold move offsets (relative to player 0 / sente) */
/* Forward, left, right, backward, forward-left, forward-right */
static const int gold_dr[6] = { -1,  0,  0,  1, -1, -1 };
static const int gold_dc[6] = {  0, -1,  1,  0, -1,  1 };

/* Silver move offsets (relative to player 0 / sente) */
/* Forward, forward-left, forward-right, back-left, back-right */
static const int silver_dr[5] = { -1, -1, -1,  1,  1 };
static const int silver_dc[5] = {  0, -1,  1, -1,  1 };

/* Knight move offsets (relative to player 0 / sente) */
/* 2 forward + 1 left, 2 forward + 1 right */
static const int knight_dr[2] = { -2, -2 };
static const int knight_dc[2] = { -1,  1 };


/* ================================================================
 * Default Constructor -- Starting Position
 * ================================================================ */

State::State(){
    /* Starting position is set by Board default initializer in state.hpp */
}


/* ================================================================
 * Promotion helpers
 * ================================================================ */

bool State::is_promotion_zone(int row, int player) const{
    /* Player 0 (sente): rows 0-1 (last 2 ranks) are promotion zone */
    /* Player 1 (gote):  rows 5-6 (last 2 ranks) are promotion zone */
    if(player == 0){
        return (row <= 1);
    }
    return (row >= BOARD_H - 2);
}

bool State::must_promote(int piece, int row, int player) const{
    /* Pawn/Lance on last rank must promote (no forward moves otherwise) */
    if((piece == PAWN || piece == LANCE) &&
       ((player == 0 && row == 0) || (player == 1 && row == BOARD_H - 1))){
        return true;
    }
    /* Knight on last 2 ranks must promote (no legal knight moves) */
    if(piece == KNIGHT &&
       ((player == 0 && row <= 1) || (player == 1 && row >= BOARD_H - 2))){
        return true;
    }
    return false;
}

int State::demote(int piece) const{
    /* Return the unpromoted base type for captured promoted pieces */
    switch(piece){
        case P_PAWN:   return PAWN;
        case P_SILVER: return SILVER;
        case P_LANCE:  return LANCE;
        case P_KNIGHT: return KNIGHT;
        case P_BISHOP: return BISHOP;
        case P_ROOK:   return ROOK;
        default:       return piece;
    }
}

int State::unpromoted_type(int piece) const{
    /* Map any piece to its hand index (1-7). King=8 never goes to hand. */
    switch(piece){
        case PAWN:   case P_PAWN:   return PAWN;
        case SILVER: case P_SILVER: return SILVER;
        case GOLD:                  return GOLD;
        case LANCE:  case P_LANCE:  return LANCE;
        case KNIGHT: case P_KNIGHT: return KNIGHT;
        case BISHOP: case P_BISHOP: return BISHOP;
        case ROOK:   case P_ROOK:   return ROOK;
        default:                    return piece;
    }
}

/* Can this piece type be promoted? */
static bool can_promote(int piece){
    return (piece == PAWN || piece == SILVER || piece == LANCE ||
            piece == KNIGHT || piece == BISHOP || piece == ROOK);
}

/* Return the promoted version of a piece */
static int promote_piece(int piece){
    switch(piece){
        case PAWN:   return P_PAWN;
        case SILVER: return P_SILVER;
        case LANCE:  return P_LANCE;
        case KNIGHT: return P_KNIGHT;
        case BISHOP: return P_BISHOP;
        case ROOK:   return P_ROOK;
        default:     return piece;
    }
}


/* ================================================================
 * Piece movement -- generate destinations for a single piece
 * ================================================================ */

/* Direction flip: player 0 goes up (dr as-is), player 1 goes down (negate dr) */
static inline int flip_dr(int dr, int player){
    return (player == 0) ? dr : -dr;
}

/* Add a move to the list. Returns true if king was captured (WIN). */
static bool try_add_move(
    std::vector<Move>& actions,
    const char self_board[BOARD_H][BOARD_W],
    const char oppn_board[BOARD_H][BOARD_W],
    int from_r, int from_c,
    int to_r, int to_c,
    int piece, int player,
    bool entering_promo, bool leaving_promo,
    GameState& game_state
){
    /* Out of bounds */
    if(to_r < 0 || to_r >= BOARD_H || to_c < 0 || to_c >= BOARD_W){
        return false;
    }
    /* Own piece blocks */
    if(self_board[to_r][to_c]){
        return false;
    }

    /* Check for king capture */
    int captured = oppn_board[to_r][to_c];
    if(captured == KING){
        game_state = WIN;
        actions.push_back(Move(Point(from_r, from_c), Point(to_r, to_c)));
        return true;
    }

    /* Determine promotion eligibility */
    bool promo_possible = can_promote(piece) && (entering_promo || leaving_promo);

    if(promo_possible){
        /* Promotion zone entry/exit: check if must promote */
        bool forced = false;
        /* Pawn/Lance on last rank must promote */
        if((piece == PAWN || piece == LANCE) &&
           ((player == 0 && to_r == 0) || (player == 1 && to_r == BOARD_H - 1))){
            forced = true;
        }
        /* Knight on last 2 ranks must promote */
        if(piece == KNIGHT &&
           ((player == 0 && to_r <= 1) || (player == 1 && to_r >= BOARD_H - 2))){
            forced = true;
        }
        if(forced){
            /* Only promoted move */
            actions.push_back(Move(Point(from_r, from_c), Point(to_r + BOARD_H, to_c)));
        }else{
            /* Both promoted and unpromoted versions */
            actions.push_back(Move(Point(from_r, from_c), Point(to_r + BOARD_H, to_c)));
            actions.push_back(Move(Point(from_r, from_c), Point(to_r, to_c)));
        }
    }else{
        /* Normal move */
        actions.push_back(Move(Point(from_r, from_c), Point(to_r, to_c)));
    }
    return false;
}


/* ================================================================
 * gen_board_moves -- generate all board moves for current player
 * ================================================================ */

void State::gen_board_moves(){
    auto& self_board = board.board[player];
    auto& oppn_board = board.board[1 - player];
    int p = player;

    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            int piece = self_board[r][c];
            if(!piece){
                continue;
            }

            bool from_promo = is_promotion_zone(r, p);

            switch(piece){

                /* === Pawn === */
                case PAWN: {
                    int dr = flip_dr(-1, p);
                    int tr = r + dr;
                    bool to_promo = (tr >= 0 && tr < BOARD_H) && is_promotion_zone(tr, p);
                    if(try_add_move(legal_actions, self_board, oppn_board,
                                    r, c, tr, c, piece, p, to_promo, from_promo, game_state)){
                        return;
                    }
                    break;
                }

                /* === Silver === */
                case SILVER: {
                    for(int d = 0; d < 5; d++){
                        int dr = flip_dr(silver_dr[d], p);
                        int dc = silver_dc[d];
                        int tr = r + dr, tc = c + dc;
                        bool to_promo = (tr >= 0 && tr < BOARD_H) && is_promotion_zone(tr, p);
                        if(try_add_move(legal_actions, self_board, oppn_board,
                                        r, c, tr, tc, piece, p, to_promo, from_promo, game_state)){
                            return;
                        }
                    }
                    break;
                }

                /* === Gold / Promoted Pawn / Promoted Silver / Promoted Lance / Promoted Knight
                 *     (all move like gold) === */
                case GOLD:
                case P_PAWN:
                case P_SILVER:
                case P_LANCE:
                case P_KNIGHT: {
                    for(int d = 0; d < 6; d++){
                        int dr = flip_dr(gold_dr[d], p);
                        int dc = gold_dc[d];
                        int tr = r + dr, tc = c + dc;
                        /* Gold/promoted pieces cannot promote further */
                        if(try_add_move(legal_actions, self_board, oppn_board,
                                        r, c, tr, tc, GOLD, p, false, false, game_state)){
                            return;
                        }
                    }
                    break;
                }

                /* === Lance (slides forward only) === */
                case LANCE: {
                    int dr = flip_dr(-1, p);
                    for(int step = 1; step < BOARD_H; step++){
                        int tr = r + dr * step;
                        int tc = c;
                        if(tr < 0 || tr >= BOARD_H){
                            break;
                        }
                        if(self_board[tr][tc]){
                            break;
                        }

                        bool to_promo = is_promotion_zone(tr, p);
                        bool king_cap = (oppn_board[tr][tc] == KING);

                        if(king_cap){
                            game_state = WIN;
                            legal_actions.push_back(Move(Point(r, c), Point(tr, tc)));
                            return;
                        }

                        /* Promotion check */
                        bool promo_ok = can_promote(piece) && (to_promo || from_promo);
                        if(promo_ok){
                            /* Must-promote: lance on last rank */
                            bool forced = ((p == 0 && tr == 0) || (p == 1 && tr == BOARD_H - 1));
                            if(forced){
                                legal_actions.push_back(Move(Point(r, c), Point(tr + BOARD_H, tc)));
                            }else{
                                legal_actions.push_back(Move(Point(r, c), Point(tr + BOARD_H, tc)));
                                legal_actions.push_back(Move(Point(r, c), Point(tr, tc)));
                            }
                        }else{
                            legal_actions.push_back(Move(Point(r, c), Point(tr, tc)));
                        }

                        if(oppn_board[tr][tc]){
                            break;  /* captured, stop sliding */
                        }
                    }
                    break;
                }

                /* === Knight (jumps 2 forward + 1 sideways) === */
                case KNIGHT: {
                    for(int d = 0; d < 2; d++){
                        int dr = flip_dr(knight_dr[d], p);
                        int dc = knight_dc[d];
                        int tr = r + dr, tc = c + dc;
                        bool to_promo = (tr >= 0 && tr < BOARD_H) && is_promotion_zone(tr, p);
                        if(try_add_move(legal_actions, self_board, oppn_board,
                                        r, c, tr, tc, piece, p, to_promo, from_promo, game_state)){
                            return;
                        }
                    }
                    break;
                }

                /* === Bishop (sliding diagonals) === */
                case BISHOP: {
                    for(int d = 4; d < 8; d++){  /* diagonal directions only */
                        for(int step = 1; step < std::max(BOARD_H, BOARD_W); step++){
                            int tr = r + dir8_dr[d] * step;
                            int tc = c + dir8_dc[d] * step;
                            if(tr < 0 || tr >= BOARD_H || tc < 0 || tc >= BOARD_W){
                                break;
                            }
                            if(self_board[tr][tc]){
                                break;
                            }

                            bool to_promo = is_promotion_zone(tr, p);
                            bool king_cap = (oppn_board[tr][tc] == KING);

                            if(king_cap){
                                game_state = WIN;
                                legal_actions.push_back(Move(Point(r, c), Point(tr, tc)));
                                return;
                            }

                            /* Promotion check */
                            bool promo_ok = can_promote(piece) && (to_promo || from_promo);
                            if(promo_ok){
                                legal_actions.push_back(Move(Point(r, c), Point(tr + BOARD_H, tc)));
                                legal_actions.push_back(Move(Point(r, c), Point(tr, tc)));
                            }else{
                                legal_actions.push_back(Move(Point(r, c), Point(tr, tc)));
                            }

                            if(oppn_board[tr][tc]){
                                break;  /* captured, stop sliding */
                            }
                        }
                    }
                    break;
                }

                /* === Rook (sliding orthogonals) === */
                case ROOK: {
                    for(int d = 0; d < 4; d++){  /* orthogonal directions only */
                        for(int step = 1; step < std::max(BOARD_H, BOARD_W); step++){
                            int tr = r + dir8_dr[d] * step;
                            int tc = c + dir8_dc[d] * step;
                            if(tr < 0 || tr >= BOARD_H || tc < 0 || tc >= BOARD_W){
                                break;
                            }
                            if(self_board[tr][tc]){
                                break;
                            }

                            bool to_promo = is_promotion_zone(tr, p);
                            bool king_cap = (oppn_board[tr][tc] == KING);

                            if(king_cap){
                                game_state = WIN;
                                legal_actions.push_back(Move(Point(r, c), Point(tr, tc)));
                                return;
                            }

                            bool promo_ok = can_promote(piece) && (to_promo || from_promo);
                            if(promo_ok){
                                legal_actions.push_back(Move(Point(r, c), Point(tr + BOARD_H, tc)));
                                legal_actions.push_back(Move(Point(r, c), Point(tr, tc)));
                            }else{
                                legal_actions.push_back(Move(Point(r, c), Point(tr, tc)));
                            }

                            if(oppn_board[tr][tc]){
                                break;
                            }
                        }
                    }
                    break;
                }

                /* === King (1 step in all 8 directions) === */
                case KING: {
                    for(int d = 0; d < 8; d++){
                        int tr = r + dir8_dr[d];
                        int tc = c + dir8_dc[d];
                        /* King cannot promote -- pass false for promo flags */
                        if(try_add_move(legal_actions, self_board, oppn_board,
                                        r, c, tr, tc, KING, p, false, false, game_state)){
                            return;
                        }
                    }
                    break;
                }

                /* === Promoted Bishop / Horse (bishop slides + 1-step orthogonal) === */
                case P_BISHOP: {
                    /* Diagonal sliding */
                    for(int d = 4; d < 8; d++){
                        for(int step = 1; step < std::max(BOARD_H, BOARD_W); step++){
                            int tr = r + dir8_dr[d] * step;
                            int tc = c + dir8_dc[d] * step;
                            if(tr < 0 || tr >= BOARD_H || tc < 0 || tc >= BOARD_W){
                                break;
                            }
                            if(self_board[tr][tc]){
                                break;
                            }

                            if(oppn_board[tr][tc] == KING){
                                game_state = WIN;
                                legal_actions.push_back(Move(Point(r, c), Point(tr, tc)));
                                return;
                            }
                            legal_actions.push_back(Move(Point(r, c), Point(tr, tc)));
                            if(oppn_board[tr][tc]){
                                break;
                            }
                        }
                    }
                    /* 1-step orthogonal (king-like addition) */
                    for(int d = 0; d < 4; d++){
                        int tr = r + dir8_dr[d];
                        int tc = c + dir8_dc[d];
                        if(try_add_move(legal_actions, self_board, oppn_board,
                                        r, c, tr, tc, P_BISHOP, p, false, false, game_state)){
                            return;
                        }
                    }
                    break;
                }

                /* === Promoted Rook / Dragon (rook slides + 1-step diagonal) === */
                case P_ROOK: {
                    /* Orthogonal sliding */
                    for(int d = 0; d < 4; d++){
                        for(int step = 1; step < std::max(BOARD_H, BOARD_W); step++){
                            int tr = r + dir8_dr[d] * step;
                            int tc = c + dir8_dc[d] * step;
                            if(tr < 0 || tr >= BOARD_H || tc < 0 || tc >= BOARD_W){
                                break;
                            }
                            if(self_board[tr][tc]){
                                break;
                            }

                            if(oppn_board[tr][tc] == KING){
                                game_state = WIN;
                                legal_actions.push_back(Move(Point(r, c), Point(tr, tc)));
                                return;
                            }
                            legal_actions.push_back(Move(Point(r, c), Point(tr, tc)));
                            if(oppn_board[tr][tc]){
                                break;
                            }
                        }
                    }
                    /* 1-step diagonal (king-like addition) */
                    for(int d = 4; d < 8; d++){
                        int tr = r + dir8_dr[d];
                        int tc = c + dir8_dc[d];
                        if(try_add_move(legal_actions, self_board, oppn_board,
                                        r, c, tr, tc, P_ROOK, p, false, false, game_state)){
                            return;
                        }
                    }
                    break;
                }

            } /* switch */
        }
    }
}


/* ================================================================
 * gen_drop_moves -- generate all drop moves for current player
 * ================================================================ */

void State::gen_drop_moves(bool skip_uchifuzume){
    auto& self_board = board.board[player];
    auto& oppn_board = board.board[1 - player];
    int p = player;

    /* Precompute: for each column, does the player already have an unpromoted pawn? */
    bool has_pawn_on_col[BOARD_W] = {};
    for(int c = 0; c < BOARD_W; c++){
        for(int r = 0; r < BOARD_H; r++){
            if(self_board[r][c] == PAWN){
                has_pawn_on_col[c] = true;
                break;
            }
        }
    }

    /* For each piece type in hand */
    for(int pt = 1; pt <= NUM_HAND_TYPES; pt++){
        if(board.hand[p][pt] <= 0){
            continue;
        }

        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                /* Must be empty -- no piece for either player */
                if(self_board[r][c] || oppn_board[r][c]){
                    continue;
                }

                /* Pawn restrictions */
                if(pt == PAWN){
                    /* Can't drop pawn on last rank (no forward moves) */
                    if(p == 0 && r == 0){
                        continue;
                    }
                    if(p == 1 && r == BOARD_H - 1){
                        continue;
                    }
                    /* Nifu: can't drop pawn on column that already has own unpromoted pawn */
                    if(has_pawn_on_col[c]){
                        continue;
                    }
                }

                /* Lance restrictions: can't drop on last rank */
                if(pt == LANCE){
                    if(p == 0 && r == 0){
                        continue;
                    }
                    if(p == 1 && r == BOARD_H - 1){
                        continue;
                    }
                }

                /* Knight restrictions: can't drop on last 2 ranks */
                if(pt == KNIGHT){
                    if(p == 0 && r <= 1){
                        continue;
                    }
                    if(p == 1 && r >= BOARD_H - 2){
                        continue;
                    }
                }

                /* Drop move: from = (DROP_ROW, piece_type), to = (row, col) */
                legal_actions.push_back(Move(Point(DROP_ROW, pt), Point(r, c)));
            }
        }
    }

    /* === Uchifuzume (打ち歩詰め) filter ===
     * A pawn drop that delivers checkmate is illegal.
     * For each pawn drop, check if it gives check and, if so, whether
     * the opponent has any legal escape.  If no escape exists the drop
     * is uchifuzume and must be removed.
     * NOTE: probe states use gen_board_moves/gen_drop_moves(true) directly
     * to avoid recursive uchifuzume checks. */
    if(!skip_uchifuzume){
    auto is_uchifuzume = [&](const Move& m) -> bool {
        /* Only pawn drops */
        if(m.first.first != DROP_ROW || (int)m.first.second != PAWN)
            return false;

        int tr = (int)m.second.first;
        int tc = (int)m.second.second;

        /* Temporarily place the pawn on the board */
        Board tmp = board;
        tmp.board[player][tr][tc] = PAWN;
        tmp.hand[player][PAWN]--;

        /* Check if opponent is in check: create state with dropper to move.
         * If dropper can capture the opponent's king -> game_state==WIN.
         * Use gen_board_moves only to avoid recursive uchifuzume. */
        State probe_check(tmp, player);
        probe_check.step = step + 1;
        probe_check.gen_board_moves();
        if(probe_check.game_state != WIN){
            return false;  /* not even check, pawn drop is fine */
        }

        /* Opponent is in check.  Check if it's checkmate:
         * create state with opponent to move, enumerate their moves,
         * and see if ANY move escapes the check. */
        State probe_opp(tmp, 1 - player);
        probe_opp.step = step + 1;
        probe_opp.gen_board_moves();
        if(probe_opp.game_state != WIN){
            probe_opp.gen_drop_moves(true);
        }

        for(auto& opp_move : probe_opp.legal_actions){
            State* child = probe_opp.next_state(opp_move);
            bool still_captured = (child->game_state == WIN);
            delete child;
            if(!still_captured){
                return false;  /* opponent can escape, not checkmate */
            }
        }

        /* No escape: this is uchifuzume -> illegal */
        return true;
    };

    auto it = std::remove_if(legal_actions.begin(), legal_actions.end(), is_uchifuzume);
    legal_actions.erase(it, legal_actions.end());
    } /* !skip_uchifuzume */
}


/* ================================================================
 * get_legal_actions -- main dispatcher
 * ================================================================ */

void State::get_legal_actions(){
    game_state = NONE;
    legal_actions.clear();
    legal_actions.reserve(192);

    /* Check draw by step limit */
    if(step >= MAX_STEP){
        game_state = DRAW;
        return;
    }

    gen_board_moves();
    if(game_state == WIN){
        return;  /* king capture found */
    }

    gen_drop_moves();

    if(legal_actions.empty()){
        /* No legal moves = loss in shogi rules.  In practice this is
         * extremely rare (drops prevent true stalemate).  We cannot
         * directly encode "opponent wins" with the current game_state
         * enum, so we mark it DRAW.  The search will never reach a
         * position with zero moves in realistic play. */
        game_state = DRAW;
    }
}


/* ================================================================
 * next_state -- apply a move and return new state
 * ================================================================ */

State* State::next_state(const Move& move){
    Board next = this->board;
    Point from = move.first;
    Point to   = move.second;

    int p = this->player;
    int opp = 1 - p;

    if(from.first == DROP_ROW){
        /* === Drop move === */
        int piece_type = (int)from.second;
        int tr = (int)to.first;
        int tc = (int)to.second;

        next.hand[p][piece_type]--;
        next.board[p][tr][tc] = (char)piece_type;

    }else{
        /* === Board move === */
        int fr = (int)from.first;
        int fc = (int)from.second;

        /* Decode promotion sentinel */
        bool promote = ((int)to.first >= BOARD_H);
        int tr = promote ? (int)to.first - BOARD_H : (int)to.first;
        int tc = (int)to.second;

        int piece = next.board[p][fr][fc];
        next.board[p][fr][fc] = 0;

        /* Capture opponent piece at destination */
        int captured = next.board[opp][tr][tc];
        if(captured){
            next.board[opp][tr][tc] = 0;
            /* Demote and add to hand */
            int base = 0;
            switch(captured){
                case PAWN:   case P_PAWN:   base = PAWN;   break;
                case SILVER: case P_SILVER: base = SILVER; break;
                case GOLD:                  base = GOLD;   break;
                case LANCE:  case P_LANCE:  base = LANCE;  break;
                case KNIGHT: case P_KNIGHT: base = KNIGHT; break;
                case BISHOP: case P_BISHOP: base = BISHOP; break;
                case ROOK:   case P_ROOK:   base = ROOK;   break;
                default: break; /* king -- should not happen in normal play */
            }
            if(base >= 1 && base <= NUM_HAND_TYPES){
                next.hand[p][base]++;
            }
        }

        /* Place piece (possibly promoted) */
        if(promote){
            next.board[p][tr][tc] = (char)promote_piece(piece);
        }else{
            next.board[p][tr][tc] = (char)piece;
        }
    }

    State* ns = new State(next, opp);
    ns->step = this->step + 1;
    if(this->game_state != WIN){
        ns->get_legal_actions();
    }
    return ns;
}


/* ================================================================
 * NNUE feature extraction -- HalfKP with hand pieces
 *
 * Feature layout (must match Python training pipeline):
 *   Board features [0, HALFKP_SIZE):
 *     king_sq * KP_FEAT + color * (NPT * NSQ) + (pt-1) * NSQ + sq
 *   Hand features [HALFKP_SIZE, HALFKP_SIZE + 2*NUM_HAND_TYPES):
 *     HALFKP_SIZE + color * NUM_HAND_TYPES + (pt-1)
 *     Added count times for each hand piece with count > 0.
 * ================================================================ */
int State::extract_nnue_features(int perspective, int* features) const{
    constexpr int NUM_SQ = BOARD_H * BOARD_W;
    constexpr int KP_FEAT = 2 * NUM_PT_NO_KING * NUM_SQ;
    constexpr int HALFKP = NUM_SQ * KP_FEAT;
    int count = 0;

    /* Find king square for this perspective */
    int king_sq = 0;
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[perspective][r][c] == KING){
                king_sq = (perspective == 0)
                    ? (r * BOARD_W + c)
                    : ((BOARD_H - 1 - r) * BOARD_W + c);
            }
        }
    }

    /* Board piece features */
    for(int color = 0; color < 2; color++){
        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                int pt = board.board[color][r][c];
                if(pt == 0 || pt == KING){ continue; }
                int feat_color, sq;
                if(perspective == 0){
                    feat_color = color;
                    sq = r * BOARD_W + c;
                }else{
                    feat_color = 1 - color;
                    sq = (BOARD_H - 1 - r) * BOARD_W + c;
                }
                if(count < 64){
                    features[count++] = (
                        king_sq * KP_FEAT
                        + feat_color * (NUM_PT_NO_KING * NUM_SQ)
                        + (pt - 1) * NUM_SQ + sq
                    );
                }
            }
        }
    }

    /* Hand piece features -- added count times per piece type */
    for(int color = 0; color < 2; color++){
        int feat_color = (perspective == 0) ? color : (1 - color);
        for(int pt = 1; pt <= NUM_HAND_TYPES; pt++){
            int cnt = board.hand[color][pt];
            int feat_idx = HALFKP + feat_color * NUM_HAND_TYPES + (pt - 1);
            for(int i = 0; i < cnt && count < 64; i++){
                features[count++] = feat_idx;
            }
        }
    }

    return count;
}


/* ================================================================
 * evaluate -- material + PST + mobility
 * ================================================================ */

int State::evaluate(
    bool use_nnue,
    bool use_kp_eval,
    bool use_mobility,
    const GameHistory* history
){
    (void)history;
    if(this->game_state == WIN){
        return P_MAX;
    }

    /* === NNUE evaluation === */
    #ifdef USE_NNUE
    if(use_nnue && nnue::g_model.loaded()){
        return nnue::g_model.evaluate(*this, this->player);
    }
    #endif
    (void)use_nnue;

    int p = this->player;
    int opp = 1 - p;
    auto& self_board = this->board.board[p];
    auto& oppn_board = this->board.board[opp];
    int self_score = 0, oppn_score = 0;

    /* Find king positions for tropism */
    int self_kr = 0, self_kc = 0, oppn_kr = 0, oppn_kc = 0;
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(self_board[r][c] == KING){ self_kr = r; self_kc = c; }
            if(oppn_board[r][c] == KING){ oppn_kr = r; oppn_kc = c; }
        }
    }

    if(use_kp_eval){
        /* === KP eval: material + PST + king tropism === */
        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                int piece;
                if((piece = self_board[r][c])){
                    self_score += material_value[piece];
                    int pr = (p == 0) ? r : (BOARD_H - 1 - r);
                    if(pst_table[piece]){
                        self_score += pst_table[piece][pr][c];
                    }
                    self_score += king_tropism(piece, r, c, oppn_kr, oppn_kc);
                }
                if((piece = oppn_board[r][c])){
                    oppn_score += material_value[piece];
                    int pr = (p == 0) ? (BOARD_H - 1 - r) : r;
                    if(pst_table[piece]){
                        oppn_score += pst_table[piece][pr][c];
                    }
                    oppn_score += king_tropism(piece, r, c, self_kr, self_kc);
                }
            }
        }

        /* Hand pieces use hand_value (premium for drop flexibility) */
        for(int pt = 1; pt <= NUM_HAND_TYPES; pt++){
            self_score += board.hand[p][pt] * hand_value[pt];
            oppn_score += board.hand[opp][pt] * hand_value[pt];
        }
    }else{
        /* === Simple material-only eval === */
        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                int piece;
                if((piece = self_board[r][c])){
                    self_score += material_value[piece];
                }
                if((piece = oppn_board[r][c])){
                    oppn_score += material_value[piece];
                }
            }
        }
        for(int pt = 1; pt <= NUM_HAND_TYPES; pt++){
            self_score += board.hand[p][pt] * hand_value[pt];
            oppn_score += board.hand[opp][pt] * hand_value[pt];
        }
    }

    int bonus = 0;

    /* === Mobility bonus === */
    if(use_mobility){
        int self_mobility = (int)this->legal_actions.size();
        State oppn_state(this->board, 1 - p);
        oppn_state.get_legal_actions();
        int oppn_mobility = (int)oppn_state.legal_actions.size();
        bonus += 2 * (self_mobility - oppn_mobility);
    }

    return self_score - oppn_score + bonus;
}


/* ================================================================
 * create_null_state
 * ================================================================ */

BaseState* State::create_null_state() const{
    State* s = new State(this->board, 1 - this->player);
    s->step = this->step;
    s->get_legal_actions();
    return s;
}


/* ================================================================
 * Zobrist hashing
 * ================================================================ */

static uint64_t zobrist_piece[2][NUM_PIECE_TYPES][BOARD_H][BOARD_W];
static uint64_t zobrist_hand[2][NUM_HAND_TYPES + 1][8]; /* hand counts 0-7 */
static uint64_t zobrist_side;
static bool zobrist_ready = false;

static void init_zobrist(){
    uint64_t s = 0x6B83A4D1E7F205C9ULL; /* different seed from minishogi */
    auto rand64 = [&s]() -> uint64_t {
        s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s;
    };
    for(int p = 0; p < 2; p++){
        for(int t = 0; t < NUM_PIECE_TYPES; t++){
            for(int r = 0; r < BOARD_H; r++){
                for(int c = 0; c < BOARD_W; c++){
                    zobrist_piece[p][t][r][c] = rand64();
                }
            }
        }
    }
    for(int p = 0; p < 2; p++){
        for(int t = 0; t <= NUM_HAND_TYPES; t++){
            for(int cnt = 0; cnt < 8; cnt++){
                zobrist_hand[p][t][cnt] = rand64();
            }
        }
    }
    zobrist_side = rand64();
    zobrist_ready = true;
}

uint64_t State::hash() const{
    if(!zobrist_ready){
        init_zobrist();
    }
    uint64_t h = 0;

    /* Board pieces */
    for(int p = 0; p < 2; p++){
        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                int piece = this->board.board[p][r][c];
                if(piece){
                    h ^= zobrist_piece[p][piece][r][c];
                }
            }
        }
    }

    /* Hand pieces */
    for(int p = 0; p < 2; p++){
        for(int t = 1; t <= NUM_HAND_TYPES; t++){
            int cnt = this->board.hand[p][t];
            if(cnt > 0 && cnt < 8){
                h ^= zobrist_hand[p][t][cnt];
            }
        }
    }

    /* Side to move */
    if(this->player){
        h ^= zobrist_side;
    }
    return h;
}


/* ================================================================
 * encode_output -- pretty-print for terminal
 * ================================================================ */

std::string State::encode_output() const{
    std::stringstream ss;

    /* Gote hand */
    ss << "Gote hand: ";
    for(int pt = 1; pt <= NUM_HAND_TYPES; pt++){
        int cnt = board.hand[1][pt];
        if(cnt > 0){
            const char* names[] = {"", "P", "S", "G", "L", "N", "B", "R"};
            ss << names[pt];
            if(cnt > 1){
                ss << cnt;
            }
            ss << " ";
        }
    }
    ss << "\n";

    /* Board */
    ss << "  ";
    for(int c = 0; c < BOARD_W; c++){
        ss << " " << (char)('a' + c) << " ";
    }
    ss << "\n";

    for(int r = 0; r < BOARD_H; r++){
        ss << (BOARD_H - r) << " ";
        for(int c = 0; c < BOARD_W; c++){
            int w = board.board[0][r][c];
            int b = board.board[1][r][c];
            if(w){
                ss << PIECE_TABLE[0][w];
            }else if(b){
                ss << PIECE_TABLE[1][b];
            }else{
                ss << " .";
            }
            ss << " ";
        }
        ss << (BOARD_H - r) << "\n";
    }

    ss << "  ";
    for(int c = 0; c < BOARD_W; c++){
        ss << " " << (char)('a' + c) << " ";
    }
    ss << "\n";

    /* Sente hand */
    ss << "Sente hand: ";
    for(int pt = 1; pt <= NUM_HAND_TYPES; pt++){
        int cnt = board.hand[0][pt];
        if(cnt > 0){
            const char* names[] = {"", "P", "S", "G", "L", "N", "B", "R"};
            ss << names[pt];
            if(cnt > 1){
                ss << cnt;
            }
            ss << " ";
        }
    }
    ss << "\n";

    ss << "Side: " << (player == 0 ? "Sente" : "Gote") << " | Step: " << step << "\n";
    return ss.str();
}


/* ================================================================
 * cell_display -- single cell string for UBGI 'd' command
 * ================================================================ */

std::string State::cell_display(int row, int col) const{
    int w = (int)board.board[0][row][col];
    int b = (int)board.board[1][row][col];
    if(w){
        return std::string(PIECE_TABLE[0][w]) + " ";
    }else if(b){
        return std::string(PIECE_TABLE[1][b]) + " ";
    }
    return " . ";
}


/* ================================================================
 * encode_board / decode_board -- SFEN-like serialization
 *
 * Format: rows from top (row 0) to bottom, '/' separated.
 * Uppercase = sente (player 0), lowercase = gote (player 1).
 * '+' prefix for promoted pieces.
 * Empty squares as digits (run-length).
 * After board: underscore '_', then hand pieces (uppercase=sente, lowercase=gote).
 * '-' if both hands empty.  Underscore avoids splitting by the UBGI parser.
 *
 * Piece chars: P=pawn, S=silver, G=gold, L=lance, N=knight, B=bishop, R=rook, K=king
 * ================================================================ */

static char piece_to_sfen_char(int piece, int player){
    /* Returns the SFEN character for a piece. Promoted pieces get '+' prefix separately. */
    static const char base_chars[] = {'.', 'P', 'S', 'G', 'L', 'N', 'B', 'R', 'K'};
    int base = piece;
    if(piece >= P_PAWN){
        switch(piece){
            case P_PAWN:   base = PAWN;   break;
            case P_SILVER: base = SILVER; break;
            case P_LANCE:  base = LANCE;  break;
            case P_KNIGHT: base = KNIGHT; break;
            case P_BISHOP: base = BISHOP; break;
            case P_ROOK:   base = ROOK;   break;
        }
    }
    if(base < 1 || base > 8){
        return '?';
    }
    char ch = base_chars[base];
    if(player == 1){
        ch = (char)(ch + ('a' - 'A')); /* lowercase for gote */
    }
    return ch;
}

static bool is_promoted_piece(int piece){
    return (piece == P_PAWN || piece == P_SILVER || piece == P_LANCE ||
            piece == P_KNIGHT || piece == P_BISHOP || piece == P_ROOK);
}

std::string State::encode_board() const{
    std::string s;

    /* Board section */
    for(int r = 0; r < BOARD_H; r++){
        if(r > 0){
            s += '/';
        }
        int empty_count = 0;
        for(int c = 0; c < BOARD_W; c++){
            int w = board.board[0][r][c];
            int b = board.board[1][r][c];
            if(w){
                if(empty_count > 0){
                    s += (char)('0' + empty_count);
                    empty_count = 0;
                }
                if(is_promoted_piece(w)) s += '+';
                s += piece_to_sfen_char(w, 0);
            }else if(b){
                if(empty_count > 0){
                    s += (char)('0' + empty_count);
                    empty_count = 0;
                }
                if(is_promoted_piece(b)) s += '+';
                s += piece_to_sfen_char(b, 1);
            }else{
                empty_count++;
            }
        }
        if(empty_count > 0){
            s += (char)('0' + empty_count);
        }
    }

    /* Hand section (underscore separator for UBGI compatibility) */
    s += '_';
    bool has_hand = false;
    /* Sente hand (uppercase) */
    static const char hand_chars_upper[] = {'.', 'P', 'S', 'G', 'L', 'N', 'B', 'R'};
    static const char hand_chars_lower[] = {'.', 'p', 's', 'g', 'l', 'n', 'b', 'r'};
    for(int pt = 1; pt <= NUM_HAND_TYPES; pt++){
        int cnt = board.hand[0][pt];
        if(cnt > 0){
            if(cnt > 1){
                s += (char)('0' + cnt);
            }
            s += hand_chars_upper[pt];
            has_hand = true;
        }
    }
    /* Gote hand (lowercase) */
    for(int pt = 1; pt <= NUM_HAND_TYPES; pt++){
        int cnt = board.hand[1][pt];
        if(cnt > 0){
            if(cnt > 1){
                s += (char)('0' + cnt);
            }
            s += hand_chars_lower[pt];
            has_hand = true;
        }
    }
    if(!has_hand){
        s += '-';
    }

    return s;
}


void State::decode_board(const std::string& s, int side_to_move){
    player = side_to_move;
    game_state = UNKNOWN;
    /* Clear board -- zero out all arrays */
    for(int p = 0; p < 2; p++){
        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                board.board[p][r][c] = 0;
            }
        }
        for(int t = 0; t <= NUM_HAND_TYPES; t++){
            board.hand[p][t] = 0;
        }
    }
    step = 0;

    /* Split into board part and hand part (separated by '_') */
    size_t sep_pos = s.find('_');
    std::string board_str = (sep_pos != std::string::npos) ? s.substr(0, sep_pos) : s;
    std::string hand_str = (sep_pos != std::string::npos) ? s.substr(sep_pos + 1) : "-";

    /* Parse board */
    int r = 0, c = 0;
    bool promoted = false;
    for(size_t i = 0; i < board_str.size(); i++){
        char ch = board_str[i];
        if(ch == '/'){
            r++;
            c = 0;
            promoted = false;
            continue;
        }
        if(ch == '+'){
            promoted = true;
            continue;
        }
        if(ch >= '1' && ch <= '9'){
            c += (ch - '0');
            promoted = false;
            continue;
        }
        if(r >= BOARD_H || c >= BOARD_W){
            promoted = false;
            continue;
        }

        int piece = 0;
        int pl = 0;
        /* Determine piece type and player from character */
        if(ch >= 'A' && ch <= 'Z'){
            pl = 0; /* sente */
            switch(ch){
                case 'P': piece = PAWN;   break;
                case 'S': piece = SILVER; break;
                case 'G': piece = GOLD;   break;
                case 'L': piece = LANCE;  break;
                case 'N': piece = KNIGHT; break;
                case 'B': piece = BISHOP; break;
                case 'R': piece = ROOK;   break;
                case 'K': piece = KING;   break;
            }
        }else if(ch >= 'a' && ch <= 'z'){
            pl = 1; /* gote */
            switch(ch){
                case 'p': piece = PAWN;   break;
                case 's': piece = SILVER; break;
                case 'g': piece = GOLD;   break;
                case 'l': piece = LANCE;  break;
                case 'n': piece = KNIGHT; break;
                case 'b': piece = BISHOP; break;
                case 'r': piece = ROOK;   break;
                case 'k': piece = KING;   break;
            }
        }

        if(piece && promoted){
            piece = promote_piece(piece);
        }

        if(piece){
            board.board[pl][r][c] = (char)piece;
        }
        c++;
        promoted = false;
    }

    /* Parse hand */
    if(hand_str != "-"){
        int count = 1;
        for(size_t i = 0; i < hand_str.size(); i++){
            char ch = hand_str[i];
            if(ch >= '1' && ch <= '9'){
                count = ch - '0';
                continue;
            }
            int pl = 0;
            int pt = 0;
            if(ch >= 'A' && ch <= 'Z'){
                pl = 0;
                switch(ch){
                    case 'P': pt = PAWN;   break;
                    case 'S': pt = SILVER; break;
                    case 'G': pt = GOLD;   break;
                    case 'L': pt = LANCE;  break;
                    case 'N': pt = KNIGHT; break;
                    case 'B': pt = BISHOP; break;
                    case 'R': pt = ROOK;   break;
                }
            }else if(ch >= 'a' && ch <= 'z'){
                pl = 1;
                switch(ch){
                    case 'p': pt = PAWN;   break;
                    case 's': pt = SILVER; break;
                    case 'g': pt = GOLD;   break;
                    case 'l': pt = LANCE;  break;
                    case 'n': pt = KNIGHT; break;
                    case 'b': pt = BISHOP; break;
                    case 'r': pt = ROOK;   break;
                }
            }
            if(pt >= 1 && pt <= NUM_HAND_TYPES){
                board.hand[pl][pt] = (char)count;
            }
            count = 1;
        }
    }

    get_legal_actions();
}


/* === Repetition: shogi 4-fold rule === */
bool State::check_repetition(const GameHistory& history, int& out_score) const {
    if(history.count(hash()) >= 4){
        out_score = 0;  /* draw (perpetual check handled by GUI) */
        return true;
    }
    return false;
}
