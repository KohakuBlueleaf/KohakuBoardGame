#pragma once
#include <vector>
#include <string>
#include <utility>
#include <cstddef>
#include <cstdint>
#include <unordered_map>

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
    std::unordered_map<uint64_t, int> hash_counts;  /* position hash → occurrence count */
    std::unordered_map<uint64_t, int> check_hash_counts; /* times position appeared while in check */

    virtual ~BaseState() = default;

    /* Inherit hash history from parent state (call in next_state) */
    void inherit_history(const BaseState* parent){
        hash_counts = parent->hash_counts;
        hash_counts[parent->hash()]++;
        check_hash_counts = parent->check_hash_counts;
    }

    /* Record whether the current position is "in check" (for perpetual check detection).
     * Call AFTER get_legal_actions on the new state, passing true if the side-to-move
     * is in check (opponent is giving check). */
    void record_check_status(bool in_check){
        if(in_check){
            check_hash_counts[hash()]++;
        }
    }

    /* Check if current position has appeared >= limit times (including now). */
    bool check_repetition(int limit = 4) const {
        auto it = hash_counts.find(hash());
        int prev = (it != hash_counts.end()) ? it->second : 0;
        return (prev + 1) >= limit;
    }

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
