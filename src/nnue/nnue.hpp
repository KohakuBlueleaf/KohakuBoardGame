#pragma once

#include "config.hpp"

#ifdef USE_NNUE

#include "base_state.hpp"
#include "state.hpp"

namespace nnue {

// Constants derived from game config macros
constexpr int NUM_SQUARES = BOARD_H * BOARD_W;
constexpr int NUM_COLORS = 2;
#ifdef NNUE_NUM_PIECE_TYPES
constexpr int NUM_PIECE_TYPES = NNUE_NUM_PIECE_TYPES;
#else
constexpr int NUM_PIECE_TYPES = 6;
#endif
#ifdef NNUE_NUM_PT_NO_KING
constexpr int NUM_PT_NO_KING = NNUE_NUM_PT_NO_KING;
#else
constexpr int NUM_PT_NO_KING = 5;
#endif
constexpr int PS_SIZE = NUM_COLORS * NUM_PIECE_TYPES * NUM_SQUARES;
constexpr int NUM_PIECE_FEATURES = NUM_COLORS * NUM_PT_NO_KING * NUM_SQUARES;
constexpr int HALFKP_SIZE = NUM_SQUARES * NUM_PIECE_FEATURES;
constexpr int MAX_ACTIVE = 20;

struct Model {
    int version;
    int feature_size;
    int accum_size;
    int l1_size;
    int l2_size;

    float* ft_weight;
    float* ft_bias;
    float* l1_weight;
    float* l1_bias;
    float* l2_weight;
    float* l2_bias;
    float* out_weight;
    float* out_bias;

    Model();
    ~Model();
    Model(const Model&) = delete;
    Model& operator=(const Model&) = delete;

    bool load(const char* path);
    bool load_from_memory(const unsigned char* data, size_t size);
    int evaluate(const BaseState& state, int player) const;
    int extract_features_ps(const Board& board, int perspective, int* features) const;
    int extract_features_halfkp(const Board& board, int perspective, int* features) const;

    bool loaded() const { return ft_weight != nullptr; }
};

extern Model g_model;
bool init(const char* path = NNUE_FILE);

} // namespace nnue

#endif // USE_NNUE
