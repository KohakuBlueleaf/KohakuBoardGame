#include "state.hpp"
#include <algorithm>
#include <cstdlib>


/* === Zobrist hashing for Gomoku === */

static uint64_t gomoku_zobrist[3][BOARD_H][BOARD_W];
static uint64_t gomoku_zobrist_side;
static bool gomoku_zobrist_ready = false;

static void init_gomoku_zobrist(){
    uint64_t s = 0xA1B2C3D4E5F6A7B8ULL;
    auto rand64 = [&s]() -> uint64_t {
        s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s;
    };
    for(int v = 0; v < 3; v++){
        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                gomoku_zobrist[v][r][c] = rand64();
            }
        }
    }
    gomoku_zobrist_side = rand64();
    gomoku_zobrist_ready = true;
}

uint64_t State::hash() const {
    if(!gomoku_zobrist_ready){ init_gomoku_zobrist(); }
    uint64_t h = 0;
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c]){
                h ^= gomoku_zobrist[static_cast<int>(board.board[r][c])][r][c];
            }
        }
    }
    if(player){ h ^= gomoku_zobrist_side; }
    return h;
}


/*============================================================
 * Count consecutive stones in one direction from (row, col).
 * Starts at (row+dr, col+dc) and walks while stones match.
 *============================================================*/
int State::count_dir(int row, int col, int dr, int dc) const {
    int who = board.board[row][col];
    int count = 0;
    int r = row + dr, c = col + dc;
    while(r >= 0 && r < BOARD_H && c >= 0 && c < BOARD_W
          && board.board[r][c] == who){
        count++;
        r += dr;
        c += dc;
    }
    return count;
}


/*============================================================
 * Check if the stone at (row, col) creates a winning line.
 * Examines 4 axes (horizontal, vertical, two diagonals).
 *============================================================*/
bool State::check_win_at(int row, int col) const {
    static const int dirs[4][2] = {{0, 1}, {1, 0}, {1, 1}, {1, -1}};
    for(auto& d : dirs){
        int total = 1 + count_dir(row, col, d[0], d[1])
                      + count_dir(row, col, -d[0], -d[1]);
        if(total >= WIN_LENGTH){
            return true;
        }
    }
    return false;
}


/*============================================================
 * Populate legal_actions with empty cells near existing stones
 * (Manhattan distance <= 2).  On an empty board, offer only
 * the centre cell.  Detects terminal states: no moves = DRAW.
 *============================================================*/
void State::get_legal_actions(){
    legal_actions.clear();
    if(game_state == WIN || game_state == DRAW){
        return;
    }

    /* --- Check whether any stone exists on the board --- */
    bool has_stone = false;
    for(int r = 0; r < BOARD_H && !has_stone; r++){
        for(int c = 0; c < BOARD_W && !has_stone; c++){
            if(board.board[r][c] != 0){
                has_stone = true;
            }
        }
    }

    /* --- Empty board: only the centre cell --- */
    if(!has_stone){
        int cr = BOARD_H / 2;
        int cc = BOARD_W / 2;
        legal_actions.push_back(Move(Point(cr, cc), Point(cr, cc)));
        return;
    }

    /* --- Build proximity mask (Manhattan distance <= 2) --- */
    bool near[BOARD_H][BOARD_W] = {};
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c] != 0){
                for(int dr = -2; dr <= 2; dr++){
                    for(int dc = -2; dc <= 2; dc++){
                        if(abs(dr) + abs(dc) > 2) continue;
                        int nr = r + dr;
                        int nc = c + dc;
                        if(nr >= 0 && nr < BOARD_H && nc >= 0 && nc < BOARD_W){
                            near[nr][nc] = true;
                        }
                    }
                }
            }
        }
    }

    /* --- Collect empty cells inside the proximity mask --- */
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c] == 0 && near[r][c]){
                legal_actions.push_back(Move(Point(r, c), Point(r, c)));
            }
        }
    }

    if(legal_actions.empty()){
        game_state = DRAW;
    }
}


/*============================================================
 * Create a new state after placing a stone.
 * Checks if the move wins; otherwise switches side to move.
 *============================================================*/
State* State::next_state(const Move& move){
    State* next = new State(this->board, 1 - this->player);
    next->step = this->step + 1;
    int r = move.second.first;
    int c = move.second.second;
    next->board.board[r][c] = this->player + 1;

    if(next->check_win_at(r, c)){
        next->player = this->player;
        next->game_state = WIN;
    }else{
        next->get_legal_actions();
    }
    return next;
}


/*============================================================
 * Threat counts for one player.
 *============================================================*/
struct ThreatCounts {
    int five  = 0;   /* already 5+ in a row                 */
    int open4 = 0;   /* 4 in a row, open on BOTH ends       */
    int half4 = 0;   /* 4 in a row, open on exactly 1 end   */
    int open3 = 0;   /* 3 in a row, open on both ends       */
    int half3 = 0;   /* 3 in a row, open on 1 end           */
    int open2 = 0;   /* 2 in a row, open on both ends       */
    int half2 = 0;   /* 2 in a row, open on 1 end           */
};

