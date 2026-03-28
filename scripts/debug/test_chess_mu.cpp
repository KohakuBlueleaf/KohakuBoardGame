#include <iostream>
#include <cstdlib>
#include "config.hpp"
#include <cstring>
#include "state.hpp"
int main(){
    srand(42);
    int ok = 0, fail = 0;
    for(int trial = 0; trial < 200; trial++){
        State* g = new State();
        g->get_legal_actions();
        for(int j = 0; j < 15; j++){
            if(g->game_state == WIN || g->game_state == DRAW || g->legal_actions.empty()) break;
            int idx = rand() % g->legal_actions.size();
            Move m = g->legal_actions[idx];
            
            /* Save original state */
            Board orig = g->board;
            int orig_player = g->player;
            uint64_t orig_hash = g->hash();
            
            /* Make then unmake */
            BaseState::UndoInfo undo;
            g->make_move(m, undo);
            g->unmake_move(m, undo);
            
            /* Verify restoration */
            bool board_ok = (memcmp(&g->board, &orig, sizeof(Board)) == 0);
            bool player_ok = (g->player == orig_player);
            bool hash_ok = (g->hash() == orig_hash);
            
            if(!board_ok || !player_ok || !hash_ok){
                fail++;
                if(fail <= 3){
                    std::cout << "FAIL t=" << trial << " j=" << j 
                              << " board=" << board_ok << " player=" << player_ok 
                              << " hash=" << hash_ok << std::endl;
                }
            }else{
                ok++;
            }
            
            /* Advance with copy-make for next iteration */
            State* next = g->next_state(m);
            next->get_legal_actions();
            delete g;
            g = next;
        }
        delete g;
    }
    std::cout << "OK=" << ok << " FAIL=" << fail << std::endl;
    return fail > 0 ? 1 : 0;
}
