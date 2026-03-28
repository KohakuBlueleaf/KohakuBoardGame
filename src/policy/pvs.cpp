#include <algorithm>
#include <vector>
#include <utility>
#include <cstdint>
#include "pvs.hpp"
#include "state.hpp"
#include "config.hpp"
#include "game_history.hpp"
#include "pvs/tt.hpp"
#include "pvs/killer_moves.hpp"
#include "pvs/move_ordering.hpp"
#include "pvs/quiescence.hpp"


/* Helper: call eval_ctx with correct window direction based on
 * whether the child has the same player as parent.
 * For standard 2-player games this compiles to normal negamax.
 *
 * copy-make version: takes ownership of child, deletes after. */
static inline int call_eval(
    State* child,
    int depth,
    int alpha,
    int beta,
    GameHistory& history,
    int ply,
    bool can_null,
    SearchContext& ctx,
    const PVSParams& p
){
    if(child->same_player_as_parent()){
        return PVS::eval_ctx(child, depth, alpha, beta, history, ply, can_null, ctx, p);
    }else{
        return -PVS::eval_ctx(child, depth, -beta, -alpha, history, ply, can_null, ctx, p);
    }
}

/* make-unmake version: mutates state in place, restores after. */
static inline int call_eval_mu(
    State* state,
    const Move& move,
    int depth,
    int alpha,
    int beta,
    GameHistory& history,
    int ply,
    bool can_null,
    SearchContext& ctx,
    const PVSParams& p
){
    BaseState::UndoInfo undo;
    state->make_move(move, undo);
    bool same = state->same_player_as_parent();
    int score = same
        ? PVS::eval_ctx(state, depth, alpha, beta, history, ply, can_null, ctx, p)
        : -PVS::eval_ctx(state, depth, -beta, -alpha, history, ply, can_null, ctx, p);
    state->unmake_move(move, undo);
    return score;
}

/*============================================================
 * PVS (Principal Variation Search) with ParamMap
 *
 * All features controlled by PVSParams (parsed once from
 * ctx.params at root, then threaded through):
 *   use_tt, use_null_move, use_lmr, use_killer_moves,
 *   use_quiescence, use_move_ordering
 *============================================================*/
/* RAII guard: push on construction, pop on destruction */
struct HistoryGuard {
    GameHistory& hist;
    uint64_t h;
    HistoryGuard(
        GameHistory& hist, uint64_t hash
    ): hist(hist), h(hash) {
        hist.push(h);
    }
    ~HistoryGuard(){
        hist.pop(h);
    }
};


