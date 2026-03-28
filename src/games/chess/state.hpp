#pragma once
#include <string>
#include <cstdlib>
#include <cstdint>
#include <vector>
#include <utility>

#include "base_state.hpp"
#include "config.hpp"


/* === Castling rights (bitmask) === */
#define CASTLE_WK 1   /* white kingside */
#define CASTLE_WQ 2   /* white queenside */
#define CASTLE_BK 4   /* black kingside */
#define CASTLE_BQ 8   /* black queenside */
#define CASTLE_ALL 15


class Board {
public:
    /*
     * Standard chess initial position:
     *   a b c d e f g h
     * 8 r n b q k b n r   <- Black (row 0)
     * 7 p p p p p p p p   <- Black (row 1)
     * 6 . . . . . . . .   (row 2)
     * 5 . . . . . . . .   (row 3)
     * 4 . . . . . . . .   (row 4)
     * 3 . . . . . . . .   (row 5)
     * 2 P P P P P P P P   <- White (row 6)
     * 1 R N B Q K B N R   <- White (row 7)
     *
     * board[0] = White pieces, board[1] = Black pieces
     */
    char board[2][BOARD_H][BOARD_W] = {{
        // White (player 0)
        {0, 0, 0, 0, 0, 0, 0, 0},  // row 0 (rank 8)
        {0, 0, 0, 0, 0, 0, 0, 0},  // row 1 (rank 7)
        {0, 0, 0, 0, 0, 0, 0, 0},  // row 2 (rank 6)
        {0, 0, 0, 0, 0, 0, 0, 0},  // row 3 (rank 5)
        {0, 0, 0, 0, 0, 0, 0, 0},  // row 4 (rank 4)
        {0, 0, 0, 0, 0, 0, 0, 0},  // row 5 (rank 3)
        {1, 1, 1, 1, 1, 1, 1, 1},  // row 6 (rank 2): P P P P P P P P
        {2, 3, 4, 5, 6, 4, 3, 2},  // row 7 (rank 1): R N B Q K B N R
    }, {
        // Black (player 1)
        {2, 3, 4, 5, 6, 4, 3, 2},  // row 0 (rank 8): r n b q k b n r
        {1, 1, 1, 1, 1, 1, 1, 1},  // row 1 (rank 7): p p p p p p p p
        {0, 0, 0, 0, 0, 0, 0, 0},  // row 2 (rank 6)
        {0, 0, 0, 0, 0, 0, 0, 0},  // row 3 (rank 5)
        {0, 0, 0, 0, 0, 0, 0, 0},  // row 4 (rank 4)
        {0, 0, 0, 0, 0, 0, 0, 0},  // row 5 (rank 3)
        {0, 0, 0, 0, 0, 0, 0, 0},  // row 6 (rank 2)
        {0, 0, 0, 0, 0, 0, 0, 0},  // row 7 (rank 1)
    }};

    uint8_t castling = CASTLE_ALL;   /* castling rights bitmask */
    int8_t  ep_col   = -1;           /* en passant target column (-1 = none) */
};


class State : public BaseState {
public:
    Board board;
    int score = 0;
    mutable uint64_t zobrist_hash = 0;
    mutable bool zobrist_valid = false;

    State(){}
    State(int player){
        this->player = player;
    }
    State(Board board): board(board){}
    State(Board board, int player): board(board){
        this->player = player;
    }

    int evaluate(
        bool use_nnue = true,
        bool use_kp_eval = true,
        bool use_mobility = true,
        const GameHistory* history = nullptr
    ) override;
    State* next_state(const Move& move) override;
    void get_legal_actions() override;
    void get_legal_actions_naive();
    void get_legal_actions_bitboard();
    std::string encode_output() const override;

    bool check_repetition(const GameHistory& history, int& out_score) const override;
    BaseState* create_null_state() const override;

    int piece_at(int player, int row, int col) const override {
        return board.board[player][row][col];
    }
    uint64_t hash() const override {
        if(!zobrist_valid){
            zobrist_hash = compute_hash_full();
            zobrist_valid = true;
        }
        return zobrist_hash;
    }
    uint64_t compute_hash_full() const;
    std::string cell_display(int row, int col) const override;

    std::string encode_board() const override;
    void decode_board(const std::string& s, int side_to_move) override;

    /* === NNUE feature extraction === */
    int extract_nnue_features(int perspective, int* features) const override;

    /* === Game description === */
    int board_h() const override { return BOARD_H; }
    int board_w() const override { return BOARD_W; }
    const char* game_name() const override { return "Chess"; }

    /* === Make-unmake for search === */
    bool supports_make_unmake() const override { return true; }
    bool make_move(const Move& m, UndoInfo& undo) override;
    void unmake_move(const Move& m, const UndoInfo& undo) override;
};
