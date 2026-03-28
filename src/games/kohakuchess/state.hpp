#pragma once
#include <string>
#include <cstdlib>
#include <vector>
#include <utility>

#include "base_state.hpp"
#include "config.hpp"


class Board {
public:
    /*
     * Initial position (Kohaku Chess 6x6):
     *   a b c d e f
     * 6 r b q n b k   <- Black (row 0)
     * 5 p p p p p n   <- Black (row 1)
     * 4 . . . . . p   <- Black (row 2)
     * 3 P . . . . .   <- White (row 3)
     * 2 N P P P P P   <- White (row 4)
     * 1 K B N Q B R   <- White (row 5)
     *
     * board[0] = White pieces, board[1] = Black pieces
     * Piece IDs: PAWN=1, ROOK=2, KNIGHT=3, BISHOP=4, QUEEN=5, KING=6
     */
    char board[2][BOARD_H][BOARD_W] = {{
        // White (player 0)
        {0, 0, 0, 0, 0, 0},  // row 0 (rank 6)
        {0, 0, 0, 0, 0, 0},  // row 1 (rank 5)
        {0, 0, 0, 0, 0, 0},  // row 2 (rank 4)
        {1, 0, 0, 0, 0, 0},  // row 3 (rank 3): P . . . . .
        {3, 1, 1, 1, 1, 1},  // row 4 (rank 2): N P P P P P
        {6, 4, 3, 5, 4, 2},  // row 5 (rank 1): K B N Q B R
    }, {
        // Black (player 1)
        {2, 4, 5, 3, 4, 6},  // row 0 (rank 6): r b q n b k
        {1, 1, 1, 1, 1, 3},  // row 1 (rank 5): p p p p p n
        {0, 0, 0, 0, 0, 1},  // row 2 (rank 4): . . . . . p
        {0, 0, 0, 0, 0, 0},  // row 3 (rank 3)
        {0, 0, 0, 0, 0, 0},  // row 4 (rank 2)
        {0, 0, 0, 0, 0, 0},  // row 5 (rank 1)
    }};
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
    std::string encode_state();

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
    const char* game_name() const override { return "KohakuChess"; }

    /* === Make-unmake for search === */
    bool supports_make_unmake() const override { return true; }
    bool make_move(const Move& m, UndoInfo& undo) override;
    void unmake_move(const Move& m, const UndoInfo& undo) override;
};
