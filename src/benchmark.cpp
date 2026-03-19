#include <iostream>
#include <chrono>
#include <iomanip>

#include "config.hpp"
#include "state.hpp"
#include "./policy/registry.hpp"
#ifdef USE_NNUE
#include "./nnue/nnue.hpp"
#endif


/* === Test position === */

struct TestPos {
    const char* name;
    Board board;
    int player;
};

static Board make_board(const char w[6][5], const char b[6][5]){
    Board bd;
    for(int i = 0; i < BOARD_H; i++){
        for(int j = 0; j < BOARD_W; j++){
            bd.board[0][i][j] = w[i][j];
            bd.board[1][i][j] = b[i][j];
        }
    }
    return bd;
}


/* === Timing helper === */

static double time_search(
    const AlgoEntry& algo,
    const TestPos& pos,
    int depth,
    double prev_ms
){
    if(prev_ms > 5000.0){ return -1.0; }
    State* state = new State(pos.board, pos.player);
    state->get_legal_actions();
    SearchContext ctx;
    ctx.params = algo.default_params;
    auto t0 = std::chrono::high_resolution_clock::now();
    algo.search(state, depth, ctx);
    auto t1 = std::chrono::high_resolution_clock::now();
    double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
    delete state;
    return ms;
}


/* === Main === */

int main(int argc, char* argv[]){
#ifdef USE_NNUE
    if(nnue::init()){
        std::cerr << "NNUE model loaded." << std::endl;
    }else{
        std::cerr << "NNUE not loaded, using handcrafted eval." << std::endl;
    }
#endif

    /* Optional label from command line */
    const char* label = (argc > 1) ? argv[1] : "";

    /* === Test positions === */
    TestPos positions[3];

    /* 1. Starting position */
    positions[0].name = "init";
    positions[0].board = Board();
    positions[0].player = 0;

    /* 2. Midgame: pieces traded, open position */
    {
        const char w[6][5] = {
            {0,0,0,0,0}, {0,0,0,0,0}, {0,0,1,0,0},
            {0,1,0,0,0}, {0,0,0,0,1}, {2,0,0,5,6},
        };
        const char b[6][5] = {
            {6,5,0,0,2}, {1,0,0,0,0}, {0,0,0,1,0},
            {0,0,1,0,0}, {0,0,0,0,0}, {0,0,0,0,0},
        };
        positions[1].name = "mid";
        positions[1].board = make_board(w, b);
        positions[1].player = 0;
    }

    /* 3. Endgame: few pieces */
    {
        const char w[6][5] = {
            {0,0,0,0,0}, {0,0,0,0,0}, {0,0,0,0,0},
            {0,0,1,0,0}, {0,0,0,0,0}, {0,0,0,2,6},
        };
        const char b[6][5] = {
            {6,0,2,0,0}, {0,0,0,0,0}, {0,1,0,0,0},
            {0,0,0,0,0}, {0,0,0,0,0}, {0,0,0,0,0},
        };
        positions[2].name = "end";
        positions[2].board = make_board(w, b);
        positions[2].player = 0;
    }

    /* === Algorithm table from registry === */
    const auto& algos = get_algo_table();
    int max_depth = 6;

    if(label[0]){ std::cout << "[ " << label << " ]\n"; }

    for(int p = 0; p < 3; p++){
        std::cout << "\n=== " << positions[p].name << " ===\n";

        /* Header */
        std::cout << std::setw(12) << "algo";
        for(int d = 1; d <= max_depth; d++){
            std::cout << " | " << std::setw(9) << ("d=" + std::to_string(d));
        }
        std::cout << "\n";
        std::cout << std::string(12, '-');
        for(int d = 1; d <= max_depth; d++){
            std::cout << "-+-" << std::string(9, '-');
        }
        std::cout << "\n";

        /* Each algorithm */
        for(const auto& algo : algos){
            std::cout << std::setw(12) << algo.name;
            double prev = 0;
            for(int d = 1; d <= max_depth; d++){
                double ms = time_search(algo, positions[p], d, prev);
                if(ms < 0){
                    std::cout << " | " << std::setw(9) << "-";
                }else{
                    std::cout << " | " << std::setw(7) << std::fixed
                              << std::setprecision(1) << ms << "ms";
                    prev = ms;
                }
            }
            std::cout << "\n";
        }
    }

    std::cout << std::endl;
    return 0;
}
