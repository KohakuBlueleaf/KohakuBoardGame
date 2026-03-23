#pragma once
#include "base_state.hpp"
#include "config.hpp"
#include <cstring>
#include <sstream>

class Board {
public:
    char board[2][BOARD_H][BOARD_W] = {{
        /* Player 0 (Sente) — SFEN: KGSBR, pawn on 5d */
        {0, 0, 0, 0, 0},
        {0, 0, 0, 0, 0},
        {0, 0, 0, 0, 0},
        {PAWN, 0, 0, 0, 0},
        {KING, GOLD, SILVER, BISHOP, ROOK},
    }, {
        /* Player 1 (Gote) — SFEN: rbsgk, pawn on 1b */
        {ROOK, BISHOP, SILVER, GOLD, KING},
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
    int evaluate(
        bool use_nnue = true,
        bool use_kp = true,
        bool use_mobility = true,
        const GameHistory* history = nullptr
    ) override;
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
    bool check_repetition(const GameHistory& history, int& out_score) const override;
    BaseState* create_null_state() const override;
    int hand_count(int player, int piece_type) const override {
        if(piece_type < 1 || piece_type > NUM_HAND_TYPES) return 0;
        return board.hand[player][piece_type];
    }
    int num_hand_types() const override { return NUM_HAND_TYPES; }
    int extract_nnue_features(int perspective, int* features) const override;

    void gen_board_moves();
    void gen_board_moves_bitboard();
    void gen_drop_moves(bool skip_uchifuzume = false);

private:
    bool is_promotion_zone(int row, int player) const;
    bool must_promote(int piece, int row, int player) const;
    int demote(int piece) const;  /* promoted -> base piece for hand */
    int unpromoted_type(int piece) const; /* get base type (1-5) for hand indexing */
};
