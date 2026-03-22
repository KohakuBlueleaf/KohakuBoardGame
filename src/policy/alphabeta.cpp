#include <utility>
#include "alphabeta.hpp"
#include "state.hpp"


/*============================================================
 * AlphaBeta — eval_ctx
 *
 * Negamax with alpha-beta pruning.
 * Caller manages memory (no delete inside).
 *============================================================*/
int AlphaBeta::eval_ctx(State *state, int depth, int alpha, int beta,
                        SearchContext& ctx, const ABParams& p, int ply){
    ctx.nodes++;
    if(ply > ctx.seldepth){
        ctx.seldepth = ply;
    }
    if(ctx.stop){
        return 0;
    }

    /* === Terminal / leaf checks === */
    GameState now_res = state->game_state;
    if(now_res == WIN){
        return P_MAX - ply;
    }
    if(now_res == DRAW){
        return 0;
    }
    if(depth == 0){
        return state->evaluate(p.use_nnue, p.use_kp_eval, p.use_eval_mobility);
    }

    /* === Alpha-beta loop === */
    for(auto& move : state->legal_actions){
        State *next = state->next_state(move);
        int score = -eval_ctx(next, depth - 1, -beta, -alpha, ctx, p, ply + 1);
        delete next;

        if(score > alpha){
            alpha = score;
        }
        if(alpha >= beta){
            return alpha;
        }
    }

    return alpha;
}


/*============================================================
 * AlphaBeta — search
 *
 * Iterate legal moves, call eval_ctx, return SearchResult.
 *============================================================*/
SearchResult AlphaBeta::search(State *state, int depth, SearchContext& ctx){
    ctx.reset();
    ABParams p = ABParams::from_map(ctx.params);
    SearchResult result;
    result.depth = depth;

    if(!state->legal_actions.size()){
        state->get_legal_actions();
    }

    int beta_root = P_MAX + 10;
    int alpha = M_MAX - 10;
    auto all_moves = state->legal_actions;
    int move_index = 0;
    int total_moves = (int)all_moves.size();

    for(auto& move : all_moves){
        State *next = state->next_state(move);
        int score = -eval_ctx(next, depth - 1, -(beta_root), -alpha, ctx, p, 1);
        delete next;

        if(score > alpha){
            result.best_move = move;
            alpha = score;
            if(p.report_partial && ctx.on_root_update){
                ctx.on_root_update({result.best_move, alpha, depth, move_index + 1, total_moves});
            }
        }
        move_index++;
    }

    result.score = alpha;
    result.nodes = ctx.nodes;
    result.seldepth = ctx.seldepth;
    result.pv = {result.best_move};
    return result;
}


/*============================================================
 * AlphaBeta — default_params / param_defs
 *============================================================*/
ParamMap AlphaBeta::default_params(){
    return {
        {"UseNNUE", "true"},
        {"UseKPEval", "true"},
        {"UseEvalMobility", "true"},
        {"ReportPartial", "true"},
    };
}

std::vector<ParamDef> AlphaBeta::param_defs(){
    return {
        {"UseNNUE", ParamDef::CHECK, "true"},
        {"UseKPEval", ParamDef::CHECK, "true"},
        {"UseEvalMobility", ParamDef::CHECK, "true"},
        {"ReportPartial", ParamDef::CHECK, "true"},
    };
}
