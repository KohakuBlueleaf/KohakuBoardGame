#include <iostream>

#include "config.hpp"
#include "state.hpp"
#include "./policy/alphabeta.hpp"
#ifdef USE_NNUE
#include "./nnue/nnue.hpp"
#endif


int main(){
    srand(RANDOM_SEED);

#ifdef USE_NNUE
    if(nnue::init()){
        std::cerr << "NNUE model loaded." << std::endl;
    }else{
        std::cerr << "NNUE not loaded, using handcrafted eval." << std::endl;
    }
#endif

    State *game = new State();
    game->get_legal_actions();
    std::cout << game->encode_output();
    std::cout << std::endl;

    int step = 0;
    while(true){
        /* === White's turn === */
        step += 1;
        if(game->game_state == WIN){
            break;
        }

        SearchContext ctx_w;
        auto action_white = AlphaBeta::search(game, 9, ctx_w).best_move;
        std::cout << "\nstep " << step << " white's turn\n";
        std::cout << action_white.first.first << ", " << action_white.first.second << " -> "
                  << action_white.second.first << ", " << action_white.second.second << "\n";

        State* prev = game;
        game = game->next_state(action_white);
        delete prev;
        std::cout << game->encode_output();
        std::cout << std::endl;

        /* === Black's turn === */
        step += 1;
        if(game->game_state == WIN){
            break;
        }

        SearchContext ctx_b;
        auto action_black = AlphaBeta::search(game, 9, ctx_b).best_move;
        std::cout << "\nstep " << step << " black's turn\n";
        std::cout << action_black.first.first << ", " << action_black.first.second << " -> "
                  << action_black.second.first << ", " << action_black.second.second << "\n";

        prev = game;
        game = game->next_state(action_black);
        delete prev;
        std::cout << game->encode_output();
        std::cout << std::endl;
    }

    /* === Final move (winning capture) === */
    Move win_action = game->legal_actions.back();
    std::cout << "\nstep " << step << " " << (game->player ? "black" : "white") << " WIN!\n";
    std::cout << win_action.first.first << ", " << win_action.first.second << " -> "
              << win_action.second.first << ", " << win_action.second.second << "\n";

    State* prev = game;
    game = game->next_state(win_action);
    delete prev;
    std::cout << game->encode_output();

    delete game;
    return 0;
}
