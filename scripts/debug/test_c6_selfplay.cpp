#include <iostream>
#include "config.hpp"
#include "state.hpp"
#include "../../policy/pvs.hpp"
#include "../../policy/game_history.hpp"
#include "../../policy/pvs/tt.hpp"

int main(){
    State* game = new State();
    game->get_legal_actions();
    
    std::cout << game->encode_output() << std::endl;
    
    GameHistory history;
    for(int step = 0; step < 30; step++){
        if(game->game_state == WIN || game->game_state == DRAW || game->legal_actions.empty()){
            std::cout << "Game over: state=" << game->game_state << std::endl;
            break;
        }
        
        tt_clear();
        SearchContext ctx;
        int depth = 2;
        auto result = PVS::search(game, depth, history, ctx);
        
        auto m = result.best_move;
        int r1 = m.first.first, c1 = m.first.second;
        int r2 = m.second.first, c2 = m.second.second;
        
        std::cout << "Step " << step << " (player " << game->player << "): "
                  << (char)('a'+c1) << (15-r1) << (char)('a'+c2) << (15-r2)
                  << " score=" << result.score 
                  << " nodes=" << ctx.nodes << std::endl;
        
        State* next = game->next_state(m);
        next->get_legal_actions();
        
        // Show eval of resulting position
        std::cout << "  After-move eval (from next player): " << next->evaluate() << std::endl;
        
        delete game;
        game = next;
        
        std::cout << game->encode_output() << std::endl;
    }
    
    delete game;
    return 0;
}
