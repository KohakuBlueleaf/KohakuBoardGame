#include "state.hpp"
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <sstream>


/* === Zobrist hashing for Connect6 === */

static uint64_t connect6_zobrist[3][BOARD_H][BOARD_W];
static uint64_t connect6_zobrist_side;
static bool connect6_zobrist_ready = false;

static void init_connect6_zobrist(){
    uint64_t s = 0xA1B2C3D4E5F6A7B8ULL;
    auto rand64 = [&s]() -> uint64_t {
        s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s;
    };
    for(int v = 0; v < 3; v++){
        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                connect6_zobrist[v][r][c] = rand64();
            }
        }
    }
    connect6_zobrist_side = rand64();
    connect6_zobrist_ready = true;
}

uint64_t State::compute_hash_full() const{
    if(!connect6_zobrist_ready){
        init_connect6_zobrist();
    }
    uint64_t h = 0;
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c]){
                h ^= connect6_zobrist[static_cast<int>(board.board[r][c])][r][c];
            }
        }
    }
    if(player){
        h ^= connect6_zobrist_side;
    }
    return h;
}


/*============================================================
 * Count consecutive stones in one direction from (row, col).
 * Starts at (row+dr, col+dc) and walks while stones match.
 *============================================================*/
int State::count_dir(int row, int col, int dr, int dc) const{
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
bool State::check_win_at(int row, int col) const{
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
 *           PATTERN-BASED THREAT EVALUATION
 *
 * Uses a precomputed lookup table for 6-cell sliding windows.
 * Each cell is encoded as: 0=empty, 1=player, 2=opponent/wall.
 * A window of 6 cells encodes to a base-3 integer (3^6 = 729).
 * The table maps each code to a ThreatType.
 *
 * This catches both consecutive and gap/broken patterns:
 *   _XXXX_  = open four      _XXX_  = open three
 *   _XX_XX_ = broken four    _XX_X_ = broken three
 *   _X_XX_  = broken three   _X_XXX = broken four
 *============================================================*/

enum ThreatType {
    THREAT_NONE = 0,
    THREAT_HALF2,       /* 2 in a row, one end open          */
    THREAT_OPEN2,       /* 2 in a row, both ends open        */
    THREAT_HALF3,       /* 3 in a row, one end open          */
    THREAT_BROKEN3,     /* 3 with gap, extensible to open-4  */
    THREAT_OPEN3,       /* 3 in a row, both ends open        */
    THREAT_HALF4,       /* 4 in a row, one end open          */
    THREAT_BROKEN4,     /* 4 with gap, one way to complete   */
    THREAT_OPEN4,       /* 4 in a row, both ends open        */
    THREAT_FIVE         /* 5 in a row (win)                  */
};

/*------------------------------------------------------------
 * Threat counts for one player (expanded with broken types).
 *------------------------------------------------------------*/
struct ThreatCounts {
    int five    = 0;
    int open4   = 0;
    int half4   = 0;   /* includes broken-4 */
    int open3   = 0;   /* includes broken open-3 */
    int half3   = 0;
    int open2   = 0;
    int half2   = 0;
};

/*------------------------------------------------------------
 * 6-cell pattern lookup table.
 * Index: base-3 encoding of 6 cells (0=empty, 1=self, 2=other).
 * Value: ThreatType.
 * Cells outside the board are treated as opponent (2).
 *------------------------------------------------------------*/
static ThreatType pattern6_table[729];   /* 3^6 = 729 */
static bool pattern6_ready = false;

/*------------------------------------------------------------
 * Classify a 6-cell window for the "player" color (encoded as 1).
 *
 * The window is cells[0..5]. We look for arrangements of exactly
 * N player stones (1s) with the right boundary conditions:
 *
 * FIVE:        5+ stones of 1 in the inner 5 cells
 * OPEN FOUR:   pattern like _1111_ (both ends empty)
 * HALF FOUR:   pattern like 21111_ or _11112 (one end blocked)
 * BROKEN FOUR: patterns like _111_1, _11_11, _1_111 etc. (4 stones, 1 gap)
 * OPEN THREE:  _111__ or __111_ etc (3 consecutive, both sides open)
 * BROKEN THREE: _1_11_, _11_1_ (3 stones with gap, both sides have room)
 * HALF THREE:  blocked on one side
 * OPEN TWO:    2 stones, both sides open with room
 * HALF TWO:    2 stones, one side open
 *
 * We enumerate all 729 patterns programmatically.
 *------------------------------------------------------------*/
static void init_pattern6_table(){
    for(int code = 0; code < 729; code++){
        /* Decode the 6 cells */
        int c[6];
        int tmp = code;
        for(int i = 5; i >= 0; i--){
            c[i] = tmp % 3;
            tmp /= 3;
        }

        /* Count player stones (1) and opponent/wall stones (2) */
        int player_count = 0;
        int opp_count = 0;
        for(int i = 0; i < 6; i++){
            if(c[i] == 1) player_count++;
            else if(c[i] == 2) opp_count++;
        }

        ThreatType result = THREAT_NONE;

        /* ---- FIVE: 5+ consecutive player stones in positions 0..5 ---- */
        /* Check if any 5 consecutive cells are all player stones */
        if(player_count >= 5){
            /* positions 0-4 or 1-5 */
            bool five_04 = (c[0]==1 && c[1]==1 && c[2]==1 && c[3]==1 && c[4]==1);
            bool five_15 = (c[1]==1 && c[2]==1 && c[3]==1 && c[4]==1 && c[5]==1);
            if(five_04 || five_15){
                result = THREAT_FIVE;
            }
        }

        if(result == THREAT_NONE && player_count == 4 && opp_count == 0){
            /* 4 player stones, 2 empty: could be open-4 or broken-4 */

            /* Open four: _1111_ */
            if(c[0]==0 && c[1]==1 && c[2]==1 && c[3]==1 && c[4]==1 && c[5]==0){
                result = THREAT_OPEN4;
            }
        }

        if(result == THREAT_NONE && player_count == 4){
            /* Half-open four: 4 consecutive with one end blocked.
             * Patterns (in the 6-cell window):
             *   21111_ (positions 1-4 are player, pos 0 is opp, pos 5 is empty)
             *   _11112 (positions 1-4 are player, pos 0 is empty, pos 5 is opp)
             *   2_1111 (not quite — need 4 consecutive)
             *
             * Actually, we need 4 consecutive player stones with exactly
             * one open end within this 6-cell window. */

            /* Check for 4 consecutive player stones at various positions */
            /* Positions 0-3 */
            if(c[0]==1 && c[1]==1 && c[2]==1 && c[3]==1){
                /* Before pos 0 is outside window (treat as boundary) */
                bool right_open = (c[4] == 0);
                /* This is a half-open four if right side is open
                 * (left boundary is unknown from this window, but since
                 *  we slide from left, the left boundary cell is handled
                 *  by adjacent windows. We classify conservatively.) */
                if(right_open && result < THREAT_HALF4){
                    result = THREAT_HALF4;
                }
            }
            /* Positions 1-4 */
            if(c[1]==1 && c[2]==1 && c[3]==1 && c[4]==1){
                bool left_open = (c[0] == 0);
                bool right_open = (c[5] == 0);
                if(left_open && right_open){
                    /* This is open-4 — already handled above */
                }else if(left_open || right_open){
                    if(result < THREAT_HALF4) result = THREAT_HALF4;
                }
            }
            /* Positions 2-5 */
            if(c[2]==1 && c[3]==1 && c[4]==1 && c[5]==1){
                bool left_open = (c[1] == 0);
                if(left_open && result < THREAT_HALF4){
                    result = THREAT_HALF4;
                }
            }

            /* Broken four: 4 player stones with 1 gap and 1 empty.
             * Patterns within the 6-cell window:
             *   1_111x  111_1x  11_11x
             *   x1_111  x111_1  x11_11
             * where x can be 0 (empty) or 2 (opponent).
             * The gap must be empty (0) and the 4 stones + gap must
             * be within a span of exactly 5 cells. */
            if(result < THREAT_HALF4){
                /* Check all 5-cell sub-windows for broken-four patterns */
                for(int start = 0; start <= 1; start++){
                    int s[5] = {c[start], c[start+1], c[start+2], c[start+3], c[start+4]};
                    int pc = 0, ec = 0;
                    for(int i = 0; i < 5; i++){
                        if(s[i] == 1) pc++;
                        else if(s[i] == 0) ec++;
                    }
                    if(pc == 4 && ec == 1){
                        /* 4 player + 1 empty in 5 cells = broken four.
                         * This is a half-open four equivalent (one way to complete). */
                        if(result < THREAT_HALF4) result = THREAT_HALF4;
                    }
                }
            }
        }

        /* ---- THREE patterns (3 player stones) ---- */
        if(result == THREAT_NONE && player_count == 3){
            /* Open three: 3 consecutive player stones with both sides
             * open and room to extend to 5.
             * Key patterns in 6-cell window:
             *   _0111_0  -> __111_ = open three (positions shifted)
             *   0_111_0  -> _111_  with both boundaries empty
             * More precisely, we look for 3 consecutive with open on both sides. */

            /* Scan for 3 consecutive in positions 0-5 */
            for(int start = 0; start <= 3; start++){
                if(c[start]==1 && c[start+1]==1 && c[start+2]==1){
                    /* Check that the cells before and after are not opponent */
                    bool left_open  = (start > 0) ? (c[start-1] == 0) : false;
                    bool right_open = (start+3 < 6) ? (c[start+3] == 0) : false;

                    /* Need room to extend: for a true open-3, need at least
                     * 2 empty cells on each side within 5-cell reach.
                     * Simplified: both adjacent cells must be empty. */
                    if(left_open && right_open){
                        if(result < THREAT_OPEN3) result = THREAT_OPEN3;
                    }else if(left_open || right_open){
                        if(result < THREAT_HALF3) result = THREAT_HALF3;
                    }
                }
            }

            /* Broken three: 3 player stones with 1 gap in 5-cell span,
             * and open boundaries.
             * Patterns: _1_11_, _11_1_ (and mirrors)
             * The 5-cell span has exactly 3 player + 1 empty + 1 empty = no.
             * Actually: 3 player + 1 gap (empty) + boundaries must be open.
             * In a 5-cell sub-window: 3 player, 2 empty, 0 opponent. */
            if(result < THREAT_OPEN3){
                for(int start = 0; start <= 1; start++){
                    int s[5] = {c[start], c[start+1], c[start+2], c[start+3], c[start+4]};
                    int pc = 0, ec = 0, oc = 0;
                    for(int i = 0; i < 5; i++){
                        if(s[i] == 1) pc++;
                        else if(s[i] == 0) ec++;
                        else oc++;
                    }
                    if(pc == 3 && ec == 2 && oc == 0){
                        /* 3 player + 2 empty in 5 cells, no opponent.
                         * This is a broken-three pattern.
                         * Check if boundaries are open for classification. */
                        bool left_open = (start > 0) ? (c[start-1] == 0) : false;
                        bool right_open = (start+5 < 6) ? (c[start+5] == 0) : false;

                        /* A broken-three is "open" (dangerous) if at least
                         * one boundary is open — because the gap + boundary
                         * give enough room. Classify as BROKEN3 if any side
                         * is open, or HALF3 otherwise.
                         * However, a broken-3 in the interior (start=0, window
                         * boundary) might actually have open boundaries
                         * that we cannot see. Be optimistic: if the pattern
                         * has 3 stones + 2 gaps with no opponent, it's at
                         * least a half-3. If a boundary cell is visible and
                         * open, upgrade to broken-3. */
                        if(left_open || right_open){
                            if(result < THREAT_BROKEN3) result = THREAT_BROKEN3;
                        }else{
                            /* Both boundary cells are either wall/opponent or at
                             * window edge. Still a live pattern if interior gaps
                             * give flexibility. Classify as half-3 minimum. */
                            if(result < THREAT_HALF3) result = THREAT_HALF3;
                        }
                    }
                }
            }
        }

        /* ---- TWO patterns (2 player stones) ---- */
        if(result == THREAT_NONE && player_count == 2 && opp_count == 0){
            /* 2 player stones, rest empty, no opponent in window.
             * Open two if 2 consecutive stones with open boundaries. */
            for(int start = 0; start <= 4; start++){
                if(c[start]==1 && c[start+1]==1){
                    bool left_open  = (start > 0) ? (c[start-1] == 0) : false;
                    bool right_open = (start+2 < 6) ? (c[start+2] == 0) : false;
                    if(left_open && right_open){
                        if(result < THREAT_OPEN2) result = THREAT_OPEN2;
                    }else if(left_open || right_open){
                        if(result < THREAT_HALF2) result = THREAT_HALF2;
                    }
                }
            }
        }

        if(result == THREAT_NONE && player_count == 2){
            /* 2 stones with gap in a window that has no opponent:
             * patterns like _1_1__ or __1_1_ */
            for(int start = 0; start <= 1; start++){
                int s[5] = {c[start], c[start+1], c[start+2], c[start+3], c[start+4]};
                int pc = 0, oc = 0;
                for(int i = 0; i < 5; i++){
                    if(s[i] == 1) pc++;
                    else if(s[i] == 2) oc++;
                }
                if(pc == 2 && oc == 0){
                    if(result < THREAT_HALF2) result = THREAT_HALF2;
                }
            }
        }

        pattern6_table[code] = result;
    }
    pattern6_ready = true;
}


/*------------------------------------------------------------
 * Read a cell, treating out-of-bounds as opponent (2).
 * Remaps: 0=empty, who=1 (self), other=2 (opponent/wall).
 *------------------------------------------------------------*/
static inline int read_cell(const Board& board, int r, int c, int who){
    if(r < 0 || r >= BOARD_H || c < 0 || c >= BOARD_W){
        return 2;   /* wall = opponent */
    }
    int v = board.board[r][c];
    if(v == 0) return 0;
    if(v == who) return 1;
    return 2;
}


/*------------------------------------------------------------
 * Count all threats for one player by scanning 6-cell windows
 * in all 4 directions across the entire board.
 *
 * To avoid double-counting, we scan each line from its start
 * only and use a "seen" flag array per direction. But a simpler
 * and equally correct approach: scan every valid window position,
 * and since the pattern table classifies each window independently,
 * we just accumulate. A given physical threat will be detected
 * by exactly one window (the one that frames it best). To avoid
 * counting the same threat from overlapping windows, we track
 * the best threat found through each cell per direction and only
 * count each run once.
 *
 * Simplified approach: scan all lines, and for each line extract
 * threats with deduplication by tracking runs.
 *------------------------------------------------------------*/
static ThreatCounts count_threats(const Board& board, int who){
    if(!pattern6_ready) init_pattern6_table();

    ThreatCounts t;
    static const int dirs[4][2] = {{0, 1}, {1, 0}, {1, 1}, {1, -1}};

    for(int dir = 0; dir < 4; dir++){
        int dr = dirs[dir][0], dc = dirs[dir][1];

        /* Determine line start positions to cover all lines in this direction.
         * For horizontal (0,1): start at (r, 0) for each row.
         * For vertical (1,0): start at (0, c) for each column.
         * For diag-down-right (1,1): start at (r, 0) and (0, c).
         * For diag-down-left (1,-1): start at (r, BOARD_W-1) and (0, c). */
        struct LineStart { int r, c; };
        LineStart starts[BOARD_H + BOARD_W];
        int nstarts = 0;

        if(dr == 0 && dc == 1){
            /* Horizontal: one line per row */
            for(int r = 0; r < BOARD_H; r++){
                starts[nstarts++] = {r, 0};
            }
        }else if(dr == 1 && dc == 0){
            /* Vertical: one line per column */
            for(int c2 = 0; c2 < BOARD_W; c2++){
                starts[nstarts++] = {0, c2};
            }
        }else if(dr == 1 && dc == 1){
            /* Diagonal down-right */
            for(int r = 0; r < BOARD_H; r++) starts[nstarts++] = {r, 0};
            for(int c2 = 1; c2 < BOARD_W; c2++) starts[nstarts++] = {0, c2};
        }else{
            /* Diagonal down-left (dr=1, dc=-1) */
            for(int r = 0; r < BOARD_H; r++) starts[nstarts++] = {r, BOARD_W - 1};
            for(int c2 = BOARD_W - 2; c2 >= 0; c2--) starts[nstarts++] = {0, c2};
        }

        for(int si = 0; si < nstarts; si++){
            int sr = starts[si].r, sc = starts[si].c;

            /* Compute line length */
            int line_len = 0;
            {
                int rr = sr, cc = sc;
                while(rr >= 0 && rr < BOARD_H && cc >= 0 && cc < BOARD_W){
                    line_len++;
                    rr += dr;
                    cc += dc;
                }
            }

            if(line_len < WIN_LENGTH) continue;   /* too short for any threat */

            /* Slide a 6-cell window along this line.
             * Window positions: i = -1 to line_len - 5 (so window covers
             * cells i..i+5; cells outside the line are wall=2). */
            ThreatType prev_best = THREAT_NONE;
            for(int i = -1; i <= line_len - 5; i++){
                int cells[6];
                for(int k = 0; k < 6; k++){
                    int pos = i + k;
                    int rr = sr + pos * dr;
                    int cc = sc + pos * dc;
                    cells[k] = read_cell(board, rr, cc, who);
                }
                int code = (
                    cells[0]*243 + cells[1]*81 + cells[2]*27
                    + cells[3]*9 + cells[4]*3 + cells[5]
                );
                ThreatType tt = pattern6_table[code];

                /* Deduplicate: only count a threat if it is new
                 * (different from what the previous window found),
                 * OR if the previous window found a lesser threat.
                 * This prevents counting the same 4-in-a-row from
                 * two overlapping windows. Simple rule: if current
                 * threat > previous, count it; if equal to previous
                 * and previous was already counted, skip. */
                if(tt != THREAT_NONE && tt != prev_best){
                    switch(tt){
                        case THREAT_FIVE:    t.five++;  break;
                        case THREAT_OPEN4:   t.open4++; break;
                        case THREAT_HALF4:
                        case THREAT_BROKEN4: t.half4++; break;
                        case THREAT_OPEN3:
                        case THREAT_BROKEN3: t.open3++; break;
                        case THREAT_HALF3:   t.half3++; break;
                        case THREAT_OPEN2:   t.open2++; break;
                        case THREAT_HALF2:   t.half2++; break;
                        default: break;
                    }
                }
                prev_best = tt;
            }
        }
    }
    return t;
}


/*------------------------------------------------------------
 * Count threats passing through a SINGLE cell (r, c) for one
 * player, as if a stone of `who` were placed there.
 * Used for move ordering — much cheaper than full board scan.
 *------------------------------------------------------------*/
static ThreatCounts count_threats_at(
    const Board& board,
    int r, int c,
    int who
){
    if(!pattern6_ready) init_pattern6_table();

    ThreatCounts t;
    static const int dirs[4][2] = {{0, 1}, {1, 0}, {1, 1}, {1, -1}};

    for(int dir = 0; dir < 4; dir++){
        int dr = dirs[dir][0], dcc = dirs[dir][1];

        /* Examine windows that include cell (r, c).
         * The cell is at position k in the window (k = 0..5).
         * Window starts at (r - k*dr, c - k*dc). */
        ThreatType best = THREAT_NONE;
        for(int k = 0; k < 6; k++){
            int sr = r - k * dr;
            int sc = c - k * dcc;

            int cells[6];
            for(int j = 0; j < 6; j++){
                int rr = sr + j * dr;
                int cc = sc + j * dcc;
                cells[j] = read_cell(board, rr, cc, who);
            }
            int code = (
                cells[0]*243 + cells[1]*81 + cells[2]*27
                + cells[3]*9 + cells[4]*3 + cells[5]
            );
            ThreatType tt = pattern6_table[code];
            if(tt > best) best = tt;
        }

        /* Accumulate the best threat found in this direction */
        switch(best){
            case THREAT_FIVE:    t.five++;  break;
            case THREAT_OPEN4:   t.open4++; break;
            case THREAT_HALF4:
            case THREAT_BROKEN4: t.half4++; break;
            case THREAT_OPEN3:
            case THREAT_BROKEN3: t.open3++; break;
            case THREAT_HALF3:   t.half3++; break;
            case THREAT_OPEN2:   t.open2++; break;
            case THREAT_HALF2:   t.half2++; break;
            default: break;
        }
    }
    return t;
}


/*------------------------------------------------------------
 * Weighted score from threat counts.
 * Each level dominates all lower levels combined.
 *------------------------------------------------------------*/
static int threat_score(const ThreatCounts& t){
    return (
        t.half4  * 5000
        + t.open3  * 800
        + t.half3  * 150
        + t.open2  * 100
        + t.half2  * 20
    );
}

/*------------------------------------------------------------
 * Positional bonus: center squares get a small bonus.
 * Stone at the center of the board can participate in more
 * five-cell lines, so center control matters.
 *------------------------------------------------------------*/
static int positional_bonus(const Board& board, int who){
    int bonus = 0;
    int center_r = BOARD_H / 2;
    int center_c = BOARD_W / 2;
    int max_dist = (BOARD_H / 2) + (BOARD_W / 2);
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c] == who){
                int dist = abs(r - center_r) + abs(c - center_c);
                bonus += (max_dist - dist);
            }
        }
    }
    return bonus;
}


