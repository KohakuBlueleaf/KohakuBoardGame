#include <iostream>
#include <sstream>
#include <cstdint>
#include <cstdlib>

#include "./state.hpp"
#include "config.hpp"
#ifdef USE_NNUE
#include "../../nnue/nnue.hpp"
#endif


/*============================================================
 * NNUE feature extraction (HalfKP)
 *
 * Moved here so the NNUE system does not need to know about
 * Kohaku Chess-specific board layout.
 *============================================================*/

int State::extract_nnue_features(int perspective, int* features) const{
    constexpr int NUM_SQ = BOARD_H * BOARD_W;
    constexpr int KP_FEAT = 2 * NUM_PT_NO_KING * NUM_SQ;
    int count = 0;

    /* Find king square for this perspective */
    int king_sq = 0;
    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            if(board.board[perspective][r][c] == KING_ID){
                king_sq = (perspective == 0)
                    ? (r * BOARD_W + c)
                    : ((BOARD_H - 1 - r) * BOARD_W + c);
            }
        }
    }

    /* HalfKP board features */
    for(int color = 0; color < 2; color++){
        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                int pt = board.board[color][r][c];
                if(pt == 0 || pt == KING_ID){ continue; }
                int feat_color, sq;
                if(perspective == 0){
                    feat_color = color;
                    sq = r * BOARD_W + c;
                }else{
                    feat_color = 1 - color;
                    sq = (BOARD_H - 1 - r) * BOARD_W + c;
                }
                features[count++] = (
                    king_sq * KP_FEAT
                    + feat_color * (NUM_PT_NO_KING * NUM_SQ)
                    + (pt - 1) * NUM_SQ + sq
                );
            }
        }
    }
    return count;
}


/*============================================================
 * KP (King-Piece) Evaluation tables
 *
 * Always compiled. Toggled at runtime via use_kp_eval param.
 *============================================================*/

// KP material (10x scale for fine positional granularity)
// PAWN=10, KNIGHT=30, BISHOP=30, ROOK=50, QUEEN=90, KING=0
static const int kp_material[7] = {0, 20, 100, 60, 60, 180, 1000};

// Material-only (simple scale)
static const int simple_material[7] = {0, 10, 50, 30, 30, 90, 0};

// Piece-Square Tables (white perspective: row 0 = rank 7 = back rank for opponent)
// Board is 7 rows x 6 columns
static const int pst[6][BOARD_H][BOARD_W] = {
    // Pawn (index 0, piece_id 1)
    {{ 0,  0,  0,  0,  0,  0}, {15, 15, 15, 15, 15, 15}, {10, 10, 12, 12, 10, 10},
     { 4,  6,  8,  8,  6,  4}, { 2,  4,  6,  6,  4,  2}, { 0,  2,  2,  2,  2,  0},
     { 0,  0,  0,  0,  0,  0}},
    // Rook (index 1, piece_id 2)
    {{ 2,  2,  2,  2,  2,  2}, { 4,  4,  4,  4,  4,  4}, { 0,  0,  2,  2,  0,  0},
     { 0,  0,  2,  2,  0,  0}, { 0,  0,  2,  2,  0,  0}, { 0,  0,  2,  2,  0,  0},
     { 0,  0,  0,  0,  0,  0}},
    // Knight (index 2, piece_id 3)
    {{-4, -2,  0,  0, -2, -4}, {-2,  2,  4,  4,  2, -2}, { 0,  4,  6,  6,  4,  0},
     { 0,  4,  8,  8,  4,  0}, { 0,  4,  6,  6,  4,  0}, {-2,  2,  4,  4,  2, -2},
     {-4, -2,  0,  0, -2, -4}},
    // Bishop (index 3, piece_id 4)
    {{-2,  0,  0,  0,  0, -2}, { 0,  3,  4,  4,  3,  0}, { 0,  4,  5,  5,  4,  0},
     { 0,  4,  5,  5,  4,  0}, { 0,  4,  5,  5,  4,  0}, { 0,  3,  4,  4,  3,  0},
     {-2,  0,  0,  0,  0, -2}},
    // Queen (index 4, piece_id 5)
    {{-2,  0,  2,  2,  0, -2}, { 0,  2,  4,  4,  2,  0}, { 0,  4,  6,  6,  4,  0},
     { 0,  4,  6,  6,  4,  0}, { 0,  4,  6,  6,  4,  0}, { 0,  2,  4,  4,  2,  0},
     {-2,  0,  2,  2,  0, -2}},
    // King (index 5, piece_id 6)
    {{-8, -8, -8, -8, -8, -8}, {-4, -4, -4, -4, -4, -4}, {-4, -4, -4, -4, -4, -4},
     {-4, -4, -4, -4, -4, -4}, {-4, -4, -4, -4, -4, -4}, { 4,  4,  0,  0,  4,  4},
     { 6,  6,  2,  2,  6,  6}},
};