int PVS::eval_ctx(
    State *state,
    int depth,
    int alpha,
    int beta,
    GameHistory& history,
    int ply,
    bool can_null,
    SearchContext& ctx,
    const PVSParams& p
){
    ctx.nodes++;
    if(ctx.stop){
        delete state;
        return 0;
    }

    /* === Lazy move generation (sets game_state) === */
    if(state->legal_actions.empty() && state->game_state == UNKNOWN){
        state->get_legal_actions();
    }

    /* === Terminal checks === */
    if(state->game_state == WIN){
        delete state;
        return P_MAX - ply;
    }
    if(state->game_state == DRAW){
        delete state;
        return 0;
    }

    /* === Repetition check (game-specific rule) === */
    uint64_t state_hash = state->hash();
    int rep_score;
    if(state->check_repetition(history, rep_score)){
        delete state;
        return rep_score;
    }
    /* RAII guard: push now, auto-pop on any return from this function */
    HistoryGuard hist_guard(history, state_hash);

    /* === Leaf node === */
    if(depth == 0){
        if(p.use_quiescence){
            /* quiescence_ctx takes ownership of state and deletes it */
            return quiescence_ctx(state, alpha, beta, 0, history, ply, ctx, p);
        }else{
            int score = state->evaluate(p.use_nnue, p.use_kp_eval, p.use_eval_mobility, &history);
            delete state;
            return score;
        }
    }

    /* === Track selective depth === */
    if(ply > ctx.seldepth){
        ctx.seldepth = ply;
    }

    int orig_alpha = alpha;
    Move tt_best;
    bool has_tt_move = false;

    /* === TT probe === */
    uint64_t hash = 0;
    if(p.use_tt){
        hash = compute_hash(state);

        TTEntry* tte = tt_probe(hash);
        if(tte && tte->depth >= depth){
            if(tte->flag == TT_EXACT){
                delete state;
                return tte->score;
            }
            if(tte->flag == TT_LOWER && tte->score >= beta){
                delete state;
                return tte->score;
            }
            if(tte->flag == TT_UPPER && tte->score <= alpha){
                delete state;
                return tte->score;
            }
        }
        if(tte){
            tt_best = tte->get_move();
            has_tt_move = true;
        }
    }

    /* === Null move pruning === */
    if(p.use_null_move && can_null && depth >= p.null_move_r + 1){
        BaseState* null_base = state->create_null_state();
        if(null_base != nullptr){
            State* null_state = static_cast<State*>(null_base);
            if(null_state->game_state != WIN && null_state->game_state != DRAW){
                int null_score = -eval_ctx(
                    null_state, depth - 1 - p.null_move_r,
                    -beta, -(beta - 1), history, ply + 1, false, ctx, p
                );
                if(ctx.stop){
                    delete state;
                    return 0;
                }
                if(null_score >= beta){
                    delete state;
                    return beta;
                }
            }else{
                delete null_state;
            }
        }
    }

    /* === Move ordering === */
    auto moves = get_ordered_moves(
        state, has_tt_move ? &tt_best : nullptr, ply, p
    );

    Move best_move;
    bool first_child = true;
    int move_index = 0;
    /* PVS eval_ctx deletes state, so make-unmake can't be used here
     * without a major refactor to ownership semantics. Use copy-make. */
    auto do_eval = [&](const Move& m, int d, int a, int b, bool cn) -> int {
        return call_eval(state->next_state(m), d, a, b, history, ply + 1, cn, ctx, p);
    };

    for(auto& move : moves){
        int score;

        if(first_child){
            /* First move: full window, full depth */
            score = do_eval(move, depth - 1, alpha, beta, true);
            first_child = false;
            best_move = move;
        }else{
            /* === Late Move Reduction === */
            bool do_lmr = false;
            if(p.use_lmr
               && move_index >= p.lmr_full_depth
               && depth >= p.lmr_depth_limit
            ){
                int to_r = move.second.first;
                int to_c = move.second.second;
                bool is_capture = state->piece_at(1 - state->player, to_r, to_c) != 0;
                if(!is_capture){
                    if(p.use_killer_moves){
                        if(!is_killer(ply, move, p.killer_slots)){
                            do_lmr = true;
                        }
                    }else{
                        do_lmr = true;
                    }
                }
            }

            if(do_lmr){
                /* LMR: null-window, reduced depth */
                score = do_eval(move, depth - 2, alpha, alpha + 1, true);
                if(score > alpha){
                    /* Re-search at full depth, null-window */
                    score = do_eval(move, depth - 1, alpha, alpha + 1, true);
                    if(score > alpha && score < beta){
                        /* Full window re-search */
                        score = do_eval(move, depth - 1, alpha, beta, true);
                    }
                }
            }else{
                /* Standard PVS null-window search */
                score = do_eval(move, depth - 1, alpha, alpha + 1, true);
                if(score > alpha && score < beta){
                    score = do_eval(move, depth - 1, alpha, beta, true);
                }
            }
        }

        if(ctx.stop){
            delete state;
            return 0;
        }

        if(score > alpha){
            alpha = score;
            best_move = move;
        }
        if(alpha >= beta){
            /* Beta cutoff -- store killer if quiet move */
            if(p.use_killer_moves){
                int to_r = move.second.first;
                int to_c = move.second.second;
                bool is_capture = state->piece_at(1 - state->player, to_r, to_c) != 0;
                if(!is_capture){
                    store_killer(ply, move, p.killer_slots);
                }
            }
            break;
        }
        move_index++;
    }

    /* === TT store === */
    if(p.use_tt){
        TTFlag flag;
        if(alpha <= orig_alpha){
            flag = TT_UPPER;
        }else if(alpha >= beta){
            flag = TT_LOWER;
        }else{
            flag = TT_EXACT;
        }
        tt_store(hash, depth, alpha, flag, best_move);
    }

    delete state;
    return alpha;
}


/*============================================================
 * Root search: returns SearchResult with best move, score,
 * node count, seldepth, and principal variation.
 *============================================================*/
