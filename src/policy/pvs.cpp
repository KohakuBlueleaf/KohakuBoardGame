#include <algorithm>
#include <vector>
#include <utility>
#include <cstdint>
#include "pvs.hpp"
#include "../state/state.hpp"
#include "../config.hpp"


/*============================================================
 * Transposition Table (Zobrist hashing + position cache)
 *
 * Zobrist hashing: XOR together random numbers for each
 * (player, piece_type, row, col) on the board. Two identical
 * positions always produce the same hash.
 *
 * The TT stores search results so that:
 * 1. Positions reached via different move orders reuse work
 * 2. Previous iterative-deepening iterations seed the next
 * 3. The TT best move is searched first (huge for PVS)
 *============================================================*/
#ifdef USE_TRANSPOSITION_TABLE

static constexpr int TT_SIZE = 1 << TT_SIZE_BITS;

// Zobrist random keys
static uint64_t zobrist_piece[2][7][BOARD_H][BOARD_W];
static uint64_t zobrist_side;
static bool zobrist_ready = false;

static void init_zobrist(){
  // xorshift64 PRNG with fixed seed for reproducibility
  uint64_t s = 0x7A35C9D1E4F02B68ULL;
  auto rand64 = [&s]() -> uint64_t {
    s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s;
  };
  for(int p = 0; p < 2; p++)
    for(int t = 0; t < 7; t++)
      for(int r = 0; r < BOARD_H; r++)
        for(int c = 0; c < BOARD_W; c++)
          zobrist_piece[p][t][r][c] = rand64();
  zobrist_side = rand64();
  zobrist_ready = true;
}

static uint64_t compute_hash(const State* state){
  if(!zobrist_ready) init_zobrist();
  uint64_t h = 0;
  for(int p = 0; p < 2; p++)
    for(int r = 0; r < BOARD_H; r++)
      for(int c = 0; c < BOARD_W; c++){
        int piece = state->board.board[p][r][c];
        if(piece) h ^= zobrist_piece[p][piece][r][c];
      }
  if(state->player) h ^= zobrist_side;
  return h;
}

// TT entry: compact representation
enum TTFlag : uint8_t { TT_NONE = 0, TT_EXACT, TT_LOWER, TT_UPPER };

struct TTEntry {
  uint64_t hash = 0;
  int score = 0;
  int depth = -1;
  TTFlag flag = TT_NONE;
  // Store move compactly (board is 6x5, each coord fits in a byte)
  uint8_t from_r = 0, from_c = 0, to_r = 0, to_c = 0;

  Move get_move() const {
    return Move(Point(from_r, from_c), Point(to_r, to_c));
  }
  void set_move(const Move& m){
    from_r = m.first.first; from_c = m.first.second;
    to_r = m.second.first; to_c = m.second.second;
  }
};

static TTEntry tt[TT_SIZE];

static TTEntry* tt_probe(uint64_t hash){
  TTEntry& e = tt[hash & (TT_SIZE - 1)];
  if(e.flag != TT_NONE && e.hash == hash) return &e;
  return nullptr;
}

static void tt_store(uint64_t hash, int depth, int score, TTFlag flag, const Move& best){
  TTEntry& e = tt[hash & (TT_SIZE - 1)];
  // Always replace if: new is deeper, or same position, or slot empty
  if(e.flag == TT_NONE || e.depth <= depth || e.hash == hash){
    e.hash = hash;
    e.score = score;
    e.depth = depth;
    e.flag = flag;
    e.set_move(best);
  }
}
#endif


/*============================================================
 * Killer Move Table
 *
 * Stores quiet moves that caused beta cutoffs at each ply.
 * Two slots per ply — when a new killer is stored, the old
 * one shifts down. Killers improve move ordering by placing
 * historically good quiet moves ahead of other quiet moves.
 *============================================================*/
#ifdef USE_KILLER_MOVES

static constexpr int MAX_PLY = 64;
static Move killer_table[MAX_PLY][KILLER_SLOTS];

static void store_killer(int ply, const Move& move){
  if(ply >= MAX_PLY) return;
  // Don't store duplicates
  if(killer_table[ply][0] == move) return;
  // Shift slot 0 → slot 1, store new move in slot 0
  for(int i = KILLER_SLOTS - 1; i > 0; i--)
    killer_table[ply][i] = killer_table[ply][i - 1];
  killer_table[ply][0] = move;
}

static bool is_killer(int ply, const Move& move){
  if(ply >= MAX_PLY) return false;
  for(int i = 0; i < KILLER_SLOTS; i++)
    if(killer_table[ply][i] == move) return true;
  return false;
}

#endif