/* 8 directions: 0-3 orthogonal, 4-7 diagonal */
static const int dir8_dr[8] = { -1,  1,  0,  0, -1, -1,  1,  1 };
static const int dir8_dc[8] = {  0,  0, -1,  1, -1,  1, -1,  1 };

// King tropism weights per piece type
static const int tropism_w[7] = {0, 0, 3, 3, 2, 5, 0};

static int king_tropism(int piece_type, int pr, int pc, int ekr, int ekc){
    int dist = std::max(std::abs(pr - ekr), std::abs(pc - ekc));
    if(dist <= 2){
        return tropism_w[piece_type] * (3 - dist);
    }
    return 0;
}


/*============================================================
 * evaluate() -- runtime-selectable eval strategy
 *============================================================*/
int State::evaluate(bool use_nnue, bool use_kp_eval, bool use_mobility){
    if(this->game_state == WIN){
        score = P_MAX;
        return score;
    }

    /* === NNUE evaluation === */
    #ifdef USE_NNUE
    if(use_nnue && nnue::g_model.loaded()){
        return nnue::g_model.evaluate(*this, this->player);
    }
    #endif
    (void)use_nnue;

    auto self_board = this->board.board[this->player];
    auto oppn_board = this->board.board[1 - this->player];
    int self_score = 0, oppn_score = 0;

    if(use_kp_eval){
        /* === KP eval: material + PST + tropism === */
        int self_kr = -1, self_kc = -1;
        int oppn_kr = -1, oppn_kc = -1;
        for(int i = 0; i < BOARD_H; i++){
            for(int j = 0; j < BOARD_W; j++){
                if(self_board[i][j] == 6){
                    self_kr = i; self_kc = j;
                }
                if(oppn_board[i][j] == 6){
                    oppn_kr = i; oppn_kc = j;
                }
            }
        }
        for(int i = 0; i < BOARD_H; i++){
            for(int j = 0; j < BOARD_W; j++){
                int piece;
                if((piece = self_board[i][j])){
                    self_score += kp_material[piece];
                    int r = (this->player == 0) ? i : (BOARD_H - 1 - i);
                    self_score += pst[piece - 1][r][j];
                    if(oppn_kr >= 0){
                        self_score += king_tropism(piece, i, j, oppn_kr, oppn_kc);
                    }
                }
                if((piece = oppn_board[i][j])){
                    oppn_score += kp_material[piece];
                    int r = (this->player == 0) ? (BOARD_H - 1 - i) : i;
                    oppn_score += pst[piece - 1][r][j];
                    if(self_kr >= 0){
                        oppn_score += king_tropism(piece, i, j, self_kr, self_kc);
                    }
                }
            }
        }
    }else{
        /* === Simple material-only eval === */
        for(int i = 0; i < BOARD_H; i++){
            for(int j = 0; j < BOARD_W; j++){
                int8_t piece;
                if((piece = self_board[i][j])){
                    self_score += simple_material[piece];
                }
                if((piece = oppn_board[i][j])){
                    oppn_score += simple_material[piece];
                }
            }
        }
    }

    int bonus = 0;
    int material_diff = self_score - oppn_score;

    /* === Endgame adjustments === */
    if(use_kp_eval){
        int total_material = self_score + oppn_score - 2000; /* subtract kings */
        bool is_endgame = (total_material < 500); /* few pieces left */
        int self_kr = -1, self_kc = -1, oppn_kr = -1, oppn_kc = -1;

        /* Re-find kings (already found above but scope is limited) */
        for(int i = 0; i < BOARD_H; i++){
            for(int j = 0; j < BOARD_W; j++){
                if(self_board[i][j] == KING){ self_kr = i; self_kc = j; }
                if(oppn_board[i][j] == KING){ oppn_kr = i; oppn_kc = j; }
            }
        }

        if(is_endgame && material_diff > 50 && oppn_kr >= 0 && self_kr >= 0){
            /* === Winning side endgame bonuses === */

            /* 1. Drive enemy king to edge/corner.
             * Center distance: king at center = 0, king at edge = high */
            int oppn_center_dist_r = std::abs(oppn_kr - BOARD_H / 2);
            int oppn_center_dist_c = std::abs(oppn_kc - BOARD_W / 2);
            int oppn_edge_bonus = (oppn_center_dist_r + oppn_center_dist_c) * 8;
            bonus += oppn_edge_bonus;

            /* 2. Bring own king closer to enemy king (help coordinate mate) */
            int king_dist = std::max(std::abs(self_kr - oppn_kr),
                                     std::abs(self_kc - oppn_kc));
            bonus += (7 - king_dist) * 6;  /* closer = higher bonus */

            /* 3. Reduce enemy king mobility (fewer escape squares = closer to mate) */
            int oppn_king_moves = 0;
            for(int d = 0; d < 8; d++){
                int nr = oppn_kr + dir8_dr[d];
                int nc = oppn_kc + dir8_dc[d];
                if(nr >= 0 && nr < BOARD_H && nc >= 0 && nc < BOARD_W
                   && !oppn_board[nr][nc]){
                    oppn_king_moves++;
                }
            }
            bonus += (8 - oppn_king_moves) * 5;
        }

        /* 4. Passed pawn bonus (pawn with no enemy pawn ahead on same/adjacent files) */
        for(int j = 0; j < BOARD_W; j++){
            for(int i = 0; i < BOARD_H; i++){
                if(self_board[i][j] == 1){  /* own pawn */
                    bool passed = true;
                    int dir = (this->player == 0) ? -1 : 1;
                    int start_r = i + dir;
                    /* Check ahead on same + adjacent files */
                    while(start_r >= 0 && start_r < BOARD_H){
                        for(int dc = -1; dc <= 1; dc++){
                            int cc = j + dc;
                            if(cc >= 0 && cc < BOARD_W && oppn_board[start_r][cc] == 1){
                                passed = false;
                            }
                        }
                        start_r += dir;
                    }
                    if(passed){
                        /* Bonus grows exponentially as pawn advances */
                        int rank_from_promo = (this->player == 0) ? i : (BOARD_H - 1 - i);
                        int advance_bonus = (BOARD_H - 1 - rank_from_promo);
                        bonus += advance_bonus * advance_bonus * 3;
                    }
                }
            }
        }
    }

    /* === Mobility bonus === */
    if(use_mobility){
        int self_mobility = (int)this->legal_actions.size();
        State oppn_state(this->board, 1 - this->player);
        oppn_state.get_legal_actions();
        int oppn_mobility = (int)oppn_state.legal_actions.size();
        bonus += 2 * (self_mobility - oppn_mobility);
    }

    /* === Anti-repetition contempt === */
    /* When winning, penalize positions we've seen before to force progress */
    if(material_diff > 30){
        uint64_t h = this->hash();
        auto it = hash_counts.find(h);
        if(it != hash_counts.end() && it->second > 0){
            bonus -= material_diff / 3;  /* lose 33% of advantage for repeating */
        }
    }

    return material_diff + bonus;
}