/*============================================================
 * Populate legal_actions with empty cells near existing stones
 * (Manhattan distance <= 2).  On an empty board, offer only
 * the centre cell.  Detects terminal states: no moves = DRAW.
 *
 * Enhancements:
 * 1. Forced-block pruning: if opponent has a half-open four,
 *    only return blocking moves + immediate winning moves.
 *    If STM has an immediate win (five or open-4), return
 *    only that winning move.
 * 2. Threat-aware move ordering: sort candidate moves by the
 *    threats they create/block, so alpha-beta prunes more
 *    effectively. Priority: winning > blocking > creating
 *    fours > creating threes > positional (center-first).
 *============================================================*/
void State::get_legal_actions(){
    legal_actions.clear();
    if(game_state == WIN || game_state == DRAW){
        return;
    }

    if(!pattern6_ready) init_pattern6_table();

    int my_id  = player + 1;
    int opp_id = 2 - player;

    /* --- Check if opponent made five (game already over) --- */
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c] == opp_id && check_win_at(r, c)){
                /* Opponent has five. No legal moves — game is over.
                 * evaluate() will return -P_MAX for this position. */
                return;
            }
        }
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
                        if(abs(dr) + abs(dc) > 2){
                            continue;
                        }
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

    /* --- Collect candidate moves with threat-based priorities --- */
    struct ScoredMove {
        Move move;
        int priority;
    };
    std::vector<ScoredMove> candidates;
    candidates.reserve(225);

    /* Track if we find any immediate wins or must-block situations */
    bool stm_has_winning_move = false;
    bool opp_has_half4 = false;

    /* First pass: score every candidate move */
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[r][c] != 0 || !near[r][c]){
                continue;
            }

            int priority = 0;

            /* Check what threats this move creates for STM */
            board.board[r][c] = my_id;
            ThreatCounts my_after = count_threats_at(board, r, c, my_id);
            board.board[r][c] = 0;

            /* Check what threats this move blocks for opponent */
            board.board[r][c] = opp_id;
            ThreatCounts opp_after = count_threats_at(board, r, c, opp_id);
            board.board[r][c] = 0;

            /* Priority hierarchy (higher = searched first):
             * 10000: creates five for STM (instant win)
             *  9000: blocks opponent five
             *  8000: creates open-4 for STM (unstoppable win)
             *  7000: creates half-4 for STM (forces response)
             *  6500: blocks opponent open-4
             *  6000: blocks opponent half-4
             *  5000: creates open-3 for STM
             *  4000: blocks opponent open-3
             *  3000: creates half-3 for STM
             *  1000-2000: positional (center distance)        */
            if(my_after.five > 0){
                priority = 10000;
                stm_has_winning_move = true;
            }else if(opp_after.five > 0){
                priority = 9000;   /* this cell completes opponent's five = must block */
            }else if(my_after.open4 > 0){
                priority = 8000;
                stm_has_winning_move = true;
            }else if(my_after.half4 > 0){
                priority = 7000;
            }else if(opp_after.open4 > 0){
                priority = 6500;
            }else if(opp_after.half4 > 0){
                priority = 6000;
                opp_has_half4 = true;
            }else if(my_after.open3 > 0){
                priority = 5000;
            }else if(opp_after.open3 > 0){
                priority = 4000;
            }else if(my_after.half3 > 0){
                priority = 3000;
            }else{
                /* Positional: center preference as tiebreaker */
                int dist_r = abs(r - BOARD_H / 2);
                int dist_c = abs(c - BOARD_W / 2);
                priority = 1000 - (dist_r + dist_c) * 30;
                if(priority < 0) priority = 0;
            }

            candidates.push_back({Move(Point(r, c), Point(r, c)), priority});
        }
    }

    /* --- Forced-block pruning --- */
    /* If STM has an immediate win, only return winning moves */
    if(stm_has_winning_move){
        for(auto& cm : candidates){
            if(cm.priority >= 8000){   /* five or open-4 */
                legal_actions.push_back(cm.move);
            }
        }
        if(!legal_actions.empty()) return;
    }

    /* If opponent has a half-4 (and STM can't win immediately),
     * only return blocking moves + any move that creates a five.
     * The blocking moves are those with priority >= 6000 (block half-4)
     * or priority >= 9000 (block five). Also include moves that
     * create a five for STM (priority 10000). */
    if(opp_has_half4){
        /* Collect the forced-response subset */
        std::vector<ScoredMove> forced;
        for(auto& cm : candidates){
            if(cm.priority >= 6000){
                forced.push_back(cm);
            }
        }
        /* Sort even the reduced set by priority */
        std::sort(
            forced.begin(), forced.end(),
            [](const ScoredMove& a, const ScoredMove& b){
                return a.priority > b.priority;
            }
        );
        for(auto& fm : forced){
            legal_actions.push_back(fm.move);
        }
        if(!legal_actions.empty()) return;
        /* If no blocking moves found (shouldn't happen), fall through */
    }

    /* --- Normal case: sort all candidates by priority --- */
    std::sort(
        candidates.begin(), candidates.end(),
        [](const ScoredMove& a, const ScoredMove& b){
            return a.priority > b.priority;
        }
    );

    legal_actions.reserve(candidates.size());
    for(auto& cm : candidates){
        legal_actions.push_back(cm.move);
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
    if(!connect6_zobrist_ready){ init_connect6_zobrist(); }

    State* next = new State(this->board, 1 - this->player);
    next->step = this->step + 1;
    int r = move.second.first;
    int c = move.second.second;
    int stone = this->player + 1;
    next->board.board[r][c] = stone;

    /* Incremental hash update */
    uint64_t h = this->hash();
    h ^= connect6_zobrist_side;      /* toggle side to move */
    h ^= connect6_zobrist[stone][r][c];  /* XOR in new stone */
    next->zobrist_hash = h;
    next->zobrist_valid = true;

    return next;
}


