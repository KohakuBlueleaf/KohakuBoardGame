#include <utility>
#include "../state/state.hpp"
#include "minimax.hpp"


/*============================================================
 * MiniMax — eval_ctx
 *
 * Negamax without pruning. Caller manages memory.
 *============================================================*/
int MiniMax::eval_ctx(State *state, int depth, SearchContext& ctx,
                      const MMParams& p, int ply){
    ctx.nodes++;
    if(ply > ctx.seldepth){
        ctx.seldepth = ply;
    }
    if(ctx.stop){
        return 0;
    }

    /*-- terminal / leaf checks --*/
    if(state->game_state == WIN){
        return 100000;
    }
    if(state->game_state == DRAW){
        return 0;
    }
    if(depth <= 0){
        return state->evaluate(p.use_nnue, p.use_kp_eval, p.use_eval_mobility);
    }

    /*-- negamax loop --*/
    int best_score = -100000;
    for(auto& action : state->legal_actions){
        State *next = state->next_state(action);
        int score = -eval_ctx(next, depth - 1, ctx, p, ply + 1);
        delete next;

        if(score > best_score){
            best_score = score;
        }
    }

    return best_score;
}


/*============================================================
 * MiniMax — search
 *
 * Iterate legal moves, call eval_ctx, return SearchResult.
 *============================================================*/
SearchResult MiniMax::search(State *state, int depth, SearchContext& ctx){
    ctx.reset();
    MMParams p = MMParams::from_map(ctx.params);
    SearchResult result;
    result.depth = depth;

    if(!state->legal_actions.size()){
        state->get_legal_actions();
    }

    int best_score = M_MAX - 10;
    int move_index = 0;
    int total_moves = (int)state->legal_actions.size();

    for(auto& action : state->legal_actions){
        State *next = state->next_state(action);
        int score = -eval_ctx(next, depth - 1, ctx, p, 1);
        delete next;

        if(score > best_score){
            best_score = score;
            result.best_move = action;
            if(p.report_partial && ctx.on_root_update){
                ctx.on_root_update({result.best_move, best_score, depth, move_index + 1, total_moves});
            }
        }
        move_index++;
    }

    result.score = best_score;
    result.nodes = ctx.nodes;
    result.seldepth = ctx.seldepth;
    result.pv = {result.best_move};
    return result;
}


/*============================================================
 * MiniMax — default_params / param_defs
 *============================================================*/
ParamMap MiniMax::default_params(){
    return {
        {"UseNNUE", "true"},
        {"UseKPEval", "true"},
        {"UseEvalMobility", "true"},
        {"ReportPartial", "true"},
    };
}

std::vector<ParamDef> MiniMax::param_defs(){
    return {
        {"UseNNUE", ParamDef::CHECK, "true"},
        {"UseKPEval", ParamDef::CHECK, "true"},
        {"UseEvalMobility", ParamDef::CHECK, "true"},
        {"ReportPartial", ParamDef::CHECK, "true"},
    };
}
