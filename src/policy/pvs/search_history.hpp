#pragma once
#include <cstdint>
#include <unordered_map>

/*============================================================
 * Search History — lightweight push/pop repetition tracking
 *
 * Instead of copying hash_counts maps between states (O(N) per
 * node), maintain a single dict per search that grows/shrinks
 * with the search depth. Size bounded by max depth, not game length.
 *
 * Usage in search:
 *   search_history_push(hash)   — before recursing into child
 *   search_history_pop(hash)    — after returning from child
 *   search_history_count(hash)  — check repetition count
 *
 * The game-level history (positions from actual play before search
 * started) is loaded once at the root via search_history_init.
 *============================================================*/

/* Global search history (one per thread if needed) */
inline std::unordered_map<uint64_t, int> g_search_history;

/* Initialize with the game-level history (call before each root search) */
inline void search_history_init(const std::unordered_map<uint64_t, int>& game_history){
    g_search_history = game_history;
}

inline void search_history_clear(){
    g_search_history.clear();
}

inline void search_history_push(uint64_t hash){
    g_search_history[hash]++;
}

inline void search_history_pop(uint64_t hash){
    auto it = g_search_history.find(hash);
    if(it != g_search_history.end()){
        it->second--;
        if(it->second <= 0){
            g_search_history.erase(it);
        }
    }
}

inline int search_history_count(uint64_t hash){
    auto it = g_search_history.find(hash);
    return (it != g_search_history.end()) ? it->second : 0;
}

/* Check if hash has appeared >= limit times */
inline bool search_history_is_repetition(uint64_t hash, int limit = 4){
    return search_history_count(hash) >= limit;
}

/* RAII guard: push on construction, pop on destruction */
struct SearchHistoryGuard {
    uint64_t h;
    bool active;
    SearchHistoryGuard(uint64_t hash) : h(hash), active(true) {
        search_history_push(h);
    }
    ~SearchHistoryGuard(){
        if(active) search_history_pop(h);
    }
    void release(){ active = false; }  /* don't pop (e.g. if popped manually) */
};
