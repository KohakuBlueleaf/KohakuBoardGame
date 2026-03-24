#include <iostream>
#include "config.hpp"
#include "state.hpp"

int main(){
    // TRUE open4: row 10, no nearby black
    Board b;
    // Clear center stone for clean test
    b.board[7][7] = 0;
    // White 4 in a row at row 4 (rank 11): e11,f11,g11,h11
    b.board[4][4] = 2;
    b.board[4][5] = 2;
    b.board[4][6] = 2;
    b.board[4][7] = 2;
    // d11 (col3) and i11 (col8) both empty = truly open4
    // Add some black stones elsewhere
    b.board[6][5] = 1;
    b.board[6][6] = 1;
    
    State s(b, 0);
    s.get_legal_actions();
    std::cout << s.encode_output();
    std::cout << "Eval: " << s.evaluate() << std::endl;
    std::cout << "Legal: " << s.legal_actions.size() << std::endl;
    std::cout << "game_state: " << s.game_state << std::endl;
    
    // Also test half4: block one end
    Board b2;
    b2.board[7][7] = 0;
    b2.board[4][4] = 2;
    b2.board[4][5] = 2;
    b2.board[4][6] = 2;
    b2.board[4][7] = 2;
    b2.board[4][3] = 1; // block left end
    b2.board[6][5] = 1;
    
    State s2(b2, 0);
    s2.get_legal_actions();
    std::cout << "\nHalf4 (left blocked):" << std::endl;
    std::cout << "Eval: " << s2.evaluate() << std::endl;
    
    // half4, BLACK to move (should be very negative)
    State s3(b2, 1);
    s3.get_legal_actions();
    std::cout << "Half4, black to move eval: " << s3.evaluate() << std::endl;
    
    return 0;
}
