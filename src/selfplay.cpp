#include <iostream>

#include "config.hpp"
#include "state.hpp"
#include "./policy/alphabeta.hpp"
#include "./policy/game_history.hpp"
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
    GameHistory game_history;
    while(true){
        /* === Player 0's turn === */
        step += 1;
        if(game->legal_actions.empty() && game->game_state == UNKNOWN){
            game->get_legal_actions();
        }
        if(game->game_state == WIN || game->game_state == DRAW){
            break;
        }

        game_history.push(game->hash());
        SearchContext ctx_0;
        auto action_0 = AlphaBeta::search(game, 9, game_history, ctx_0).best_move;
        std::cout << "\nstep " << step << " Player 0's turn\n";
        std::cout << action_0.first.first << ", " << action_0.first.second << " -> "
            << action_0.second.first << ", " << action_0.second.second << "\n";

        State* prev = game;
        game = game->next_state(action_0);
        delete prev;
        std::cout << game->encode_output();
        std::cout << std::endl;

        /* === Player 1's turn === */
        step += 1;
        if(game->legal_actions.empty() && game->game_state == UNKNOWN){
            game->get_legal_actions();
        }
        if(game->game_state == WIN || game->game_state == DRAW){
            break;
        }

        game_history.push(game->hash());
        SearchContext ctx_1;
        auto action_1 = AlphaBeta::search(game, 9, game_history, ctx_1).best_move;
        std::cout << "\nstep " << step << " Player 1's turn\n";
        std::cout << action_1.first.first << ", " << action_1.first.second << " -> "
            << action_1.second.first << ", " << action_1.second.second << "\n";

        prev = game;
        game = game->next_state(action_1);
        delete prev;
        std::cout << game->encode_output();
        std::cout << std::endl;
    }

    if(game->game_state == DRAW){
        std::cout << "\nDraw by repetition or step limit!\n";
        delete game;
        return 0;
    }

    /* === Final move (winning capture) === */
    Move win_action = game->legal_actions.back();
    std::cout << "\nstep " << step << " Player " << game->player << " WIN!\n";
    std::cout << win_action.first.first << ", " << win_action.first.second << " -> "
        << win_action.second.first << ", " << win_action.second.second << "\n";

    State* prev = game;
    game = game->next_state(win_action);
    delete prev;
    std::cout << game->encode_output();

    delete game;
    return 0;
}
