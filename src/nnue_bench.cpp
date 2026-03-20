// Build: make nnue_bench
// g++ --std=c++2a -O3 -march=native -o build/nnue_bench src/state/state.cpp src/nnue/nnue.cpp src/nnue_bench.cpp

#include "config.hpp"

#ifdef USE_NNUE

#include "./nnue/nnue.hpp"
#include "./nnue/compute.hpp"

// Optional SIMD / quantized headers — guarded so we compile without them
#if __has_include("./nnue/compute_simd.hpp")
#include "./nnue/compute_simd.hpp"
#define HAS_SIMD_HEADER 1
#else
#define HAS_SIMD_HEADER 0
#endif

#if __has_include("./nnue/compute_quant.hpp")
#include "./nnue/compute_quant.hpp"
#define HAS_QUANT_HEADER 1
#else
#define HAS_QUANT_HEADER 0
#endif

#include <cstdio>
#include <cstring>
#include <cmath>
#include <cstdint>
#include "timer/timer.hpp"

static inline int64_t now_ns(){ return hires_time(); }

// ---------------------------------------------------------------------------
// Board construction helper (same pattern as benchmark.cpp)
// ---------------------------------------------------------------------------
static Board make_board(const char w[6][5], const char b[6][5]){
    Board bd;
    for(int i = 0; i < BOARD_H; i++){
        for(int j = 0; j < BOARD_W; j++){
            bd.board[0][i][j] = w[i][j];
            bd.board[1][i][j] = b[i][j];
        }
    }
    return bd;
}

// ---------------------------------------------------------------------------
// Scalar float evaluate -- mirrors nnue::Model::evaluate() exactly,
// calling the functions from compute.hpp.
// ---------------------------------------------------------------------------
static int evaluate_scalar(const nnue::Model& m, const Board& board, int player){
    int white_features[NNUE_MAX_ACTIVE];
    int black_features[NNUE_MAX_ACTIVE];
    int w_count, b_count;

    if(m.version == 1){
        w_count = m.extract_features_ps(board, 0, white_features);
        b_count = m.extract_features_ps(board, 1, black_features);
    }else{
        w_count = m.extract_features_halfkp(board, 0, white_features);
        b_count = m.extract_features_halfkp(board, 1, black_features);
    }

    float w_accum[256], b_accum[256];
    nnue::accumulate_sparse(white_features, w_count, m.ft_weight, m.ft_bias, w_accum, m.accum_size);
    nnue::accumulate_sparse(black_features, b_count, m.ft_weight, m.ft_bias, b_accum, m.accum_size);

    nnue::screlu(w_accum, m.accum_size);
    nnue::screlu(b_accum, m.accum_size);

    float concat[512];
    if(player == 0){
        std::memcpy(concat, w_accum, m.accum_size * sizeof(float));
        std::memcpy(concat + m.accum_size, b_accum, m.accum_size * sizeof(float));
    }else{
        std::memcpy(concat, b_accum, m.accum_size * sizeof(float));
        std::memcpy(concat + m.accum_size, w_accum, m.accum_size * sizeof(float));
    }

    float l1_out[128];
    nnue::linear_forward(concat, m.l1_weight, m.l1_bias, l1_out, m.accum_size * 2, m.l1_size);
    nnue::screlu(l1_out, m.l1_size);

    float l2_out[128];
    nnue::linear_forward(l1_out, m.l2_weight, m.l2_bias, l2_out, m.l1_size, m.l2_size);
    nnue::screlu(l2_out, m.l2_size);

    float raw_score;
    nnue::linear_forward(l2_out, m.out_weight, m.out_bias, &raw_score, m.l2_size, 1);

    return static_cast<int>(raw_score);
}

// ---------------------------------------------------------------------------
// SIMD float evaluate
// ---------------------------------------------------------------------------
#if HAS_SIMD_HEADER && (defined(NNUE_NEON) || defined(NNUE_AVX2))
#define HAS_SIMD_EVAL 1

