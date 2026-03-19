#pragma once
#include "search_types.hpp"

struct ABParams {
    bool use_nnue = true;
    bool use_kp_eval = true;
    bool use_eval_mobility = true;
    bool report_partial = true;

    static ABParams from_map(const ParamMap& m){
        ABParams p;
        p.use_nnue          = param_bool(m, "UseNNUE", true);
        p.use_kp_eval       = param_bool(m, "UseKPEval", true);
        p.use_eval_mobility = param_bool(m, "UseEvalMobility", true);
        p.report_partial    = param_bool(m, "ReportPartial", true);
        return p;
    }
};

class AlphaBeta{
public:
    static int eval_ctx(State *state, int depth, int alpha, int beta,
                        SearchContext& ctx, const ABParams& p, int ply = 0);
    static SearchResult search(State *state, int depth, SearchContext& ctx);

    static ParamMap default_params();
    static std::vector<ParamDef> param_defs();
};
