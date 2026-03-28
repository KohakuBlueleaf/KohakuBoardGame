#include <iostream>
#include <sstream>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <algorithm>

#include "./state.hpp"
#include "config.hpp"
#include "../../policy/game_history.hpp"
#include "../../search_params.hpp"
#ifdef USE_NNUE
#include "../../nnue/nnue.hpp"
#endif


/*============================================================
 * NNUE feature extraction (HalfKP)
 *============================================================*/
int State::extract_nnue_features(int perspective, int* features) const {
    constexpr int NUM_SQ = BOARD_H * BOARD_W;
    constexpr int KP_FEAT = 2 * NUM_PT_NO_KING * NUM_SQ;
    int count = 0;

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

    for(int color = 0; color < 2; color++){
        for(int r = 0; r < BOARD_H; r++){
            for(int c = 0; c < BOARD_W; c++){
                int pt = board.board[color][r][c];
                if(pt == 0 || pt == KING_ID) continue;
                int feat_color, sq;
                if(perspective == 0){
                    feat_color = color;
                    sq = r * BOARD_W + c;
                }else{
                    feat_color = 1 - color;
                    sq = (BOARD_H - 1 - r) * BOARD_W + c;
                }
                int idx = king_sq * KP_FEAT
                    + feat_color * (NUM_PT_NO_KING * NUM_SQ)
                    + (pt - 1) * NUM_SQ + sq;
                if(count < 32) features[count++] = idx;
            }
        }
    }
    return count;
}


/*============================================================
 * Tapered Eval — packed MG/EG score
 *
 * Each eval term produces S(mg, eg) packed into one int32.
 * At the end of evaluate(), we interpolate by game phase.
 *============================================================*/
#define S(mg, eg) (((int32_t)(mg) << 16) + (int16_t)(eg))
static inline int mg_of(int s){ return (int16_t)((uint16_t)((unsigned)(s) + 0x8000u) >> 16); }
static inline int eg_of(int s){ return (int16_t)((uint16_t)((unsigned)(s) & 0xFFFFu)); }

/* Phase weights: N=1, B=1, R=2, Q=4. Total starting = 24.  */
static const int phase_weight[7] = {0, 0, 2, 1, 1, 4, 0};
static constexpr int TOTAL_PHASE = 24;  /* 4N + 4B + 4R + 2Q */

/*============================================================
 * Material values (MG / EG)
 *============================================================*/
static const int mat_mg[7] = {0, 100, 500, 320, 330, 900, 20000};
static const int mat_eg[7] = {0, 130, 550, 320, 340, 950, 20000};
static const int simple_material[7] = {0, 10, 50, 30, 30, 90, 0};

/*============================================================
 * Piece-Square Tables (white perspective, row 0 = rank 8)
 * Separate MG and EG tables.
 *============================================================*/

/* --- Middlegame PST --- */
static const int pst_mg[6][8][8] = {
    // Pawn MG
    {{ 0, 0, 0, 0, 0, 0, 0, 0}, {50,50,50,50,50,50,50,50},
     {10,10,20,30,30,20,10,10}, { 5, 5,10,25,25,10, 5, 5},
     { 0, 0, 0,20,20, 0, 0, 0}, { 5,-5,-10,0, 0,-10,-5,5},
     { 5,10,10,-20,-20,10,10,5}, { 0, 0, 0, 0, 0, 0, 0, 0}},
    // Rook MG
    {{ 0, 0, 0, 0, 0, 0, 0, 0}, { 5,10,10,10,10,10,10, 5},
     {-5, 0, 0, 0, 0, 0, 0,-5}, {-5, 0, 0, 0, 0, 0, 0,-5},
     {-5, 0, 0, 0, 0, 0, 0,-5}, {-5, 0, 0, 0, 0, 0, 0,-5},
     {-5, 0, 0, 0, 0, 0, 0,-5}, { 0, 0, 0, 5, 5, 0, 0, 0}},
    // Knight MG
    {{-50,-40,-30,-30,-30,-30,-40,-50}, {-40,-20, 0, 0, 0, 0,-20,-40},
     {-30, 0,10,15,15,10, 0,-30}, {-30, 5,15,20,20,15, 5,-30},
     {-30, 0,15,20,20,15, 0,-30}, {-30, 5,10,15,15,10, 5,-30},
     {-40,-20, 0, 5, 5, 0,-20,-40}, {-50,-40,-30,-30,-30,-30,-40,-50}},
    // Bishop MG
    {{-20,-10,-10,-10,-10,-10,-10,-20}, {-10, 0, 0, 0, 0, 0, 0,-10},
     {-10, 0, 5,10,10, 5, 0,-10}, {-10, 5, 5,10,10, 5, 5,-10},
     {-10, 0,10,10,10,10, 0,-10}, {-10,10,10,10,10,10,10,-10},
     {-10, 5, 0, 0, 0, 0, 5,-10}, {-20,-10,-10,-10,-10,-10,-10,-20}},
    // Queen MG
    {{-20,-10,-10,-5,-5,-10,-10,-20}, {-10, 0, 0, 0, 0, 0, 0,-10},
     {-10, 0, 5, 5, 5, 5, 0,-10}, { -5, 0, 5, 5, 5, 5, 0, -5},
     {  0, 0, 5, 5, 5, 5, 0, -5}, {-10, 5, 5, 5, 5, 5, 0,-10},
     {-10, 0, 5, 0, 0, 0, 0,-10}, {-20,-10,-10,-5,-5,-10,-10,-20}},
    // King MG — stay safe, hide behind pawns
    {{-30,-40,-40,-50,-50,-40,-40,-30}, {-30,-40,-40,-50,-50,-40,-40,-30},
     {-30,-40,-40,-50,-50,-40,-40,-30}, {-30,-40,-40,-50,-50,-40,-40,-30},
     {-20,-30,-30,-40,-40,-30,-30,-20}, {-10,-20,-20,-20,-20,-20,-20,-10},
     { 20, 20,  0,  0,  0,  0, 20, 20}, { 20, 30, 10,  0,  0, 10, 30, 20}},
};

