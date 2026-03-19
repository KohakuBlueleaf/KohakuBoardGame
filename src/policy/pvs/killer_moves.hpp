#pragma once
#include "config.hpp"
#include "state.hpp"

/*============================================================
 * Killer Move Table
 *
 * Stores quiet moves that caused beta cutoffs at each ply.
 * Array sized to MAX_KILLER_SLOTS; runtime param controls
 * how many slots are actually used.
 *============================================================*/
static constexpr int MAX_PLY = 64;
static constexpr int MAX_KILLER_SLOTS = 4;
inline Move killer_table[MAX_PLY][MAX_KILLER_SLOTS];

inline void store_killer(int ply, const Move& move, int slots){
    if(ply >= MAX_PLY){ return; }
    if(killer_table[ply][0] == move){ return; }
    int n = (slots > MAX_KILLER_SLOTS) ? MAX_KILLER_SLOTS : slots;
    for(int i = n - 1; i > 0; i--){
        killer_table[ply][i] = killer_table[ply][i - 1];
    }
    killer_table[ply][0] = move;
}

inline bool is_killer(int ply, const Move& move, int slots){
    if(ply >= MAX_PLY){ return false; }
    int n = (slots > MAX_KILLER_SLOTS) ? MAX_KILLER_SLOTS : slots;
    for(int i = 0; i < n; i++){
        if(killer_table[ply][i] == move){
            return true;
        }
    }
    return false;
}
