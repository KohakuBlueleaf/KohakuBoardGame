#include <algorithm>
#include <vector>
#include <utility>
#include <cstdint>
#include "pvs.hpp"
#include "../state/state.hpp"
#include "../config.hpp"
#include "pvs/tt.hpp"
#include "pvs/killer_moves.hpp"
#include "pvs/move_ordering.hpp"
#include "pvs/quiescence.hpp"


/*============================================================
 * PVS (Principal Variation Search) with ParamMap
 *
 * All features controlled by PVSParams (parsed once from
 * ctx.params at root, then threaded through):
 *   use_tt, use_null_move, use_lmr, use_killer_moves,
 *   use_quiescence, use_move_ordering
 *============================================================*/
int PVS::eval_ctx(
    State *state,
    int depth,
    int alpha,
    int beta,
    SearchContext& ctx,
    const PVSParams& p,
    int ply,
    bool can_null
) {
    ctx.nodes++;
    if(ctx.stop){
        delete state;
        return 0;
    }

    /* === Terminal checks === */
    if(state->game_state == WIN){
        delete state;
        return P_MAX;
    }
    if(state->game_state == DRAW){
        delete state;
        return 0;
    }

    /* === Leaf node === */
    if(depth == 0){
        if(p.use_quiescence){
            return quiescence_ctx(state, alpha, beta, 0, ctx, p, ply);
        }else{
            int score = state->evaluate(p.use_nnue, p.use_kp_eval, p.use_eval_mobility);
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
        State* null_state = new State(state->board, 1 - state->player);
        null_state->get_legal_actions();

        if(null_state->game_state != WIN && null_state->game_state != DRAW){
            int null_score = -eval_ctx(
                null_state, depth - 1 - p.null_move_r,
                -beta, -(beta - 1), ctx, p, ply + 1, false
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

    /* === Move ordering === */
    auto moves = get_ordered_moves(
        state, has_tt_move ? &tt_best : nullptr, ply, p
    );

    Move best_move;
    bool first_child = true;
    int move_index = 0;

    for(auto& move : moves){
        int score;

        if(first_child){
            /* First move: full window, full depth */
            score = -eval_ctx(
                state->next_state(move), depth - 1,
                -beta, -alpha, ctx, p, ply + 1, true
            );
            first_child = false;
            best_move = move;
        }else{
            /* === Late Move Reduction === */
            bool do_lmr = false;
            if(p.use_lmr
               && move_index >= p.lmr_full_depth
               && depth >= p.lmr_depth_limit
            ) {
                int to_r = move.second.first;
                int to_c = move.second.second;
                bool is_capture = state->board.board[1 - state->player][to_r][to_c] != 0;
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
                score = -eval_ctx(
                    state->next_state(move), depth - 2,
                    -(alpha + 1), -alpha, ctx, p, ply + 1, true
                );
                if(score > alpha){
                    /* Re-search at full depth, null-window */
                    score = -eval_ctx(
                        state->next_state(move), depth - 1,
                        -(alpha + 1), -alpha, ctx, p, ply + 1, true
                    );
                    if(score > alpha && score < beta){
                        /* Full window re-search */
                        score = -eval_ctx(
                            state->next_state(move), depth - 1,
                            -beta, -alpha, ctx, p, ply + 1, true
                        );
                    }
                }
            }else{
                /* Standard PVS null-window search */
                score = -eval_ctx(
                    state->next_state(move), depth - 1,
                    -(alpha + 1), -alpha, ctx, p, ply + 1, true
                );
                if(score > alpha && score < beta){
                    score = -eval_ctx(
                        state->next_state(move), depth - 1,
                        -beta, -alpha, ctx, p, ply + 1, true
                    );
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
                bool is_capture = state->board.board[1 - state->player][to_r][to_c] != 0;
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
SearchResult PVS::search(State *state, int depth, SearchContext& ctx){
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

    for(auto& move : moves){
        int score;

        if(first_child){
            score = -eval_ctx(
                state->next_state(move), depth - 1,
                -beta, -alpha, ctx, p, 1, true
            );
            first_child = false;
        }else{
            score = -eval_ctx(
                state->next_state(move), depth - 1,
                -(alpha + 1), -alpha, ctx, p, 1, true
            );
            if(score > alpha && score < beta){
                score = -eval_ctx(
                    state->next_state(move), depth - 1,
                    -beta, -alpha, ctx, p, 1, true
                );
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
    result.pv = extract_pv(state, depth + 10);  // try beyond nominal depth
    // Always ensure best_move is the first PV move
    if(result.pv.empty() && best_move != Move()){
        result.pv = {best_move};
    }else if(!result.pv.empty() && result.pv[0] != best_move && best_move != Move()){
        result.pv[0] = best_move;
    }

    return result;
}


/*============================================================
 * Extract principal variation by walking the TT from the
 * current position. Returns up to `depth` moves.
 *============================================================*/
std::vector<Move> PVS::extract_pv(State *state, int max_len){
    std::vector<Move> pv;
    State* cur = new State(state->board, state->player);
    cur->get_legal_actions();

    // Use a set to detect TT cycles (avoid infinite loops)
    std::vector<uint64_t> seen;

    for(int i = 0; i < max_len; i++){
        if(cur->game_state == WIN || cur->game_state == DRAW){
            break;
        }
        uint64_t hash = compute_hash(cur);

        // Cycle detection
        bool cycle = false;
        for(auto h : seen){
            if(h == hash){ cycle = true; break; }
        }
        if(cycle){ break; }
        seen.push_back(hash);

        TTEntry* tte = tt_probe(hash);
        if(!tte || tte->flag == TT_NONE){
            break;
        }
        Move mv = tte->get_move();

        // Validate legality
        bool legal = false;
        for(auto& m : cur->legal_actions){
            if(m == mv){ legal = true; break; }
        }
        if(!legal){ break; }

        pv.push_back(mv);
        State* next = cur->next_state(mv);
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