/**
 * @brief return next state after the move
 *
 * @param move
 * @return State*
 */
State* State::next_state(const Move& move){
    Board next = this->board;
    Point from = move.first, to = move.second;

    int8_t moved = next.board[this->player][from.first][from.second];

    /* Decode chess promotion encoding:
     *   to.first = actual_row + BOARD_H * promo_idx
     *   promo_idx: 0=none, 1=Queen, 2=Rook, 3=Bishop, 4=Knight */
    size_t actual_to_row = to.first;
    if(to.first >= static_cast<size_t>(BOARD_H)){
        int promo_idx = static_cast<int>(to.first / BOARD_H);
        actual_to_row = to.first % BOARD_H;
        static const int promo_piece[5] = {0, QUEEN, ROOK, BISHOP, KNIGHT};
        if(promo_idx >= 1 && promo_idx <= 4){
            moved = promo_piece[promo_idx];
        }
    }

    if(next.board[1 - this->player][actual_to_row][to.second]){
        next.board[1 - this->player][actual_to_row][to.second] = 0;
    }

    next.board[this->player][from.first][from.second] = 0;
    next.board[this->player][actual_to_row][to.second] = moved;

    State* ns = new State(next, 1 - this->player);
    ns->inherit_history(this);

    if(this->game_state != WIN){
        ns->get_legal_actions();
    }
    return ns;
}