static int evaluate_simd(const nnue::Model& m, const Board& board, int player){
    int white_features[NNUE_MAX_ACTIVE];
    int black_features[NNUE_MAX_ACTIVE];
    int w_count, b_count;

    if(m.version == 1){
        w_count = m.extract_features_ps(board, 0, white_features);
        b_count = m.extract_features_ps(board, 1, black_features);
    }else{
        w_count = m.extract_features_halfkp(board, 0, white_features);
        b_count = m.extract_features_halfkp(board, 1, black_features);
    }

    float w_accum[256], b_accum[256];
    nnue::accumulate_sparse_simd(white_features, w_count, m.ft_weight, m.ft_bias, w_accum, m.accum_size);
    nnue::accumulate_sparse_simd(black_features, b_count, m.ft_weight, m.ft_bias, b_accum, m.accum_size);

    nnue::screlu_simd(w_accum, m.accum_size);
    nnue::screlu_simd(b_accum, m.accum_size);

    float concat[512];
    if(player == 0){
        std::memcpy(concat, w_accum, m.accum_size * sizeof(float));
        std::memcpy(concat + m.accum_size, b_accum, m.accum_size * sizeof(float));
    }else{
        std::memcpy(concat, b_accum, m.accum_size * sizeof(float));
        std::memcpy(concat + m.accum_size, w_accum, m.accum_size * sizeof(float));
    }

    float l1_out[128];
    nnue::linear_forward_simd(concat, m.l1_weight, m.l1_bias, l1_out, m.accum_size * 2, m.l1_size);
    nnue::screlu_simd(l1_out, m.l1_size);

    float l2_out[128];
    nnue::linear_forward_simd(l1_out, m.l2_weight, m.l2_bias, l2_out, m.l1_size, m.l2_size);
    nnue::screlu_simd(l2_out, m.l2_size);

    float raw_score;
    nnue::linear_forward_simd(l2_out, m.out_weight, m.out_bias, &raw_score, m.l2_size, 1);

    return static_cast<int>(raw_score);
}

#else
#define HAS_SIMD_EVAL 0
#endif // SIMD eval

// ---------------------------------------------------------------------------
// Quantized evaluate
// ---------------------------------------------------------------------------
#if HAS_QUANT_HEADER
#define HAS_QUANT_EVAL 1

// Quantized weight storage. Weights are quantized at startup from the float
// model. Dense layer weights are TRANSPOSED from the float layout:
//   float: (out_size, in_size) row-major
//   quant: (in_size, out_size) for the ikj "loop depack" access pattern
// used by linear_q.
struct QuantModel {
    int16_t* ft_weight;   // (feature_size, accum_size), scale QA
    int16_t* ft_bias;     // (accum_size), scale QA
    int8_t*  l1_weight;   // TRANSPOSED: (accum_size*2, l1_size), scale QB
    int32_t* l1_bias;     // (l1_size), scale QAQB
    int8_t*  l2_weight;   // TRANSPOSED: (l1_size, l2_size), scale QB
    int32_t* l2_bias;     // (l2_size), scale QAQB
    int8_t*  out_weight;  // TRANSPOSED: (l2_size, 1), scale QB
    int32_t* out_bias;    // (1), scale QAQB

    int accum_size;
    int l1_size;
    int l2_size;
    int feature_size;

    QuantModel() : ft_weight(nullptr), ft_bias(nullptr),
                   l1_weight(nullptr), l1_bias(nullptr),
                   l2_weight(nullptr), l2_bias(nullptr),
                   out_weight(nullptr), out_bias(nullptr) {}

    ~QuantModel(){
        delete[] ft_weight; delete[] ft_bias;
        delete[] l1_weight; delete[] l1_bias;
        delete[] l2_weight; delete[] l2_bias;
        delete[] out_weight; delete[] out_bias;
    }

