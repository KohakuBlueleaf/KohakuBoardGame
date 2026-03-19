#pragma once
#include "search_types.hpp"

/* === PVS-specific params (parsed from ParamMap for fast access) === */
struct PVSParams {
    bool use_nnue = true;
    bool use_kp_eval = true;
    bool use_eval_mobility = true;
    bool use_move_ordering = true;
    bool use_quiescence = true;
    int  quiescence_max_depth = 16;
    bool use_tt = true;
    bool use_killer_moves = true;
    int  killer_slots = 2;
    bool use_null_move = true;
    int  null_move_r = 2;
    bool use_lmr = true;
    int  lmr_full_depth = 3;
    int  lmr_depth_limit = 3;
    bool report_partial = true;

    static PVSParams from_map(const ParamMap& m){
        PVSParams p;
        p.use_nnue           = param_bool(m, "UseNNUE", true);
        p.use_kp_eval        = param_bool(m, "UseKPEval", true);
        p.use_eval_mobility  = param_bool(m, "UseEvalMobility", true);
        p.use_move_ordering  = param_bool(m, "UseMoveOrdering", true);
        p.use_quiescence     = param_bool(m, "UseQuiescence", true);
        p.quiescence_max_depth = param_int(m, "QuiescenceMaxDepth", 16);
        p.use_tt             = param_bool(m, "UseTT", true);
        p.use_killer_moves   = param_bool(m, "UseKillerMoves", true);
        p.killer_slots       = param_int(m, "KillerSlots", 2);
        p.use_null_move      = param_bool(m, "UseNullMove", true);
        p.null_move_r        = param_int(m, "NullMoveR", 2);
        p.use_lmr            = param_bool(m, "UseLMR", true);
        p.lmr_full_depth     = param_int(m, "LMRFullDepth", 3);
        p.lmr_depth_limit    = param_int(m, "LMRDepthLimit", 3);
        p.report_partial     = param_bool(m, "ReportPartial", true);
        return p;
    }
};

class PVS{
public:
    static int eval_ctx(State *state, int depth, int alpha, int beta,
                        SearchContext& ctx, const PVSParams& p,
                        int ply = 0, bool can_null = true);
    static SearchResult search(State *state, int depth, SearchContext& ctx);
    static std::vector<Move> extract_pv(State *state, int depth);

    static ParamMap default_params();
    static std::vector<ParamDef> param_defs();
};
