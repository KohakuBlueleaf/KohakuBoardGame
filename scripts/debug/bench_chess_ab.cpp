#include <iostream>
#include <chrono>
#include <cstdlib>
#include "config.hpp"
#include "state.hpp"
#include "../../policy/alphabeta.hpp"
#include "../../policy/game_history.hpp"
#include "../../policy/pvs/tt.hpp"

int main(){
    srand(42);
    State* g = new State();
    g->get_legal_actions();
    for(int i = 0; i < 6; i++){
        if(g->game_state == WIN || g->legal_actions.empty()) break;
        State* next = g->next_state(g->legal_actions[0]);
        next->get_legal_actions();
        delete g; g = next;
    }
    std::cout << "Position: player=" << g->player << " legal=" << g->legal_actions.size() << std::endl;
    for(int depth = 4; depth <= 6; depth++){
        tt_clear();
        SearchContext ctx;
        GameHistory history;
        auto t0 = std::chrono::high_resolution_clock::now();
        auto result = AlphaBeta::search(g, depth, history, ctx);
        auto t1 = std::chrono::high_resolution_clock::now();
        double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        uint64_t nps = ms > 0 ? (uint64_t)(ctx.nodes * 1000.0 / ms) : 0;
        std::cout << "d=" << depth << " score=" << result.score << " nodes=" << ctx.nodes
                  << " time=" << ms << "ms nps=" << nps << std::endl;
    }
    delete g;
    return 0;
}
