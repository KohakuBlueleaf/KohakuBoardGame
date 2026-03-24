#include <iostream>
#include "config.hpp"
#include "state.hpp"

void test_pos(const char* label, Board& b, int player){
    State s(b, player);
    s.get_legal_actions();
    std::cout << "=== " << label << " ===" << std::endl;
    std::cout << s.encode_output();
    std::cout << "Eval: " << s.evaluate() << std::endl;
    std::cout << "Legal moves: " << s.legal_actions.size() << std::endl;
    std::cout << "Game state: " << s.game_state << std::endl;
    std::cout << std::endl;
}

int main(){
    /* Test 1: White 4 in a row, BOTH ends open, with nearby pieces */
    {
        Board b;
        b.board[7][7] = 1; // black center
        b.board[7][3] = 2; // white d8
        b.board[7][4] = 2; // white e8
        b.board[7][5] = 2; // white f8
        b.board[7][6] = 2; // white g8
        // Nearby black stones so there's context
        b.board[6][5] = 1; // black f9
        b.board[8][4] = 1; // black e7
        b.board[6][3] = 1; // black d9
        // Both ends open: c8 and h8 are empty
        test_pos("White 4-in-row (d8-g8), both ends open, white to move", b, 0);
        test_pos("White 4-in-row (d8-g8), both ends open, BLACK to move", b, 1);
    }

    /* Test 2: White 4 in a row, ONE end blocked */
    {
        Board b;
        b.board[7][7] = 1; // black center
        b.board[7][3] = 2; // white d8
        b.board[7][4] = 2; // white e8
        b.board[7][5] = 2; // white f8
        b.board[7][6] = 2; // white g8
        b.board[7][2] = 1; // BLACK blocks c8
        b.board[6][5] = 1;
        b.board[8][4] = 1;
        // h8 is open
        test_pos("White 4-in-row, LEFT blocked by black, white to move", b, 0);
    }

    /* Test 3: Black 5 in a row, one end open */
    {
        Board b;
        b.board[7][7] = 1; // black
        b.board[7][6] = 1; // black
        b.board[7][5] = 1; // black
        b.board[7][4] = 1; // black
        b.board[7][3] = 1; // black - 5 in a row!
        b.board[7][2] = 2; // white blocks left
        // right (h8) is open
        b.board[6][5] = 2;
        b.board[8][4] = 2;
        test_pos("Black 5-in-row (d8-h8), left blocked, BLACK to move", b, 1);
        test_pos("Black 5-in-row (d8-h8), left blocked, WHITE to move", b, 0);
    }
    
    /* Test 4: White 3 in a row, both open - should be decent */
    {
        Board b;
        b.board[7][7] = 1; // black center
        b.board[7][5] = 2; // white f8
        b.board[7][6] = 2; // white g8  
        b.board[7][8] = 2; // white i8 - 3 whites but gap at h8(black)
        // Actually make it clean 3: e8,f8,g8
        Board b2;
        b2.board[7][7] = 1;
        b2.board[7][4] = 2;
        b2.board[7][5] = 2;
        b2.board[7][6] = 2;
        b2.board[6][5] = 1;
        b2.board[8][4] = 1;
        test_pos("White 3-in-row (e8-g8), both open, white to move", b2, 0);
    }

    return 0;
}
