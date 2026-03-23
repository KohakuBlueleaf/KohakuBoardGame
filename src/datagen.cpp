/*
 * datagen.cpp -- Self-play data generator for NNUE training
 *
 * Plays self-play games using PVS, records (position, score) pairs
 * in a compact binary format for fast Python loading.
 *
 * Usage:
 *   ./build/datagen [options]
 *     -n NUM_GAMES    Number of games to play (default: 1000)
 *     -d DEPTH        Search depth (default: 6)
 *     -e EPSILON      Jitter probability (default: 0.15)
 *     -o OUTPUT       Output file path (default: data/train.bin)
 *     -s SEED         Random seed (default: 42)
 *
 * For multi-process parallelism, run multiple instances:
 *   ./build/datagen -n 500 -s 1 -o data/train_0.bin &
 *   ./build/datagen -n 500 -s 2 -o data/train_1.bin &
 *   wait
 */

#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <ctime>
#include <chrono>
#include <vector>

#include "config.hpp"
#include "state.hpp"
#include "./policy/pvs.hpp"
#include "./policy/game_history.hpp"

#ifdef USE_NNUE
#include "nnue/nnue.hpp"
#endif


/*============================================================
 * Binary format structures
 *============================================================*/
#pragma pack(push, 1)

struct DataHeader {
    char magic[4];       /* "BGDT" (Board Game Data Training) */
    int32_t version;     /* format version (5 = with hand) */
    int32_t count;       /* number of records (updated at end) */
    int16_t board_h;     /* board height */
    int16_t board_w;     /* board width */
    int16_t num_hand;    /* hand types per player (0 for no hand) */
    int16_t reserved;    /* padding for alignment */
    char game_name[16];  /* null-terminated game name string */
};

constexpr int NUM_SQUARES = BOARD_H * BOARD_W;

/* Max hand types across all games (for fixed record size) */
#ifndef NUM_HAND_TYPES
#define NUM_HAND_TYPES 0
#endif
constexpr int HAND_SIZE = NUM_HAND_TYPES;

struct DataRecord {
    int8_t board[2][BOARD_H][BOARD_W]; /* per-game board layout */
    int8_t hand[2][HAND_SIZE > 0 ? HAND_SIZE : 1]; /* hand pieces (unused slots = 0) */
    int8_t player;                     /* 1 byte: side to move (0 or 1) */
    int16_t score;                     /* 2 bytes: PVS score from STM perspective */
    int8_t result;                     /* 1 byte: game result from STM (1=win, 0=draw, -1=loss) */
    uint16_t ply;                      /* 2 bytes: ply count from game start */
    uint16_t best_move;                /* 2 bytes: encoded as from_sq*NUM_SQUARES+to_sq (0xFFFF = none) */
};

#pragma pack(pop)


/*============================================================
 * Progress bar
 *============================================================*/
static void print_progress(
    int games_done,
    int total_games,
    int total_positions,
    double elapsed_s
){
    const int bar_width = 25;
    int filled = (games_done * bar_width) / total_games;

    char bar[bar_width + 1];
    for(int i = 0; i < bar_width; i++){
        if(i < filled){
            bar[i] = '=';
        }else if(i == filled){
            bar[i] = '>';
        }else{
            bar[i] = ' ';
        }
    }
    bar[bar_width] = '\0';

    double pos_per_s = (elapsed_s > 0.001) ? (total_positions / elapsed_s) : 0.0;

    std::fprintf(
        stderr, "\r[%s] %d/%d games | %d positions | %.1f pos/s",
        bar, games_done, total_games, total_positions, pos_per_s
    );
    std::fflush(stderr);
}


/*============================================================
 * Random number helpers
 *============================================================*/
static unsigned int rng_state;

static void rng_seed(unsigned int seed){
    if(seed == 0){
        seed = 1;
    }
    rng_state = seed;
}

