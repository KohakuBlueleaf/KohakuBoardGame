#include "state.hpp"
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <sstream>


/* === Zobrist hashing === */

static uint64_t c6_zobrist[3][BOARD_H][BOARD_W];
static uint64_t c6_zobrist_side;
static uint64_t c6_zobrist_stone2;  /* XOR when stones_left == 1 (mid-turn) */
static bool c6_zobrist_ready = false;

static void init_c6_zobrist(){
    uint64_t s = 0xA1B2C3D4E5F6A7B8ULL;
    auto rand64 = [&s]() -> uint64_t {
        s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s;
    };
    for(int v = 0; v < 3; v++){
        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                c6_zobrist[v][r][c] = rand64();
            }
        }
    }
    c6_zobrist_side = rand64();
    c6_zobrist_stone2 = rand64();
    c6_zobrist_ready = true;
}

uint64_t State::compute_hash_full() const {
    if(!c6_zobrist_ready) init_c6_zobrist();
    uint64_t h = 0;
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c]){
                h ^= c6_zobrist[(int)board.board[r][c]][r][c];
            }
        }
    }
    if(player) h ^= c6_zobrist_side;
    if(stones_left == 1) h ^= c6_zobrist_stone2;
    return h;
}


/*============================================================
 * Count consecutive stones in one direction from (row, col).
 *============================================================*/
int State::count_dir(int row, int col, int dr, int dc) const {
    int who = board.board[row][col];
    int count = 0;
    int r = row + dr, c = col + dc;
    while(r >= 0 && r < BOARD_H && c >= 0 && c < BOARD_W
        && board.board[r][c] == who)
    {
        count++;
        r += dr;
        c += dc;
    }
    return count;
}


/*============================================================
 * Check if stone at (row, col) creates a winning line (6+).
 *============================================================*/
bool State::check_win_at(int row, int col) const {
    static const int dirs[4][2] = {{0, 1}, {1, 0}, {1, 1}, {1, -1}};
    for(auto& d : dirs){
        int total = (
            1 + count_dir(row, col, d[0], d[1])
            + count_dir(row, col, -d[0], -d[1])
        );
        if(total >= WIN_LENGTH){
            return true;
        }
    }
    return false;
}


/*============================================================
 * 6-cell sliding window scoring.
 *
 * Scans all 6-cell windows in 4 directions across the board.
 * A window is "pure" if it contains only one player's stones
 * (+ empty cells). Mixed windows are dead (score 0).
 *
 * For a pure window with N stones of player `who`:
 *   N=6: win (shouldn't happen — already detected)
 *   N=5: 1 stone from win
 *   N=4: 2 stones from win
 *   N=3: building
 *   N=2: developing
 *   N=1: minimal
 *
 * Weights use exponential scaling (following YoungHeonRo approach).
 *============================================================*/

/* Window scores indexed by stone count 0..6.
 * Heavily exponential: each additional stone is ~20-50x more valuable.
 * 5 stones = 1 from win = nearly terminal. 4 stones = 2 from win.
 * The large gaps ensure the engine strongly prefers extending existing
 * lines over creating new scattered windows. */
static const int WINDOW_SCORE[7] = {
    0,          /* 0 stones: empty window */
    1,          /* 1 stone: minimal */
    5,          /* 2 stones: developing */
    50,         /* 3 stones: building */
    5000,       /* 4 stones: serious — 2 from win, 100x jump */
    500000,     /* 5 stones: critical — 1 from win, 100x jump */
    10000000,   /* 6 stones: won */
};

/* Scan all 6-cell windows and return total score for player `who`.
 * Only pure windows (containing only `who` stones + empty) count. */
static int window_score_for(
    const char brd[BOARD_H][BOARD_W],
    int who
){
    int total = 0;
    static const int dirs[4][2] = {{0, 1}, {1, 0}, {1, 1}, {1, -1}};
    int other = (who == 1) ? 2 : 1;

    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            for(auto& d : dirs){
                /* Check if all 6 cells are in bounds */
                int er = r + d[0] * 5, ec = c + d[1] * 5;
                if(er < 0 || er >= BOARD_H || ec < 0 || ec >= BOARD_W){
                    continue;
                }

                /* Count stones in this window */
                int mine = 0;
                bool dead = false;
                for(int k = 0; k < 6; k++){
                    int wr = r + d[0] * k, wc = c + d[1] * k;
                    char v = brd[wr][wc];
                    if(v == other){
                        dead = true;
                        break;
                    }
                    if(v == who){
                        mine++;
                    }
                }
                if(!dead && mine > 0){
                    total += WINDOW_SCORE[mine];
                }
            }
        }
    }
    return total;
}


/*============================================================
 * Score a single placement for move ordering.
 * Computes DELTA: (score with stone) - (score without stone)
 * for all windows passing through (r,c).
 * This measures the MARGINAL VALUE of placing here.
 *============================================================*/
