#include <iostream>
#include <sstream>
#include <cstdint>
#include <cstdlib>

#include "./state.hpp"
#include "../config.hpp"
#ifdef USE_NNUE
#include "../nnue/nnue.hpp"
#endif


#ifdef USE_KP_EVAL
/*
 * KP (King-Piece) Evaluation
 *
 * The idea: a piece's value depends not just on its type, but on WHERE it is
 * and WHERE THE KINGS are. A knight in the center is worth more than one on
 * the edge. A rook near the enemy king is threatening.
 *
 * Components:
 *   1. Material (scaled 10x for finer positional granularity)
 *   2. Piece-Square Tables (PST): positional bonus per piece per square
 *   3. King Tropism: bonus for attacking pieces near the enemy king
 *
 * This is a simplified form of the KP tables used in engines like Bonanza,
 * Apery, and pre-NNUE Stockfish. Full KP would store a separate PST for
 * each king square (30 x 5 x 30 = 4500 entries), but the decomposed form
 * (PST + tropism) captures most of the value with far fewer parameters.
 */

// Material values (10x scale to allow fine-grained positional scoring)
//                     empty pawn rook knight bishop queen  king
static const int kp_material[7] = {0, 20, 60, 70, 80, 200, 1000};

// Piece-Square Tables from white (player 0) perspective
// White's back rank = row 5, advances toward row 0
// For black: mirror vertically (row -> BOARD_H-1-row)
// Index: pst[piece_type - 1][row][col]
static const int pst[6][BOARD_H][BOARD_W] = {
  // Pawn (type 1)
  {
    { 0,  0,  0,  0,  0},  // row 0: promotion rank (becomes queen)
    {15, 15, 15, 15, 15},  // row 1: one step from promotion
    { 4,  6, 10,  6,  4},  // row 2: strong advance, center bonus
    { 2,  4,  6,  4,  2},  // row 3: moderate advance
    { 0,  2,  2,  2,  0},  // row 4: starting rank
    { 0,  0,  0,  0,  0},  // row 5: impossible for pawns
  },
  // Rook (type 2)
  {
    { 2,  2,  2,  2,  2},  // deep penetration
    { 4,  4,  4,  4,  4},  // 7th rank (strong in chess)
    { 0,  0,  2,  0,  0},  // center file
    { 0,  0,  2,  0,  0},
    { 0,  0,  2,  0,  0},
    { 0,  0,  0,  0,  0},
  },
  // Knight (type 3) - loves the center, hates edges
  {
    {-4, -2,  0, -2, -4},
    {-2,  2,  4,  2, -2},
    { 0,  4,  6,  4,  0},
    { 0,  4,  6,  4,  0},
    {-2,  2,  4,  2, -2},
    {-4, -2,  0, -2, -4},
  },
  // Bishop (type 4) - likes diagonals and center
  {
    {-2,  0,  0,  0, -2},
    { 0,  3,  4,  3,  0},
    { 0,  4,  4,  4,  0},
    { 0,  4,  4,  4,  0},
    { 0,  3,  4,  3,  0},
    {-2,  0,  0,  0, -2},
  },
  // Queen (type 5) - center control, active squares
  {
    {-2,  0,  2,  0, -2},
    { 0,  2,  4,  2,  0},
    { 0,  4,  6,  4,  0},
    { 0,  4,  6,  4,  0},
    { 0,  2,  4,  2,  0},
    {-2,  0,  2,  0, -2},
  },
  // King (type 6) - prefers back rank safety
  {
    {-8, -8, -8, -8, -8},
    {-4, -4, -4, -4, -4},
    {-4, -4, -4, -4, -4},
    {-4, -4, -4, -4, -4},
    { 4,  4,  0,  4,  4},
    { 6,  6,  2,  6,  6},
  },
};

// King tropism: attacking pieces near enemy king get bonus
//                         empty pawn rook knight bishop queen king
static const int tropism_w[7] = {0, 0, 3, 3, 2, 5, 0};

static int king_tropism(int piece_type, int pr, int pc, int ekr, int ekc){
  int dist = std::max(std::abs(pr - ekr), std::abs(pc - ekc));
  if(dist <= 2)
    return tropism_w[piece_type] * (3 - dist);
  return 0;
}