static const int move_table_rook_bishop[8][7][2] = {
  {{0, 1}, {0, 2}, {0, 3}, {0, 4}, {0, 5}, {0, 6}, {0, 7}},
  {{0, -1}, {0, -2}, {0, -3}, {0, -4}, {0, -5}, {0, -6}, {0, -7}},
  {{1, 0}, {2, 0}, {3, 0}, {4, 0}, {5, 0}, {6, 0}, {7, 0}},
  {{-1, 0}, {-2, 0}, {-3, 0}, {-4, 0}, {-5, 0}, {-6, 0}, {-7, 0}},
  {{1, 1}, {2, 2}, {3, 3}, {4, 4}, {5, 5}, {6, 6}, {7, 7}},
  {{1, -1}, {2, -2}, {3, -3}, {4, -4}, {5, -5}, {6, -6}, {7, -7}},
  {{-1, 1}, {-2, 2}, {-3, 3}, {-4, 4}, {-5, 5}, {-6, 6}, {-7, 7}},
  {{-1, -1}, {-2, -2}, {-3, -3}, {-4, -4}, {-5, -5}, {-6, -6}, {-7, -7}},
};
static const int move_table_knight[8][2] = {
  {1, 2}, {1, -2},
  {-1, 2}, {-1, -2},
  {2, 1}, {2, -1},
  {-2, 1}, {-2, -1},
};
static const int move_table_king[8][2] = {
  {1, 0}, {0, 1}, {-1, 0}, {0, -1},
  {1, 1}, {1, -1}, {-1, 1}, {-1, -1},
};


/*============================================================
 * Naive move generation (array-based, branch-heavy)
 *============================================================*/
