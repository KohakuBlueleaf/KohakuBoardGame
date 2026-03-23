#include "state.hpp"
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <sstream>


/* === Zobrist hashing === */

static uint64_t c6_zobrist[3][BOARD_H][BOARD_W];
static uint64_t c6_zobrist_side;
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
 * Score a single placement for move ordering.
 * Higher = more valuable (wins, blocks, creates threats).
 * who = stone color (1 or 2).
 *============================================================*/
int State::score_single_placement(int r, int c, int who) const {
    int score = 0;

    /* Temporarily place stone */
    const_cast<char&>(board.board[r][c]) = who;

    /* Check each direction for threat patterns */
    static const int dirs[4][2] = {{0, 1}, {1, 0}, {1, 1}, {1, -1}};
    for(auto& d : dirs){
        int fwd = count_dir(r, c, d[0], d[1]);
        int bwd = count_dir(r, c, -d[0], -d[1]);
        int total = 1 + fwd + bwd;

        if(total >= 6){
            score += 100000; /* creates six = win */
        }else if(total == 5){
            /* Check if both ends are open */
            int er = r + d[0] * (fwd + 1), ec = c + d[1] * (fwd + 1);
            int sr = r - d[0] * (bwd + 1), sc = c - d[1] * (bwd + 1);
            bool end_open = (
                er >= 0 && er < BOARD_H && ec >= 0 && ec < BOARD_W
                && board.board[er][ec] == 0
            );
            bool start_open = (
                sr >= 0 && sr < BOARD_H && sc >= 0 && sc < BOARD_W
                && board.board[sr][sc] == 0
            );
            if(end_open && start_open){
                score += 50000; /* open-5 */
            }else if(end_open || start_open){
                score += 10000; /* half-5 */
            }
        }else if(total == 4){
            score += 1000; /* building toward six */
        }else if(total == 3){
            score += 100;
        }else if(total == 2){
            score += 10;
        }
    }

    /* Center bonus */
    int dr = abs(r - BOARD_H / 2);
    int dc = abs(c - BOARD_W / 2);
    score += 50 - (dr + dc) * 3;

    const_cast<char&>(board.board[r][c]) = 0;
    return score;
}


/*============================================================
 * Legal move generation for Connect6.
 *
 * Each move places 2 stones: Move = ((r1,c1), (r2,c2)).
 * Uses proximity pruning + threat scoring to limit branching:
 * 1. Find all empty squares near existing stones (Manhattan ≤ 2)
 * 2. Score each square by threat value
 * 3. Take top-K candidates
 * 4. Generate all pairs from top-K
 *============================================================*/
void State::get_legal_actions(){
    legal_actions.clear();
    if(game_state == WIN || game_state == DRAW){
        return;
    }

    int my_id = (player == 0) ? 2 : 1;
    int opp_id = (player == 0) ? 1 : 2;

    /* Check if opponent's last stones created a win */
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c] == opp_id && check_win_at(r, c)){
                game_state = WIN; /* opponent already won = current player lost */
                return;
            }
        }
    }

    /* Build proximity mask (Manhattan distance ≤ 2 from any stone) */
    bool near[BOARD_H][BOARD_W] = {};
    int stone_count = 0;
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c] != 0){
                stone_count++;
                for(int dr = -2; dr <= 2; dr++){
                    for(int dc = -2; dc <= 2; dc++){
                        if(abs(dr) + abs(dc) > 2) continue;
                        int nr = r + dr, nc = c + dc;
                        if(nr >= 0 && nr < BOARD_H && nc >= 0 && nc < BOARD_W){
                            near[nr][nc] = true;
                        }
                    }
                }
            }
        }
    }

    /* Collect and score nearby empty squares */
    struct ScoredSq {
        int r, c, score;
    };
    std::vector<ScoredSq> candidates;
    candidates.reserve(128);

    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c] != 0 || !near[r][c]) continue;

            /* Score for both attacking and defending */
            int atk = score_single_placement(r, c, my_id);
            int def = score_single_placement(r, c, opp_id);
            int sc = atk + def * 9 / 10; /* slight attack preference */
            candidates.push_back({r, c, sc});
        }
    }

    if(candidates.empty()){
        /* Board full */
        game_state = DRAW;
        return;
    }

    /* Sort by score descending */
    std::sort(
        candidates.begin(), candidates.end(),
        [](const ScoredSq& a, const ScoredSq& b){
            return a.score > b.score;
        }
    );

    /* Limit to top-K to control branching */
    constexpr int MAX_SINGLES = 30;
    int n = std::min((int)candidates.size(), MAX_SINGLES);

    /* Check for immediate wins: if placing 1 stone creates six,
     * pair it with any second stone */
    for(int i = 0; i < n; i++){
        if(candidates[i].score >= 100000){
            /* This single placement wins. Pair with first other candidate. */
            int r1 = candidates[i].r, c1 = candidates[i].c;
            for(int j = 0; j < n; j++){
                if(j == i) continue;
                int r2 = candidates[j].r, c2 = candidates[j].c;
                legal_actions.push_back(
                    Move(Point(r1, c1), Point(r2, c2))
                );
                return; /* Only need one winning move */
            }
            /* Only 1 candidate total — shouldn't happen but handle */
            legal_actions.push_back(
                Move(Point(r1, c1), Point(r1, c1))
            );
            return;
        }
    }

    /* Generate all ordered pairs from top-K.
     * (r1,c1) < (r2,c2) in raster order to avoid duplicates. */
    legal_actions.reserve(n * (n - 1) / 2);
    for(int i = 0; i < n; i++){
        for(int j = i + 1; j < n; j++){
            legal_actions.push_back(
                Move(
                    Point(candidates[i].r, candidates[i].c),
                    Point(candidates[j].r, candidates[j].c)
                )
            );
        }
    }

    if(legal_actions.empty()){
        /* Only 1 candidate — place it twice (degenerate) */
        if(!candidates.empty()){
            int r = candidates[0].r, c = candidates[0].c;
            legal_actions.push_back(Move(Point(r, c), Point(r, c)));
        }else{
            game_state = DRAW;
        }
    }
}