/* Simple xorshift32 for fast, deterministic RNG */
static unsigned int rng_next(){
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 17;
    rng_state ^= rng_state << 5;
    return rng_state;
}

/* Returns a random int in [0, n) */
static int rng_int(int n){
    return (int)(rng_next() % (unsigned int)n);
}


/*============================================================
 * Argument parsing
 *============================================================*/
struct Config {
    int num_games = 1000;
    int depth = 6;
    double epsilon = 0.15;
    int random_move_count = 8;   /* max random moves per game */
    int random_move_maxply = 24; /* only randomize within first N plies */
    const char* output = "data/train.bin";
    const char* nnue_model = nullptr;
    unsigned int seed = 42;
};

static void print_usage(const char* prog){
    std::fprintf(stderr, "Usage: %s [options]\n", prog);
    std::fprintf(stderr, "  -n NUM_GAMES    Number of games (default: 1000)\n");
    std::fprintf(stderr, "  -d DEPTH        Search depth (default: 6)\n");
    std::fprintf(stderr, "  -e EPSILON      Jitter probability (default: 0.15)\n");
    std::fprintf(stderr, "  -r RANDOM_MOVES Max random moves per game (default: 8)\n");
    std::fprintf(stderr, "  -p RANDOM_PLY   Only randomize within first N plies (default: 24)\n");
    std::fprintf(stderr, "  -o OUTPUT       Output file (default: data/train.bin)\n");
    std::fprintf(stderr, "  -m MODEL        NNUE model file (default: auto-detect)\n");
    std::fprintf(stderr, "  -s SEED         Random seed (default: 42)\n");
    std::fprintf(stderr, "  -h              Show this help\n");
}

static Config parse_args(int argc, char* argv[]){
    Config cfg;
    for(int i = 1; i < argc; i++){
        if(argv[i][0] != '-' || argv[i][1] == '\0'){
            std::fprintf(stderr, "Unknown argument: %s\n", argv[i]);
            print_usage(argv[0]);
            std::exit(1);
        }
        char flag = argv[i][1];
        if(flag == 'h'){
            print_usage(argv[0]);
            std::exit(0);
        }
        /* All other flags require a value */
        if(i + 1 >= argc){
            std::fprintf(stderr, "Missing value for -%c\n", flag);
            std::exit(1);
        }
        const char* val = argv[++i];
        switch(flag){
            case 'n': cfg.num_games = std::atoi(val); break;
            case 'd': cfg.depth = std::atoi(val); break;
            case 'e': cfg.epsilon = std::atof(val); break;
            case 'r': cfg.random_move_count = std::atoi(val); break;
            case 'p': cfg.random_move_maxply = std::atoi(val); break;
            case 'o': cfg.output = val; break;
            case 'm': cfg.nnue_model = val; break;
            case 's': cfg.seed = (unsigned int)std::atoi(val); break;
            default:
                std::fprintf(stderr, "Unknown flag: -%c\n", flag);
                print_usage(argv[0]);
                std::exit(1);
        }
    }
    return cfg;
}


/*============================================================
 * Play one self-play game, collecting (position, score) pairs
 *============================================================*/
