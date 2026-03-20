#pragma once
#include <vector>
#include <string>
#include <utility>
#include <cstddef>
#include <cstdint>

/* === Type aliases === */
typedef std::pair<size_t, size_t> Point;
typedef std::pair<Point, Point> Move;

enum GameState { UNKNOWN = 0, WIN, DRAW, NONE };

/* === Score bounds === */
constexpr int P_MAX = 100000;
constexpr int M_MAX = -100000;

class BaseState {
public:
    int player = 0;
    GameState game_state = UNKNOWN;
    std::vector<Move> legal_actions;

    virtual ~BaseState() = default;

    /* === Core === */
    virtual BaseState* next_state(const Move& m) = 0;
    virtual void get_legal_actions() = 0;
    virtual int evaluate(bool use_nnue = true, bool use_kp = true, bool use_mobility = true) = 0;

    /* === Game description === */
    virtual int board_h() const = 0;
    virtual int board_w() const = 0;
    virtual const char* game_name() const = 0;

    /* === Null move: create a state with side-to-move flipped (pass) === */
    virtual BaseState* create_null_state() const { return nullptr; }

    /* === Piece query: returns piece type at (row, col) for given player === */
    virtual int piece_at(int /*player*/, int /*row*/, int /*col*/) const { return 0; }

    /* === Board hash for transposition table === */
    virtual uint64_t hash() const { return 0; }

    /* === Display string for a cell at (row, col) === */
    virtual std::string cell_display(int /*row*/, int /*col*/) const { return " . "; }

    /* === Hand pieces (for games with captures-to-hand like shogi) === */
    virtual int hand_count(int /*player*/, int /*piece_type*/) const { return 0; }
    virtual int num_hand_types() const { return 0; }

    /* === NNUE feature extraction — implemented per game === */
    virtual int extract_nnue_features(int /*perspective*/, int* /*features*/) const { return 0; }

    /* === Board serialization for UBGI 'position board' command === */
    virtual std::string encode_board() const = 0;
    virtual void decode_board(const std::string& s, int side_to_move) = 0;

    /* === Display === */
    virtual std::string encode_output() const = 0;
};