/*============================================================
 * Move ordering: captures scored by MVV-LVA
 * With TT: TT best move gets highest priority
 * With Killers: killer moves rank below captures, above quiet
 *============================================================*/
#ifdef USE_MOVE_ORDERING
static const int piece_val[7] = {0, 2, 6, 7, 8, 20, 100};

static int score_move(
  const State* state,
  const Move& move,
  [[maybe_unused]] int ply = 0)
{
  int to_r = move.second.first;
  int to_c = move.second.second;
  int captured = state->board.board[1 - state->player][to_r][to_c];
  if(captured){
    int from_r = move.first.first;
    int from_c = move.first.second;
    int attacker = state->board.board[state->player][from_r][from_c];
    return piece_val[captured] * 100 - piece_val[attacker];
  }
#ifdef USE_KILLER_MOVES
  if(is_killer(ply, move))
    return 50;
#endif
  return 0;
}
#endif

// Unified move ordering: MVV-LVA + killers + optional TT best move first
static std::vector<Move> get_ordered_moves(
  [[maybe_unused]] const State* state,
  [[maybe_unused]] const Move* tt_move = nullptr,
  [[maybe_unused]] int ply = 0)
{
  auto moves = state->legal_actions;

#ifdef USE_MOVE_ORDERING
  std::sort(moves.begin(), moves.end(),
    [state, ply](const Move& a, const Move& b){
      return score_move(state, a, ply) > score_move(state, b, ply);
    });
#endif

#ifdef USE_TRANSPOSITION_TABLE
  // Swap TT best move to front (highest priority)
  if(tt_move){
    for(size_t i = 0; i < moves.size(); i++){
      if(moves[i] == *tt_move){
        std::swap(moves[0], moves[i]);
        break;
      }
    }
  }
#endif

  return moves;
}


/*============================================================
 * Quiescence Search
 *============================================================*/
#ifdef USE_QUIESCENCE
static int quiescence(State *state, int alpha, int beta, int qdepth){
  if(state->game_state == WIN){
    delete state;
    return P_MAX;
  }
  if(state->game_state == DRAW){
    delete state;
    return 0;
  }

  int stand_pat = state->evaluate();
  if(stand_pat >= beta){
    delete state;
    return beta;
  }
  if(stand_pat > alpha)
    alpha = stand_pat;

  if(qdepth >= QUIESCENCE_MAX_DEPTH){
    delete state;
    return alpha;
  }

  for(auto& move : state->legal_actions){
    int to_r = move.second.first;
    int to_c = move.second.second;
    if(!state->board.board[1 - state->player][to_r][to_c])
      continue;

    int score = -quiescence(state->next_state(move), -beta, -alpha, qdepth + 1);
    if(score >= beta){
      delete state;
      return beta;
    }
    if(score > alpha)
      alpha = score;
  }

  delete state;
  return alpha;
}
#endif


/*============================================================
 * PVS (Principal Variation Search)
 *============================================================*/