int State::score_single_placement(int r, int c, int who) const {
    int other = (who == 1) ? 2 : 1;
    static const int dirs[4][2] = {{0, 1}, {1, 0}, {1, 1}, {1, -1}};

    int gain = 0;   /* how much our windows improve */
    int damage = 0; /* how much opponent's windows we destroy */

    /* Scan all windows passing through (r,c) BEFORE placing our stone.
     * (r,c) is currently empty. */
    for(auto& d : dirs){
        for(int off = -5; off <= 0; off++){
            int sr = r + d[0] * off, sc = c + d[1] * off;
            int er = sr + d[0] * 5, ec = sc + d[1] * 5;
            if(sr < 0 || sr >= BOARD_H || sc < 0 || sc >= BOARD_W) continue;
            if(er < 0 || er >= BOARD_H || ec < 0 || ec >= BOARD_W) continue;

            int my_count = 0, opp_count = 0;
            for(int k = 0; k < 6; k++){
                int wr = sr + d[0] * k, wc = sc + d[1] * k;
                char v = board.board[wr][wc];
                if(v == who) my_count++;
                else if(v == other) opp_count++;
            }

            if(opp_count == 0 && my_count >= 0){
                /* Pure our window (or empty): placing adds 1 stone.
                 * Before: WINDOW_SCORE[my_count], After: WINDOW_SCORE[my_count+1] */
                gain += WINDOW_SCORE[my_count + 1] - WINDOW_SCORE[my_count];
            }
            if(my_count == 0 && opp_count > 0){
                /* Pure opponent window: our placement makes it mixed = dead.
                 * We destroy WINDOW_SCORE[opp_count] worth of opponent value. */
                damage += WINDOW_SCORE[opp_count];
            }
        }
    }

    return gain + damage;
}


/*============================================================
 * Legal move generation for Connect6 (single-stone moves).
 *
 * Each move places 1 stone: Move = ((r,c), (r,c)) with from==to.
 * The stones_left counter tracks whether this is stone 1 or 2
 * of the current turn. Player switches after stone 2.
 *
 * Uses proximity pruning (Chebyshev dist ≤ 3) + threat scoring.
 *============================================================*/
void State::get_legal_actions(){
    legal_actions.clear();
    if(game_state == WIN || game_state == DRAW){
        return;
    }

    /* Ensure stones_left is consistent with step.
     * This handles states constructed via State(board, player) + step
     * where stones_left wasn't set by next_state (e.g. UBGI replay). */
    if(step > 0){
        stones_left = (step % 2 == 0) ? 2 : 1;
    }

    int opp_id = (player == 0) ? 1 : 2;

    /* Check if opponent (or same player's previous stone) created a win */
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c] != 0 && check_win_at(r, c)){
                /* Someone has 6 in a row. If it's the opponent's stones,
                 * current player lost. If same player's stones (from stone 1
                 * of this turn), the current player already won. */
                int winner_stone = board.board[r][c];
                int my_id = (player == 0) ? 2 : 1;
                if(winner_stone == my_id){
                    /* Current player already has 6 — they won (from stone 1) */
                    game_state = WIN;
                }else{
                    /* Opponent has 6 — current player lost */
                    game_state = WIN;
                }
                return;
            }
        }
    }

    /* Build proximity mask (Chebyshev distance ≤ 2) */
    bool near[BOARD_H][BOARD_W] = {};
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c] != 0){
                for(int dr = -2; dr <= 2; dr++){
                    for(int dc = -2; dc <= 2; dc++){
                        int nr = r + dr, nc = c + dc;
                        if(nr >= 0 && nr < BOARD_H && nc >= 0 && nc < BOARD_W){
                            near[nr][nc] = true;
                        }
                    }
                }
            }
        }
    }

    /* Single-stone moves: each legal move places 1 stone.
     * Move = ((r,c), (r,c)) with from == to (placement). */
    int my_id = (player == 0) ? 2 : 1;
    struct ScoredSq { int r, c, score; };
    std::vector<ScoredSq> candidates;
    candidates.reserve(128);

    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c] != 0 || !near[r][c]) continue;
            /* score_single_placement includes attack gain + defensive damage */
            int sc = score_single_placement(r, c, my_id);
            /* Skip very low-value squares — only include if the stone
             * actually contributes to or blocks a meaningful window */
            if(sc > 5){
                candidates.push_back({r, c, sc});
            }
        }
    }

    if(candidates.empty()){
        game_state = DRAW;
        return;
    }

    /* Sort by score, take top-K */
    std::sort(
        candidates.begin(), candidates.end(),
        [](const ScoredSq& a, const ScoredSq& b){
            return a.score > b.score;
        }
    );

    constexpr int MAX_CANDIDATES = 25;
    int n = std::min((int)candidates.size(), MAX_CANDIDATES);

    legal_actions.reserve(n);
    for(int i = 0; i < n; i++){
        int r = candidates[i].r, c = candidates[i].c;
        legal_actions.push_back(Move(Point(r, c), Point(r, c)));
    }
}


