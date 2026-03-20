#pragma once

#include "config.hpp"

#ifdef USE_NNUE

#include "base_state.hpp"
#include "state.hpp"

namespace nnue {

/* All dimensions come from the per-game config.hpp macros.
 * Games must define: BOARD_H, BOARD_W, NUM_PIECE_TYPES, NUM_PT_NO_KING.
 */
#define NNUE_NUM_SQUARES   (BOARD_H * BOARD_W)
#define NNUE_NUM_COLORS    2
#define NNUE_PS_SIZE       (NNUE_NUM_COLORS * NUM_PIECE_TYPES * NNUE_NUM_SQUARES)
#define NNUE_PIECE_FEATURES (NNUE_NUM_COLORS * NUM_PT_NO_KING * NNUE_NUM_SQUARES)
#define NNUE_HALFKP_SIZE   (NNUE_NUM_SQUARES * NNUE_PIECE_FEATURES)
#define NNUE_MAX_ACTIVE    32

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
