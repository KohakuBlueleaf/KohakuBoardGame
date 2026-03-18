#include "../config.hpp"

#ifdef USE_NNUE

#include "nnue.hpp"
#include "compute.hpp"

#include <cstdio>
#include <cstring>

namespace nnue {

// -------------------------------------------------------------------------
// Embedded weights via .incbin
// -------------------------------------------------------------------------
// -------------------------------------------------------------------------
// Global instance
// -------------------------------------------------------------------------
Model g_model;

bool init(const char* path) {
    return g_model.load(path);
}

// -------------------------------------------------------------------------
// Constructor / Destructor
// -------------------------------------------------------------------------
Model::Model()
    : version(0), feature_size(0), accum_size(0), l1_size(0), l2_size(0)
    , ft_weight(nullptr), ft_bias(nullptr)
    , l1_weight(nullptr), l1_bias(nullptr)
    , l2_weight(nullptr), l2_bias(nullptr)
    , out_weight(nullptr), out_bias(nullptr)
{}

Model::~Model() {
    delete[] ft_weight;  delete[] ft_bias;
    delete[] l1_weight;  delete[] l1_bias;
    delete[] l2_weight;  delete[] l2_bias;
    delete[] out_weight; delete[] out_bias;
}

// -------------------------------------------------------------------------
// Allocate weight buffers
// -------------------------------------------------------------------------
static void alloc_weights(Model& m) {
    delete[] m.ft_weight;  delete[] m.ft_bias;
    delete[] m.l1_weight;  delete[] m.l1_bias;
    delete[] m.l2_weight;  delete[] m.l2_bias;
    delete[] m.out_weight; delete[] m.out_bias;

    m.ft_weight  = new float[m.feature_size * m.accum_size];
    m.ft_bias    = new float[m.accum_size];
    m.l1_weight  = new float[m.l1_size * m.accum_size * 2];
    m.l1_bias    = new float[m.l1_size];
    m.l2_weight  = new float[m.l2_size * m.l1_size];
    m.l2_bias    = new float[m.l2_size];
    m.out_weight = new float[m.l2_size];
    m.out_bias   = new float[1];
}

// -------------------------------------------------------------------------
// Load from file
// -------------------------------------------------------------------------
bool Model::load(const char* path) {
    FILE* f = std::fopen(path, "rb");
    if (!f) {
        std::fprintf(stderr, "nnue: cannot open '%s'\n", path);
        return false;
    }

    char magic[4];
    if (std::fread(magic, 1, 4, f) != 4 || std::memcmp(magic, "MCNN", 4) != 0) {
        std::fprintf(stderr, "nnue: bad magic in '%s'\n", path);
        std::fclose(f);
        return false;
    }

    auto read_i32 = [&](int& out) -> bool {
        int32_t v;
        if (std::fread(&v, sizeof(v), 1, f) != 1) return false;
        out = v;
        return true;
    };

    if (!read_i32(version) || !read_i32(feature_size) ||
        !read_i32(accum_size) || !read_i32(l1_size) || !read_i32(l2_size)) {
        std::fclose(f);
        return false;
    }

    alloc_weights(*this);

    auto read_floats = [&](float* dst, size_t n) -> bool {
        return std::fread(dst, sizeof(float), n, f) == n;
    };

    bool ok = true;
    ok = ok && read_floats(ft_weight,  (size_t)feature_size * accum_size);
    ok = ok && read_floats(ft_bias,    accum_size);
    ok = ok && read_floats(l1_weight,  (size_t)l1_size * accum_size * 2);
    ok = ok && read_floats(l1_bias,    l1_size);
    ok = ok && read_floats(l2_weight,  (size_t)l2_size * l1_size);
    ok = ok && read_floats(l2_bias,    l2_size);
    ok = ok && read_floats(out_weight, l2_size);
    ok = ok && read_floats(out_bias,   1);

    std::fclose(f);
    if (!ok) {
        std::fprintf(stderr, "nnue: truncated weights in '%s'\n", path);
        return false;
    }

    std::fprintf(stderr, "nnue: loaded %s (v%d, feat=%d, accum=%d)\n",
                 path, version, feature_size, accum_size);
    return true;
}

// -------------------------------------------------------------------------
// Load from memory buffer (for embedded weights)
// -------------------------------------------------------------------------
bool Model::load_from_memory(const unsigned char* data, size_t size) {
    if (size < 24 || std::memcmp(data, "MCNN", 4) != 0) {
        std::fprintf(stderr, "nnue: invalid embedded data\n");
        return false;
    }

    auto read_i32 = [&](size_t off) -> int {
        int32_t v;
        std::memcpy(&v, data + off, 4);
        return v;
    };

    version      = read_i32(4);
    feature_size = read_i32(8);
    accum_size   = read_i32(12);
    l1_size      = read_i32(16);
    l2_size      = read_i32(20);

    alloc_weights(*this);

    const float* ptr = reinterpret_cast<const float*>(data + 24);
    auto copy_floats = [&](float* dst, size_t n) {
        std::memcpy(dst, ptr, n * sizeof(float));
        ptr += n;
    };

    copy_floats(ft_weight,  (size_t)feature_size * accum_size);
    copy_floats(ft_bias,    accum_size);
    copy_floats(l1_weight,  (size_t)l1_size * accum_size * 2);
    copy_floats(l1_bias,    l1_size);
    copy_floats(l2_weight,  (size_t)l2_size * l1_size);
    copy_floats(l2_bias,    l2_size);
    copy_floats(out_weight, l2_size);
    copy_floats(out_bias,   1);

    std::fprintf(stderr, "nnue: loaded embedded (v%d, feat=%d, accum=%d)\n",
                 version, feature_size, accum_size);
    return true;
}

// -------------------------------------------------------------------------
// PS feature extraction
// -------------------------------------------------------------------------
int Model::extract_features_ps(const Board& board, int perspective, int* features) const {
    int count = 0;
    for (int color_plane = 0; color_plane < 2; ++color_plane) {
        for (int r = 0; r < BOARD_H; ++r) {
            for (int c = 0; c < BOARD_W; ++c) {
                int pt = board.board[color_plane][r][c];
                if (pt == 0) continue;
                int pt_idx = pt - 1;

                if (perspective == 0) {
                    int sq = r * BOARD_W + c;
                    features[count++] = color_plane * NUM_PIECE_TYPES * NUM_SQUARES
                                      + pt_idx * NUM_SQUARES + sq;
                } else {
                    int mir_r = BOARD_H - 1 - r;
                    int sq = mir_r * BOARD_W + c;
                    features[count++] = (1 - color_plane) * NUM_PIECE_TYPES * NUM_SQUARES
                                      + pt_idx * NUM_SQUARES + sq;
                }
            }
        }
    }
    return count;
}

// -------------------------------------------------------------------------
// HalfKP feature extraction
// -------------------------------------------------------------------------
int Model::extract_features_halfkp(const Board& board, int perspective, int* features) const {
    int count = 0;

    if (perspective == 0) {
        // White perspective — find white king square
        int king_sq = -1;
        for (int r = 0; r < BOARD_H; ++r)
            for (int c = 0; c < BOARD_W; ++c)
                if (board.board[0][r][c] == 6)
                    king_sq = r * BOARD_W + c;

        for (int color_plane = 0; color_plane < 2; ++color_plane) {
            for (int r = 0; r < BOARD_H; ++r) {
                for (int c = 0; c < BOARD_W; ++c) {
                    int pt = board.board[color_plane][r][c];
                    if (pt == 0 || pt == 6) continue;
                    int sq = r * BOARD_W + c;
                    features[count++] = king_sq * NUM_PIECE_FEATURES
                                      + color_plane * (NUM_PT_NO_KING * NUM_SQUARES)
                                      + (pt - 1) * NUM_SQUARES + sq;
                }
            }
        }
    } else {
        // Black perspective — find black king, mirror
        int king_sq_mir = -1;
        for (int r = 0; r < BOARD_H; ++r)
            for (int c = 0; c < BOARD_W; ++c)
                if (board.board[1][r][c] == 6)
                    king_sq_mir = (BOARD_H - 1 - r) * BOARD_W + c;

        for (int color_plane = 0; color_plane < 2; ++color_plane) {
            for (int r = 0; r < BOARD_H; ++r) {
                for (int c = 0; c < BOARD_W; ++c) {
                    int pt = board.board[color_plane][r][c];
                    if (pt == 0 || pt == 6) continue;
                    int mir_sq = (BOARD_H - 1 - r) * BOARD_W + c;
                    features[count++] = king_sq_mir * NUM_PIECE_FEATURES
                                      + (1 - color_plane) * (NUM_PT_NO_KING * NUM_SQUARES)
                                      + (pt - 1) * NUM_SQUARES + mir_sq;
                }
            }
        }
    }
    return count;
}

// -------------------------------------------------------------------------
// Forward pass
// -------------------------------------------------------------------------
int Model::evaluate(const Board& board, int player) const {
    int white_features[MAX_ACTIVE];
    int black_features[MAX_ACTIVE];
    int w_count, b_count;

    if (version == 1) {
        w_count = extract_features_ps(board, 0, white_features);
        b_count = extract_features_ps(board, 1, black_features);
    } else {
        w_count = extract_features_halfkp(board, 0, white_features);
        b_count = extract_features_halfkp(board, 1, black_features);
    }

    float w_accum[256], b_accum[256];
    accumulate_sparse(white_features, w_count, ft_weight, ft_bias, w_accum, accum_size);
    accumulate_sparse(black_features, b_count, ft_weight, ft_bias, b_accum, accum_size);

    screlu(w_accum, accum_size);
    screlu(b_accum, accum_size);

    float concat[512];
    if (player == 0) {
        std::memcpy(concat, w_accum, accum_size * sizeof(float));
        std::memcpy(concat + accum_size, b_accum, accum_size * sizeof(float));
    } else {
        std::memcpy(concat, b_accum, accum_size * sizeof(float));
        std::memcpy(concat + accum_size, w_accum, accum_size * sizeof(float));
    }

    float l1_out[128];
    linear_forward(concat, l1_weight, l1_bias, l1_out, accum_size * 2, l1_size);
    screlu(l1_out, l1_size);

    float l2_out[128];
    linear_forward(l1_out, l2_weight, l2_bias, l2_out, l1_size, l2_size);
    screlu(l2_out, l2_size);

    float raw_score;
    linear_forward(l2_out, out_weight, out_bias, &raw_score, l2_size, 1);

    return static_cast<int>(raw_score);
}

} // namespace nnue

#endif // USE_NNUE
