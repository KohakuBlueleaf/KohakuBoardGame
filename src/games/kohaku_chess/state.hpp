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
     * Initial position (Kohaku Chess):
     *   a b c d e f
     * 7 r b n . q k   <- Black (row 0)
     * 6 p p p p . b   <- Black (row 1)
     * 5 . . . . p p   <- Black (row 2)
     * 4 . . . . . .   (row 3)
     * 3 P P . . . .   <- White (row 4)
     * 2 B . P P P P   <- White (row 5)
     * 1 K Q . N B R   <- White (row 6)
     *
     * board[0] = White pieces, board[1] = Black pieces
     * Piece IDs: PAWN=1, ROOK=2, KNIGHT=3, BISHOP=4, QUEEN=5, KING=6
     */
    char board[2][BOARD_H][BOARD_W] = {{
        // White (player 0)
        {0, 0, 0, 0, 0, 0},  // row 0 (rank 7)
        {0, 0, 0, 0, 0, 0},  // row 1 (rank 6)
        {0, 0, 0, 0, 0, 0},  // row 2 (rank 5)
        {0, 0, 0, 0, 0, 0},  // row 3 (rank 4)
        {1, 1, 0, 0, 0, 0},  // row 4 (rank 3): P P . . . .
        {4, 0, 1, 1, 1, 1},  // row 5 (rank 2): B . P P P P
        {6, 5, 0, 3, 4, 2},  // row 6 (rank 1): K Q . N B R
    }, {
        // Black (player 1)
        {2, 4, 3, 0, 5, 6},  // row 0 (rank 7): r b n . q k
        {1, 1, 1, 1, 0, 4},  // row 1 (rank 6): p p p p . b
        {0, 0, 0, 0, 1, 1},  // row 2 (rank 5): . . . . p p
        {0, 0, 0, 0, 0, 0},  // row 3 (rank 4)
        {0, 0, 0, 0, 0, 0},  // row 4 (rank 3)
        {0, 0, 0, 0, 0, 0},  // row 5 (rank 2)
        {0, 0, 0, 0, 0, 0},  // row 6 (rank 1)
    }};
};


class State : public BaseState {
public:
    Board board;
    int score = 0;

    State(){}
    State(int player){
        this->player = player;
    }
    State(Board board): board(board){}
    State(Board board, int player): board(board){
        this->player = player;
    }

    int evaluate(bool use_nnue = true, bool use_kp_eval = true, bool use_mobility = true) override;
    State* next_state(const Move& move) override;
    void get_legal_actions() override;
    void get_legal_actions_naive();
    void get_legal_actions_bitboard();
    std::string encode_output() const override;
    std::string encode_state();

    BaseState* create_null_state() const override;

    int piece_at(int player, int row, int col) const override {
        return board.board[player][row][col];
    }
    uint64_t hash() const override;
    std::string cell_display(int row, int col) const override;

    std::string encode_board() const override;
    void decode_board(const std::string& s, int side_to_move) override;

    /* === NNUE feature extraction === */
    int extract_nnue_features(int perspective, int* features) const override;

    /* === Game description === */
    int board_h() const override { return BOARD_H; }
    int board_w() const override { return BOARD_W; }
    const char* game_name() const override { return "KohakuChess"; }
};
