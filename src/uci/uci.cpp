// Standard headers.
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <mutex>
#include <chrono>
#include <algorithm>
#include <cstdlib>

#include "uci.hpp"
#include "../config.hpp"
#include "../search_types.hpp"
#include "../policy/registry.hpp"
#include "../policy/pvs/tt.hpp"

#ifdef USE_NNUE
#include "../nnue/nnue.hpp"
#endif

namespace uci {


/* === Global State === */

static Board              g_board;
static int                g_player = 0;
static int                g_step   = 0;
static const AlgoEntry*   g_algo   = nullptr;
static ParamMap            g_params;
static SearchContext       g_ctx;
static std::thread         g_search_thread;
static std::mutex          g_io_mutex;
static std::atomic<bool>   g_searching{false};
static Move                g_best_move;


/* === Helpers === */

static void send(const std::string& msg){
    std::lock_guard<std::mutex> lock(g_io_mutex);
    std::cout << msg << std::endl;
}


/* === Move Conversion === */

std::string move_to_str(const Move& m){
    char buf[5];
    buf[0] = 'a' + static_cast<char>(m.first.second);
    buf[1] = '6' - static_cast<char>(m.first.first);
    buf[2] = 'a' + static_cast<char>(m.second.second);
    buf[3] = '6' - static_cast<char>(m.second.first);
    buf[4] = '\0';
    return std::string(buf);
}

Move str_to_move(const std::string& s){
    size_t from_col = static_cast<size_t>(s[0] - 'a');
    size_t from_row = static_cast<size_t>('6' - s[1]);
    size_t to_col   = static_cast<size_t>(s[2] - 'a');
    size_t to_row   = static_cast<size_t>('6' - s[3]);
    return Move(Point(from_row, from_col), Point(to_row, to_col));
}


/* === Position Handling === */

void set_position(
    const std::string& line,
    Board& board,
    int& player,
    int& step
){
    Board start_board;
    board = start_board;
    player = 0;
    step = 0;

    std::istringstream iss(line);
    std::string token;
    iss >> token;  // "startpos"

    if(iss >> token && token == "moves"){
        std::string move_str;
        while(iss >> move_str){
            if(move_str.size() < 4){
                continue;
            }
            Move mv = str_to_move(move_str);
            State current(board, player);
            current.get_legal_actions();
            State* next = current.next_state(mv);
            board = next->board;
            player = next->player;
            step++;
            delete next;
        }
    }
}


/* === PV Formatting === */

static std::string format_pv(const std::vector<Move>& pv){
    std::string result;
    for(size_t i = 0; i < pv.size(); i++){
        if(i > 0){
            result += ' ';
        }
        result += move_to_str(pv[i]);
    }
    return result;
}


/* === Search Dispatch (worker thread) === */

/* === Search generation counter === */
// Each `go` increments this. The search thread checks it to know
// if it has been superseded (abandoned). If so, it silently exits
// without sending bestmove — the new search owns output now.
static std::atomic<uint32_t> g_search_gen{0};

static void do_search(
    int max_depth,
    int64_t movetime_ms,
    [[maybe_unused]] bool infinite,
    uint32_t my_gen,
    SearchContext ctx,
    Board board,
    int player
){
    State state(board, player);
    state.get_legal_actions();

    // Check if we've been superseded or stopped
    auto alive = [&](){
        if(my_gen != g_search_gen.load()){ return false; }
        if(g_ctx.stop){ ctx.stop = true; }  // propagate global stop to local ctx
        return !ctx.stop;
    };

    if(state.legal_actions.empty()){
        if(alive()){ send("bestmove 0000"); }
        g_searching = false;
        return;
    }
    if(state.game_state == WIN){
        if(alive()){ send("bestmove " + move_to_str(state.legal_actions[0])); }
        g_searching = false;
        return;
    }

    Move best_move = state.legal_actions[0];
    g_best_move = best_move;
    int depth_limit = (max_depth > 0) ? max_depth : 100;
    uint64_t total_nodes = 0;

    auto search_start = std::chrono::high_resolution_clock::now();

    /* === Root move partial-result callback === */
    ctx.on_root_update = [&](const RootUpdate& upd){
        if(my_gen != g_search_gen.load()){ return; }
        best_move = upd.best_move;
        g_best_move = upd.best_move;
        std::ostringstream oss;
        oss << "info depth " << upd.depth
            << " currmove " << move_to_str(upd.best_move)
            << " currmovenumber " << upd.move_number
            << " score cp " << upd.score;
        send(oss.str());
    };

    for(int depth = 1; depth <= depth_limit; depth++){
        if(!alive()){ break; }

        auto depth_start = std::chrono::high_resolution_clock::now();
        SearchResult result = g_algo->search(&state, depth, ctx);

        if(!alive() && depth > 1){ break; }

        auto now = std::chrono::high_resolution_clock::now();
        int64_t depth_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            now - depth_start
        ).count();
        int64_t total_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            now - search_start
        ).count();

