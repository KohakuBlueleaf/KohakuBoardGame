#include <iostream>
#include <fstream>

#include "../config.hpp"
#include "../state/state.hpp"
#include "../policy/pvs.hpp"
#ifdef USE_NNUE
#include "../nnue/nnue.hpp"
#endif


State* root;
void read_board(std::ifstream& fin) {
  Board board;
  int player;
  fin >> player;

  for (int pl=0; pl<2; pl++) {
    for (int i=0; i<BOARD_H; i++) {
      for (int j=0; j<BOARD_W; j++) {
        int c; fin >> c;
        board.board[pl][i][j] = c;
      }
    }
  }
  root = new State(board, player);
  root->get_legal_actions();
}


void write_valid_spot(std::ofstream& fout) {
  int threshold = 1;
  // Keep updating the output until getting killed.
  while(true) {
    auto move = PVS::get_move(root, threshold);
    fout << move.first.first << " " << move.first.second << " "\
         << move.second.first << " " << move.second.second << std::endl;
    fout.flush();
    threshold += 1;
  }
}


int main(int, char** argv) {
  srand(RANDOM_SEED);

#ifdef USE_NNUE
  if(nnue::init()){
    std::cerr << "NNUE model loaded." << std::endl;
  }else{
    std::cerr << "NNUE not loaded, using handcrafted eval." << std::endl;
  }
#endif

  std::ifstream fin(argv[1]);
  std::ofstream fout(argv[2]);

  read_board(fin);
  write_valid_spot(fout);

  fin.close();
  fout.close();
  return 0;
}
