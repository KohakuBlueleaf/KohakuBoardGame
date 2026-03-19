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
#include "./state/state.hpp"
#include "./policy/pvs.hpp"


/*============================================================
 * Binary format structures
 *============================================================*/
#pragma pack(push, 1)

struct DataHeader {
    char magic[4];     // "MCDT" (MiniChess Data Training)
    int32_t version;   // 1
    int32_t count;     // number of records (updated at end)
};

struct DataRecord {
    int8_t board[2][6][5];  // 60 bytes: both player boards
    int8_t player;          // 1 byte: side to move (0 or 1)
    int16_t score;          // 2 bytes: PVS score from side-to-move perspective
    int8_t result;          // 1 byte: game result from STM perspective (1=win, 0=draw, -1=loss)
    uint16_t ply;           // 2 bytes: ply count from game start
};

#pragma pack(pop)


/*============================================================
 * Progress bar
 *============================================================*/
static void print_progress(int games_done, int total_games, int total_positions, double elapsed_s){
    const int bar_width = 25;
    int filled = (games_done * bar_width) / total_games;

    char bar[bar_width + 1];
    for(int i = 0; i < bar_width; i++){
        if(i < filled){ bar[i] = '='; }
        else if(i == filled){ bar[i] = '>'; }
        else{ bar[i] = ' '; }
    }
    bar[bar_width] = '\0';

    double pos_per_s = (elapsed_s > 0.001) ? (total_positions / elapsed_s) : 0.0;

    std::fprintf(stderr, "\r[%s] %d/%d games | %d positions | %.1f pos/s",
                 bar, games_done, total_games, total_positions, pos_per_s);
    std::fflush(stderr);
}


/*============================================================
 * Random number helpers
 *============================================================*/
static unsigned int rng_state;

static void rng_seed(unsigned int seed){
    if(seed == 0){ seed = 1; }
    rng_state = seed;
}

/* Simple xorshift32 for fast, deterministic RNG */
static unsigned int rng_next(){
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 17;
    rng_state ^= rng_state << 5;
    return rng_state;
}

/* Returns a float in [0, 1) */
static double rng_float(){
    return (rng_next() & 0x7FFFFFFF) / (double)0x80000000;
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
    const char* output = "data/train.bin";
    unsigned int seed = 42;
};

static void print_usage(const char* prog){
    std::fprintf(stderr, "Usage: %s [options]\n", prog);
    std::fprintf(stderr, "  -n NUM_GAMES    Number of games (default: 1000)\n");
    std::fprintf(stderr, "  -d DEPTH        Search depth (default: 6)\n");
    std::fprintf(stderr, "  -e EPSILON      Jitter probability (default: 0.15)\n");
    std::fprintf(stderr, "  -o OUTPUT       Output file (default: data/train.bin)\n");
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
            case 'o': cfg.output = val; break;
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
    int winner = -1;  // -1=undecided, 0=white wins, 1=black wins, 2=draw

    int step = 0;
    while(step < MAX_STEP){
        /* Check for terminal state */
        if(game->game_state == WIN){
            winner = game->player;
            break;
        }
        if(game->game_state == DRAW){
            winner = 2;
            break;
        }
        if(game->legal_actions.empty()){
            winner = 2;
            break;
        }

        /* Decide which move to play */
        Move chosen_move;
        bool jitter = (rng_float() < cfg.epsilon);

        if(jitter){
            /* Random legal move */
            int idx = rng_int((int)game->legal_actions.size());
            chosen_move = game->legal_actions[idx];
        }else{
            /* PVS best move */
            SearchContext search_ctx;
            chosen_move = PVS::search(game, cfg.depth, search_ctx).best_move;
        }

        /* Make the move */
        State* next = game->next_state(chosen_move);
        step++;

        /* Record the position if it's not terminal */
        if(next->game_state != WIN){
            State* eval_copy = new State(next->board, next->player);
            eval_copy->get_legal_actions();

            SearchContext eval_ctx;
            int score = PVS::search(eval_copy, cfg.depth, eval_ctx).score;
            delete eval_copy;

            if(score > 32767){ score = 32767; }
            if(score < -32768){ score = -32768; }

            DataRecord rec;
            for(int p = 0; p < 2; p++){
                for(int r = 0; r < BOARD_H; r++){
                    for(int c = 0; c < BOARD_W; c++){
                        rec.board[p][r][c] = next->board.board[p][r][c];
                    }
                }
            }
            rec.player = (int8_t)next->player;
            rec.score = (int16_t)score;
            rec.result = 0;  // placeholder, filled below
            rec.ply = (uint16_t)step;
            records.push_back(rec);
        }

        delete game;
        game = next;
    }

    if(winner == -1){ winner = 2; }  // max steps reached -> draw

    /* Backfill game result for all positions in this game */
    for(size_t i = first_record; i < records.size(); i++){
        if(winner == 2){
            records[i].result = 0;   // draw
        }else if(records[i].player == winner){
            records[i].result = 1;   // STM won
        }else{
            records[i].result = -1;  // STM lost
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

    std::fprintf(stderr, "MiniChess Data Generator\n");
    std::fprintf(stderr, "  Games:   %d\n", cfg.num_games);
    std::fprintf(stderr, "  Depth:   %d\n", cfg.depth);
    std::fprintf(stderr, "  Epsilon: %.2f\n", cfg.epsilon);
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
    std::memcpy(header.magic, "MCDT", 4);
    header.version = 2;
    header.count = 0;
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
    std::fprintf(stderr, "  File size:        %.1f KB\n",
                 (sizeof(DataHeader) + (double)total_positions * sizeof(DataRecord)) / 1024.0);
    std::fprintf(stderr, "  Output:           %s\n", cfg.output);

    return 0;
}