int State::evaluate(){
  if(this->game_state == WIN){
    score = P_MAX;
    return score;
  }

  // Use NNUE evaluation if model is loaded
#ifdef USE_NNUE
  if(nnue::g_model.loaded()){
    return nnue::g_model.evaluate(this->board, this->player);
  }
#endif

  auto self_board = this->board.board[this->player];
  auto oppn_board = this->board.board[1 - this->player];

  int self_score = 0, oppn_score = 0;

  // Find king positions for tropism calculation
  int self_kr = -1, self_kc = -1;
  int oppn_kr = -1, oppn_kc = -1;
  for(int i=0; i<BOARD_H; i++){
    for(int j=0; j<BOARD_W; j++){
      if(self_board[i][j] == 6){ self_kr = i; self_kc = j; }
      if(oppn_board[i][j] == 6){ oppn_kr = i; oppn_kc = j; }
    }
  }

  for(int i=0; i<BOARD_H; i++){
    for(int j=0; j<BOARD_W; j++){
      int piece;
      if((piece = self_board[i][j])){
        self_score += kp_material[piece];
        // PST lookup: mirror row for black (player 1)
        int r = (this->player == 0) ? i : (BOARD_H - 1 - i);
        self_score += pst[piece - 1][r][j];
        // Tropism: bonus for being near enemy king
        if(oppn_kr >= 0)
          self_score += king_tropism(piece, i, j, oppn_kr, oppn_kc);
      }
      if((piece = oppn_board[i][j])){
        oppn_score += kp_material[piece];
        int r = (this->player == 0) ? (BOARD_H - 1 - i) : i;
        oppn_score += pst[piece - 1][r][j];
        if(self_kr >= 0)
          oppn_score += king_tropism(piece, i, j, self_kr, self_kc);
      }
    }
  }

  int bonus = 0;

#ifdef USE_EVAL_MOBILITY
  /*
   * Mobility: count legal moves for each side.
   * More legal moves = more options = stronger position.
   * We already have self's legal_actions. For opponent, we do a quick count
   * by temporarily generating their moves on a copy.
   *
   * Weight: 2 per move difference (roughly 0.1 pawn per move)
   */
  {
    int self_mobility = (int)this->legal_actions.size();
    // Generate opponent mobility
    State oppn_state(this->board, 1 - this->player);
    oppn_state.get_legal_actions();
    int oppn_mobility = (int)oppn_state.legal_actions.size();
    bonus += 2 * (self_mobility - oppn_mobility);
  }
#endif


  return self_score - oppn_score + bonus;
}

#else
/*
 * Default: Material-only evaluation
 * Simply sums piece values. No positional knowledge.
 */
//score of empty, pawn, rook, knight, bishop, queen, king
static const int score_table[7] = {0, 2, 6, 7, 8, 20, 100};
int State::evaluate(){
  if(this->game_state == WIN){
    score = P_MAX;
    return score;
  }

  // Use NNUE evaluation if model is loaded
#ifdef USE_NNUE
  if(nnue::g_model.loaded()){
    return nnue::g_model.evaluate(this->board, this->player);
  }
#endif

  auto self_board = this->board.board[this->player];
  auto oppn_board = this->board.board[1 - this->player];

  int self_score=0, oppn_score=0;
  int8_t now_piece;
  for(int i=0; i<BOARD_H; i+=1){
    for(int j=0; j<BOARD_W; j+=1){
      if((now_piece = self_board[i][j])){
        self_score += score_table[now_piece];
      }else if((now_piece = oppn_board[i][j])){
        oppn_score += score_table[now_piece];
      }
    }
  }
  return self_score - oppn_score;
}
#endif



/**
 * @brief return next state after the move
 * 
 * @param move 
 * @return State* 
 */