    // Quantize from float model using helpers from compute_quant.hpp.
    void quantize_from(const nnue::Model& m){
        feature_size = m.feature_size;
        accum_size   = m.accum_size;
        l1_size      = m.l1_size;
        l2_size      = m.l2_size;

        // Feature transformer: float -> int16 (scale QA)
        size_t ft_total = (size_t)feature_size * accum_size;
        ft_weight = new int16_t[ft_total];
        ft_bias   = new int16_t[accum_size];
        nnue::quantize_ft(m.ft_weight, ft_weight, (int)ft_total);
        nnue::quantize_ft(m.ft_bias, ft_bias, accum_size);

        // L1: float (l1_size, accum_size*2) -> int8 TRANSPOSED (accum_size*2, l1_size)
        int l1_in = accum_size * 2;
        l1_weight = new int8_t[(size_t)l1_in * l1_size];
        l1_bias   = new int32_t[l1_size];
        // Transpose during quantization: src[o][i] -> dst[i][o]
        for(int o = 0; o < l1_size; o++){
            for(int i = 0; i < l1_in; i++){
                float v = m.l1_weight[o * l1_in + i];
                int q = static_cast<int>(std::round(v * nnue::QB));
                if(q < -128){
                    q = -128;
                }
                if(q > 127){
                    q = 127;
                }
                l1_weight[i * l1_size + o] = static_cast<int8_t>(q);
            }
        }
        nnue::quantize_dense_bias(m.l1_bias, l1_bias, l1_size);

        // L2: float (l2_size, l1_size) -> int8 TRANSPOSED (l1_size, l2_size)
        l2_weight = new int8_t[(size_t)l1_size * l2_size];
        l2_bias   = new int32_t[l2_size];
        for(int o = 0; o < l2_size; o++){
            for(int i = 0; i < l1_size; i++){
                float v = m.l2_weight[o * l1_size + i];
                int q = static_cast<int>(std::round(v * nnue::QB));
                if(q < -128){
                    q = -128;
                }
                if(q > 127){
                    q = 127;
                }
                l2_weight[i * l2_size + o] = static_cast<int8_t>(q);
            }
        }
        nnue::quantize_dense_bias(m.l2_bias, l2_bias, l2_size);

        // Output: float (1, l2_size) -> int8 TRANSPOSED (l2_size, 1)
        out_weight = new int8_t[l2_size];
        out_bias   = new int32_t[1];
        nnue::quantize_dense_weight(m.out_weight, out_weight, l2_size);
        nnue::quantize_dense_bias(m.out_bias, out_bias, 1);
    }
};

static int evaluate_quant(const nnue::Model& m, const QuantModel& qm,
                           const Board& board, int player){
    int white_features[NNUE_MAX_ACTIVE];
    int black_features[NNUE_MAX_ACTIVE];
    int w_count, b_count;

    if(m.version == 1){
        w_count = m.extract_features_ps(board, 0, white_features);
        b_count = m.extract_features_ps(board, 1, black_features);
    }else{
        w_count = m.extract_features_halfkp(board, 0, white_features);
        b_count = m.extract_features_halfkp(board, 1, black_features);
    }

    // FT: int16 sparse accumulation
    int16_t w_accum[256], b_accum[256];
    nnue::accumulate_sparse_q(white_features, w_count,
        qm.ft_weight, qm.ft_bias, w_accum, qm.accum_size);
    nnue::accumulate_sparse_q(black_features, b_count,
        qm.ft_weight, qm.ft_bias, b_accum, qm.accum_size);

    // SCReLU: int16 -> uint8
    uint8_t w_act[256], b_act[256];
    nnue::screlu_ft_q(w_accum, w_act, qm.accum_size);
    nnue::screlu_ft_q(b_accum, b_act, qm.accum_size);

    // Concat uint8 accumulators (stm first)
    uint8_t concat_q[512];
    int asize = qm.accum_size;
    if(player == 0){
        std::memcpy(concat_q, w_act, asize);
        std::memcpy(concat_q + asize, b_act, asize);
    }else{
        std::memcpy(concat_q, b_act, asize);
        std::memcpy(concat_q + asize, w_act, asize);
    }

    // L1: int8 x int8 -> int32, weight is transposed (in_size, out_size)
    int32_t l1_raw[128];
    nnue::linear_q(concat_q, qm.l1_weight, qm.l1_bias, l1_raw,
                   asize * 2, qm.l1_size);

    // SCReLU dense: int32 -> int8
    uint8_t l1_out_q[128];
    nnue::screlu_dense_q(l1_raw, l1_out_q, qm.l1_size);

    // L2: int8 x int8 -> int32
    int32_t l2_raw[128];
    nnue::linear_q(l1_out_q, qm.l2_weight, qm.l2_bias, l2_raw,
                   qm.l1_size, qm.l2_size);

    // SCReLU dense: int32 -> int8
    uint8_t l2_out_q[128];
    nnue::screlu_dense_q(l2_raw, l2_out_q, qm.l2_size);

    // Output layer: int8 x int8 -> int32
    int32_t out_raw;
    nnue::linear_q(l2_out_q, qm.out_weight, qm.out_bias, &out_raw,
                   qm.l2_size, 1);

    // Dequantize: raw / (QA_HIDDEN * QB) = raw / 8128
    return nnue::dequant_output(out_raw);
}