        best_move = result.best_move;
        g_best_move = best_move;
        total_nodes += result.nodes;

        uint64_t nps = (depth_ms > 0)
            ? (result.nodes * 1000ULL / static_cast<uint64_t>(depth_ms))
            : 0;

        std::ostringstream info;
        info << "info depth " << depth
             << " seldepth " << result.seldepth
             << " score cp " << result.score
             << " nodes " << total_nodes
             << " time " << total_ms
             << " nps " << nps;
        if(!result.pv.empty()){
            info << " pv " << format_pv(result.pv);
        }

        if(alive()){ send(info.str()); }

        if(!alive()){ break; }
        if(movetime_ms > 0 && total_ms * 2 >= movetime_ms){ break; }
        if(result.score >= P_MAX - 100 || result.score <= M_MAX + 100){ break; }
    }

    if(alive()){ send("bestmove " + move_to_str(best_move)); }
    g_searching = false;
}


/* === Command: go === */

static void cmd_go(std::istringstream& iss){
    // Abandon any running search — don't block
    g_ctx.stop = true;
    g_search_gen++;  // old thread sees generation mismatch, exits silently
    if(g_search_thread.joinable()){
        g_search_thread.detach();
    }

    int max_depth = 0;
    int64_t movetime_ms = 0;
    bool infinite = false;

    std::string token;
    while(iss >> token){
        if(token == "depth"){
            iss >> max_depth;
        }else if(token == "movetime"){
            iss >> movetime_ms;
        }else if(token == "infinite"){
            infinite = true;
        }
    }

    if(max_depth == 0 && movetime_ms == 0 && !infinite){
        max_depth = 6;
    }

    SearchContext ctx;
    ctx.params = g_params;
    g_ctx.stop = false;
    g_searching = true;
    uint32_t gen = g_search_gen.load();
    g_best_move = Move();
    g_search_thread = std::thread(do_search, max_depth, movetime_ms, infinite, gen, ctx, g_board, g_player);
}


/* === Command: position === */

static void cmd_position(std::istringstream& iss){
    std::string rest;
    std::getline(iss, rest);
    size_t start = rest.find_first_not_of(' ');
    if(start != std::string::npos){
        rest = rest.substr(start);
    }
    set_position(rest, g_board, g_player, g_step);
}


/* === Command: setoption === */

static void cmd_setoption(std::istringstream& iss){
    std::string token, name, value;
    while(iss >> token){
        if(token == "name"){
            iss >> name;
        }else if(token == "value"){
            iss >> value;
        }
    }

    if(name == "Algorithm" || name == "algorithm"){
        std::string lower = value;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        const AlgoEntry* entry = find_algo(lower);
        if(entry){
            g_algo = entry;
            g_params = entry->default_params;
        }
    }else if(name == "Hash"){
        int bits = std::atoi(value.c_str());
        if(bits >= 10 && bits <= 24){
            tt_resize(bits);
            send("info string TT resized to 2^" + value + " entries");
        }
    }else if(name == "UseNNUE"){
        bool want = (value == "true" || value == "1");
        if(want && !nnue_available()){
            send("info string ERROR: NNUE not compiled in (build with USE_NNUE)");
        }else{
            g_params[name] = value;
        }
    }else{
        // Any param that's not Algorithm or Hash goes into the param map
        g_params[name] = value;
    }
}


