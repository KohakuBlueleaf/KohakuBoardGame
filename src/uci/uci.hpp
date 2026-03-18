#pragma once
#include "../state/state.hpp"
#include <string>

namespace uci {
        // Move format: "a6c5" (col_from + row_from + col_to + row_to)
        // Columns: A=0, B=1, C=2, D=3, E=4 (lowercase in UCI)
        // Rows: 6=0, 5=1, 4=2, 3=3, 2=4, 1=5
        std::string move_to_str(const Move& m);
        Move str_to_move(const std::string& s);

        // Board position from move list
        // "startpos" or "startpos moves a2a3 e5e4 ..."
        void set_position(const std::string& line, Board& board, int& player, int& step);

        // Main UCI loop
        void loop();
}