/* --- Endgame PST --- */
static const int pst_eg[6][8][8] = {
    // Pawn EG — strongly reward advancement
    {{ 0, 0, 0, 0, 0, 0, 0, 0}, {80,80,80,80,80,80,80,80},
     {50,50,50,50,50,50,50,50}, {30,30,30,30,30,30,30,30},
     {15,15,15,20,20,15,15,15}, { 5, 5, 5,10,10, 5, 5, 5},
     { 0, 0, 0, 0, 0, 0, 0, 0}, { 0, 0, 0, 0, 0, 0, 0, 0}},
    // Rook EG — 7th rank bonus, otherwise flat
    {{ 0, 0, 0, 0, 0, 0, 0, 0}, {10,10,10,10,10,10,10,10},
     { 0, 0, 0, 0, 0, 0, 0, 0}, { 0, 0, 0, 0, 0, 0, 0, 0},
     { 0, 0, 0, 0, 0, 0, 0, 0}, { 0, 0, 0, 0, 0, 0, 0, 0},
     { 0, 0, 0, 0, 0, 0, 0, 0}, { 0, 0, 0, 0, 0, 0, 0, 0}},
    // Knight EG — center preference (same as MG but milder)
    {{-40,-30,-20,-20,-20,-20,-30,-40}, {-30,-10, 0, 5, 5, 0,-10,-30},
     {-20, 0,10,15,15,10, 0,-20}, {-20, 5,15,20,20,15, 5,-20},
     {-20, 5,15,20,20,15, 5,-20}, {-20, 0,10,15,15,10, 0,-20},
     {-30,-10, 0, 5, 5, 0,-10,-30}, {-40,-30,-20,-20,-20,-20,-30,-40}},
    // Bishop EG — center preference, mild
    {{-20,-10,-10,-10,-10,-10,-10,-20}, {-10, 0, 0, 0, 0, 0, 0,-10},
     {-10, 0, 5,10,10, 5, 0,-10}, {-10, 5,10,15,15,10, 5,-10},
     {-10, 5,10,15,15,10, 5,-10}, {-10, 0, 5,10,10, 5, 0,-10},
     {-10, 0, 0, 0, 0, 0, 0,-10}, {-20,-10,-10,-10,-10,-10,-10,-20}},
    // Queen EG — center preference
    {{-20,-10,-10,-5,-5,-10,-10,-20}, {-10, 0, 0, 0, 0, 0, 0,-10},
     {-10, 0, 5, 5, 5, 5, 0,-10}, { -5, 0, 5,10,10, 5, 0, -5},
     { -5, 0, 5,10,10, 5, 0, -5}, {-10, 0, 5, 5, 5, 5, 0,-10},
     {-10, 0, 0, 0, 0, 0, 0,-10}, {-20,-10,-10,-5,-5,-10,-10,-20}},
    // King EG — CENTRALIZE (complete reversal from MG)
    {{-50,-30,-30,-30,-30,-30,-30,-50}, {-30,-10,  0,  0,  0,  0,-10,-30},
     {-30,  0, 10, 15, 15, 10,  0,-30}, {-30,  0, 15, 20, 20, 15,  0,-30},
     {-30,  0, 15, 20, 20, 15,  0,-30}, {-30,  0, 10, 15, 15, 10,  0,-30},
     {-30,-10,  0,  0,  0,  0,-10,-30}, {-50,-30,-30,-30,-30,-30,-30,-50}},
};


/*============================================================
 * Direction tables
 *============================================================*/
static const int dir8_dr[8] = {-1, 1, 0, 0, -1, -1, 1, 1};
static const int dir8_dc[8] = { 0, 0,-1, 1, -1,  1,-1, 1};

static const int knight_dr[8] = {-2,-2,-1,-1, 1, 1, 2, 2};
static const int knight_dc[8] = {-1, 1,-2, 2,-2, 2,-1, 1};


/*============================================================
 * Magic Bitboards for sliding piece attack generation
 *
 * 8x8 = 64 squares. Each square has a precomputed attack table
 * indexed by (occupancy & mask) * magic >> shift.
 *============================================================*/
#define SQ(r, c)   ((r) * 8 + (c))
#define ROW(sq)    ((sq) / 8)
#define COL(sq)    ((sq) % 8)

struct MagicEntry {
    uint64_t mask;
    uint64_t magic;
    int shift;
    uint64_t* attacks;  /* pointer into attack table */
};

static MagicEntry rook_magics[64];
static MagicEntry bishop_magics[64];
static uint64_t rook_table[102400];   /* total rook attack entries */
static uint64_t bishop_table[5248];   /* total bishop attack entries */

/* Precomputed leaper attack tables */
static uint64_t knight_attacks[64];
static uint64_t king_attacks[64];
static uint64_t pawn_attacks[2][64];  /* [color][sq] — capture squares */

static bool magic_ready = false;

