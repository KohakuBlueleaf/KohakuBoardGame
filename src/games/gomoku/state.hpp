#pragma once
#include "base_state.hpp"
#include "config.hpp"
#include <cstring>
#include <sstream>

class Board {
public:
    char board[BOARD_H][BOARD_W] = {};
};

class State : public BaseState {
public:
    Board board;
    int step = 0;
    int score = 0;

    State(){}
    State(int player){
        this->player = player;
    }
    State(Board board, int player): board(board){
        this->player = player;
    }

    State* next_state(const Move& move) override;
    void get_legal_actions() override;
    int evaluate(bool use_nnue = true, bool use_kp = true, bool use_mobility = true) override;
    std::string encode_output() const override;
    uint64_t hash() const override;
    int piece_at(int /*player*/, int /*row*/, int /*col*/) const override { return 0; }
    std::string cell_display(int row, int col) const override{
        char v = board.board[row][col];
        if(v == 1){
            return " X ";
        }
        if(v == 2){
            return " O ";
        }
        return " . ";
    }

    std::string encode_board() const override;
    void decode_board(const std::string& s, int side_to_move) override;

    /* === Game description === */
    int board_h() const override { return BOARD_H; }
    int board_w() const override { return BOARD_W; }
    const char* game_name() const override { return "Gomoku"; }
    BaseState* create_null_state() const override { return nullptr; }

private:
    bool check_win_at(int row, int col) const;
    int count_dir(int row, int col, int dr, int dc) const;
};
