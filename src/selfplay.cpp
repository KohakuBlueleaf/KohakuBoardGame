#include <iostream>

#include "config.hpp"
#include "./state/state.hpp"
#include "./policy/minimax.hpp"
#include "./policy/alphabeta.hpp"
#include "./policy/random.hpp"
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
  game->print();
  std::cout << std::endl;
  
  int step = 0;
  while (1){
    step += 1;
    if(game->game_state == WIN) break;
    auto action_white = AlphaBeta::get_move(game, 9);
    std::cout << "\nstep " << step << " white's turn\n";
    std::cout << action_white.first.first << ", " << action_white.first.second << " → "\
              << action_white.second.first << ", " << action_white.second.second << "\n";
    game = game->next_state(action_white);
    game->print();
    std::cout << std::endl;
    
    step += 1;
    if(game->game_state == WIN) break;
    auto action_black = AlphaBeta::get_move(game, 9);
    std::cout << "\nstep " << step << " black's turn\n";
    std::cout << action_black.first.first << ", " << action_black.first.second << " → "\
              << action_black.second.first << ", " << action_black.second.second << "\n";
    game = game->next_state(action_black);
    game->print();
    std::cout << std::endl;
  }
  
  Move win_action = game->legal_actions.back();
  std::cout << "\nstep " << step << " " << (game->player?"black":"white") << " WIN!\n";
  std::cout << win_action.first.first << ", " << win_action.first.second << " → "\
            << win_action.second.first << ", " << win_action.second.second << "\n";
  game = game->next_state(win_action);
  game->print();
  
  return 0;
}