/* Generate sliding attacks for a single square with given blockers */
static uint64_t sliding_attack(
    int sq, uint64_t blockers, const int* dr, const int* dc, int num_dirs
){
    uint64_t attacks = 0;
    int r0 = ROW(sq), c0 = COL(sq);
    for(int d = 0; d < num_dirs; d++){
        int r = r0 + dr[d], c = c0 + dc[d];
        while(r >= 0 && r < 8 && c >= 0 && c < 8){
            attacks |= 1ULL << SQ(r, c);
            if(blockers & (1ULL << SQ(r, c))) break;
            r += dr[d];
            c += dc[d];
        }
    }
    return attacks;
}

static uint64_t rook_mask(int sq){
    static const int dr[4] = {-1, 1, 0, 0};
    static const int dc[4] = { 0, 0,-1, 1};
    uint64_t mask = 0;
    int r0 = ROW(sq), c0 = COL(sq);
    for(int d = 0; d < 4; d++){
        int r = r0 + dr[d], c = c0 + dc[d];
        while(r >= 0 && r < 8 && c >= 0 && c < 8){
            int nr = r + dr[d], nc = c + dc[d];
            if(nr < 0 || nr >= 8 || nc < 0 || nc >= 8) break; /* exclude edges */
            mask |= 1ULL << SQ(r, c);
            r = nr; c = nc;
        }
    }
    return mask;
}

static uint64_t bishop_mask(int sq){
    static const int dr[4] = {-1, -1, 1, 1};
    static const int dc[4] = {-1,  1,-1, 1};
    uint64_t mask = 0;
    int r0 = ROW(sq), c0 = COL(sq);
    for(int d = 0; d < 4; d++){
        int r = r0 + dr[d], c = c0 + dc[d];
        while(r >= 0 && r < 8 && c >= 0 && c < 8){
            int nr = r + dr[d], nc = c + dc[d];
            if(nr < 0 || nr >= 8 || nc < 0 || nc >= 8) break;
            mask |= 1ULL << SQ(r, c);
            r = nr; c = nc;
        }
    }
    return mask;
}

/* Enumerate all subsets of a mask */
static uint64_t next_subset(uint64_t subset, uint64_t mask){
    return (subset - mask) & mask;
}

/* Known good magic numbers (from public domain / Stockfish-derived) */
static const uint64_t ROOK_MAGICS_KNOWN[64] = {
    0x0080001020400080ULL, 0x0040001000200040ULL, 0x0080081000200080ULL, 0x0080040800100080ULL,
    0x0080020400080080ULL, 0x0080010200040080ULL, 0x0080008001000200ULL, 0x0080002040800100ULL,
    0x0000800020400080ULL, 0x0000400020005000ULL, 0x0000801000200080ULL, 0x0000800800100080ULL,
    0x0000800400080080ULL, 0x0000800200040080ULL, 0x0000800100020080ULL, 0x0000800040800100ULL,
    0x0000208000400080ULL, 0x0000404000201000ULL, 0x0000808010002000ULL, 0x0000808008001000ULL,
    0x0000808004000800ULL, 0x0000808002000400ULL, 0x0000010100020004ULL, 0x0000020000408104ULL,
    0x0000208080004000ULL, 0x0000200040005000ULL, 0x0000100080200080ULL, 0x0000080080100080ULL,
    0x0000040080080080ULL, 0x0000020080040080ULL, 0x0000010080800200ULL, 0x0000800080004100ULL,
    0x0000204000800080ULL, 0x0000200040401000ULL, 0x0000100080802000ULL, 0x0000080080801000ULL,
    0x0000040080800800ULL, 0x0000020080800400ULL, 0x0000020001010004ULL, 0x0000800040800100ULL,
    0x0000204000808000ULL, 0x0000200040008080ULL, 0x0000100020008080ULL, 0x0000080010008080ULL,
    0x0000040008008080ULL, 0x0000020004008080ULL, 0x0000010002008080ULL, 0x0000004081020004ULL,
    0x0000204000800080ULL, 0x0000200040008080ULL, 0x0000100020008080ULL, 0x0000080010008080ULL,
    0x0000040008008080ULL, 0x0000020004008080ULL, 0x0000800100020080ULL, 0x0000800041000080ULL,
    0x00FFFCDDFCED714AULL, 0x007FFCDDFCED714AULL, 0x003FFFCDFFD88096ULL, 0x0000040810002101ULL,
    0x0001000204080011ULL, 0x0001000204000801ULL, 0x0001000082000401ULL, 0x0001FFFAABFAD1A2ULL,
};