void State::get_legal_actions_naive(){
    this->game_state = NONE;
    std::vector<Move> all_actions;
    auto self_board = this->board.board[this->player];
    auto oppn_board = this->board.board[1 - this->player];

    int now_piece, oppn_piece;
    for(int i = 0; i < BOARD_H; i++){
        for(int j = 0; j < BOARD_W; j++){
            if((now_piece = self_board[i][j])){
                switch(now_piece){
                    case 1: { // pawn
                        /* Helper lambda: add pawn move, generating 4 promotion
                         * variants (Q/R/B/N) when reaching the last rank. */
                        auto add_pawn_move = [&](int fr, int fc, int tr, int tc){
                            bool promotes = (this->player == 0 && tr == 0)
                                         || (this->player == 1 && tr == BOARD_H - 1);
                            if(promotes){
                                for(int pidx = 1; pidx <= 4; pidx++){
                                    all_actions.push_back(
                                        Move(Point(fr, fc),
                                             Point(tr + BOARD_H * pidx, tc)));
                                }
                            }else{
                                all_actions.push_back(
                                    Move(Point(fr, fc), Point(tr, tc)));
                            }
                        };
                        if(this->player && i < BOARD_H - 1){
                            // black: advance down (+row)
                            if(!oppn_board[i+1][j] && !self_board[i+1][j]){
                                add_pawn_move(i, j, i+1, j);
                            }
                            if(j < BOARD_W - 1 && (oppn_piece = oppn_board[i+1][j+1]) > 0){
                                if(oppn_piece == 6){
                                    this->game_state = WIN;
                                    all_actions.push_back(Move(Point(i, j), Point(i+1, j+1)));
                                    this->legal_actions = all_actions;
                                    return;
                                }
                                add_pawn_move(i, j, i+1, j+1);
                            }
                            if(j > 0 && (oppn_piece = oppn_board[i+1][j-1]) > 0){
                                if(oppn_piece == 6){
                                    this->game_state = WIN;
                                    all_actions.push_back(Move(Point(i, j), Point(i+1, j-1)));
                                    this->legal_actions = all_actions;
                                    return;
                                }
                                add_pawn_move(i, j, i+1, j-1);
                            }
                        }else if(!this->player && i > 0){
                            // white: advance up (-row)
                            if(!oppn_board[i-1][j] && !self_board[i-1][j]){
                                add_pawn_move(i, j, i-1, j);
                            }
                            if(j < BOARD_W - 1 && (oppn_piece = oppn_board[i-1][j+1]) > 0){
                                if(oppn_piece == 6){
                                    this->game_state = WIN;
                                    all_actions.push_back(Move(Point(i, j), Point(i-1, j+1)));
                                    this->legal_actions = all_actions;
                                    return;
                                }
                                add_pawn_move(i, j, i-1, j+1);
                            }
                            if(j > 0 && (oppn_piece = oppn_board[i-1][j-1]) > 0){
                                if(oppn_piece == 6){
                                    this->game_state = WIN;
                                    all_actions.push_back(Move(Point(i, j), Point(i-1, j-1)));
                                    this->legal_actions = all_actions;
                                    return;
                                }
                                add_pawn_move(i, j, i-1, j-1);
                            }
                        }
                        break;
                    }

                    case 2: // rook
                    case 4: // bishop
                    case 5: // queen
                        int st, end;
                        switch(now_piece){
                            case 2: st=0; end=4; break;  // rook: orthogonal
                            case 4: st=4; end=8; break;  // bishop: diagonal
                            case 5: st=0; end=8; break;  // queen: both
                            default: st=0; end=-1;
                        }
                        for(int part = st; part < end; part++){
                            auto move_list = move_table_rook_bishop[part];
                            for(int k = 0; k < std::max(BOARD_H, BOARD_W); k++){
                                int p[2] = {move_list[k][0] + i, move_list[k][1] + j};

                                if(p[0] >= BOARD_H || p[0] < 0 || p[1] >= BOARD_W || p[1] < 0){
                                    break;
                                }
                                now_piece = self_board[p[0]][p[1]];
                                if(now_piece){
                                    break;
                                }

                                all_actions.push_back(Move(Point(i, j), Point(p[0], p[1])));

                                oppn_piece = oppn_board[p[0]][p[1]];
                                if(oppn_piece){
                                    if(oppn_piece == 6){
                                        this->game_state = WIN;
                                        this->legal_actions = all_actions;
                                        return;
                                    }else{
                                        break;
                                    }
                                };
                            }
                        }
                        break;

                    case 3: // knight
                        for(auto move: move_table_knight){
                            int x = move[0] + i;
                            int y = move[1] + j;

                            if(x >= BOARD_H || x < 0 || y >= BOARD_W || y < 0){
                                continue;
                            }
                            now_piece = self_board[x][y];
                            if(now_piece){
                                continue;
                            }
                            all_actions.push_back(Move(Point(i, j), Point(x, y)));

                            oppn_piece = oppn_board[x][y];
                            if(oppn_piece == 6){
                                this->game_state = WIN;
                                this->legal_actions = all_actions;
                                return;
                            }
                        }
                        break;

                    case 6: // king
                        for(auto move: move_table_king){
                            int p[2] = {move[0] + i, move[1] + j};

                            if(p[0] >= BOARD_H || p[0] < 0 || p[1] >= BOARD_W || p[1] < 0){
                                continue;
                            }
                            now_piece = self_board[p[0]][p[1]];
                            if(now_piece){
                                continue;
                            }

                            all_actions.push_back(Move(Point(i, j), Point(p[0], p[1])));

                            oppn_piece = oppn_board[p[0]][p[1]];
                            if(oppn_piece == 6){
                                this->game_state = WIN;
                                this->legal_actions = all_actions;
                                return;
                            }
                        }
                        break;
                }
            }
        }
    }
    this->legal_actions = all_actions;
}


/*============================================================
 * Bitboard move generation
 *
 * 7x6 = 42 squares fit in a uint64_t.
 * Square (r,c) -> bit index r*6+c.
 * Precomputed attack masks for leapers (knight, king, pawn).
 * Bit-scan loop (__builtin_ctzll) replaces nested array iteration.
 *============================================================*/
#define BB_SQ(r, c)  ((r) * BOARD_W + (c))
#define BB_ROW(sq)   ((sq) / BOARD_W)
#define BB_COL(sq)   ((sq) % BOARD_W)

static constexpr int NUM_SQ = BOARD_H * BOARD_W;  // 42

// Precomputed attack tables (initialized once)
static uint64_t bb_knight[NUM_SQ];       // knight attack mask per square
static uint64_t bb_king[NUM_SQ];         // king attack mask per square
static uint64_t bb_pawn_push[2][NUM_SQ]; // pawn push target per player/square
static uint64_t bb_pawn_cap[2][NUM_SQ];  // pawn capture targets per player/square
static bool bb_ready = false;