static ThreatCounts count_threats(const Board& board, int who){
    ThreatCounts t;
    static const int dirs[4][2] = {{0, 1}, {1, 0}, {1, 1}, {1, -1}};
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c] != who){ continue; }
            for(auto& d : dirs){
                /* skip if not the start of the line */
                int pr = r - d[0], pc = c - d[1];
                if(pr >= 0 && pr < BOARD_H && pc >= 0 && pc < BOARD_W
                   && board.board[pr][pc] == who){
                    continue;
                }

                /* measure consecutive length */
                int len = 1;
                int nr = r + d[0], nc = c + d[1];
                while(nr >= 0 && nr < BOARD_H && nc >= 0 && nc < BOARD_W
                      && board.board[nr][nc] == who){
                    len++;
                    nr += d[0];
                    nc += d[1];
                }

                /* count open ends */
                int open_ends = 0;
                if(nr >= 0 && nr < BOARD_H && nc >= 0 && nc < BOARD_W
                   && board.board[nr][nc] == 0){ open_ends++; }
                if(pr >= 0 && pr < BOARD_H && pc >= 0 && pc < BOARD_W
                   && board.board[pr][pc] == 0){ open_ends++; }

                /* classify */
                if(len >= WIN_LENGTH)    { t.five++;  }
                else if(len == 4){
                    if(open_ends == 2)   { t.open4++; }
                    else if(open_ends==1){ t.half4++; }
                }
                else if(len == 3){
                    if(open_ends == 2)   { t.open3++; }
                    else if(open_ends==1){ t.half3++; }
                }
                else if(len == 2){
                    if(open_ends == 2)   { t.open2++; }
                    else if(open_ends==1){ t.half2++; }
                }
            }
        }
    }
    return t;
}

/* Weighted score from threat counts (used for non-decisive positions) */
static int threat_score(const ThreatCounts& t){
    return t.open3 * 500
         + t.half3 * 80
         + t.open2 * 60
         + t.half2 * 10;
}


/*============================================================
 * Heuristic evaluation for Gomoku.
 *
 * Key insight: certain threats are IMMEDIATELY decisive
 * regardless of what the rest of the board looks like.
 * We detect these first, then fall back to weighted scoring.
 *
 * Decisive (from STM's perspective):
 *   - STM has 5+          → already won           → +P_MAX
 *   - STM has open-4      → wins next move        → +(P_MAX-1)
 *   - STM has 2+ half-4   → wins (can't block 2)  → +(P_MAX-2)
 *   - OPP has 5+          → already lost           → -P_MAX
 *   (if none of those, but OPP has open-4 or 2+ half-4,
 *    STM must respond immediately — very bad)
 *   - STM has open-3 + any half-4 → wins          → +(P_MAX-3)
 *   - STM has 2+ open-3   → wins (double threat)  → +(P_MAX-4)
 *============================================================*/
int State::evaluate(bool /*use_nnue*/, bool /*use_kp*/, bool /*use_mobility*/){
    if(game_state == WIN){
        return P_MAX;
    }
    if(game_state == DRAW){
        return 0;
    }

    int my_id  = player + 1;
    int opp_id = 2 - player;
    ThreatCounts my  = count_threats(board, my_id);
    ThreatCounts opp = count_threats(board, opp_id);

    /* --- STM decisive wins --- */
    if(my.five  > 0)                          { return  P_MAX - 1; }
    if(my.open4 > 0)                          { return  P_MAX - 2; }
    if(my.half4 >= 2)                         { return  P_MAX - 3; }
    if(my.half4 >= 1 && my.open3 >= 1)        { return  P_MAX - 4; }
    if(my.open3 >= 2)                         { return  P_MAX - 5; }

    /* --- OPP decisive threats (STM can't stop) --- */
    if(opp.five  > 0)                         { return -(P_MAX - 1); }
    if(opp.open4 > 0)                         { return -(P_MAX - 10); }
    if(opp.half4 >= 2)                        { return -(P_MAX - 10); }
    if(opp.half4 >= 1 && opp.open3 >= 1)      { return -(P_MAX - 20); }
    if(opp.open3 >= 2)                        { return -(P_MAX - 20); }

    /* --- OPP has single half-4: STM must block (tempo penalty) --- */
    int score = threat_score(my) - threat_score(opp);
    if(opp.half4 >= 1){
        score -= 5000;
    }
    /* --- STM has half-4: big advantage (forces response) --- */
    if(my.half4 >= 1){
        score += 5000;
    }

    return score;
}


/*============================================================
 * Render the board as a human-readable string.
 *============================================================*/
std::string State::encode_output() const {
    std::stringstream ss;
    ss << "  ";
    for(int c = 0; c < BOARD_W; c++){
        ss << (char)('A' + c) << " ";
    }
    ss << "\n";
    for(int r = 0; r < BOARD_H; r++){
        ss << (BOARD_H - r);
        if(BOARD_H - r < 10){
            ss << " ";
        }
        ss << " ";
        for(int c = 0; c < BOARD_W; c++){
            char ch = board.board[r][c];
            if(ch == 0){
                ss << ". ";
            }else if(ch == 1){
                ss << "X ";
            }else{
                ss << "O ";
            }
        }
        ss << (BOARD_H - r) << "\n";
    }
    ss << "  ";
    for(int c = 0; c < BOARD_W; c++){
        ss << (char)('A' + c) << " ";
    }
    ss << "\n";
    return ss.str();
}


/* === Board serialization === */
std::string State::encode_board() const {
    std::string s;
    for(int r = 0; r < BOARD_H; r++){
        if(r > 0){ s += '/'; }
        for(int c = 0; c < BOARD_W; c++){
            char v = board.board[r][c];
            if(v == 1){ s += 'X'; }
            else if(v == 2){ s += 'O'; }
            else{ s += '.'; }
        }
    }
    return s;
}

void State::decode_board(const std::string& s, int side_to_move){
    player = side_to_move;
    game_state = UNKNOWN;
    step = 0;
    board = Board{};
    int r = 0, c = 0;
    for(char ch : s){
        if(ch == '/'){
            r++;
            c = 0;
            continue;
        }
        if(r >= BOARD_H || c >= BOARD_W){ break; }
        if(ch == 'X'){ board.board[r][c] = 1; step++; }
        else if(ch == 'O'){ board.board[r][c] = 2; step++; }
        c++;
    }
    get_legal_actions();
}
