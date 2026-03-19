#pragma once
#include "base_state.hpp"
#include "config.hpp"
#include <cstring>
#include <sstream>

class Board {
public:
    char board[2][BOARD_H][BOARD_W] = {{
        /* Player 0 (Sente) */
        {0, 0, 0, 0, 0},
        {0, 0, 0, 0, 0},
        {0, 0, 0, 0, 0},
        {PAWN, 0, 0, 0, 0},
        {ROOK, BISHOP, SILVER, GOLD, KING},
    }, {
        /* Player 1 (Gote) */
        {KING, GOLD, SILVER, BISHOP, ROOK},
        {0, 0, 0, 0, PAWN},
        {0, 0, 0, 0, 0},
        {0, 0, 0, 0, 0},
        {0, 0, 0, 0, 0},
    }};
    char hand[2][NUM_HAND_TYPES + 1] = {}; /* hand[player][piece_type] = count (1-5 only) */
};

class State : public BaseState {
public:
    Board board;
    int step = 0;

    State();  /* default = starting position */
    State(int player){ this->player = player; }
    State(Board board, int player): board(board){ this->player = player; }

    State* next_state(const Move& move) override;
    void get_legal_actions() override;
    int evaluate(bool use_nnue = true, bool use_kp = true, bool use_mobility = true) override;
    std::string encode_output() const override;
    uint64_t hash() const override;

    int piece_at(int player, int row, int col) const override {
        return board.board[player][row][col];
    }
    std::string cell_display(int row, int col) const override;

    std::string encode_board() const override;
    void decode_board(const std::string& s, int side_to_move) override;

    int board_h() const override { return BOARD_H; }
    int board_w() const override { return BOARD_W; }
    const char* game_name() const override { return "MiniShogi"; }
    BaseState* create_null_state() const override;

private:
    void gen_board_moves();
    void gen_drop_moves();
    bool is_promotion_zone(int row, int player) const;
    bool must_promote(int piece, int row, int player) const;
    int demote(int piece) const;  /* promoted -> base piece for hand */
    int unpromoted_type(int piece) const; /* get base type (1-5) for hand indexing */
};