// Sliding piece direction vectors (0-3: rook, 4-7: bishop, 0-7: queen)
static const int bb_dr[8] = {0, 0, 1, -1, 1, 1, -1, -1};
static const int bb_dc[8] = {1, -1, 0, 0, 1, -1, 1, -1};

static void bb_init(){
    static const int kn_dr[8] = {1, 1, -1, -1, 2, 2, -2, -2};
    static const int kn_dc[8] = {2, -2, 2, -2, 1, -1, 1, -1};
    static const int ki_dr[8] = {1, 0, -1, 0, 1, 1, -1, -1};
    static const int ki_dc[8] = {0, 1, 0, -1, 1, -1, 1, -1};

    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            int sq = BB_SQ(r, c);

            // Knight
            bb_knight[sq] = 0;
            for(int d = 0; d < 8; d++){
                int nr = r + kn_dr[d], nc = c + kn_dc[d];
                if(nr >= 0 && nr < BOARD_H && nc >= 0 && nc < BOARD_W){
                    bb_knight[sq] |= 1ULL << BB_SQ(nr, nc);
                }
            }

            // King
            bb_king[sq] = 0;
            for(int d = 0; d < 8; d++){
                int nr = r + ki_dr[d], nc = c + ki_dc[d];
                if(nr >= 0 && nr < BOARD_H && nc >= 0 && nc < BOARD_W){
                    bb_king[sq] |= 1ULL << BB_SQ(nr, nc);
                }
            }

            // Pawn (player 0 = white, advances up = row-1)
            bb_pawn_push[0][sq] = 0;
            bb_pawn_cap[0][sq] = 0;
            if(r > 0){
                bb_pawn_push[0][sq] = 1ULL << BB_SQ(r-1, c);
                if(c > 0){
                    bb_pawn_cap[0][sq] |= 1ULL << BB_SQ(r-1, c-1);
                }
                if(c < BOARD_W-1){
                    bb_pawn_cap[0][sq] |= 1ULL << BB_SQ(r-1, c+1);
                }
            }

            // Pawn (player 1 = black, advances down = row+1)
            bb_pawn_push[1][sq] = 0;
            bb_pawn_cap[1][sq] = 0;
            if(r < BOARD_H-1){
                bb_pawn_push[1][sq] = 1ULL << BB_SQ(r+1, c);
                if(c > 0){
                    bb_pawn_cap[1][sq] |= 1ULL << BB_SQ(r+1, c-1);
                }
                if(c < BOARD_W-1){
                    bb_pawn_cap[1][sq] |= 1ULL << BB_SQ(r+1, c+1);
                }
            }
        }
    }
    bb_ready = true;
}