/* === Command: d (debug display) === */

static void cmd_display(){
    std::ostringstream oss;
    oss << "\n  ";
    for(int c = 0; c < BOARD_W; c++){
        oss << " " << static_cast<char>('a' + c) << " ";
    }
    oss << "\n";

    for(int r = 0; r < BOARD_H; r++){
        int row_label = BOARD_H - r;
        oss << row_label << " ";
        for(int c = 0; c < BOARD_W; c++){
            int w = static_cast<int>(g_board.board[0][r][c]);
            int b = static_cast<int>(g_board.board[1][r][c]);
            if(w){
                const char* names = ".PRNBQK";
                oss << " " << names[w] << " ";
            }else if(b){
                const char* names = ".prnbqk";
                oss << " " << names[b] << " ";
            }else{
                oss << " . ";
            }
        }
        oss << " " << row_label << "\n";
    }

    oss << "  ";
    for(int c = 0; c < BOARD_W; c++){
        oss << " " << static_cast<char>('a' + c) << " ";
    }
    oss << "\n";

    oss << "Side to move: " << (g_player == 0 ? "white" : "black") << "\n";
    oss << "Step: " << g_step << "\n";
    oss << "Algorithm: " << g_algo->name << "\n";

    send(oss.str());
}


/* === Algorithm Option String === */

static std::string algo_option_str(){
    const auto& table = get_algo_table();
    std::string s = "option name Algorithm type combo default " + default_algo_name();
    for(auto& entry : table){
        s += " var " + entry.name;
    }
    return s;
}


/* === Main Loop === */

void loop(){
    std::cout << std::unitbuf;

    g_algo = find_algo(default_algo_name());
    g_params = g_algo->default_params;

    #ifdef USE_NNUE
    nnue::init();
    #endif

    std::string line;
    while(std::getline(std::cin, line)){
        if(!line.empty() && line.back() == '\r'){
            line.pop_back();
        }
        if(line.empty()){
            continue;
        }

        std::istringstream iss(line);
        std::string cmd;
        iss >> cmd;

        if(cmd == "uci"){
            send("id name MiniChess");
            send("id author MiniChess Team");
            send(algo_option_str());
            for(auto& pd : g_algo->param_defs){
                if(pd.type == ParamDef::CHECK){
                    send("option name " + pd.name + " type check default " + pd.default_val);
                }else{
                    send("option name " + pd.name + " type spin default " + pd.default_val
                         + " min " + std::to_string(pd.min_val) + " max " + std::to_string(pd.max_val));
                }
            }
            // Global options (not algo-specific)
            send("option name Hash type spin default 18 min 10 max 24");
            send("uciok");
        }else if(cmd == "isready"){
            send("readyok");
        }else if(cmd == "setoption"){
            cmd_setoption(iss);
        }else if(cmd == "position"){
            cmd_position(iss);
        }else if(cmd == "go"){
            cmd_go(iss);
        }else if(cmd == "stop"){
            g_ctx.stop = true;
            g_search_gen++;
            // Send bestmove immediately so the GUI isn't stuck waiting
            if(g_searching){
                // The old thread will exit silently (gen mismatch)
                Move bm = g_best_move;
                send("bestmove " + move_to_str(bm));
                g_searching = false;
            }
            if(g_search_thread.joinable()){
                g_search_thread.detach();
            }
        }else if(cmd == "d"){
            cmd_display();
        }else if(cmd == "quit"){
            g_ctx.stop = true;
            g_search_gen++;
            // Give the thread a moment to notice, then exit
            if(g_search_thread.joinable()){
                g_search_thread.detach();
            }
            break;
        }
    }

    // Don't join on exit — detached threads clean up on process exit
    if(g_search_thread.joinable()){
        g_search_thread.detach();
    }
}

} // namespace uci


/* === Entry Point === */

int main(){
    uci::loop();
    return 0;
}
