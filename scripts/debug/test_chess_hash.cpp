#include <iostream>
#include <cstdlib>
#include "config.hpp"
#include "state.hpp"
int main(){
    srand(42);
    int mismatches = 0, total = 0;
    for(int trial = 0; trial < 500; trial++){
        State* g = new State();
        g->get_legal_actions();
        int moves = rand() % 20;
        for(int j = 0; j < moves; j++){
            if(g->game_state == WIN || g->game_state == DRAW || g->legal_actions.empty()) break;
            int idx = rand() % g->legal_actions.size();
            State* next = g->next_state(g->legal_actions[idx]);
            next->get_legal_actions();
            uint64_t inc = next->hash();
            uint64_t full = next->compute_hash_full();
            total++;
            if(inc != full){ mismatches++; if(mismatches<=3) std::cout << "MISMATCH t=" << trial << " m=" << j << std::endl; }
            delete g; g = next;
        }
        delete g;
    }
    std::cout << "Tested " << total << ", mismatches: " << mismatches << std::endl;
    return mismatches > 0 ? 1 : 0;
}