void State::get_legal_actions_bitboard(){
    if(!bb_ready){
        bb_init();
    }

    this->game_state = NONE;
    this->legal_actions.clear();
    this->legal_actions.reserve(128);

    int self = this->player;
    int oppn = 1 - self;

    // Build occupancy bitmasks and piece-type lookup
    uint64_t self_occ = 0, oppn_occ = 0;
    int self_pt[NUM_SQ] = {};
    int oppn_pt[NUM_SQ] = {};

    for(int r = 0; r < BOARD_H; r++){
        for(int c = 0; c < BOARD_W; c++){
            int sq = BB_SQ(r, c);
            if(this->board.board[self][r][c]){
                self_occ |= 1ULL << sq;
                self_pt[sq] = this->board.board[self][r][c];
            }
            if(this->board.board[oppn][r][c]){
                oppn_occ |= 1ULL << sq;
                oppn_pt[sq] = this->board.board[oppn][r][c];
            }
        }
    }

    uint64_t all_occ = self_occ | oppn_occ;

    // Iterate own pieces via bit scan
    uint64_t pieces = self_occ;
    while(pieces){
        int sq = __builtin_ctzll(pieces);
        pieces &= pieces - 1;
        int r = BB_ROW(sq), c = BB_COL(sq);
        int piece = self_pt[sq];
        uint64_t targets = 0;

        switch(piece){
            case 1: { // Pawn
                uint64_t push = bb_pawn_push[self][sq] & ~all_occ;
                uint64_t cap = bb_pawn_cap[self][sq] & oppn_occ;
                // Check for king capture in captures
                uint64_t cap_scan = cap;
                while(cap_scan){
                    int to = __builtin_ctzll(cap_scan);
                    cap_scan &= cap_scan - 1;
                    if(oppn_pt[to] == 6){
                        this->game_state = WIN;
                        this->legal_actions.push_back(
                            Move(Point(r, c), Point(BB_ROW(to), BB_COL(to))));
                        return;
                    }
                }
                /* Pawn moves need special handling for promotion:
                 * generate 4 separate moves (Q/R/B/N) when reaching last rank. */
                uint64_t pawn_targets = push | cap;
                while(pawn_targets){
                    int to = __builtin_ctzll(pawn_targets);
                    pawn_targets &= pawn_targets - 1;
                    int to_r = BB_ROW(to), to_c = BB_COL(to);
                    bool promotes = (self == 0 && to_r == 0)
                                 || (self == 1 && to_r == BOARD_H - 1);
                    if(promotes){
                        for(int pidx = 1; pidx <= 4; pidx++){
                            this->legal_actions.push_back(
                                Move(Point(r, c),
                                     Point(to_r + BOARD_H * pidx, to_c)));
                        }
                    }else{
                        this->legal_actions.push_back(
                            Move(Point(r, c), Point(to_r, to_c)));
                    }
                }
                /* targets stays 0 — pawn moves already added above */
                break;
            }

            case 3: { // Knight
                targets = bb_knight[sq] & ~self_occ;
                uint64_t opp_targets = targets & oppn_occ;
                while(opp_targets){
                    int to = __builtin_ctzll(opp_targets);
                    opp_targets &= opp_targets - 1;
                    if(oppn_pt[to] == 6){
                        this->game_state = WIN;
                        this->legal_actions.push_back(
                            Move(Point(r, c), Point(BB_ROW(to), BB_COL(to))));
                        return;
                    }
                }
                break;
            }

            case 6: { // King
                targets = bb_king[sq] & ~self_occ;
                uint64_t opp_targets = targets & oppn_occ;
                while(opp_targets){
                    int to = __builtin_ctzll(opp_targets);
                    opp_targets &= opp_targets - 1;
                    if(oppn_pt[to] == 6){
                        this->game_state = WIN;
                        this->legal_actions.push_back(
                            Move(Point(r, c), Point(BB_ROW(to), BB_COL(to))));
                        return;
                    }
                }
                break;
            }

            case 2: // Rook
            case 4: // Bishop
            case 5: { // Queen
                int d_start = (piece == 4) ? 4 : 0;
                int d_end   = (piece == 2) ? 4 : 8;
                for(int d = d_start; d < d_end; d++){
                    int cr = r + bb_dr[d], cc = c + bb_dc[d];
                    while(cr >= 0 && cr < BOARD_H && cc >= 0 && cc < BOARD_W){
                        int to = BB_SQ(cr, cc);
                        uint64_t to_bit = 1ULL << to;
                        if(self_occ & to_bit){
                            break; // own piece blocks
                        }

                        if((oppn_occ & to_bit) && oppn_pt[to] == 6){
                            this->game_state = WIN;
                            this->legal_actions.push_back(
                                Move(Point(r, c), Point(cr, cc)));
                            return;
                        }

                        targets |= to_bit;
                        if(oppn_occ & to_bit){
                            break; // captured, stop sliding
                        }
                        cr += bb_dr[d]; cc += bb_dc[d];
                    }
                }
                break;
            }
        }

        // Convert target bitmask to Move objects
        while(targets){
            int to = __builtin_ctzll(targets);
            targets &= targets - 1;
            this->legal_actions.push_back(
                Move(Point(r, c), Point(BB_ROW(to), BB_COL(to))));
        }
    }
}


/*============================================================
 * Dispatcher
 *============================================================*/
void State::get_legal_actions(){
    /* 4-fold repetition -> draw */
    if(check_repetition()){
        game_state = DRAW;
        legal_actions.clear();
        return;
    }
    #ifdef USE_BITBOARD
    get_legal_actions_bitboard();
    #else
    get_legal_actions_naive();
    #endif

    /* Stalemate: no legal moves and not already a king-capture (WIN).
     * In our king-capture model, if the opponent could capture our king,
     * game_state would already be WIN from the previous ply's movegen.
     * So empty legal_actions + no WIN = stalemate = DRAW (chess rule). */
    if(legal_actions.empty() && game_state != WIN){
        game_state = DRAW;
    }
}


