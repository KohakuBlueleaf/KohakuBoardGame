#include <iostream>
#include "config.hpp"
#include "state.hpp"

int main(){
    // White 4 in a row d8-g8, both ends open
    Board b;
    b.board[7][7] = 1; // black center h8
    b.board[7][3] = 2; // white d8
    b.board[7][4] = 2; // white e8
    b.board[7][5] = 2; // white f8
    b.board[7][6] = 2; // white g8
    b.board[6][5] = 1; // black f9
    b.board[8][4] = 1; // black e7
    b.board[6][3] = 1; // black d9

    // Check: is c8 (row7,col2) empty? YES
    // Is h8 (row7,col7) = black? YES — so RIGHT end is blocked!
    std::cout << "c8 = " << (int)b.board[7][2] << " (should be 0=empty)" << std::endl;
    std::cout << "h8 = " << (int)b.board[7][7] << " (should be 1=black)" << std::endl;
    std::cout << std::endl;
    std::cout << "White 4-row d8-g8: c8 is open but h8 is BLACK" << std::endl;
    std::cout << "So this is half4, NOT open4!" << std::endl;
    
    // Make a REAL open4: no black at h8
    Board b2;
    b2.board[7][3] = 2; // white d8
    b2.board[7][4] = 2; // white e8
    b2.board[7][5] = 2; // white f8
    b2.board[7][6] = 2; // white g8
    // c8 empty, h8 empty = truly open4
    b2.board[6][5] = 1;
    b2.board[8][4] = 1;
    
    State s(b2, 0);
    s.get_legal_actions();
    std::cout << "\nTrue open4 (no black at h8):" << std::endl;
    std::cout << s.encode_output();
    std::cout << "Eval: " << s.evaluate() << std::endl;
    
    return 0;
}