/*============================================================
 * Heuristic evaluation for Connect6.
 *
 * Phase 1: Terminal state check (win/draw).
 * Phase 2: Count threats for both sides using pattern table.
 * Phase 3: Detect decisive compound threats.
 * Phase 4: Weighted threat scoring with defensive bias.
 * Phase 5: Positional center bonus.
 *
 * Decisive compound threats (from STM's perspective):
 *   STM has five         -> already won           -> +P_MAX
 *   STM has open-4       -> wins next move         -> +(P_MAX-1)
 *   STM has 2+ half-4    -> can't block both       -> +(P_MAX-2)
 *   STM has half-4+open-3-> block four, three wins  -> +(P_MAX-3)
 *   STM has 2+ open-3    -> double-three fork       -> +(P_MAX-4)
 *   OPP has five         -> lost                   -> -(P_MAX-1)
 *   OPP has open-4       -> loses next move         -> -(P_MAX-10)
 *   OPP has 2+ half-4    -> can't block both        -> -(P_MAX-10)
 *   OPP has half-4+open-3-> loses                   -> -(P_MAX-20)
 *   OPP has 2+ open-3    -> loses                   -> -(P_MAX-20)
 *============================================================*/
int State::evaluate(
    bool /*use_nnue*/,
    bool /*use_kp*/,
    bool /*use_mobility*/,
    const GameHistory* /*history*/
){
    if(game_state == WIN){
        return P_MAX;  /* should not happen for connect6 */
    }
    if(game_state == DRAW){
        return 0;
    }

    int my_id  = player + 1;
    int opp_id = 2 - player;

    /* No legal actions = opponent made five OR board full (draw).
     * get_legal_actions sets game_state=DRAW for full board. */
    if(legal_actions.empty()){
        return (game_state == DRAW) ? 0 : -P_MAX;
    }

    ThreatCounts my  = count_threats(board, my_id);
    ThreatCounts opp = count_threats(board, opp_id);

    /* --- Phase 3: Decisive threats ---
     * Only actual five-in-a-row uses P_MAX (terminal).
     * Near-winning compound threats use large but non-P_MAX scores
     * so the search keeps deepening to verify. */

    /* STM has open-4 or half-4: one move from five → very strong */
    if(my.open4 > 0 || my.half4 >= 1){
        return 50000;
    }
    /* STM has double open-3: opponent can only block one */
    if(my.open3 >= 2){
        return 40000;
    }

    /* OPP has open-4: unstoppable */
    if(opp.open4 > 0){
        return -50000;
    }
    /* OPP has half-4 + open-3 or double half-4: can't block both */
    if(opp.half4 >= 1 && (opp.half4 >= 2 || opp.open3 >= 1)){
        return -40000;
    }
    /* OPP has double open-3: can't block both */
    if(opp.open3 >= 2){
        return -35000;
    }

    /* --- Phase 4: Weighted threat scoring --- */
    /* Opponent threats weighted 1.1x for defensive bias */
    int score = threat_score(my) - (threat_score(opp) * 11 / 10);

    /* Opponent half-4: STM must block → lose tempo */
    if(opp.half4 >= 1){
        score -= 8000;
    }

    /* --- Phase 5: Positional center bonus --- */
    score += positional_bonus(board, my_id) - positional_bonus(board, opp_id);

    return score;
}