State* State::next_state(Move move){
  Board next = this->board;
  Point from = move.first, to = move.second;
  
  int8_t moved = next.board[this->player][from.first][from.second];
  //promotion for pawn
  if(moved == 1 && (to.first==BOARD_H-1 || to.first==0)){
    moved = 5;
  }
  if(next.board[1-this->player][to.first][to.second]){
    next.board[1-this->player][to.first][to.second] = 0;
  }
  
  next.board[this->player][from.first][from.second] = 0;
  next.board[this->player][to.first][to.second] = moved;
  
  State* next_state = new State(next, 1-this->player);
  
  if(this->game_state != WIN)
    next_state->get_legal_actions();
  return next_state;
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
  for(int i=0; i<BOARD_H; i+=1){
    for(int j=0; j<BOARD_W; j+=1){
      if((now_piece=self_board[i][j])){
        switch (now_piece){
          case 1: //pawn
            if(this->player && i<BOARD_H-1){
              //black
              if(!oppn_board[i+1][j] && !self_board[i+1][j])
                all_actions.push_back(Move(Point(i, j), Point(i+1, j)));
              if(j<BOARD_W-1 && (oppn_piece=oppn_board[i+1][j+1])>0){
                all_actions.push_back(Move(Point(i, j), Point(i+1, j+1)));
                if(oppn_piece==6){
                  this->game_state = WIN;
                  this->legal_actions = all_actions;
                  return;
                }
              }
              if(j>0 && (oppn_piece=oppn_board[i+1][j-1])>0){
                all_actions.push_back(Move(Point(i, j), Point(i+1, j-1)));
                if(oppn_piece==6){
                  this->game_state = WIN;
                  this->legal_actions = all_actions;
                  return;
                }
              }
            }else if(!this->player && i>0){
              //white
              if(!oppn_board[i-1][j] && !self_board[i-1][j])
                all_actions.push_back(Move(Point(i, j), Point(i-1, j)));
              if(j<BOARD_W-1 && (oppn_piece=oppn_board[i-1][j+1])>0){
                all_actions.push_back(Move(Point(i, j), Point(i-1, j+1)));
                if(oppn_piece==6){
                  this->game_state = WIN;
                  this->legal_actions = all_actions;
                  return;
                }
              }
              if(j>0 && (oppn_piece=oppn_board[i-1][j-1])>0){
                all_actions.push_back(Move(Point(i, j), Point(i-1, j-1)));
                if(oppn_piece==6){
                  this->game_state = WIN;
                  this->legal_actions = all_actions;
                  return;
                }
              }
            }
            break;

          case 2: //rook
          case 4: //bishop
          case 5: //queen
            int st, end;
            switch (now_piece){
              case 2: st=0; end=4; break; //rook
              case 4: st=4; end=8; break; //bishop
              case 5: st=0; end=8; break; //queen
              default: st=0; end=-1;
            }
            for(int part=st; part<end; part+=1){
              auto move_list = move_table_rook_bishop[part];
              for(int k=0; k<std::max(BOARD_H, BOARD_W); k+=1){
                int p[2] = {move_list[k][0] + i, move_list[k][1] + j};

                if(p[0]>=BOARD_H || p[0]<0 || p[1]>=BOARD_W || p[1]<0) break;
                now_piece = self_board[p[0]][p[1]];
                if(now_piece) break;

                all_actions.push_back(Move(Point(i, j), Point(p[0], p[1])));

                oppn_piece = oppn_board[p[0]][p[1]];
                if(oppn_piece){
                  if(oppn_piece==6){
                    this->game_state = WIN;
                    this->legal_actions = all_actions;
                    return;
                  }else
                    break;
                };
              }
            }
            break;

          case 3: //knight
            for(auto move: move_table_knight){
              int x = move[0] + i;
              int y = move[1] + j;

              if(x>=BOARD_H || x<0 || y>=BOARD_W || y<0) continue;
              now_piece = self_board[x][y];
              if(now_piece) continue;
              all_actions.push_back(Move(Point(i, j), Point(x, y)));

              oppn_piece = oppn_board[x][y];
              if(oppn_piece==6){
                this->game_state = WIN;
                this->legal_actions = all_actions;
                return;
              }
            }
            break;

          case 6: //king
            for(auto move: move_table_king){
              int p[2] = {move[0] + i, move[1] + j};

              if(p[0]>=BOARD_H || p[0]<0 || p[1]>=BOARD_W || p[1]<0) continue;
              now_piece = self_board[p[0]][p[1]];
              if(now_piece) continue;

              all_actions.push_back(Move(Point(i, j), Point(p[0], p[1])));

              oppn_piece = oppn_board[p[0]][p[1]];
              if(oppn_piece==6){
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
 * 6x5 = 30 squares fit in a uint32_t.
 * Square (r,c) -> bit index r*5+c.
 * Precomputed attack masks for leapers (knight, king, pawn).
 * Bit-scan loop (__builtin_ctz) replaces nested array iteration.
 *============================================================*/
#define BB_SQ(r, c)  ((r) * BOARD_W + (c))
#define BB_ROW(sq)   ((sq) / BOARD_W)
#define BB_COL(sq)   ((sq) % BOARD_W)

// Precomputed attack tables (initialized once)
static uint32_t bb_knight[30];       // knight attack mask per square
static uint32_t bb_king[30];         // king attack mask per square
static uint32_t bb_pawn_push[2][30]; // pawn push target per player/square
static uint32_t bb_pawn_cap[2][30];  // pawn capture targets per player/square
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
        if(nr >= 0 && nr < BOARD_H && nc >= 0 && nc < BOARD_W)
          bb_knight[sq] |= 1u << BB_SQ(nr, nc);
      }

      // King
      bb_king[sq] = 0;
      for(int d = 0; d < 8; d++){
        int nr = r + ki_dr[d], nc = c + ki_dc[d];
        if(nr >= 0 && nr < BOARD_H && nc >= 0 && nc < BOARD_W)
          bb_king[sq] |= 1u << BB_SQ(nr, nc);
      }

      // Pawn (player 0 = white, advances up = row-1)
      bb_pawn_push[0][sq] = 0;
      bb_pawn_cap[0][sq] = 0;
      if(r > 0){
        bb_pawn_push[0][sq] = 1u << BB_SQ(r-1, c);
        if(c > 0)         bb_pawn_cap[0][sq] |= 1u << BB_SQ(r-1, c-1);
        if(c < BOARD_W-1) bb_pawn_cap[0][sq] |= 1u << BB_SQ(r-1, c+1);
      }

      // Pawn (player 1 = black, advances down = row+1)
      bb_pawn_push[1][sq] = 0;
      bb_pawn_cap[1][sq] = 0;
      if(r < BOARD_H-1){
        bb_pawn_push[1][sq] = 1u << BB_SQ(r+1, c);
        if(c > 0)         bb_pawn_cap[1][sq] |= 1u << BB_SQ(r+1, c-1);
        if(c < BOARD_W-1) bb_pawn_cap[1][sq] |= 1u << BB_SQ(r+1, c+1);
      }
    }
  }
  bb_ready = true;
}

void State::get_legal_actions_bitboard(){
  if(!bb_ready) bb_init();

  this->game_state = NONE;
  this->legal_actions.clear();
  this->legal_actions.reserve(64);

  int self = this->player;
  int oppn = 1 - self;

  // Build occupancy bitmasks and piece-type lookup
  uint32_t self_occ = 0, oppn_occ = 0;
  int self_pt[30] = {};  // piece type at each square (self)
  int oppn_pt[30] = {};  // piece type at each square (opponent)

  for(int r = 0; r < BOARD_H; r++){
    for(int c = 0; c < BOARD_W; c++){
      int sq = BB_SQ(r, c);
      if(this->board.board[self][r][c]){
        self_occ |= 1u << sq;
        self_pt[sq] = this->board.board[self][r][c];
      }
      if(this->board.board[oppn][r][c]){
        oppn_occ |= 1u << sq;
        oppn_pt[sq] = this->board.board[oppn][r][c];
      }
    }
  }

  uint32_t all_occ = self_occ | oppn_occ;

  // Iterate own pieces via bit scan
  uint32_t pieces = self_occ;
  while(pieces){
    int sq = __builtin_ctz(pieces);
    pieces &= pieces - 1;
    int r = BB_ROW(sq), c = BB_COL(sq);
    int piece = self_pt[sq];
    uint32_t targets = 0;

    switch(piece){
      case 1: { // Pawn
        uint32_t push = bb_pawn_push[self][sq] & ~all_occ;
        uint32_t cap = bb_pawn_cap[self][sq] & oppn_occ;
        // Check for king capture in captures
        uint32_t cap_scan = cap;
        while(cap_scan){
          int to = __builtin_ctz(cap_scan);
          cap_scan &= cap_scan - 1;
          if(oppn_pt[to] == 6){
            this->game_state = WIN;
            this->legal_actions.push_back(
              Move(Point(r, c), Point(BB_ROW(to), BB_COL(to))));
            return;
          }
        }
        targets = push | cap;
        break;
      }

      case 3: { // Knight
        targets = bb_knight[sq] & ~self_occ;
        uint32_t opp_targets = targets & oppn_occ;
        while(opp_targets){
          int to = __builtin_ctz(opp_targets);
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
        uint32_t opp_targets = targets & oppn_occ;
        while(opp_targets){
          int to = __builtin_ctz(opp_targets);
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
            uint32_t to_bit = 1u << to;
            if(self_occ & to_bit) break; // own piece blocks

            if((oppn_occ & to_bit) && oppn_pt[to] == 6){
              this->game_state = WIN;
              this->legal_actions.push_back(
                Move(Point(r, c), Point(cr, cc)));
              return;
            }

            targets |= to_bit;
            if(oppn_occ & to_bit) break; // captured, stop sliding
            cr += bb_dr[d]; cc += bb_dc[d];
          }
        }
        break;
      }
    }

    // Convert target bitmask to Move objects
    while(targets){
      int to = __builtin_ctz(targets);
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
#ifdef USE_BITBOARD
  get_legal_actions_bitboard();
#else
  get_legal_actions_naive();
#endif
}


const char piece_table[2][7][5] = {
  {" ", "♙", "♖", "♘", "♗", "♕", "♔"},
  {" ", "♟", "♜", "♞", "♝", "♛", "♚"}
};
/**
 * @brief encode the output for command line output
 * 
 * @return std::string 
 */
std::string State::encode_output(){
  std::stringstream ss;
  int now_piece;
  for(int i=0; i<BOARD_H; i+=1){
    for(int j=0; j<BOARD_W; j+=1){
      if((now_piece = this->board.board[0][i][j])){
        ss << std::string(piece_table[0][now_piece]);
      }else if((now_piece = this->board.board[1][i][j])){
        ss << std::string(piece_table[1][now_piece]);
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
  for(int pl=0; pl<2; pl+=1){
    for(int i=0; i<BOARD_H; i+=1){
      for(int j=0; j<BOARD_W; j+=1){
        ss << int(this->board.board[pl][i][j]);
        ss << " ";
      }
      ss << "\n";
    }
    ss << "\n";
  }
  return ss.str();
}