SearchResult PVS::search(
    State *state,
    int depth,
    GameHistory& history,
    SearchContext& ctx
){
    ctx.reset();
    PVSParams p = PVSParams::from_map(ctx.params);

    int alpha = M_MAX - 10;
    int beta  = P_MAX + 10;

    Move tt_best;
    bool has_tt_move = false;

    /* === TT probe at root === */
    if(p.use_tt){
        uint64_t hash = compute_hash(state);
        TTEntry* tte = tt_probe(hash);
        if(tte){
            tt_best = tte->get_move();
            has_tt_move = true;
        }
    }

    auto moves = get_ordered_moves(
        state, has_tt_move ? &tt_best : nullptr, 0, p
    );

    Move best_move;
    bool first_child = true;
    int move_index = 0;
    int total_moves = (int)moves.size();

    auto do_eval_root = [&](const Move& m, int d, int a, int b) -> int {
        return call_eval(state->next_state(m), d, a, b, history, 1, true, ctx, p);
    };

    for(auto& move : moves){
        int score;

        if(first_child){
            score = do_eval_root(move, depth - 1, alpha, beta);
            first_child = false;
        }else{
            score = do_eval_root(move, depth - 1, alpha, alpha + 1);
            if(score > alpha && score < beta){
                score = do_eval_root(move, depth - 1, alpha, beta);
            }
        }

        if(ctx.stop){
            break;
        }

        if(score > alpha){
            best_move = move;
            alpha = score;
            if(p.report_partial && ctx.on_root_update){
                ctx.on_root_update({best_move, alpha, depth, move_index + 1, total_moves});
            }
        }
        move_index++;
    }

    /* === Build result === */
    SearchResult result;
    result.best_move = best_move;
    result.score     = alpha;
    result.depth     = depth;
    result.seldepth  = ctx.seldepth;
    result.nodes     = ctx.nodes;
    result.pv = extract_pv(state, depth + 10);
    /* Ensure PV starts with root best_move */
    if(best_move != Move() && (result.pv.empty() || result.pv[0] != best_move)){
        /* TT PV disagrees with root — rebuild from best_move's child */
        State* child = state->next_state(best_move);
        auto tail = extract_pv(child, depth + 9);
        delete child;
        result.pv.clear();
        result.pv.push_back(best_move);
        result.pv.insert(result.pv.end(), tail.begin(), tail.end());
    }

    return result;
}


/*============================================================
 * Extract principal variation by walking the TT from the
 * current position. Returns up to `depth` moves.
 *============================================================*/
std::vector<Move> PVS::extract_pv(State *state, int max_len){
    std::vector<Move> pv;
    State* cur = new State(*state);  /* copy the full state */
    cur->get_legal_actions();

    std::vector<uint64_t> seen;

    for(int i = 0; i < max_len; i++){
        if(cur->game_state == WIN || cur->game_state == DRAW){
            break;
        }
        uint64_t hash = compute_hash(cur);

        /* Cycle detection */
        bool cycle = false;
        for(auto h : seen){
            if(h == hash){
                cycle = true;
                break;
            }
        }
        if(cycle){
            break;
        }
        seen.push_back(hash);

        TTEntry* tte = tt_probe(hash);
        if(!tte || tte->flag == TT_NONE){
            break;
        }
        Move mv = tte->get_move();

        /* Validate legality */
        bool legal = false;
        for(auto& m : cur->legal_actions){
            if(m == mv){
                legal = true;
                break;
            }
        }
        if(!legal){
            break;
        }

        pv.push_back(mv);
        State* next = cur->next_state(mv);
        next->get_legal_actions();
        delete cur;
        cur = next;
    }

    delete cur;
    return pv;
}


/*============================================================
 * Default parameters and UCI option definitions
 *============================================================*/
ParamMap PVS::default_params(){
    return {
        {"UseNNUE", "true"},
        {"UseKPEval", "true"},
        {"UseEvalMobility", "true"},
        {"UseMoveOrdering", "true"},
        {"UseQuiescence", "true"},
        {"QuiescenceMaxDepth", "16"},
        {"UseTT", "true"},
        {"UseKillerMoves", "true"},
        {"KillerSlots", "2"},
        {"UseNullMove", "true"},
        {"NullMoveR", "2"},
        {"UseLMR", "true"},
        {"LMRFullDepth", "3"},
        {"LMRDepthLimit", "3"},
        {"ReportPartial", "true"},
    };
}

std::vector<ParamDef> PVS::param_defs(){
    return {
        {"UseNNUE", ParamDef::CHECK, "true"},
        {"UseKPEval", ParamDef::CHECK, "true"},
        {"UseEvalMobility", ParamDef::CHECK, "true"},
        {"UseMoveOrdering", ParamDef::CHECK, "true"},
        {"UseQuiescence", ParamDef::CHECK, "true"},
        {"QuiescenceMaxDepth", ParamDef::SPIN, "16", 1, 64},
        {"UseTT", ParamDef::CHECK, "true"},
        {"UseKillerMoves", ParamDef::CHECK, "true"},
        {"KillerSlots", ParamDef::SPIN, "2", 1, 4},
        {"UseNullMove", ParamDef::CHECK, "true"},
        {"NullMoveR", ParamDef::SPIN, "2", 1, 4},
        {"UseLMR", ParamDef::CHECK, "true"},
        {"LMRFullDepth", ParamDef::SPIN, "3", 1, 10},
        {"LMRDepthLimit", ParamDef::SPIN, "3", 1, 10},
        {"ReportPartial", ParamDef::CHECK, "true"},
    };
}