#else
#define HAS_QUANT_EVAL 0
#endif // HAS_QUANT_HEADER

// ---------------------------------------------------------------------------
// Test positions
// ---------------------------------------------------------------------------
struct TestPos {
    const char* name;
    Board board;
    int player;
};

static void make_positions(TestPos* positions){
    // 1. Starting position (default Board constructor)
    positions[0].name   = "starting";
    positions[0].board   = Board();
    positions[0].player  = 0;

    // 2. Midgame: some pieces traded, open files
    {
        const char w[6][5] = {
            {0,0,0,0,0}, {0,0,0,0,0}, {0,0,1,0,0},
            {0,1,0,0,0}, {0,0,0,0,1}, {2,0,0,5,6},
        };
        const char b[6][5] = {
            {6,5,0,0,2}, {1,0,0,0,0}, {0,0,0,1,0},
            {0,0,1,0,0}, {0,0,0,0,0}, {0,0,0,0,0},
        };
        positions[1].name   = "midgame";
        positions[1].board   = make_board(w, b);
        positions[1].player  = 0;
    }

    // 3. Endgame: very few pieces
    {
        const char w[6][5] = {
            {0,0,0,0,0}, {0,0,0,0,0}, {0,0,0,0,0},
            {0,0,1,0,0}, {0,0,0,0,0}, {0,0,0,2,6},
        };
        const char b[6][5] = {
            {6,0,2,0,0}, {0,0,0,0,0}, {0,1,0,0,0},
            {0,0,0,0,0}, {0,0,0,0,0}, {0,0,0,0,0},
        };
        positions[2].name   = "endgame";
        positions[2].board   = make_board(w, b);
        positions[2].player  = 0;
    }

    // 4. Midgame black to move
    {
        const char w[6][5] = {
            {0,0,0,0,0}, {0,0,0,0,0}, {0,0,0,4,0},
            {1,0,0,0,1}, {0,1,0,1,0}, {2,3,0,0,6},
        };
        const char b[6][5] = {
            {6,0,0,3,2}, {0,1,1,0,0}, {1,0,0,0,0},
            {0,0,0,4,0}, {0,0,0,0,0}, {0,0,0,0,0},
        };
        positions[3].name   = "mid_black";
        positions[3].board   = make_board(w, b);
        positions[3].player  = 1;
    }

    // 5. Near-endgame: kings + pawns only
    {
        const char w[6][5] = {
            {0,0,0,0,0}, {0,0,0,0,0}, {0,0,0,0,0},
            {0,1,0,1,0}, {0,0,0,0,0}, {0,0,6,0,0},
        };
        const char b[6][5] = {
            {0,0,6,0,0}, {0,0,0,0,0}, {0,1,0,1,0},
            {0,0,0,0,0}, {0,0,0,0,0}, {0,0,0,0,0},
        };
        positions[4].name   = "kp_endgame";
        positions[4].board   = make_board(w, b);
        positions[4].player  = 0;
    }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
int main(){
    // Load model
    nnue::Model model;
    if(!model.load(NNUE_FILE)){
        std::fprintf(stderr, "Failed to load NNUE model from %s\n", NNUE_FILE);
        return 1;
    }

    std::printf("=== NNUE Eval Benchmark ===\n");
    std::printf("Model: v%d, features=%d, accum=%d, l1=%d, l2=%d\n\n",
                model.version, model.feature_size, model.accum_size,
                model.l1_size, model.l2_size);

    // Prepare quantized model (if available)
#if HAS_QUANT_EVAL
    QuantModel qmodel;
    qmodel.quantize_from(model);
    std::printf("Quantized model prepared (QA=%d, QA_HIDDEN=%d, QB=%d, QAH_QB=%d).\n\n",
                (int)nnue::QA, (int)nnue::QA_HIDDEN, nnue::QB, nnue::QAH_QB);
#endif

    // Set up test positions
    constexpr int NUM_POS = 5;
    TestPos positions[NUM_POS];
    make_positions(positions);

    constexpr int N_ITERS = 1000000;

    // Accumulators for speedup summary
    double total_scalar_ns = 0;
    double total_simd_ns   = 0;
    double total_quant_ns  = 0;
    int simd_count  = 0;
    int quant_count = 0;

    for(int p = 0; p < NUM_POS; p++){
        const TestPos& pos = positions[p];
        std::printf("Position: %s (player=%d)\n", pos.name, pos.player);

        // --- Scalar float ---
        int score_scalar = 0;
        {
            // Warm up
            for(int i = 0; i < 1000; i++){
                score_scalar = evaluate_scalar(model, pos.board, pos.player);
            }

            int64_t t0 = now_ns();
            for(int i = 0; i < N_ITERS; i++){
                score_scalar = evaluate_scalar(model, pos.board, pos.player);
            }
            int64_t t1 = now_ns();

            double ns_per = (double)(t1 - t0) / N_ITERS;
            total_scalar_ns += ns_per;
            std::printf("  Scalar float:  %7.1f ns/eval, score=%d\n", ns_per, score_scalar);
        }

        // --- SIMD float ---
#if HAS_SIMD_EVAL
        int score_simd = 0;
        {
            for(int i = 0; i < 1000; i++){
                score_simd = evaluate_simd(model, pos.board, pos.player);
            }

            int64_t t0 = now_ns();
            for(int i = 0; i < N_ITERS; i++){
                score_simd = evaluate_simd(model, pos.board, pos.player);
            }
            int64_t t1 = now_ns();

            double ns_per = (double)(t1 - t0) / N_ITERS;
            total_simd_ns += ns_per;
            simd_count++;
            std::printf("  SIMD float:    %7.1f ns/eval, score=%d\n", ns_per, score_simd);

            // Correctness: SIMD must match scalar exactly
            if(score_simd != score_scalar){
                std::printf("  *** MISMATCH: scalar=%d, simd=%d ***\n",
                            score_scalar, score_simd);
            }else{
                std::printf("  [OK] SIMD matches scalar exactly.\n");
            }
        }
#else
        std::printf("  SIMD float:    (not available -- no NNUE_NEON/NNUE_AVX2)\n");
#endif

        // --- Quantized ---
#if HAS_QUANT_EVAL
        int score_quant = 0;
        {
            for(int i = 0; i < 1000; i++){
                score_quant = evaluate_quant(model, qmodel, pos.board, pos.player);
            }

            int64_t t0 = now_ns();
            for(int i = 0; i < N_ITERS; i++){
                score_quant = evaluate_quant(model, qmodel, pos.board, pos.player);
            }
            int64_t t1 = now_ns();

            double ns_per = (double)(t1 - t0) / N_ITERS;
            total_quant_ns += ns_per;
            quant_count++;
            std::printf("  Quantized:     %7.1f ns/eval, score=%d\n", ns_per, score_quant);

            // Correctness: quantized should be close (within +/- 5 centipawns)
            int diff = std::abs(score_quant - score_scalar);
            if(diff > 5){
                std::printf("  *** WARNING: quantized differs by %d cp (scalar=%d, quant=%d) ***\n",
                            diff, score_scalar, score_quant);
            }else{
                std::printf("  [OK] Quantized within +/-%d cp of scalar.\n", diff);
            }
        }
#else
        std::printf("  Quantized:     (not available -- no compute_quant.hpp)\n");
#endif

        std::printf("\n");
    }

    // --- Summary ---
    std::printf("=== Speedup Summary (averaged over %d positions) ===\n", NUM_POS);
    double avg_scalar = total_scalar_ns / NUM_POS;
    std::printf("  Scalar float:  %7.1f ns/eval (baseline)\n", avg_scalar);

    if(simd_count > 0){
        double avg_simd = total_simd_ns / simd_count;
        std::printf("  SIMD float:    %7.1f ns/eval, speedup=%.2fx\n",
                    avg_simd, avg_scalar / avg_simd);
    }else{
        std::printf("  SIMD float:    (not available)\n");
    }

    if(quant_count > 0){
        double avg_quant = total_quant_ns / quant_count;
        std::printf("  Quantized:     %7.1f ns/eval, speedup=%.2fx\n",
                    avg_quant, avg_scalar / avg_quant);
    }else{
        std::printf("  Quantized:     (not available)\n");
    }

    std::printf("\nDone.\n");
    return 0;
}

#else // !USE_NNUE

#include <cstdio>

int main(){
    std::printf("NNUE is disabled (USE_NNUE not defined). Nothing to benchmark.\n");
    return 0;
}

#endif // USE_NNUE