static const uint64_t BISHOP_MAGICS_KNOWN[64] = {
    0x0002020202020200ULL, 0x0002020202020000ULL, 0x0004010202000000ULL, 0x0004040080000000ULL,
    0x0001104000000000ULL, 0x0000821040000000ULL, 0x0000410410400000ULL, 0x0000104104104000ULL,
    0x0000040404040400ULL, 0x0000020202020200ULL, 0x0000040102020000ULL, 0x0000040400800000ULL,
    0x0000011040000000ULL, 0x0000008210400000ULL, 0x0000004104104000ULL, 0x0000002082082000ULL,
    0x0004000808080800ULL, 0x0002000404040400ULL, 0x0001000202020200ULL, 0x0000800802004000ULL,
    0x0000800400A00000ULL, 0x0000200100884000ULL, 0x0000400082082000ULL, 0x0000200041041000ULL,
    0x0002080010101000ULL, 0x0001040008080800ULL, 0x0000208004010400ULL, 0x0000404004010200ULL,
    0x0000840000802000ULL, 0x0000404002011000ULL, 0x0000808001041000ULL, 0x0000404000820800ULL,
    0x0001041000202000ULL, 0x0000820800101000ULL, 0x0000104400080800ULL, 0x0000020080080080ULL,
    0x0000404040040100ULL, 0x0000808100020100ULL, 0x0001010100020800ULL, 0x0000808080010400ULL,
    0x0000820820004000ULL, 0x0000410410002000ULL, 0x0000208208001000ULL, 0x0000002084000800ULL,
    0x0000000020880000ULL, 0x0000001002020000ULL, 0x0000040408020000ULL, 0x0000040820040000ULL,
    0x0001010101000200ULL, 0x0000808080800400ULL, 0x0000404040404000ULL, 0x0000202020202000ULL,
    0x0000204008040000ULL, 0x0000020080080000ULL, 0x0000040100400000ULL, 0x0000020200200000ULL,
    0x0000010100100000ULL, 0x0000008080808000ULL, 0x0000020020202000ULL, 0x0000104104104000ULL,
    0x0000002082082000ULL, 0x0000000020841000ULL, 0x0000000000208800ULL, 0x0000000010020200ULL,
};

static const int ROOK_SHIFTS[64] = {
    52,53,53,53,53,53,53,52, 53,54,54,54,54,54,54,53,
    53,54,54,54,54,54,54,53, 53,54,54,54,54,54,54,53,
    53,54,54,54,54,54,54,53, 53,54,54,54,54,54,54,53,
    53,54,54,54,54,54,54,53, 52,53,53,53,53,53,53,52,
};

static const int BISHOP_SHIFTS[64] = {
    58,59,59,59,59,59,59,58, 59,59,59,59,59,59,59,59,
    59,59,57,57,57,57,59,59, 59,59,57,55,55,57,59,59,
    59,59,57,55,55,57,59,59, 59,59,57,57,57,57,59,59,
    59,59,59,59,59,59,59,59, 58,59,59,59,59,59,59,58,
};

static void init_magics(){
    /* Init leaper tables */
    for(int sq = 0; sq < 64; sq++){
        int r = ROW(sq), c = COL(sq);

        knight_attacks[sq] = 0;
        for(int d = 0; d < 8; d++){
            int nr = r + knight_dr[d], nc = c + knight_dc[d];
            if(nr >= 0 && nr < 8 && nc >= 0 && nc < 8)
                knight_attacks[sq] |= 1ULL << SQ(nr, nc);
        }

        king_attacks[sq] = 0;
        for(int d = 0; d < 8; d++){
            int nr = r + dir8_dr[d], nc = c + dir8_dc[d];
            if(nr >= 0 && nr < 8 && nc >= 0 && nc < 8)
                king_attacks[sq] |= 1ULL << SQ(nr, nc);
        }

        /* Pawn captures (white = up = row-1, black = down = row+1) */
        pawn_attacks[0][sq] = 0;
        if(r > 0 && c > 0) pawn_attacks[0][sq] |= 1ULL << SQ(r-1, c-1);
        if(r > 0 && c < 7) pawn_attacks[0][sq] |= 1ULL << SQ(r-1, c+1);
        pawn_attacks[1][sq] = 0;
        if(r < 7 && c > 0) pawn_attacks[1][sq] |= 1ULL << SQ(r+1, c-1);
        if(r < 7 && c < 7) pawn_attacks[1][sq] |= 1ULL << SQ(r+1, c+1);
    }

    /* Init rook magics */
    static const int rook_dr[4] = {-1, 1, 0, 0};
    static const int rook_dc[4] = { 0, 0,-1, 1};
    uint64_t* rook_ptr = rook_table;

    for(int sq = 0; sq < 64; sq++){
        MagicEntry& me = rook_magics[sq];
        me.mask = rook_mask(sq);
        me.magic = ROOK_MAGICS_KNOWN[sq];
        me.shift = ROOK_SHIFTS[sq];
        me.attacks = rook_ptr;

        int bits = 64 - me.shift;
        int size = 1 << bits;

        /* Fill attack table for all blocker subsets */
        uint64_t subset = 0;
        do {
            uint64_t idx = (subset * me.magic) >> me.shift;
            me.attacks[idx] = sliding_attack(sq, subset, rook_dr, rook_dc, 4);
            subset = next_subset(subset, me.mask);
        } while(subset);

        rook_ptr += size;
    }

    /* Init bishop magics */
    static const int bishop_dr[4] = {-1, -1, 1, 1};
    static const int bishop_dc[4] = {-1,  1,-1, 1};
    uint64_t* bishop_ptr = bishop_table;

    for(int sq = 0; sq < 64; sq++){
        MagicEntry& me = bishop_magics[sq];
        me.mask = bishop_mask(sq);
        me.magic = BISHOP_MAGICS_KNOWN[sq];
        me.shift = BISHOP_SHIFTS[sq];
        me.attacks = bishop_ptr;

        int bits = 64 - me.shift;
        int size = 1 << bits;

        uint64_t subset = 0;
        do {
            uint64_t idx = (subset * me.magic) >> me.shift;
            me.attacks[idx] = sliding_attack(sq, subset, bishop_dr, bishop_dc, 4);
            subset = next_subset(subset, me.mask);
        } while(subset);

        bishop_ptr += size;
    }

    magic_ready = true;
}

static inline uint64_t rook_attacks_bb(int sq, uint64_t occ){
    MagicEntry& me = rook_magics[sq];
    return me.attacks[((occ & me.mask) * me.magic) >> me.shift];
}

