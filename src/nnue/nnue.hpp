#pragma once

#include "config.hpp"

#ifdef USE_NNUE

#include "base_state.hpp"

namespace nnue {

/* NNUE is game-agnostic. It receives sparse feature indices from
 * state.extract_nnue_features() and runs the forward pass.
 * Feature semantics (HalfKP, PS, etc.) are defined per-game. */

constexpr int MAX_ACTIVE = 32;

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

    /* Forward pass: calls state.extract_nnue_features() for feature indices,
     * then runs accumulator + hidden layers + output. */
    int evaluate(const BaseState& state, int player) const;

    bool loaded() const { return ft_weight != nullptr; }
};

extern Model g_model;
bool init(const char* path = NNUE_FILE);

} // namespace nnue

#endif // USE_NNUE
