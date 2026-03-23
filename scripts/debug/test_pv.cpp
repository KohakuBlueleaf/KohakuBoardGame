#include <iostream>
#include <cstdlib>
#include "config.hpp"
#include "state.hpp"
#include "../../policy/pvs.hpp"
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
        delete g;
        g = next;
    }

    for(int depth = 4; depth <= 8; depth++){
        tt_clear();
        State* s = new State(g->board, g->player);
        s->get_legal_actions();
        SearchContext ctx;
        GameHistory history;
        auto result = PVS::search(s, depth, history, ctx);
        std::cout << "d=" << depth
                  << " score=" << result.score
                  << " pv_len=" << result.pv.size()
                  << " nodes=" << ctx.nodes
                  << " pv:";
        for(auto& m : result.pv){
            std::cout << " (" << m.first.first << "," << m.first.second
                      << ">" << m.second.first << "," << m.second.second << ")";
        }
        std::cout << std::endl;
        delete s;
    }
    delete g;
    return 0;
}
