#include <iostream>
#include <cstdlib>
#include "config.hpp"
#include "state.hpp"

int main(){
    srand(42);
    int mismatches = 0;
    int total = 0;
    
    for(int trial = 0; trial < 1000; trial++){
        State* g = new State();
        g->get_legal_actions();
        int moves = rand() % 30;
        for(int j = 0; j < moves; j++){
            if(g->game_state == WIN || g->game_state == DRAW || g->legal_actions.empty()) break;
            int idx = rand() % g->legal_actions.size();
            State* next = g->next_state(g->legal_actions[idx]);
            next->get_legal_actions();
            
            /* Compare incremental hash with full recompute */
            uint64_t inc_hash = next->hash();
            uint64_t full_hash = next->compute_hash_full();
            total++;
            if(inc_hash != full_hash){
                mismatches++;
                if(mismatches <= 5){
                    std::cout << "MISMATCH trial=" << trial << " move=" << j
                              << " inc=0x" << std::hex << inc_hash
                              << " full=0x" << full_hash << std::dec << std::endl;
                }
            }
            
            delete g;
            g = next;
        }
        delete g;
    }
    
    std::cout << "Tested " << total << " positions, " << mismatches << " mismatches" << std::endl;
    return mismatches > 0 ? 1 : 0;
}
