#pragma once
#include "base_state.hpp"
#include "config.hpp"
#include <cstring>
#include <sstream>

class Board {
public:
    /* board[r][c]: 0=empty, 1=black, 2=white
     * Initial position: black stone at center */
    char board[BOARD_H][BOARD_W] = {};
    Board(){
        board[BOARD_H / 2][BOARD_W / 2] = 1;
    }
};

class State : public BaseState {
public:
    Board board;
    int step = 0;
    int score = 0;
    int stones_left = 2;  /* 2 = first stone of turn, 1 = second stone */
    mutable uint64_t zobrist_hash = 0;
    mutable bool zobrist_valid = false;

    /* Default: Connect6 initial position.
     * Black stone pre-placed at center. Player 0 (white) moves first.
     * Player 0 = white (stone value 2), Player 1 = black (stone value 1). */
    State(){
        player = 0;
        step = 0;
        stones_left = 2;
    }
    State(int player): stones_left(2){
        this->player = player;
    }
    State(Board board, int player): board(board), stones_left(2){
        this->player = player;
    }

    State* next_state(const Move& move) override;
    void get_legal_actions() override;
    int evaluate(
        bool use_nnue = true,
        bool use_kp = true,
        bool use_mobility = true,
        const GameHistory* history = nullptr
    ) override;
    std::string encode_output() const override;
    uint64_t hash() const override {
        if(!zobrist_valid){
            zobrist_hash = compute_hash_full();
            zobrist_valid = true;
        }
        return zobrist_hash;
    }
    uint64_t compute_hash_full() const;
    int piece_at(int p, int row, int col) const override {
        return (board.board[row][col] == p + 1) ? 1 : 0;
    }
    std::string cell_display(int row, int col) const override {
        char v = board.board[row][col];
        if(v == 1) return " X ";
        if(v == 2) return " O ";
        return " . ";
    }

    std::string encode_board() const override;
    void decode_board(const std::string& s, int side_to_move) override;

    /* === Multi-stone turn: same player places 2 stones ===
     * Returns true when this is the second stone of a turn
     * (same player as parent, search should not negate score). */
    bool same_player_as_parent() const override {
        return stones_left == 1;
    }

    /* === Game description === */
    int board_h() const override { return BOARD_H; }
    int board_w() const override { return BOARD_W; }
    const char* game_name() const override { return "Connect6"; }
    bool check_repetition(const GameHistory& history, int& out_score) const override;
    BaseState* create_null_state() const override { return nullptr; }

    /* === NNUE feature extraction === */
    int extract_nnue_features(int perspective, int* features) const override;

    bool check_win_at(int row, int col) const;
    int count_dir(int row, int col, int dr, int dc) const;
    int score_single_placement(int r, int c, int who) const;
};
