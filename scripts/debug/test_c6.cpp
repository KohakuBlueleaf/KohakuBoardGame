#include <iostream>
#include <chrono>
#include "config.hpp"
#include "state.hpp"
#include "../../policy/pvs.hpp"
#include "../../policy/game_history.hpp"
#include "../../policy/pvs/tt.hpp"

int main(){
    Board b;
    State state(b, 0);
    std::cout << "Center stone: " << (int)state.board.board[7][7] << std::endl;
    std::cout << "Player: " << state.player << std::endl;

    state.get_legal_actions();
    std::cout << "Legal actions: " << state.legal_actions.size() << std::endl;
    std::cout << "GameState: " << state.game_state << std::endl;

    if(state.legal_actions.empty()){
        std::cout << "NO LEGAL ACTIONS" << std::endl;
        return 1;
    }

    for(int depth = 1; depth <= 3; depth++){
        tt_clear();
        SearchContext ctx;
        GameHistory history;
        auto t0 = std::chrono::high_resolution_clock::now();
        auto result = PVS::search(&state, depth, history, ctx);
        auto t1 = std::chrono::high_resolution_clock::now();
        double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        std::cout << "d=" << depth
                  << " score=" << result.score
                  << " nodes=" << ctx.nodes
                  << " pv=" << result.pv.size()
                  << " time=" << ms << "ms" << std::endl;
    }
    return 0;
}