static void play_game(
    const Config& cfg,
    std::vector<DataRecord>& records)
{
    State* game = new State();
    game->get_legal_actions();

    size_t first_record = records.size();
    int winner = -1;  /* -1=undecided, 0=player0, 1=player1, 2=draw */

    int step = 0;

    /* Game-level repetition tracking */
    GameHistory game_history;

    /* Stockfish-style: scatter random_move_count random plies
     * within [0, random_move_maxply) using Fisher-Yates shuffle. */
    bool random_ply_flag[MAX_STEP] = {};
    {
        int max_ply = std::min(cfg.random_move_maxply, MAX_STEP);
        std::vector<int> candidates;
        for(int i = 0; i < max_ply; i++){
            candidates.push_back(i);
        }
        int count = std::min(cfg.random_move_count, (int)candidates.size());
        for(int i = 0; i < count; i++){
            int j = i + rng_int((int)candidates.size() - i);
            std::swap(candidates[i], candidates[j]);
            random_ply_flag[candidates[i]] = true;
        }
    }
    while(step < MAX_STEP){
        /* Lazy move generation */
        if(game->legal_actions.empty() && game->game_state == UNKNOWN){
            game->get_legal_actions();
        }

        /* Check for terminal state */
        if(game->game_state == WIN){
            winner = game->player;
            break;
        }
        if(game->legal_actions.empty()){
            winner = 2;
            break;
        }

        /* 4-fold repetition check (game level) */
        {
            uint64_t h = game->hash();
            game_history.push(h);
            if(game_history.is_repetition(h)){
                winner = 2;  /* draw by repetition */
                break;
            }
        }

        /* Decide which move to play.
         * Stockfish-style: search ALWAYS runs (for score label).
         * On flagged plies, play a random legal move instead of
         * the search best move. Score is always from search. */
        Move chosen_move;
        int search_score = 0;

        SearchContext search_ctx;
        auto result = PVS::search(game, cfg.depth, game_history, search_ctx);
        search_score = result.score;

        if(step < MAX_STEP && random_ply_flag[step]){
            /* Flagged ply: play random legal move */
            int idx = rng_int((int)game->legal_actions.size());
            chosen_move = game->legal_actions[idx];
        }else{
            /* Normal ply: play search best move */
            chosen_move = result.best_move;
        }

        /* Make the move */
        State* next = game->next_state(chosen_move);
        step++;

        /* Lazy move generation for terminal detection */
        if(next->legal_actions.empty() && next->game_state == UNKNOWN){
            next->get_legal_actions();
        }

        /* Record position after the move with search score */
        if(next->game_state != WIN){
            /* search_score is from game->player perspective (before move),
               negate for next->player perspective (after move) */
            int score = -search_score;

            if(score > 32767){
                score = 32767;
            }
            if(score < -32768){
                score = -32768;
            }

            DataRecord rec;
            std::memset(&rec, 0, sizeof(rec));
            for(int p = 0; p < 2; p++){
                for(int r = 0; r < BOARD_H; r++){
                    for(int c = 0; c < BOARD_W; c++){
                        rec.board[p][r][c] = (int8_t)next->piece_at(p, r, c);
                    }
                }
            }
            /* Export hand pieces */
            for(int p = 0; p < 2; p++){
                for(int pt = 0; pt < HAND_SIZE; pt++){
                    rec.hand[p][pt] = (int8_t)next->hand_count(p, pt + 1);
                }
            }
            rec.player = (int8_t)next->player;
            rec.score = (int16_t)score;
            rec.result = 0;  /* placeholder, filled below */
            rec.ply = (uint16_t)step;

            /* Best move from the search (or the jittered move) */
            uint16_t encoded_move = 0xFFFF;
            if(chosen_move != Move()){
                int from_sq = chosen_move.first.first * BOARD_W + chosen_move.first.second;
                int to_sq = chosen_move.second.first * BOARD_W + chosen_move.second.second;
                encoded_move = (uint16_t)(from_sq * NUM_SQUARES + to_sq);
            }
            rec.best_move = encoded_move;

            records.push_back(rec);
        }

        delete game;
        game = next;
    }

    if(winner == -1){
        winner = 2;  /* max steps reached -> draw */
    }

    /* Backfill game result for all positions in this game */
    for(size_t i = first_record; i < records.size(); i++){
        if(winner == 2){
            records[i].result = 0;   /* draw */
        }else if(records[i].player == winner){
            records[i].result = 1;   /* STM won */
        }else{
            records[i].result = -1;  /* STM lost */
        }
    }

    delete game;
}


/*============================================================
 * Main
 *============================================================*/