static inline uint64_t bishop_attacks_bb(int sq, uint64_t occ){
    MagicEntry& me = bishop_magics[sq];
    return me.attacks[((occ & me.mask) * me.magic) >> me.shift];
}


/*============================================================
 * Zobrist hashing
 *============================================================*/
static uint64_t zobrist_piece[2][7][64];
static uint64_t zobrist_side;
static uint64_t zobrist_castle[16];
static uint64_t zobrist_ep[8];
static bool zobrist_ready = false;

static void init_zobrist(){
    uint64_t s = 0xDEADBEEFCAFEBABEULL;
    auto rand64 = [&s]() -> uint64_t {
        s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s;
    };
    for(int p = 0; p < 2; p++)
        for(int t = 0; t < 7; t++)
            for(int sq = 0; sq < 64; sq++)
                zobrist_piece[p][t][sq] = rand64();
    zobrist_side = rand64();
    for(int i = 0; i < 16; i++) zobrist_castle[i] = rand64();
    for(int i = 0; i < 8; i++) zobrist_ep[i] = rand64();
    zobrist_ready = true;
}

uint64_t State::compute_hash_full() const {
    if(!zobrist_ready) init_zobrist();
    uint64_t h = 0;
    for(int p = 0; p < 2; p++)
        for(int r = 0; r < 8; r++)
            for(int c = 0; c < 8; c++){
                int pt = board.board[p][r][c];
                if(pt) h ^= zobrist_piece[p][pt][SQ(r,c)];
            }
    if(player) h ^= zobrist_side;
    h ^= zobrist_castle[board.castling];
    if(board.ep_col >= 0) h ^= zobrist_ep[board.ep_col];
    return h;
}


/*============================================================
 * Evaluate — tapered eval (material + PST MG/EG + tropism)
 *
 * Game-agnostic: only this file is changed; search/base_state
 * interface is unchanged (returns int from side-to-move POV).
 *============================================================*/

/* Tropism: bonus for pieces close to enemy king (MG only) */
static const int tropism_weight[7] = {0, 0, 1, 2, 1, 3, 0};

int State::evaluate(
    bool use_nnue,
    bool use_kp_eval,
    bool use_mobility,
    const GameHistory* history
){
    (void)history;
    if(game_state == WIN) return P_MAX;
    if(game_state == DRAW) return 0;

#ifdef USE_NNUE
    if(use_nnue && nnue_available()){
        return nnue::g_model.evaluate(*this, player);
    }
#else
    (void)use_nnue;
#endif

    int self = player, oppn = 1 - player;
    int mg = 0, eg = 0;
    int phase = 0;

    /* Find king positions (for tropism) */
    int self_kr = 0, self_kc = 0, oppn_kr = 0, oppn_kc = 0;
    for(int r = 0; r < 8; r++){
        for(int c = 0; c < 8; c++){
            if(board.board[self][r][c] == KING){ self_kr = r; self_kc = c; }
            if(board.board[oppn][r][c] == KING){ oppn_kr = r; oppn_kc = c; }
        }
    }

    for(int r = 0; r < 8; r++){
        for(int c = 0; c < 8; c++){
            int pt;
            /* === Own pieces === */
            if((pt = board.board[self][r][c])){
                mg += mat_mg[pt];
                eg += mat_eg[pt];
                phase += phase_weight[pt];
                if(use_kp_eval && pt >= 1 && pt <= 6){
                    int pr = (self == 0) ? r : 7 - r;
                    mg += pst_mg[pt-1][pr][c];
                    eg += pst_eg[pt-1][pr][c];
                    /* King tropism (MG only) */
                    if(use_mobility && tropism_weight[pt]){
                        int dist = std::abs(r - oppn_kr) + std::abs(c - oppn_kc);
                        mg += tropism_weight[pt] * (14 - dist);
                    }
                }
            }
            /* === Opponent pieces === */
            if((pt = board.board[oppn][r][c])){
                mg -= mat_mg[pt];
                eg -= mat_eg[pt];
                phase += phase_weight[pt];
                if(use_kp_eval && pt >= 1 && pt <= 6){
                    int pr = (oppn == 0) ? r : 7 - r;
                    mg -= pst_mg[pt-1][pr][c];
                    eg -= pst_eg[pt-1][pr][c];
                    if(use_mobility && tropism_weight[pt]){
                        int dist = std::abs(r - self_kr) + std::abs(c - self_kc);
                        mg -= tropism_weight[pt] * (14 - dist);
                    }
                }
            }
        }
    }

    /* === Taper: interpolate between MG and EG === */
    /* phase: 0 = all pieces gone (endgame), TOTAL_PHASE = opening */
    if(phase > TOTAL_PHASE) phase = TOTAL_PHASE;
    int score = (mg * phase + eg * (TOTAL_PHASE - phase)) / TOTAL_PHASE;

    return score;
}


/*============================================================
 * Check repetition (3-fold draw)
 *============================================================*/
bool State::check_repetition(
    const GameHistory& history,
    int& out_score
) const {
    if(history.count(hash()) >= 3){
        out_score = 0;
        return true;
    }
    return false;
}


/*============================================================
 * Null move
 *============================================================*/
BaseState* State::create_null_state() const {
    Board nb = board;
    nb.ep_col = -1; /* clear en passant after null move */
    State* ns = new State(nb, 1 - player);
    ns->step = step + 1;
    ns->zobrist_valid = false;
    return ns;
}


