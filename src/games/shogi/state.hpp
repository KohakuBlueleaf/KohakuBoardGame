#pragma once
#include "base_state.hpp"
#include "config.hpp"
#include <cstring>
#include <sstream>

class Board {
public:
    /*
     * Standard Shogi Initial Position (9x9, row 0 = top = rank 9):
     *   a  b  c  d  e  f  g  h  i
     * 9 L  N  S  G  K  G  S  N  L   <- Gote (row 0)
     * 8 .  R  .  .  .  .  .  B  .   <- Gote (row 1)
     * 7 P  P  P  P  P  P  P  P  P   <- Gote (row 2)
     * 6 .  .  .  .  .  .  .  .  .   (row 3)
     * 5 .  .  .  .  .  .  .  .  .   (row 4)
     * 4 .  .  .  .  .  .  .  .  .   (row 5)
     * 3 P  P  P  P  P  P  P  P  P   <- Sente (row 6)
     * 2 .  B  .  .  .  .  .  R  .   <- Sente (row 7)
     * 1 L  N  S  G  K  G  S  N  L   <- Sente (row 8)
     *
     * board[0] = Sente, board[1] = Gote
     */
    char board[2][BOARD_H][BOARD_W] = {{
        /* Player 0 (Sente) */
        {0,0,0,0,0,0,0,0,0},  /* row 0 (rank 9) */
        {0,0,0,0,0,0,0,0,0},  /* row 1 (rank 8) */
        {0,0,0,0,0,0,0,0,0},  /* row 2 (rank 7) */
        {0,0,0,0,0,0,0,0,0},  /* row 3 (rank 6) */
        {0,0,0,0,0,0,0,0,0},  /* row 4 (rank 5) */
        {0,0,0,0,0,0,0,0,0},  /* row 5 (rank 4) */
        {PAWN,PAWN,PAWN,PAWN,PAWN,PAWN,PAWN,PAWN,PAWN}, /* row 6 (rank 3) */
        {0,BISHOP,0,0,0,0,0,ROOK,0},                     /* row 7 (rank 2) */
        {LANCE,KNIGHT,SILVER,GOLD,KING,GOLD,SILVER,KNIGHT,LANCE}, /* row 8 (rank 1) */
    }, {
        /* Player 1 (Gote) — 180° rotated */
        {LANCE,KNIGHT,SILVER,GOLD,KING,GOLD,SILVER,KNIGHT,LANCE}, /* row 0 (rank 9) */
        {0,ROOK,0,0,0,0,0,BISHOP,0},                               /* row 1 (rank 8) */
        {PAWN,PAWN,PAWN,PAWN,PAWN,PAWN,PAWN,PAWN,PAWN},           /* row 2 (rank 7) */
        {0,0,0,0,0,0,0,0,0},  /* row 3 (rank 6) */
        {0,0,0,0,0,0,0,0,0},  /* row 4 (rank 5) */
        {0,0,0,0,0,0,0,0,0},  /* row 5 (rank 4) */
        {0,0,0,0,0,0,0,0,0},  /* row 6 (rank 3) */
        {0,0,0,0,0,0,0,0,0},  /* row 7 (rank 2) */
        {0,0,0,0,0,0,0,0,0},  /* row 8 (rank 1) */
    }};
    char hand[2][NUM_HAND_TYPES + 1] = {};
};

class State : public BaseState {
public:
    Board board;
    mutable uint64_t zobrist_hash = 0;
    mutable bool zobrist_valid = false;

    State();
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
    uint64_t hash() const override {
        if(!zobrist_valid){
            zobrist_hash = compute_hash_full();
            zobrist_valid = true;
        }
        return zobrist_hash;
    }
    uint64_t compute_hash_full() const;

    int piece_at(int player, int row, int col) const override {
        return board.board[player][row][col];
    }
    std::string cell_display(int row, int col) const override;

    std::string encode_board() const override;
    void decode_board(const std::string& s, int side_to_move) override;

    int board_h() const override { return BOARD_H; }
    int board_w() const override { return BOARD_W; }
    const char* game_name() const override { return "Shogi"; }
    bool check_repetition(const GameHistory& history, int& out_score) const override;
    BaseState* create_null_state() const override;
    int hand_count(int player, int piece_type) const override {
        if(piece_type < 1 || piece_type > NUM_HAND_TYPES) return 0;
        return board.hand[player][piece_type];
    }
    int num_hand_types() const override { return NUM_HAND_TYPES; }
    int extract_nnue_features(int perspective, int* features) const override;

    void gen_board_moves();
    void gen_drop_moves(bool skip_uchifuzume = false);

private:
    bool is_promotion_zone(int row, int player) const;
    bool must_promote(int piece, int row, int player) const;
    int demote(int piece) const;
    int unpromoted_type(int piece) const;
};
