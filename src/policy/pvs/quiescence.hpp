#pragma once
#include <algorithm>
#include <vector>
#include "config.hpp"
#include "state.hpp"
#include "search_types.hpp"
#include "../pvs.hpp"
#include "../game_history.hpp"
#include "move_ordering.hpp"

/*============================================================
 * Quiescence Search with SearchContext (node counting)
 *============================================================*/
inline int quiescence_ctx(
    State *state,
    int alpha,
    int beta,
    int qdepth,
    GameHistory& history,
    int ply,
    SearchContext& ctx,
    const PVSParams& p
){
    ctx.nodes++;
    if(ply > ctx.seldepth){
        ctx.seldepth = ply;
    }
    if(ctx.stop){
        delete state;
        return 0;
    }

    if(state->game_state == WIN){
        delete state;
        return P_MAX - ply;
    }
    if(state->game_state == DRAW){
        delete state;
        return 0;
    }

    int stand_pat = state->evaluate(p.use_nnue, p.use_kp_eval, p.use_eval_mobility, &history);
    if(stand_pat >= beta){
        delete state;
        return beta;
    }
    if(stand_pat > alpha){
        alpha = stand_pat;
    }

    if(qdepth >= p.quiescence_max_depth){
        delete state;
        return alpha;
    }

    /* === Collect and sort captures by MVV-LVA === */
    std::vector<Move> captures;
    for(auto& move : state->legal_actions){
        int to_r = move.second.first;
        int to_c = move.second.second;
        if(state->piece_at(1 - state->player, to_r, to_c)){
            captures.push_back(move);
        }
    }
    if(p.use_move_ordering){
        std::sort(captures.begin(), captures.end(),
            [state](const Move& a, const Move& b){
                return score_move(state, a, 0, 0) > score_move(state, b, 0, 0);
            }
        );
    }

    for(auto& move : captures){
        int score = -quiescence_ctx(
            state->next_state(move), -beta, -alpha, qdepth + 1, history, ply + 1, ctx, p
        );
        if(ctx.stop){
            delete state;
            return 0;
        }
        if(score >= beta){
            delete state;
            return beta;
        }
        if(score > alpha){
            alpha = score;
        }
    }

    delete state;
    return alpha;
}
