#pragma once
/*============================================================
 * Algorithm Registry
 *
 * Each algorithm defines:
 *   - search() function
 *   - default_params() returning ParamMap
 *   - param_defs() for UCI option advertisement
 *============================================================*/

#include <string>
#include <functional>
#include <vector>
#include "../search_types.hpp"
#include "pvs.hpp"
#include "alphabeta.hpp"
#include "minimax.hpp"
#include "random.hpp"

struct AlgoEntry {
    std::string name;
    ParamMap default_params;
    std::vector<ParamDef> param_defs;
    std::function<SearchResult(State*, int, SearchContext&)> search;
};

inline const std::vector<AlgoEntry>& get_algo_table(){
    static const std::vector<AlgoEntry> table = {
        {"pvs",       PVS::default_params(),       PVS::param_defs(),
         [](State* s, int d, SearchContext& c){ return PVS::search(s, d, c); }},
        {"alphabeta", AlphaBeta::default_params(),  AlphaBeta::param_defs(),
         [](State* s, int d, SearchContext& c){ return AlphaBeta::search(s, d, c); }},
        {"minimax",   MiniMax::default_params(),    MiniMax::param_defs(),
         [](State* s, int d, SearchContext& c){ return MiniMax::search(s, d, c); }},
        {"random",    Random::default_params(),     Random::param_defs(),
         [](State* s, int d, SearchContext& c){ return Random::search(s, d, c); }},
    };
    return table;
}

inline const AlgoEntry* find_algo(const std::string& name){
    for(auto& entry : get_algo_table()){
        if(entry.name == name){ return &entry; }
    }
    return nullptr;
}

inline std::string default_algo_name(){ return "pvs"; }