/*============================================================
 * Build per-piece-type bitboards from board array
 *============================================================*/
struct PieceBB {
    uint64_t occ[2];     /* occupancy per player */
    uint64_t pawns[2];
    uint64_t knights[2];
    uint64_t bishops[2];
    uint64_t rooks[2];
    uint64_t queens[2];
    uint64_t kings[2];
    uint64_t all;
};

static PieceBB build_piece_bb(const Board& board){
    PieceBB bb = {};
    for(int p = 0; p < 2; p++){
        for(int r = 0; r < 8; r++){
            for(int c = 0; c < 8; c++){
                int pt = board.board[p][r][c];
                if(!pt) continue;
                uint64_t bit = 1ULL << SQ(r, c);
                bb.occ[p] |= bit;
                switch(pt){
                    case PAWN:   bb.pawns[p]   |= bit; break;
                    case KNIGHT: bb.knights[p]  |= bit; break;
                    case BISHOP: bb.bishops[p]  |= bit; break;
                    case ROOK:   bb.rooks[p]    |= bit; break;
                    case QUEEN:  bb.queens[p]   |= bit; break;
                    case KING:   bb.kings[p]    |= bit; break;
                }
            }
        }
    }
    bb.all = bb.occ[0] | bb.occ[1];
    return bb;
}


/*============================================================
 * is_square_attacked — using precomputed piece bitboards
 *============================================================*/
static bool is_square_attacked_bb(
    int sq,
    int attacker,
    const PieceBB& bb
){
    /* Pawn attacks: from defender's perspective */
    int defender = 1 - attacker;
    if(pawn_attacks[defender][sq] & bb.pawns[attacker]) return true;

    /* Knight */
    if(knight_attacks[sq] & bb.knights[attacker]) return true;

    /* King */
    if(king_attacks[sq] & bb.kings[attacker]) return true;

    /* Rook + Queen (orthogonal) */
    uint64_t rq = bb.rooks[attacker] | bb.queens[attacker];
    if(rook_attacks_bb(sq, bb.all) & rq) return true;

    /* Bishop + Queen (diagonal) */
    uint64_t bq = bb.bishops[attacker] | bb.queens[attacker];
    if(bishop_attacks_bb(sq, bb.all) & bq) return true;

    return false;
}

/* Convenience wrapper (builds bitboards on the fly — avoid in hot path) */
[[maybe_unused]]
static bool is_square_attacked(
    const Board& board,
    int sq,
    int attacker
){
    if(!magic_ready) init_magics();
    PieceBB bb = build_piece_bb(board);
    return is_square_attacked_bb(sq, attacker, bb);
}


/*============================================================
 * Move generation — naive (with castling, en passant, promotion)
 *============================================================*/
