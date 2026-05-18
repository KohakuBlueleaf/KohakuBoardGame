#pragma once
#include <algorithm>
#include <vector>
#include "config.hpp"
#include "state.hpp"
#include "../pvs.hpp"
#include "killer_moves.hpp"

/*============================================================
 * Move ordering: captures scored by MVV-LVA
 * With TT: TT best move gets highest priority
 * With Killers: killer moves rank below captures, above quiet
 *
 * Some games encode move metadata in the row component of the
 * destination square (e.g. promotion choices). Generic search
 * code must decode that back to a board row before probing the
 * board with piece_at().
 *============================================================*/
inline int decode_move_row(size_t encoded_row){
    int row = static_cast<int>(encoded_row);
    if(row >= BOARD_H){
        row %= BOARD_H;
    }
    return row;
}

inline void decode_move_to_square(const Move& move, int& to_r, int& to_c){
    to_r = decode_move_row(move.second.first);
    to_c = static_cast<int>(move.second.second);
}

inline int score_move(
    const State* state,
    const Move& move,
    int ply,
    int killer_slots
){
    int to_r, to_c;
    decode_move_to_square(move, to_r, to_c);
    int captured = state->piece_at(1 - state->player, to_r, to_c);
    if(captured){
        int from_r = move.first.first;
        int from_c = move.first.second;
        int attacker = state->piece_at(state->player, from_r, from_c);
        return PIECE_VALUES[captured] * 100 - PIECE_VALUES[attacker];
    }
    if(is_killer(ply, move, killer_slots)){
        return 50;
    }
    return 0;
}

/*------------------------------------------------------------
 * Unified move ordering: MVV-LVA + killers + optional TT
 * best move first
 *------------------------------------------------------------*/
inline std::vector<Move> get_ordered_moves(
    const State* state,
    const Move* tt_move,
    int ply,
    const PVSParams& params
){
    auto moves = state->legal_actions;

    if(params.use_move_ordering){
        int ks = params.killer_slots;
        std::sort(moves.begin(), moves.end(),
            [state, ply, ks](const Move& a, const Move& b){
                return score_move(state, a, ply, ks) > score_move(state, b, ply, ks);
            }
        );
    }

    if(params.use_tt && tt_move){
        for(size_t i = 0; i < moves.size(); i++){
            if(moves[i] == *tt_move){
                std::swap(moves[0], moves[i]);
                break;
            }
        }
    }

    return moves;
}