/*============================================================
 * next_state: place 1 stone. Tracks stones_left for turn cycle.
 * stones_left=2 → place stone, set stones_left=1, same player
 * stones_left=1 → place stone, set stones_left=2, switch player
 *============================================================*/
State* State::next_state(const Move& move){
    if(!c6_zobrist_ready) init_c6_zobrist();

    int r = move.second.first, c = move.second.second;
    int stone = (this->player == 0) ? 2 : 1;

    bool switch_player = (this->stones_left == 1);

    State* ns = new State();
    /* Copy board manually to avoid Board() constructor placing center */
    std::memcpy(ns->board.board, this->board.board, sizeof(this->board.board));
    ns->board.board[r][c] = stone;

    ns->player = switch_player ? (1 - this->player) : this->player;
    ns->stones_left = switch_player ? 2 : 1;
    ns->step = this->step + 1;

    /* Incremental hash */
    uint64_t h = this->hash();
    if(switch_player){
        h ^= c6_zobrist_side;  /* player flips */
    }
    /* Toggle stones_left key: parent had stones_left=N, child has different */
    if(this->stones_left == 2){
        /* parent was stone1 (no stone2 key), child is stone2 (add stone2 key) */
        h ^= c6_zobrist_stone2;
    }else{
        /* parent was stone2 (had stone2 key), child is stone1 (remove stone2 key) */
        h ^= c6_zobrist_stone2;
    }
    h ^= c6_zobrist[stone][r][c];
    ns->zobrist_hash = h;
    ns->zobrist_valid = true;

    return ns;
}


/*============================================================
 * Evaluate — 6-cell sliding window heuristic for Connect6.
 *
 * Scans every 6-cell window in all 4 directions.
 * A pure window (only one player's stones + empty) is scored
 * by stone count. Mixed windows are dead (score 0).
 * This catches gap patterns like XX_X_X that consecutive-run
 * evaluation misses.
 *
 * Score = my_windows - opp_windows * 1.2 (defensive bias)
 *============================================================*/
int State::evaluate(
    bool /*use_nnue*/,
    bool /*use_kp*/,
    bool /*use_mobility*/,
    const GameHistory* /*history*/
){
    if(game_state == WIN){
        return P_MAX;
    }
    if(game_state == DRAW){
        return 0;
    }
    if(legal_actions.empty()){
        return (game_state == DRAW) ? 0 : -P_MAX;
    }

    int my_id = (player == 0) ? 2 : 1;
    int opp_id = (player == 0) ? 1 : 2;

    int my_score = window_score_for(board.board, my_id);
    int opp_score = window_score_for(board.board, opp_id);

    /* Check for decisive windows (6 or 5 stones) */
    if(my_score >= 100000) return P_MAX - 1;
    if(opp_score >= 100000) return -(P_MAX - 1);

    return my_score - opp_score * 12 / 10;
}


/*============================================================
 * Repetition: Connect6 has no repetition rule.
 *============================================================*/
bool State::check_repetition(
    const GameHistory& /*history*/,
    int& /*out_score*/
) const {
    return false;
}


/*============================================================
 * Display
 *============================================================*/
std::string State::encode_output() const {
    std::stringstream ss;
    ss << "   ";
    for(int c = 0; c < BOARD_W; c++){
        ss << (char)('A' + c) << "  ";
    }
    ss << "\n";
    for(int r = 0; r < BOARD_H; r++){
        int label = BOARD_H - r;
        if(label < 10) ss << " ";
        ss << label << " ";
        for(int c = 0; c < BOARD_W; c++){
            ss << cell_display(r, c);
        }
        ss << label << "\n";
    }
    ss << "   ";
    for(int c = 0; c < BOARD_W; c++){
        ss << (char)('A' + c) << "  ";
    }
    ss << "\n";
    ss << "Side: " << (player == 0 ? "White" : "Black")
       << " | Step: " << step << "\n";
    return ss.str();
}


/*============================================================
 * Board encoding for UBGI protocol
 *============================================================*/
std::string State::encode_board() const {
    std::string s;
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            s += ('0' + board.board[r][c]);
        }
    }
    return s;
}

void State::decode_board(const std::string& s, int side_to_move){
    player = side_to_move;
    game_state = UNKNOWN;
    zobrist_valid = false;
    int idx = 0;
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(idx < (int)s.size()){
                board.board[r][c] = s[idx] - '0';
            }
            idx++;
        }
    }
}


/*============================================================
 * NNUE feature extraction (placeholder)
 *============================================================*/
int State::extract_nnue_features(int /*perspective*/, int* /*features*/) const {
    return 0;
}