void State::get_legal_actions_naive(){
    if(!magic_ready) init_magics();
    game_state = NONE;
    legal_actions.clear();
    legal_actions.reserve(256);

    if(step >= MAX_STEP){
        game_state = DRAW;
        return;
    }

    int self = player, oppn = 1 - player;
    auto& self_board = board.board[self];
    auto& oppn_board = board.board[oppn];

    /* Precompute piece bitboards once for castling checks */
    PieceBB pbb = build_piece_bb(board);
    int pawn_dir = (self == 0) ? -1 : 1;
    int start_rank = (self == 0) ? 6 : 1;
    int promo_rank = (self == 0) ? 0 : 7;

    std::vector<Move> all_actions;
    all_actions.reserve(256);

    for(int r = 0; r < 8; r++){
        for(int c = 0; c < 8; c++){
            int piece = self_board[r][c];
            if(!piece) continue;

            switch(piece){
                case PAWN: {
                    int tr = r + pawn_dir;
                    /* Forward push */
                    if(tr >= 0 && tr < 8 && !self_board[tr][c] && !oppn_board[tr][c]){
                        if(tr == promo_rank){
                            for(int pi = 1; pi <= 4; pi++)
                                all_actions.push_back(Move(Point(r,c), Point(tr + 8*pi, c)));
                        }else{
                            all_actions.push_back(Move(Point(r,c), Point(tr, c)));
                        }
                        /* Double push from starting rank */
                        if(r == start_rank){
                            int tr2 = r + 2 * pawn_dir;
                            if(!self_board[tr2][c] && !oppn_board[tr2][c]){
                                all_actions.push_back(Move(Point(r,c), Point(tr2, c)));
                            }
                        }
                    }
                    /* Captures (including en passant) */
                    for(int dc = -1; dc <= 1; dc += 2){
                        int tc = c + dc;
                        if(tc < 0 || tc >= 8) continue;
                        if(tr >= 0 && tr < 8){
                            bool is_capture = (oppn_board[tr][tc] != 0);
                            bool is_ep = (tr == (self == 0 ? 2 : 5) && board.ep_col == tc);
                            if(is_capture || is_ep){
                                if(oppn_board[tr][tc] == KING){
                                    game_state = WIN;
                                    legal_actions.push_back(Move(Point(r,c), Point(tr, tc)));
                                    return;
                                }
                                if(tr == promo_rank){
                                    for(int pi = 1; pi <= 4; pi++)
                                        all_actions.push_back(Move(Point(r,c), Point(tr + 8*pi, tc)));
                                }else{
                                    all_actions.push_back(Move(Point(r,c), Point(tr, tc)));
                                }
                            }
                        }
                    }
                    break;
                }

                case KNIGHT: {
                    for(int d = 0; d < 8; d++){
                        int tr = r + knight_dr[d], tc = c + knight_dc[d];
                        if(tr < 0 || tr >= 8 || tc < 0 || tc >= 8) continue;
                        if(self_board[tr][tc]) continue;
                        if(oppn_board[tr][tc] == KING){
                            game_state = WIN;
                            legal_actions.push_back(Move(Point(r,c), Point(tr, tc)));
                            return;
                        }
                        all_actions.push_back(Move(Point(r,c), Point(tr, tc)));
                    }
                    break;
                }

                case KING: {
                    for(int d = 0; d < 8; d++){
                        int tr = r + dir8_dr[d], tc = c + dir8_dc[d];
                        if(tr < 0 || tr >= 8 || tc < 0 || tc >= 8) continue;
                        if(self_board[tr][tc]) continue;
                        if(oppn_board[tr][tc] == KING){
                            game_state = WIN;
                            legal_actions.push_back(Move(Point(r,c), Point(tr, tc)));
                            return;
                        }
                        all_actions.push_back(Move(Point(r,c), Point(tr, tc)));
                    }
                    /* Castling */
                    int king_row = (self == 0) ? 7 : 0;
                    if(r == king_row && c == 4){
                        /* Kingside */
                        int ks_flag = (self == 0) ? CASTLE_WK : CASTLE_BK;
                        if((board.castling & ks_flag)
                            && !self_board[king_row][5] && !oppn_board[king_row][5]
                            && !self_board[king_row][6] && !oppn_board[king_row][6]
                            && self_board[king_row][7] == ROOK
                            && !is_square_attacked_bb(SQ(king_row, 4), oppn, pbb)
                            && !is_square_attacked_bb(SQ(king_row, 5), oppn, pbb)
                            && !is_square_attacked_bb(SQ(king_row, 6), oppn, pbb)
                        ){
                            all_actions.push_back(Move(Point(r,c), Point(king_row, 6)));
                        }
                        /* Queenside */
                        int qs_flag = (self == 0) ? CASTLE_WQ : CASTLE_BQ;
                        if((board.castling & qs_flag)
                            && !self_board[king_row][3] && !oppn_board[king_row][3]
                            && !self_board[king_row][2] && !oppn_board[king_row][2]
                            && !self_board[king_row][1] && !oppn_board[king_row][1]
                            && self_board[king_row][0] == ROOK
                            && !is_square_attacked_bb(SQ(king_row, 4), oppn, pbb)
                            && !is_square_attacked_bb(SQ(king_row, 3), oppn, pbb)
                            && !is_square_attacked_bb(SQ(king_row, 2), oppn, pbb)
                        ){
                            all_actions.push_back(Move(Point(r,c), Point(king_row, 2)));
                        }
                    }
                    break;
                }

                case ROOK:
                case BISHOP:
                case QUEEN: {
                    int d_start = (piece == BISHOP) ? 4 : 0;
                    int d_end   = (piece == ROOK)   ? 4 : 8;
                    for(int d = d_start; d < d_end; d++){
                        int tr = r + dir8_dr[d], tc = c + dir8_dc[d];
                        while(tr >= 0 && tr < 8 && tc >= 0 && tc < 8){
                            if(self_board[tr][tc]) break;
                            if(oppn_board[tr][tc] == KING){
                                game_state = WIN;
                                legal_actions.push_back(Move(Point(r,c), Point(tr, tc)));
                                return;
                            }
                            all_actions.push_back(Move(Point(r,c), Point(tr, tc)));
                            if(oppn_board[tr][tc]) break;
                            tr += dir8_dr[d]; tc += dir8_dc[d];
                        }
                    }
                    break;
                }
            }
        }
    }

    legal_actions = all_actions;
}


/*============================================================
 * Bitboard move generation (TODO: magic-based)
 *============================================================*/
