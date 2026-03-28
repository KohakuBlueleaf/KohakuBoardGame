#include <iostream>
#include <chrono>
#include <cstdlib>
#include "config.hpp"
#include "state.hpp"
#include "../../policy/pvs.hpp"
#include "../../policy/alphabeta.hpp"
#include "../../policy/game_history.hpp"
#include "../../policy/pvs/tt.hpp"

static State* play_random_moves(int n){
    State* s = new State();
    s->get_legal_actions();
    for(int i = 0; i < n; i++){
        if(s->game_state == WIN || s->game_state == DRAW || s->legal_actions.empty()) break;
        int idx = rand() % (int)s->legal_actions.size();
        State* next = s->next_state(s->legal_actions[idx]);
        next->get_legal_actions();
        delete s;
        s = next;
    }
    return s;
}

int main(){
    srand(42);
    State temp;
    std::cout << "Game: " << temp.game_name() << " (" << BOARD_H << "x" << BOARD_W << ")" << std::endl;

    struct TestPos { const char* name; State* state; };
    TestPos positions[3];
    positions[0] = {"init", new State()};
    positions[0].state->get_legal_actions();
    positions[1] = {"mid", play_random_moves(10)};
    positions[2] = {"late", play_random_moves(25)};

    int max_depth = 7;

    for(int p = 0; p < 3; p++){
        std::cout << "\n=== " << positions[p].name << " ===" << std::endl;
        std::cout << "  algo |";
        for(int d = 1; d <= max_depth; d++) std::cout << "    d=" << d << " |";
        std::cout << std::endl;

        /* PVS */
        std::cout << "   pvs |";
        double prev_pvs = 0;
        for(int d = 1; d <= max_depth; d++){
            if(prev_pvs > 5000){ std::cout << "       - |"; continue; }
            tt_clear();
            State* s = new State(*positions[p].state);
            s->get_legal_actions();
            SearchContext ctx;
            GameHistory history;
            auto t0 = std::chrono::high_resolution_clock::now();
            PVS::search(s, d, history, ctx);
            auto t1 = std::chrono::high_resolution_clock::now();
            double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
            prev_pvs = ms;
            uint64_t nps = ms > 0 ? (uint64_t)(ctx.nodes * 1000.0 / ms) : 0;
            std::cout << " " << ms << "ms(" << nps/1000 << "k) |";
            delete s;
        }
        std::cout << std::endl;

        /* AlphaBeta */
        std::cout << "    ab |";
        double prev_ab = 0;
        for(int d = 1; d <= max_depth; d++){
            if(prev_ab > 5000){ std::cout << "       - |"; continue; }
            tt_clear();
            State* s = new State(*positions[p].state);
            s->get_legal_actions();
            SearchContext ctx;
            GameHistory history;
            auto t0 = std::chrono::high_resolution_clock::now();
            AlphaBeta::search(s, d, history, ctx);
            auto t1 = std::chrono::high_resolution_clock::now();
            double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
            prev_ab = ms;
            uint64_t nps = ms > 0 ? (uint64_t)(ctx.nodes * 1000.0 / ms) : 0;
            std::cout << " " << ms << "ms(" << nps/1000 << "k) |";
            delete s;
        }
        std::cout << std::endl;
    }

    for(int p = 0; p < 3; p++) delete positions[p].state;
    return 0;
}
