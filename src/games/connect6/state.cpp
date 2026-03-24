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

    static const int dirs[4][2] = {{0, 1}, {1, 0}, {1, 1}, {1, -1}};
    for(auto& d : dirs){
        int fwd = count_dir(r, c, d[0], d[1]);
        int bwd = count_dir(r, c, -d[0], -d[1]);
        int total = 1 + fwd + bwd;

        /* Count empty spaces beyond the run */
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
        int opens = (end_open ? 1 : 0) + (start_open ? 1 : 0);

        if(total >= 6){
            score += 1000000; /* instant win */
        }else if(total == 5 && opens >= 1){
            score += 500000; /* 1 stone from win */
        }else if(total == 4 && opens == 2){
            score += 100000; /* open-4: 2 stones complete it */
        }else if(total == 4 && opens == 1){
            score += 20000; /* half-4 */
        }else if(total == 3 && opens == 2){
            score += 5000; /* open-3 */
        }else if(total == 3 && opens == 1){
            score += 1000; /* half-3 */
        }else if(total == 2 && opens == 2){
            score += 200; /* open-2 */
        }else if(total == 2 && opens == 1){
            score += 50;
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

    /* Build proximity mask (Chebyshev distance ≤ 3 from any stone).
     * Larger radius than Gomoku because Connect6 needs 6-in-a-row
     * and each turn places 2 stones that can bridge gaps. */
    bool near[BOARD_H][BOARD_W] = {};
    int stone_count = 0;
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c] != 0){
                stone_count++;
                for(int dr = -3; dr <= 3; dr++){
                    for(int dc = -3; dc <= 3; dc++){
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

    /* Take top-K1 for first stone, top-K2 for second stone.
     * The second stone candidates include ALL nearby squares (not just top-K1)
     * because placing the first stone may make new positions relevant. */
    constexpr int MAX_FIRST = 20;
    constexpr int MAX_SECOND = 30;
    int n1 = std::min((int)candidates.size(), MAX_FIRST);
    int n2 = std::min((int)candidates.size(), MAX_SECOND);

    /* Check for immediate wins first */
    for(int i = 0; i < n1; i++){
        if(candidates[i].score >= 500000){
            /* This placement makes 5+ or creates open-4. Pair with best other. */
            int r1 = candidates[i].r, c1 = candidates[i].c;
            for(int j = 0; j < n2; j++){
                if(j == i) continue;
                legal_actions.push_back(
                    Move(Point(r1, c1), Point(candidates[j].r, candidates[j].c))
                );
                return;
            }
            legal_actions.push_back(Move(Point(r1, c1), Point(r1, c1)));
            return;
        }
    }

    /* Generate pairs: top-K1 first stones × top-K2 second stones.
     * Allow second stone to be any top-K2 candidate, not just those
     * with index > first stone. This captures the "first stone changes
     * what's relevant for second stone" insight. */
    legal_actions.reserve(n1 * n2);
    for(int i = 0; i < n1; i++){
        for(int j = i + 1; j < n2; j++){
            legal_actions.push_back(
                Move(
                    Point(candidates[i].r, candidates[i].c),
                    Point(candidates[j].r, candidates[j].c)
                )
            );
        }
    }

    if(legal_actions.empty()){
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
 * Key difference from Gomoku: each player places 2 stones per turn.
 * This means:
 *   - 5 consecutive + any open end = INSTANT WIN (place 1 stone)
 *   - 4 consecutive + 2 open ends = INSTANT WIN (place 2 stones)
 *   - 4 consecutive + 1 open end  = very strong (extend to 5, then win)
 *   - Need 2 empty in a row to "fill gap" threats
 *
 * Scans all 4 directions for each run of consecutive stones.
 * Also counts empty spaces around runs for potential analysis.
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

    /* Count threats for one side.
     * For each consecutive run of stones, check:
     * - run length
     * - number of open ends (0, 1, 2)
     * - empty spaces beyond open ends (room to extend)
     * A "potential" window is the total reachable length along the line
     * (consecutive + empty on both sides, stopping at opponent/wall). */

    struct Threats {
        int six = 0;       /* 6+ in a row = already won */
        int open5 = 0;     /* 5 + both ends open = instant win (1 stone) */
        int half5 = 0;     /* 5 + one end open = instant win (1 stone) */
        int open4 = 0;     /* 4 + both ends open = instant win (2 stones on ends) */
        int half4 = 0;     /* 4 + one end open with room for 6 */
        int open3 = 0;     /* 3 + both ends open with room for 6 */
        int half3 = 0;     /* 3 + one end open */
        int open2 = 0;     /* 2 + both ends open */
    };

    auto count_threats = [&](int who) -> Threats {
        Threats t;
        static const int dirs[4][2] = {{0, 1}, {1, 0}, {1, 1}, {1, -1}};

        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                if(board.board[r][c] != who) continue;

                for(auto& d : dirs){
                    /* Only count from the start of a run */
                    int pr = r - d[0], pc = c - d[1];
                    if(pr >= 0 && pr < BOARD_H && pc >= 0 && pc < BOARD_W
                        && board.board[pr][pc] == who)
                    {
                        continue;
                    }

                    /* Count consecutive stones */
                    int len = 1;
                    int cr = r + d[0], cc = c + d[1];
                    while(cr >= 0 && cr < BOARD_H && cc >= 0 && cc < BOARD_W
                        && board.board[cr][cc] == who)
                    {
                        len++;
                        cr += d[0];
                        cc += d[1];
                    }

                    /* Count empty spaces at end (forward) */
                    int end_empty = 0;
                    int er = cr, ec = cc;
                    while(er >= 0 && er < BOARD_H && ec >= 0 && ec < BOARD_W
                        && board.board[er][ec] == 0)
                    {
                        end_empty++;
                        er += d[0];
                        ec += d[1];
                    }

                    /* Count empty spaces at start (backward) */
                    int start_empty = 0;
                    int sr = r - d[0], sc = c - d[1];
                    while(sr >= 0 && sr < BOARD_H && sc >= 0 && sc < BOARD_W
                        && board.board[sr][sc] == 0)
                    {
                        start_empty++;
                        sr -= d[0];
                        sc -= d[1];
                    }

                    bool end_open = (end_empty > 0);
                    bool start_open = (start_empty > 0);
                    int opens = (end_open ? 1 : 0) + (start_open ? 1 : 0);
                    /* Total room: can this run potentially reach 6? */
                    int potential = len + end_empty + start_empty;

                    if(potential < 6) continue; /* dead — can never reach 6 */

                    if(len >= 6){
                        t.six++;
                    }else if(len == 5){
                        /* Need 1 more stone. Any open end = instant win (place 1 of 2) */
                        if(opens >= 1) t.open5++;
                        /* Even with 0 opens, if potential >= 6 via gap... but
                         * we only count consecutive, so 0 opens + 5 = dead end */
                    }else if(len == 4){
                        if(opens == 2){
                            t.open4++; /* instant win: place 2 stones on both ends */
                        }else if(opens == 1){
                            t.half4++;
                        }
                    }else if(len == 3){
                        if(opens == 2){
                            t.open3++;
                        }else if(opens == 1){
                            t.half3++;
                        }
                    }else if(len == 2){
                        if(opens == 2){
                            t.open2++;
                        }
                    }
                }
            }
        }
        return t;
    };

    Threats my = count_threats(my_id);
    Threats opp = count_threats(opp_id);

    /* === Decisive threats (from STM perspective) ===
     *
     * Connect6: 2 stones per turn changes threat evaluation:
     * - open5/half5: need 1 stone = instant win (still have 1 stone left for anything)
     * - open4: need 2 stones on both ends = instant win
     * - 2x half4: opponent can only block 1 with their 2 stones, other extends
     * - half4 + open3: block the 4, the open3 becomes unstoppable */

    /* === Decisive threats (Connect6: 2 stones per turn) ===
     *
     * In Connect6, threats are much more severe than Gomoku:
     * - open5/half5: 1 stone wins, still have 1 stone for anything = instant win
     * - open4: 2 stones on both ends = instant win
     * - single half4: extend to 5 with 1 stone + use 2nd stone = nearly winning
     * - 2x half4: opponent blocks 1, other extends = winning
     * - half4 + open3: block the 4, open3 becomes 2-turn win
     * - 2x open3: 2 stones make one into open5 = winning
     * - single open3: 2 stones → open5 (need opponent to block or lose) */

    /* STM wins immediately */
    if(my.six > 0) return P_MAX;
    if(my.open5 > 0) return P_MAX - 1;
    if(my.half5 > 0) return P_MAX - 1;  /* 1 stone extends to 6 */
    if(my.open4 > 0) return P_MAX - 2;
    if(my.half4 >= 2) return P_MAX - 3;
    if(my.half4 >= 1 && my.open3 >= 1) return P_MAX - 4;
    if(my.open3 >= 2) return P_MAX - 5;  /* 2 open3s: make one into open5 */

    /* OPP threats (they get 2 stones next turn) */
    if(opp.open5 > 0) return -(P_MAX - 1);
    if(opp.half5 > 0) return -(P_MAX - 1);
    if(opp.open4 > 0) return -(P_MAX - 2);
    if(opp.half4 >= 2) return -(P_MAX - 3);
    if(opp.half4 >= 1 && opp.open3 >= 1) return -(P_MAX - 4);
    if(opp.open3 >= 2) return -(P_MAX - 5);

    /* === Weighted scoring ===
     * Weights reflect Connect6 threat severity:
     * half4 is very dangerous (1 stone → 5, second stone free)
     * open3 is serious (2 stones → open5 = guaranteed win next turn)
     * Even half3 matters (2 stones can make it 5 with extension) */
    auto threat_score = [](const Threats& t) -> int {
        return (
            t.open5 * 90000
            + t.half5 * 80000
            + t.open4 * 70000
            + t.half4 * 30000
            + t.open3 * 10000
            + t.half3 * 3000
            + t.open2 * 500
        );
    };

    int sc = threat_score(my) - threat_score(opp) * 12 / 10;  /* 1.2x defensive bias */

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
