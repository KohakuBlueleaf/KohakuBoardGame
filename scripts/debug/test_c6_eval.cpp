#include <iostream>
#include "config.hpp"
#include "state.hpp"

int main(){
    /* Set up a position with white having 4 in a row */
    Board b;
    // Black at center
    // White has 4 in a row: h6, h7, h8(center is black), h9
    // Actually let's put white stones at g8, i8 (flanking center)
    // and h9, h10 
    b.board[7][7] = 1; // black center
    b.board[7][6] = 2; // white g8
    b.board[7][8] = 2; // white i8
    b.board[6][7] = 2; // white h9
    b.board[5][7] = 2; // white h10
    // Black has some stones
    b.board[8][7] = 1; // black h7
    b.board[9][7] = 1; // black h6

    State s(b, 0); // white to move
    s.get_legal_actions();
    
    std::cout << s.encode_output() << std::endl;
    std::cout << "Legal moves: " << s.legal_actions.size() << std::endl;
    std::cout << "Game state: " << s.game_state << std::endl;
    
    int eval = s.evaluate();
    std::cout << "Eval: " << eval << std::endl;
    
    /* Now test: white 4 in a row horizontally */
    Board b2;
    b2.board[7][7] = 1; // black center
    b2.board[7][4] = 2; // white e8
    b2.board[7][5] = 2; // white f8
    b2.board[7][6] = 2; // white g8
    b2.board[7][8] = 2; // white i8 -- 4 whites with gap at h8(black)
    
    // Separate line: white d7, e7, f7, g7 = 4 in a row
    b2.board[8][3] = 2;
    b2.board[8][4] = 2;
    b2.board[8][5] = 2;
    b2.board[8][6] = 2;
    
    State s2(b2, 0); // white to move
    s2.get_legal_actions();
    std::cout << "\n=== Position 2: White 4-in-a-row ===" << std::endl;
    std::cout << s2.encode_output() << std::endl;
    std::cout << "Eval: " << s2.evaluate() << std::endl;
    std::cout << "Legal moves: " << s2.legal_actions.size() << std::endl;
    
    // Check what score_single_placement gives for extending the 4-row
    std::cout << "\nScore for h7 (extend row): " << s2.score_single_placement(8, 7, 2) << std::endl;
    std::cout << "Score for c7 (other end): " << s2.score_single_placement(8, 2, 2) << std::endl;
    std::cout << "Score for random: " << s2.score_single_placement(0, 0, 2) << std::endl;
    
    return 0;
}