void State::get_legal_actions_bitboard(){
    /* For now, delegate to naive. Magic-based movegen can be
     * implemented later for performance. */
    get_legal_actions_naive();
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


/*============================================================
 * next_state — apply a move
 *============================================================*/
State* State::next_state(const Move& move){
    if(!zobrist_ready) init_zobrist();
    if(!magic_ready) init_magics();

    Board next = board;
    int fr = move.first.first, fc = move.first.second;
    int tr = move.second.first, tc = move.second.second;
    int self = player, oppn = 1 - self;

    /* Decode promotion */
    bool promote = (tr >= 8);
    int promo_piece = 0;
    if(promote){
        promo_piece = tr / 8; /* 1=Q, 2=R, 3=B, 4=N */
        tr = tr % 8;
    }

    int piece = next.board[self][fr][fc];
    int captured = next.board[oppn][tr][tc];

    /* Start incremental hash from current */
    uint64_t h = this->hash();
    h ^= zobrist_side; /* toggle side */
    h ^= zobrist_castle[board.castling]; /* will re-XOR new castling later */
    if(board.ep_col >= 0) h ^= zobrist_ep[board.ep_col]; /* remove old EP */

    /* XOR out piece from source */
    h ^= zobrist_piece[self][piece][SQ(fr, fc)];
    next.board[self][fr][fc] = 0;

    /* Handle en passant capture */
    if(piece == PAWN && tc != fc && captured == 0){
        h ^= zobrist_piece[oppn][PAWN][SQ(fr, tc)];
        next.board[oppn][fr][tc] = 0;
    }

    /* XOR out captured piece at destination */
    if(captured){
        h ^= zobrist_piece[oppn][captured][SQ(tr, tc)];
    }
    next.board[oppn][tr][tc] = 0;

    /* Place piece (or promoted piece) at destination */
    int placed;
    if(promote){
        static const int promo_map[5] = {0, QUEEN, ROOK, BISHOP, KNIGHT};
        placed = promo_map[promo_piece];
    }else{
        placed = piece;
    }
    next.board[self][tr][tc] = placed;
    h ^= zobrist_piece[self][placed][SQ(tr, tc)];

    /* Castling: move rook */
    if(piece == KING){
        int king_row = (self == 0) ? 7 : 0;
        if(fr == king_row && fc == 4){
            if(tc == 6){ /* kingside */
                h ^= zobrist_piece[self][ROOK][SQ(king_row, 7)];
                next.board[self][king_row][7] = 0;
                next.board[self][king_row][5] = ROOK;
                h ^= zobrist_piece[self][ROOK][SQ(king_row, 5)];
            }else if(tc == 2){ /* queenside */
                h ^= zobrist_piece[self][ROOK][SQ(king_row, 0)];
                next.board[self][king_row][0] = 0;
                next.board[self][king_row][3] = ROOK;
                h ^= zobrist_piece[self][ROOK][SQ(king_row, 3)];
            }
        }
    }

    /* Update castling rights */
    if(piece == KING){
        if(self == 0) next.castling &= ~(CASTLE_WK | CASTLE_WQ);
        else next.castling &= ~(CASTLE_BK | CASTLE_BQ);
    }
    if(piece == ROOK){
        if(self == 0 && fr == 7 && fc == 0) next.castling &= ~CASTLE_WQ;
        if(self == 0 && fr == 7 && fc == 7) next.castling &= ~CASTLE_WK;
        if(self == 1 && fr == 0 && fc == 0) next.castling &= ~CASTLE_BQ;
        if(self == 1 && fr == 0 && fc == 7) next.castling &= ~CASTLE_BK;
    }
    if(tr == 0 && tc == 0) next.castling &= ~CASTLE_BQ;
    if(tr == 0 && tc == 7) next.castling &= ~CASTLE_BK;
    if(tr == 7 && tc == 0) next.castling &= ~CASTLE_WQ;
    if(tr == 7 && tc == 7) next.castling &= ~CASTLE_WK;

    h ^= zobrist_castle[next.castling]; /* XOR in new castling */

    /* En passant target */
    next.ep_col = -1;
    if(piece == PAWN && std::abs(tr - fr) == 2){
        next.ep_col = fc;
        h ^= zobrist_ep[fc];
    }

    State* ns = new State(next, oppn);
    ns->step = step + 1;
    ns->zobrist_hash = h;
    ns->zobrist_valid = true;

    return ns;
}


/*============================================================
 * Display
 *============================================================*/
std::string State::cell_display(int row, int col) const {
    for(int p = 0; p < 2; p++){
        int pt = board.board[p][row][col];
        if(pt){
            return std::string(PIECE_TABLE[p][pt]) + " ";
        }
    }
    return " . ";
}

std::string State::encode_output() const {
    std::stringstream ss;
    for(int r = 0; r < 8; r++){
        int rank = 8 - r;
        ss << rank << " ";
        for(int c = 0; c < 8; c++){
            bool found = false;
            for(int p = 0; p < 2; p++){
                int pt = board.board[p][r][c];
                if(pt){
                    ss << PIECE_UNICODE[p][pt] << " ";
                    found = true;
                    break;
                }
            }
            if(!found) ss << ". ";
        }
        ss << rank << "\n";
    }
    ss << "  a b c d e f g h\n";
    ss << "Side: " << (player == 0 ? "White" : "Black")
       << " | Step: " << step;
    if(board.castling){
        ss << " | Castle: ";
        if(board.castling & CASTLE_WK) ss << "K";
        if(board.castling & CASTLE_WQ) ss << "Q";
        if(board.castling & CASTLE_BK) ss << "k";
        if(board.castling & CASTLE_BQ) ss << "q";
    }
    if(board.ep_col >= 0){
        ss << " | EP: " << (char)('a' + board.ep_col);
    }
    ss << "\n";
    return ss.str();
}


/*============================================================
 * Board encoding for UBGI protocol
 *============================================================*/
std::string State::encode_board() const {
    std::string s;
    for(int r = 0; r < 8; r++)
        for(int c = 0; c < 8; c++){
            int w = board.board[0][r][c];
            int b = board.board[1][r][c];
            if(w) s += ('0' + w);
            else if(b) s += ('0' + b + 6); /* 7-12 for black pieces */
            else s += '0';
        }
    s += ('0' + board.castling);
    s += (board.ep_col >= 0) ? ('a' + board.ep_col) : '-';
    return s;
}

void State::decode_board(const std::string& s, int side_to_move){
    player = side_to_move;
    game_state = UNKNOWN;
    zobrist_valid = false;
    std::memset(board.board, 0, sizeof(board.board));
    int idx = 0;
    for(int r = 0; r < 8; r++){
        for(int c = 0; c < 8; c++){
            if(idx >= (int)s.size()) break;
            int v = s[idx++] - '0';
            if(v >= 1 && v <= 6) board.board[0][r][c] = v;
            else if(v >= 7 && v <= 12) board.board[1][r][c] = v - 6;
        }
    }
    if(idx < (int)s.size()) board.castling = s[idx++] - '0';
    if(idx < (int)s.size()){
        char ep = s[idx++];
        board.ep_col = (ep == '-') ? -1 : (ep - 'a');
    }
}
