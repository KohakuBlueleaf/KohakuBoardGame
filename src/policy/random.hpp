#pragma once
#include "search_types.hpp"

class Random{
public:
    static SearchResult search(State *state, int depth, SearchContext& ctx);

    static ParamMap default_params();
    static std::vector<ParamDef> param_defs();
};
