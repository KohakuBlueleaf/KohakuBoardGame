#pragma once
#include "base_state.hpp"
#include "config.hpp"
#include <cstring>
#include <sstream>

class Board {
public:
    /*
     * Initial Position (6x7, row 0 = top = rank 7):
     *   a b c d e f
     * 7 b r l s g k   <- Gote (row 0)
     * 6 p p p p s n   <- Gote (row 1)
     * 5 . . . . p p   <- Gote (row 2)
     * 4 . . . . . .   (row 3)
     * 3 P P . . . .   <- Sente (row 4)
     * 2 N S P P P P   <- Sente (row 5)
     * 1 K G S L R B   <- Sente (row 6)
     */
    char board[2][BOARD_H][BOARD_W] = {{
        /* Player 0 (Sente) — pieces on rows 4-6 */
        {0, 0, 0, 0, 0, 0},          /* row 0 (rank 7) */
        {0, 0, 0, 0, 0, 0},          /* row 1 (rank 6) */
        {0, 0, 0, 0, 0, 0},          /* row 2 (rank 5) */
        {0, 0, 0, 0, 0, 0},          /* row 3 (rank 4) */
        {PAWN, PAWN, 0, 0, 0, 0},    /* row 4 (rank 3): P P . . . . */
        {KNIGHT, SILVER, PAWN, PAWN, PAWN, PAWN},  /* row 5 (rank 2): N S P P P P */
        {KING, GOLD, SILVER, LANCE, ROOK, BISHOP},  /* row 6 (rank 1): K G S L R B */
    }, {
        /* Player 1 (Gote) — pieces stored at visual position (same coords) */
        {BISHOP, ROOK, LANCE, SILVER, GOLD, KING},  /* row 0 (rank 7): b r l s g k */
        {PAWN, PAWN, PAWN, PAWN, SILVER, KNIGHT},   /* row 1 (rank 6): p p p p s n */
        {0, 0, 0, 0, PAWN, PAWN},                   /* row 2 (rank 5): . . . . p p */
        {0, 0, 0, 0, 0, 0},          /* row 3 (rank 4) */
        {0, 0, 0, 0, 0, 0},          /* row 4 (rank 3) */
        {0, 0, 0, 0, 0, 0},          /* row 5 (rank 2) */
        {0, 0, 0, 0, 0, 0},          /* row 6 (rank 1) */
    }};
    char hand[2][NUM_HAND_TYPES + 1] = {}; /* hand[player][piece_type] = count (1-7 only) */
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
    const char* game_name() const override { return "KohakuShogi"; }
    BaseState* create_null_state() const override;
    int hand_count(int player, int piece_type) const override {
        if(piece_type < 1 || piece_type > NUM_HAND_TYPES) return 0;
        return board.hand[player][piece_type];
    }
    int num_hand_types() const override { return NUM_HAND_TYPES; }
    int extract_nnue_features(int perspective, int* features) const override;

private:
    void gen_board_moves();
    void gen_drop_moves();
    bool is_promotion_zone(int row, int player) const;
    bool must_promote(int piece, int row, int player) const;
    int demote(int piece) const;  /* promoted -> base piece for hand */
    int unpromoted_type(int piece) const; /* get base type (1-7) for hand indexing */
};
