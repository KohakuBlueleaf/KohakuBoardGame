#pragma once
#include "search_types.hpp"

struct MMParams {
    bool use_nnue = true;
    bool use_kp_eval = true;
    bool use_eval_mobility = true;
    bool report_partial = true;

    static MMParams from_map(const ParamMap& m){
        MMParams p;
        p.use_nnue          = param_bool(m, "UseNNUE", true);
        p.use_kp_eval       = param_bool(m, "UseKPEval", true);
        p.use_eval_mobility = param_bool(m, "UseEvalMobility", true);
        p.report_partial    = param_bool(m, "ReportPartial", true);
        return p;
    }
};

class MiniMax{
public:
    static int eval_ctx(State *state, int depth, SearchContext& ctx,
                        const MMParams& p, int ply = 0);
    static SearchResult search(State *state, int depth, SearchContext& ctx);

    static ParamMap default_params();
    static std::vector<ParamDef> param_defs();
};
