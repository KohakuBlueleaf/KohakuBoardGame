#include <utility>
#include "alphabeta.hpp"
#include "state.hpp"


/*============================================================
 * AlphaBeta — eval_ctx
 *
 * Negamax with alpha-beta pruning.
 * Caller manages memory (no delete inside).
 *============================================================*/
int AlphaBeta::eval_ctx(
    State *state,
    int depth,
    int alpha,
    int beta,
    GameHistory& history,
    int ply,
    SearchContext& ctx,
    const ABParams& p
){
    ctx.nodes++;
    if(ply > ctx.seldepth){
        ctx.seldepth = ply;
    }
    if(ctx.stop){
        return 0;
    }

    /* === Lazy move generation (sets game_state) === */
    if(state->legal_actions.empty() && state->game_state == UNKNOWN){
        state->get_legal_actions();
    }

    /* === Terminal / leaf checks === */
    GameState now_res = state->game_state;
    if(now_res == WIN){
        return P_MAX - ply;
    }
    if(now_res == DRAW){
        return 0;
    }

    /* === Repetition check (game-specific) === */
    int rep_score;
    if(state->check_repetition(history, rep_score)){
        return rep_score;
    }
    history.push(state->hash());

    if(depth == 0){
        int score = state->evaluate(p.use_nnue, p.use_kp_eval, p.use_eval_mobility, &history);
        history.pop(state->hash());
        return score;
    }

    /* === Alpha-beta loop === */
    for(auto& move : state->legal_actions){
        State *next = state->next_state(move);
        bool same = next->same_player_as_parent();
        int score = same
            ? eval_ctx(next, depth - 1, alpha, beta, history, ply + 1, ctx, p)
            : -eval_ctx(next, depth - 1, -beta, -alpha, history, ply + 1, ctx, p);
        delete next;

        if(score > alpha){
            alpha = score;
        }
        if(alpha >= beta){
            history.pop(state->hash());
            return alpha;
        }
    }

    history.pop(state->hash());
    return alpha;
}


/*============================================================
 * AlphaBeta — eval_ctx_mu (make-unmake variant)
 *
 * Same as eval_ctx but uses in-place make/unmake instead of
 * next_state/delete. Zero allocation in the search loop.
 *============================================================*/
int AlphaBeta::eval_ctx_mu(
    State *state,
    int depth,
    int alpha,
    int beta,
    GameHistory& history,
    int ply,
    SearchContext& ctx,
    const ABParams& p
){
    ctx.nodes++;
    if(ply > ctx.seldepth) ctx.seldepth = ply;
    if(ctx.stop) return 0;

    if(state->legal_actions.empty() && state->game_state == UNKNOWN){
        state->get_legal_actions();
    }

    if(state->game_state == WIN) return P_MAX - ply;
    if(state->game_state == DRAW) return 0;

    int rep_score;
    if(state->check_repetition(history, rep_score)) return rep_score;
    history.push(state->hash());

    if(depth == 0){
        int score = state->evaluate(p.use_nnue, p.use_kp_eval, p.use_eval_mobility, &history);
        history.pop(state->hash());
        return score;
    }

    /* Save legal actions (make_move clears them) */
    auto moves = state->legal_actions;

    for(auto& move : moves){
        BaseState::UndoInfo undo;
        state->make_move(move, undo);

        bool same = state->same_player_as_parent();
        int score = same
            ? eval_ctx_mu(state, depth - 1, alpha, beta, history, ply + 1, ctx, p)
            : -eval_ctx_mu(state, depth - 1, -beta, -alpha, history, ply + 1, ctx, p);

        state->unmake_move(move, undo);

        if(score > alpha) alpha = score;
        if(alpha >= beta){
            history.pop(state->hash());
            return alpha;
        }
    }

    history.pop(state->hash());
    return alpha;
}


/*============================================================
 * AlphaBeta — search
 *
 * Iterate legal moves, call eval_ctx, return SearchResult.
 *============================================================*/
SearchResult AlphaBeta::search(
    State *state,
    int depth,
    GameHistory& history,
    SearchContext& ctx
){
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

    bool use_mu = state->supports_make_unmake();

    for(auto& move : all_moves){
        int score;
        if(use_mu){
            BaseState::UndoInfo undo;
            state->make_move(move, undo);
            bool same = state->same_player_as_parent();
            score = same
                ? eval_ctx_mu(state, depth - 1, alpha, beta_root, history, 1, ctx, p)
                : -eval_ctx_mu(state, depth - 1, -(beta_root), -alpha, history, 1, ctx, p);
            state->unmake_move(move, undo);
        }else{
            State *next = state->next_state(move);
            bool same = next->same_player_as_parent();
            score = same
                ? eval_ctx(next, depth - 1, alpha, beta_root, history, 1, ctx, p)
                : -eval_ctx(next, depth - 1, -(beta_root), -alpha, history, 1, ctx, p);
            delete next;
        }

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
