#pragma once
#include <cstdint>
#include <vector>
#include "../../config.hpp"
#include "../../state/state.hpp"

/*============================================================
 * Transposition Table (Zobrist hashing + position cache)
 *
 * TT is dynamically allocated so size can be changed at
 * runtime via UCI "Hash" option (tt_resize).
 *============================================================*/

/* === Zobrist random keys === */
inline uint64_t zobrist_piece[2][7][BOARD_H][BOARD_W];
inline uint64_t zobrist_side;
inline bool zobrist_ready = false;

inline void init_zobrist(){
    uint64_t s = 0x7A35C9D1E4F02B68ULL;
    auto rand64 = [&s]() -> uint64_t {
        s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s;
    };
    for(int p = 0; p < 2; p++){
        for(int t = 0; t < 7; t++){
            for(int r = 0; r < BOARD_H; r++){
                for(int c = 0; c < BOARD_W; c++){
                    zobrist_piece[p][t][r][c] = rand64();
                }
            }
        }
    }
    zobrist_side = rand64();
    zobrist_ready = true;
}

inline uint64_t compute_hash(const State* state){
    if(!zobrist_ready){ init_zobrist(); }
    uint64_t h = 0;
    for(int p = 0; p < 2; p++){
        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                int piece = state->board.board[p][r][c];
                if(piece){ h ^= zobrist_piece[p][piece][r][c]; }
            }
        }
    }
    if(state->player){ h ^= zobrist_side; }
    return h;
}

/* === TT entry === */
enum TTFlag : uint8_t { TT_NONE = 0, TT_EXACT, TT_LOWER, TT_UPPER };

struct TTEntry {
    uint64_t hash = 0;
    int score = 0;
    int depth = -1;
    TTFlag flag = TT_NONE;
    uint8_t from_r = 0, from_c = 0, to_r = 0, to_c = 0;

    Move get_move() const {
        return Move(Point(from_r, from_c), Point(to_r, to_c));
    }
    void set_move(const Move& m){
        from_r = m.first.first;  from_c = m.first.second;
        to_r = m.second.first;   to_c = m.second.second;
    }
};

/* === Dynamic TT === */
inline std::vector<TTEntry> tt;
inline int tt_size_bits = DEFAULT_TT_SIZE_BITS;
inline int tt_mask = 0;

inline void tt_resize(int bits){
    tt_size_bits = bits;
    int size = 1 << bits;
    tt_mask = size - 1;
    tt.assign(size, TTEntry{});
}

inline void tt_init(){
    if(tt.empty()){
        tt_resize(DEFAULT_TT_SIZE_BITS);
    }
}

inline void tt_clear(){
    std::fill(tt.begin(), tt.end(), TTEntry{});
}

inline TTEntry* tt_probe(uint64_t hash){
    tt_init();
    TTEntry& e = tt[hash & tt_mask];
    if(e.flag != TT_NONE && e.hash == hash){
        return &e;
    }
    return nullptr;
}

inline void tt_store(
    uint64_t hash,
    int depth,
    int score,
    TTFlag flag,
    const Move& best
){
    tt_init();
    TTEntry& e = tt[hash & tt_mask];
    if(e.flag == TT_NONE || e.depth <= depth){
        e.hash = hash;
        e.score = score;
        e.depth = depth;
        e.flag = flag;
        e.set_move(best);
    }
}