int main(int argc, char* argv[]){
    Config cfg = parse_args(argc, argv);
    rng_seed(cfg.seed);
    /* Also seed stdlib rand (used by some engine internals) */
    srand(cfg.seed);

    /* Use a temporary State to get game_name at runtime */
    State temp_state;
    const char* gname = temp_state.game_name();

    /* Load NNUE model if available */
#ifdef USE_NNUE
    if(cfg.nnue_model){
        if(nnue::init(cfg.nnue_model)){
            std::fprintf(stderr, "NNUE loaded: %s\n", cfg.nnue_model);
        }else{
            std::fprintf(stderr, "Warning: failed to load NNUE from %s\n", cfg.nnue_model);
        }
    }else{
        if(nnue::init()){
            std::fprintf(stderr, "NNUE loaded: %s\n", NNUE_FILE);
        }
    }
#endif

    std::fprintf(stderr, "%s Data Generator\n", gname);
    std::fprintf(stderr, "  Games:   %d\n", cfg.num_games);
    std::fprintf(stderr, "  Depth:   %d\n", cfg.depth);
    std::fprintf(stderr, "  Random:  %d moves in first %d plies\n",
                 cfg.random_move_count, cfg.random_move_maxply);
    std::fprintf(stderr, "  Output:  %s\n", cfg.output);
    std::fprintf(stderr, "  Seed:    %u\n\n", cfg.seed);

    /* Open output file */
    FILE* fp = std::fopen(cfg.output, "wb");
    if(!fp){
        std::fprintf(stderr, "Error: cannot open %s for writing\n", cfg.output);
        return 1;
    }

    /* Write placeholder header (count will be updated at end) */
    DataHeader header;
    std::memset(&header, 0, sizeof(header));
    std::memcpy(header.magic, "BGDT", 4);
    header.version = 5;
    header.count = 0;
    header.board_h = (int16_t)BOARD_H;
    header.board_w = (int16_t)BOARD_W;
    header.num_hand = (int16_t)HAND_SIZE;
    header.reserved = 0;
    std::strncpy(header.game_name, gname, sizeof(header.game_name) - 1);
    std::fwrite(&header, sizeof(DataHeader), 1, fp);

    auto t_start = std::chrono::steady_clock::now();
    int total_positions = 0;

    for(int g = 0; g < cfg.num_games; g++){
        std::vector<DataRecord> records;
        records.reserve(MAX_STEP);

        play_game(cfg, records);

        /* Write records to file */
        if(!records.empty()){
            std::fwrite(records.data(), sizeof(DataRecord), records.size(), fp);
            total_positions += (int)records.size();
        }

        /* Update progress */
        auto t_now = std::chrono::steady_clock::now();
        double elapsed = std::chrono::duration<double>(t_now - t_start).count();
        print_progress(g + 1, cfg.num_games, total_positions, elapsed);
    }

    /* Update header with final count */
    header.count = total_positions;
    std::fseek(fp, 0, SEEK_SET);
    std::fwrite(&header, sizeof(DataHeader), 1, fp);
    std::fclose(fp);

    /* Final summary */
    auto t_end = std::chrono::steady_clock::now();
    double total_time = std::chrono::duration<double>(t_end - t_start).count();

    std::fprintf(stderr, "\n\nDone!\n");
    std::fprintf(stderr, "  Games played:     %d\n", cfg.num_games);
    std::fprintf(stderr, "  Positions saved:  %d\n", total_positions);
    std::fprintf(stderr, "  Avg pos/game:     %.1f\n", (double)total_positions / cfg.num_games);
    std::fprintf(stderr, "  Total time:       %.1f s\n", total_time);
    std::fprintf(stderr, "  Throughput:       %.1f pos/s\n", total_positions / total_time);
    std::fprintf(
        stderr, "  File size:        %.1f KB\n",
        (sizeof(DataHeader) + (double)total_positions * sizeof(DataRecord)) / 1024.0
    );
    std::fprintf(stderr, "  Output:           %s\n", cfg.output);

    return 0;
}