const char kc_piece_table[2][7][5] = {
  {" ", "\xe2\x99\x99", "\xe2\x99\x96", "\xe2\x99\x98", "\xe2\x99\x97", "\xe2\x99\x95", "\xe2\x99\x94"},
  {" ", "\xe2\x99\x9f", "\xe2\x99\x9c", "\xe2\x99\x9e", "\xe2\x99\x9d", "\xe2\x99\x9b", "\xe2\x99\x9a"}
};
/**
 * @brief encode the output for command line output
 *
 * @return std::string
 */
std::string State::encode_output() const{
    std::stringstream ss;
    int now_piece;
    for(int i = 0; i < BOARD_H; i++){
        for(int j = 0; j < BOARD_W; j++){
            if((now_piece = this->board.board[0][i][j])){
                ss << std::string(kc_piece_table[0][now_piece]);
            }else if((now_piece = this->board.board[1][i][j])){
                ss << std::string(kc_piece_table[1][now_piece]);
            }else{
                ss << " ";
            }
            ss << " ";
        }
        ss << "\n";
    }
    return ss.str();
}


/**
 * @brief encode the state to the format for player
 *
 * @return std::string
 */
std::string State::encode_state(){
    std::stringstream ss;
    ss << this->player;
    ss << "\n";
    for(int pl = 0; pl < 2; pl++){
        for(int i = 0; i < BOARD_H; i++){
            for(int j = 0; j < BOARD_W; j++){
                ss << int(this->board.board[pl][i][j]);
                ss << " ";
            }
            ss << "\n";
        }
        ss << "\n";
    }
    return ss.str();
}


BaseState* State::create_null_state() const{
    State* s = new State(this->board, 1 - this->player);
    s->get_legal_actions();
    return s;
}


/* === Board serialization === */
static const char* piece_chars = ".PRNBQK";
static const char* piece_chars_lower = ".prnbqk";

std::string State::encode_board() const{
    std::string s;
    for(int r = 0; r < BOARD_H; r++){
        if(r > 0){
            s += '/';
        }
        for(int c = 0; c < BOARD_W; c++){
            int w = board.board[0][r][c];
            int b = board.board[1][r][c];
            if(w > 0 && w <= 6){
                s += piece_chars[w];
            }else if(b > 0 && b <= 6){
                s += piece_chars_lower[b];
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
    board = Board{};
    // Clear default position
    for(int p = 0; p < 2; p++){
        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                board.board[p][r][c] = 0;
            }
        }
    }
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
        if(ch >= 'A' && ch <= 'Z'){
            for(int p = 1; p <= 6; p++){
                if(piece_chars[p] == ch){
                    board.board[0][r][c] = p;
                    break;
                }
            }
        }else if(ch >= 'a' && ch <= 'z'){
            for(int p = 1; p <= 6; p++){
                if(piece_chars_lower[p] == ch){
                    board.board[1][r][c] = p;
                    break;
                }
            }
        }
        c++;
    }
    get_legal_actions();
}


/*============================================================
 * Zobrist hash for transposition table
 *============================================================*/
static uint64_t zobrist_piece[2][7][BOARD_H][BOARD_W];
static uint64_t zobrist_side;
static bool zobrist_ready = false;

static void init_zobrist(){
    // Use a different seed than minichess to avoid hash collisions
    uint64_t s = 0x4B8E2F17D6A3C950ULL;
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

uint64_t State::hash() const{
    if(!zobrist_ready){
        init_zobrist();
    }
    uint64_t h = 0;
    for(int p = 0; p < 2; p++){
        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                int piece = this->board.board[p][r][c];
                if(piece){
                    h ^= zobrist_piece[p][piece][r][c];
                }
            }
        }
    }
    if(this->player){
        h ^= zobrist_side;
    }
    return h;
}


/*============================================================
 * Cell display for protocol (d command)
 *============================================================*/
std::string State::cell_display(int row, int col) const{
    int w = static_cast<int>(board.board[0][row][col]);
    int b = static_cast<int>(board.board[1][row][col]);
    if(w){
        const char* names = ".PRNBQK";
        return std::string(" ") + names[w] + " ";
    }else if(b){
        const char* names = ".prnbqk";
        return std::string(" ") + names[b] + " ";
    }else{
        return " . ";
    }
}
