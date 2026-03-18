#ifndef NNUE_COMPUTE_HPP
#define NNUE_COMPUTE_HPP

#include <cstring>

namespace nnue {

// Dense matrix-vector multiply with bias.
// Computes: output[o] = bias[o] + sum_i(weight[o * in_size + i] * input[i])
// Weight layout: (out_size, in_size) row-major (PyTorch nn.Linear default).
inline void linear_forward(
    const float* __restrict__ input,
    const float* __restrict__ weight,
    const float* __restrict__ bias,
    float* __restrict__ output,
    int in_size,
    int out_size)
{
    for (int o = 0; o < out_size; ++o) {
        float sum = bias[o];
        const float* row = weight + o * in_size;
        for (int i = 0; i < in_size; ++i) {
            sum += row[i] * input[i];
        }
        output[o] = sum;
    }
}

// Sparse feature accumulation for the feature transformer.
// Given a list of active feature indices, sums the corresponding weight rows
// onto the bias to produce the accumulator output.
// Computes: output[j] = bias[j] + sum_feat(weight[feat * accum_size + j])
// Weight layout: (feature_size, accum_size) row-major.
inline void accumulate_sparse(
    const int* __restrict__ features,
    int num_features,
    const float* __restrict__ weight,
    const float* __restrict__ bias,
    float* __restrict__ output,
    int accum_size)
{
    std::memcpy(output, bias, accum_size * sizeof(float));

    for (int f = 0; f < num_features; ++f) {
        const float* row = weight + features[f] * accum_size;
        for (int j = 0; j < accum_size; ++j) {
            output[j] += row[j];
        }
    }
}

// In-place Squared Clipped ReLU: x[i] = clamp(x[i], 0, 1)^2
inline void screlu(float* __restrict__ x, int size)
{
    for (int i = 0; i < size; ++i) {
        float v = x[i] < 0.0f ? 0.0f : (x[i] > 1.0f ? 1.0f : x[i]);
        x[i] = v * v;
    }
}

// Out-of-place Squared Clipped ReLU: output[i] = clamp(input[i], 0, 1)^2
inline void screlu_copy(
    const float* __restrict__ input,
    float* __restrict__ output,
    int size)
{
    for (int i = 0; i < size; ++i) {
        float v = input[i] < 0.0f ? 0.0f : (input[i] > 1.0f ? 1.0f : input[i]);
        output[i] = v * v;
    }
}

} // namespace nnue

#endif // NNUE_COMPUTE_HPP