/*============================================================
 * Render the board as a human-readable string.
 *============================================================*/
std::string State::encode_output() const{
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
std::string State::encode_board() const{
    std::string s;
    for(int r = 0; r < BOARD_H; r++){
        if(r > 0){
            s += '/';
        }
        for(int c = 0; c < BOARD_W; c++){
            char v = board.board[r][c];
            if(v == 1){
                s += 'X';
            }else if(v == 2){
                s += 'O';
            }else{
                s += '.';
            }
        }
    }
    return s;
}

void State::decode_board(const std::string& s, int side_to_move){
    player = side_to_move;
    game_state = UNKNOWN;
    zobrist_valid = false;
    step = 0;
    board = Board{};
    int r = 0, c = 0;
    for(char ch : s){
        if(ch == '/'){
            r++;
            c = 0;
            continue;
        }
        if(r >= BOARD_H || c >= BOARD_W){
            break;
        }
        if(ch == 'X'){
            board.board[r][c] = 1;
            step++;
        }else if(ch == 'O'){
            board.board[r][c] = 2;
            step++;
        }
        c++;
    }
    get_legal_actions();
}


/* === Repetition: connect6 has no repetition rule === */
bool State::check_repetition(const GameHistory& /*history*/, int& /*out_score*/) const {
    return false;
}
