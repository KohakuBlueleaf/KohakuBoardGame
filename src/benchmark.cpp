#include <iostream>
#include <chrono>
#include <iomanip>
#include <functional>

#include "config.hpp"
#include "./state/state.hpp"
#include "./policy/minimax.hpp"
#include "./policy/alphabeta.hpp"
#include "./policy/pvs.hpp"


struct TestPos {
  const char* name;
  Board board;
  int player;
};

static Board make_board(const char w[6][5], const char b[6][5]){
  Board bd;
  for(int i = 0; i < BOARD_H; i++)
    for(int j = 0; j < BOARD_W; j++){
      bd.board[0][i][j] = w[i][j];
      bd.board[1][i][j] = b[i][j];
    }
  return bd;
}

// Time a get_move call, return ms. Returns -1 if skipped (previous depth too slow).
static double time_get_move(
  std::function<Move(State*, int)> get_move,
  const TestPos& pos, int depth, double prev_ms)
{
  // Skip if previous depth already > 5s
  if(prev_ms > 5000.0) return -1.0;

  State* state = new State(pos.board, pos.player);
  state->get_legal_actions();

  auto t0 = std::chrono::high_resolution_clock::now();
  get_move(state, depth);
  auto t1 = std::chrono::high_resolution_clock::now();

  double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
  delete state;
  return ms;
}


int main(int argc, char* argv[]){
  // Optional label from command line
  const char* label = (argc > 1) ? argv[1] : "";

  TestPos positions[3];

  // 1. Starting position
  positions[0].name = "init";
  positions[0].board = Board();
  positions[0].player = 0;

  // 2. Midgame: pieces traded, open position
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

  // 3. Endgame: few pieces
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

  // Algorithms to test
  struct Algo {
    const char* name;
    std::function<Move(State*, int)> get_move;
  };

  Algo algos[] = {
    {"minimax",  [](State* s, int d){ return MiniMax::get_move(s, d); }},
    {"alphabeta",[](State* s, int d){ return AlphaBeta::get_move(s, d); }},
    {"pvs",      [](State* s, int d){ return PVS::get_move(s, d); }},
  };

  int max_depth = 6;

  if(label[0]) std::cout << "[ " << label << " ]\n";

  for(int p = 0; p < 3; p++){
    std::cout << "\n=== " << positions[p].name << " ===\n";
    // Header
    std::cout << std::setw(12) << "algo";
    for(int d = 1; d <= max_depth; d++)
      std::cout << " | " << std::setw(9) << ("d=" + std::to_string(d));
    std::cout << "\n";
    std::cout << std::string(12, '-');
    for(int d = 1; d <= max_depth; d++)
      std::cout << "-+-" << std::string(9, '-');
    std::cout << "\n";

    for(auto& algo : algos){
      std::cout << std::setw(12) << algo.name;
      double prev = 0;
      for(int d = 1; d <= max_depth; d++){
        double ms = time_get_move(algo.get_move, positions[p], d, prev);
        if(ms < 0){
          std::cout << " | " << std::setw(9) << "-";
        }else{
          std::cout << " | " << std::setw(7) << std::fixed << std::setprecision(1) << ms << "ms";
          prev = ms;
        }
      }
      std::cout << "\n";
    }
  }

  std::cout << std::endl;
  return 0;
}