int PVS::eval(
  State *state, int depth, int alpha, int beta,
  [[maybe_unused]] int ply, [[maybe_unused]] bool can_null)
{
  if(state->game_state == WIN){
    delete state;
    return P_MAX;
  }
  if(state->game_state == DRAW){
    delete state;
    return 0;
  }
  if(depth == 0){
#ifdef USE_QUIESCENCE
    return quiescence(state, alpha, beta, 0);
#else
    int score = state->evaluate();
    delete state;
    return score;
#endif
  }

  int orig_alpha = alpha;
  [[maybe_unused]] Move tt_best;
  [[maybe_unused]] bool has_tt_move = false;

#ifdef USE_TRANSPOSITION_TABLE
  uint64_t hash = compute_hash(state);

  // Probe TT
  TTEntry* tte = tt_probe(hash);
  if(tte && tte->depth >= depth){
    if(tte->flag == TT_EXACT){
      delete state;
      return tte->score;
    }
    if(tte->flag == TT_LOWER && tte->score >= beta){
      delete state;
      return tte->score;
    }
    if(tte->flag == TT_UPPER && tte->score <= alpha){
      delete state;
      return tte->score;
    }
  }
  if(tte){
    tt_best = tte->get_move();
    has_tt_move = true;
  }
#endif

  /*------------------------------------------------------------
   * Null Move Pruning
   *
   * If we skip our turn (pass) and search at reduced depth,
   * and the result is still >= beta, the position is so good
   * that a real move will also beat beta. Prune early.
   *------------------------------------------------------------*/
#ifdef USE_NULL_MOVE
  if(can_null && depth >= NULL_MOVE_R + 1){
    // Create a "pass" state: same board, switch player
    State* null_state = new State(state->board, 1 - state->player);
    null_state->get_legal_actions();

    // Only do null move if the position is not terminal
    if(null_state->game_state != WIN && null_state->game_state != DRAW){
      int null_score = -eval(null_state, depth - 1 - NULL_MOVE_R, -beta, -(beta - 1), ply + 1, false);
      if(null_score >= beta){
        delete state;
        return beta;
      }
    }else{
      delete null_state;
    }
  }
#endif

  // Move ordering (TT move first if available)
#ifdef USE_TRANSPOSITION_TABLE
  auto moves = get_ordered_moves(state, has_tt_move ? &tt_best : nullptr, ply);
#else
  auto moves = get_ordered_moves(state, nullptr, ply);
#endif

  Move best_move;
  bool first_child = true;
  int move_index = 0;
  for(auto& move : moves){
    int score;
    if(first_child){
      // First move: full window, full depth
      score = -eval(state->next_state(move), depth - 1, -beta, -alpha, ply + 1, true);
      first_child = false;
      best_move = move;
    }else{
      /*----------------------------------------------------------
       * Late Move Reduction (LMR)
       *
       * Moves ordered late are unlikely to be good. Search them
       * at reduced depth first; only re-search at full depth if
       * the reduced search suggests they might be interesting.
       *----------------------------------------------------------*/
      bool do_lmr = false;
#ifdef USE_LMR
      if(move_index >= LMR_FULL_DEPTH && depth >= LMR_DEPTH_LIMIT){
        // Only reduce quiet (non-capture) moves
        int to_r = move.second.first;
        int to_c = move.second.second;
        bool is_capture = state->board.board[1 - state->player][to_r][to_c] != 0;
        if(!is_capture){
#ifdef USE_KILLER_MOVES
          // Don't reduce killer moves
          if(!is_killer(ply, move))
            do_lmr = true;
#else
          do_lmr = true;
#endif
        }
      }
#endif

      if(do_lmr){
        // LMR: null-window, reduced depth
        score = -eval(state->next_state(move), depth - 2, -(alpha + 1), -alpha, ply + 1, true);
        if(score > alpha){
          // Re-search at full depth, null-window
          score = -eval(state->next_state(move), depth - 1, -(alpha + 1), -alpha, ply + 1, true);
          if(score > alpha && score < beta){
            // Full window re-search
            score = -eval(state->next_state(move), depth - 1, -beta, -alpha, ply + 1, true);
          }
        }
      }else{
        // Standard PVS null-window search
        score = -eval(state->next_state(move), depth - 1, -(alpha + 1), -alpha, ply + 1, true);
        if(score > alpha && score < beta){
          score = -eval(state->next_state(move), depth - 1, -beta, -alpha, ply + 1, true);
        }
      }
    }

    if(score > alpha){
      alpha = score;
      best_move = move;
    }
    if(alpha >= beta){
      // Beta cutoff — store killer if this is a quiet move
#ifdef USE_KILLER_MOVES
      {
        int to_r = move.second.first;
        int to_c = move.second.second;
        bool is_capture = state->board.board[1 - state->player][to_r][to_c] != 0;
        if(!is_capture)
          store_killer(ply, move);
      }
#endif
      break;
    }
    move_index++;
  }

#ifdef USE_TRANSPOSITION_TABLE
  // Store result in TT
  TTFlag flag;
  if(alpha <= orig_alpha)
    flag = TT_UPPER;
  else if(alpha >= beta)
    flag = TT_LOWER;
  else
    flag = TT_EXACT;
  tt_store(hash, depth, alpha, flag, best_move);
#endif

  delete state;
  return alpha;
}


Move PVS::get_move(State *state, int depth){
  Move best_action;
  int alpha = M_MAX - 10;
  int beta = P_MAX + 10;

  [[maybe_unused]] Move tt_best;
  [[maybe_unused]] bool has_tt_move = false;

#ifdef USE_TRANSPOSITION_TABLE
  uint64_t hash = compute_hash(state);
  TTEntry* tte = tt_probe(hash);
  if(tte){
    tt_best = tte->get_move();
    has_tt_move = true;
  }
  auto moves = get_ordered_moves(state, has_tt_move ? &tt_best : nullptr, 0);
#else
  auto moves = get_ordered_moves(state, nullptr, 0);
#endif

  bool first_child = true;
  for(auto& move : moves){
    int score;
    if(first_child){
      score = -eval(state->next_state(move), depth - 1, -beta, -alpha, 0, true);
      first_child = false;
    }else{
      score = -eval(state->next_state(move), depth - 1, -(alpha + 1), -alpha, 0, true);
      if(score > alpha && score < beta){
        score = -eval(state->next_state(move), depth - 1, -beta, -alpha, 0, true);
      }
    }

    if(score > alpha){
      best_action = move;
      alpha = score;
    }
  }

  return best_action;
}