/*============================================================
 * next_state: place 2 stones of current player's color.
 * Move = ((r1,c1), (r2,c2)) — both are placement targets.
 *============================================================*/
State* State::next_state(const Move& move){
    if(!c6_zobrist_ready) init_c6_zobrist();

    State* ns = new State(this->board, 1 - this->player);
    ns->step = this->step + 1;
    int stone = (this->player == 0) ? 2 : 1;

    int r1 = move.first.first, c1 = move.first.second;
    int r2 = move.second.first, c2 = move.second.second;

    /* Place first stone */
    ns->board.board[r1][c1] = stone;

    /* Place second stone (may be same square in degenerate case) */
    if(r1 != r2 || c1 != c2){
        ns->board.board[r2][c2] = stone;
    }

    /* Check for win after placement */
    if(check_win_at(r1, c1) || (r1 != r2 || c1 != c2) ? false : false){
        /* Win check happens in get_legal_actions of the next state */
    }

    /* Incremental hash */
    uint64_t h = this->hash();
    h ^= c6_zobrist_side;
    h ^= c6_zobrist[stone][r1][c1];
    if(r1 != r2 || c1 != c2){
        h ^= c6_zobrist[stone][r2][c2];
    }
    ns->zobrist_hash = h;
    ns->zobrist_valid = true;

    return ns;
}


/*============================================================
 * Evaluate — threat-based heuristic for Connect6.
 *
 * Similar to Gomoku eval but adjusted for 6-in-a-row:
 * - Scans all lines for threat patterns
 * - Counts open-5, half-5, open-4, etc.
 * - Compound threats detected
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

    /* Count threats for both sides */
    struct Threats {
        int six = 0;
        int open5 = 0;
        int half5 = 0;
        int open4 = 0;
        int half4 = 0;
        int open3 = 0;
        int half3 = 0;
    };

    auto count_threats = [&](int who) -> Threats {
        Threats t;
        static const int dirs[4][2] = {{0, 1}, {1, 0}, {1, 1}, {1, -1}};

        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                if(board.board[r][c] != who) continue;

                for(auto& d : dirs){
                    /* Only count from the "start" of a line to avoid double-counting */
                    int pr = r - d[0], pc = c - d[1];
                    if(pr >= 0 && pr < BOARD_H && pc >= 0 && pc < BOARD_W
                        && board.board[pr][pc] == who)
                    {
                        continue; /* not the start of this run */
                    }

                    int len = count_dir(r, c, d[0], d[1]) + 1;

                    /* Check open ends */
                    int er = r + d[0] * len, ec = c + d[1] * len;
                    int sr = r - d[0], sc = c - d[1];
                    bool end_open = (
                        er >= 0 && er < BOARD_H && ec >= 0 && ec < BOARD_W
                        && board.board[er][ec] == 0
                    );
                    bool start_open = (
                        sr >= 0 && sr < BOARD_H && sc >= 0 && sc < BOARD_W
                        && board.board[sr][sc] == 0
                    );
                    int opens = (end_open ? 1 : 0) + (start_open ? 1 : 0);

                    if(len >= 6){
                        t.six++;
                    }else if(len == 5){
                        if(opens == 2) t.open5++;
                        else if(opens == 1) t.half5++;
                    }else if(len == 4){
                        if(opens == 2) t.open4++;
                        else if(opens == 1) t.half4++;
                    }else if(len == 3){
                        if(opens == 2) t.open3++;
                        else if(opens == 1) t.half3++;
                    }
                }
            }
        }
        return t;
    };

    Threats my = count_threats(my_id);
    Threats opp = count_threats(opp_id);

    /* Decisive threats */
    if(my.open5 > 0) return 60000;
    if(my.half5 >= 2) return 55000;
    if(my.half5 >= 1 && my.open4 >= 1) return 50000;
    if(my.open4 >= 2) return 45000;

    if(opp.open5 > 0) return -60000;
    if(opp.half5 >= 2) return -55000;
    if(opp.half5 >= 1 && opp.open4 >= 1) return -50000;
    if(opp.open4 >= 2) return -45000;

    /* Weighted scoring */
    auto threat_score = [](const Threats& t) -> int {
        return (
            t.open5 * 30000
            + t.half5 * 5000
            + t.open4 * 3000
            + t.half4 * 500
            + t.open3 * 300
            + t.half3 * 50
        );
    };

    int sc = threat_score(my) - threat_score(opp) * 11 / 10;

    /* Center bonus */
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c] == my_id){
                sc += 7 - abs(r - 7) - abs(c - 7);
            }else if(board.board[r][c] == opp_id){
                sc -= 7 - abs(r - 7) - abs(c - 7);
            }
        }
    }

    return sc;
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
