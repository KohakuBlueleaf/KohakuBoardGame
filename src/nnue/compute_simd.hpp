#pragma once
#ifndef NNUE_COMPUTE_SIMD_HPP
#define NNUE_COMPUTE_SIMD_HPP

// =========================================================================
// Vectorized float32 NNUE compute kernels.
//
// Platform detection:
//   - ARM NEON  (AArch64 / ARMv7 with NEON)
//   - x86 AVX2  (with FMA)
//   - Scalar fallback (delegates to compute.hpp)
//
// Compile with: -O3 -march=native
// =========================================================================

#include "compute.hpp"   // scalar fallback
#include <cstring>

// ---------------------------------------------------------------------------
// Platform detection
// ---------------------------------------------------------------------------
#if defined(__ARM_NEON) || defined(__ARM_NEON__)
  #include <arm_neon.h>
  #define NNUE_NEON
#elif defined(__AVX2__)
  #include <immintrin.h>
  #define NNUE_AVX2
#endif

namespace nnue {

// =========================================================================
// 1. accumulate_sparse_simd
//
// For each active feature index, adds the corresponding weight row to the
// output accumulator (which starts as a copy of bias).
//
// Weight layout: (feature_size, accum_size) row-major.
// output[j] = bias[j] + sum_{f in features} weight[f * accum_size + j]
// =========================================================================
inline void accumulate_sparse_simd(
    const int* __restrict__ features,
    int num_features,
    const float* __restrict__ weight,
    const float* __restrict__ bias,
    float* __restrict__ output,
    int accum_size)
{
    #if defined(NNUE_NEON)
    // -- NEON: 4 floats per vector register ----------------------------------
    std::memcpy(output, bias, accum_size * sizeof(float));

    for(int f = 0; f < num_features; ++f){
        const float* row = weight + features[f] * accum_size;
        int j = 0;

        // Main loop: 4 floats at a time
        for(; j + 3 < accum_size; j += 4){
            float32x4_t acc = vld1q_f32(output + j);
            float32x4_t w   = vld1q_f32(row + j);
            acc = vaddq_f32(acc, w);
            vst1q_f32(output + j, acc);
        }

        // Remainder (safety, should not trigger when accum_size % 4 == 0)
        for(; j < accum_size; ++j){
            output[j] += row[j];
        }
    }

    #elif defined(NNUE_AVX2)
    // -- AVX2: 8 floats per vector register ----------------------------------
    std::memcpy(output, bias, accum_size * sizeof(float));

    for(int f = 0; f < num_features; ++f){
        const float* row = weight + features[f] * accum_size;
        int j = 0;

        // Main loop: 8 floats at a time
        for(; j + 7 < accum_size; j += 8){
            __m256 acc = _mm256_loadu_ps(output + j);
            __m256 w   = _mm256_loadu_ps(row + j);
            acc = _mm256_add_ps(acc, w);
            _mm256_storeu_ps(output + j, acc);
        }

        // Remainder: 4 floats (SSE)
        for(; j + 3 < accum_size; j += 4){
            __m128 acc = _mm_loadu_ps(output + j);
            __m128 w   = _mm_loadu_ps(row + j);
            acc = _mm_add_ps(acc, w);
            _mm_storeu_ps(output + j, acc);
        }

        // Scalar tail
        for(; j < accum_size; ++j){
            output[j] += row[j];
        }
    }

    #else
    // -- Scalar fallback -----------------------------------------------------
    accumulate_sparse(features, num_features, weight, bias, output, accum_size);
    #endif
}

// =========================================================================
// 2. linear_forward_simd
//
// Dense matrix-vector multiply with bias (vectorized dot product per row).
//
// Computes: output[o] = bias[o] + dot(weight[o*in_size .. (o+1)*in_size], input)
// Weight layout: (out_size, in_size) row-major (standard PyTorch nn.Linear).
//
// Strategy: for each output neuron, compute a vectorized dot product of the
// weight row with the input vector, then horizontally reduce.
// =========================================================================
inline void linear_forward_simd(
    const float* __restrict__ input,
    const float* __restrict__ weight,
    const float* __restrict__ bias,
    float* __restrict__ output,
    int in_size,
    int out_size)
{
    #if defined(NNUE_NEON)
    // -- NEON: vectorized dot product per output row -------------------------
    for(int o = 0; o < out_size; ++o){
        const float* row = weight + o * in_size;

        // Accumulate in up to 4 vector accumulators for ILP
        float32x4_t sum0 = vdupq_n_f32(0.0f);
        float32x4_t sum1 = vdupq_n_f32(0.0f);
        float32x4_t sum2 = vdupq_n_f32(0.0f);
        float32x4_t sum3 = vdupq_n_f32(0.0f);

        int i = 0;

        // Unrolled main loop: 16 floats per iteration
        for(; i + 15 < in_size; i += 16){
            float32x4_t r0 = vld1q_f32(row + i);
            float32x4_t x0 = vld1q_f32(input + i);
            sum0 = vfmaq_f32(sum0, r0, x0);

            float32x4_t r1 = vld1q_f32(row + i + 4);
            float32x4_t x1 = vld1q_f32(input + i + 4);
            sum1 = vfmaq_f32(sum1, r1, x1);

            float32x4_t r2 = vld1q_f32(row + i + 8);
            float32x4_t x2 = vld1q_f32(input + i + 8);
            sum2 = vfmaq_f32(sum2, r2, x2);

            float32x4_t r3 = vld1q_f32(row + i + 12);
            float32x4_t x3 = vld1q_f32(input + i + 12);
            sum3 = vfmaq_f32(sum3, r3, x3);
        }

        // Remaining groups of 4
        for(; i + 3 < in_size; i += 4){
            float32x4_t r = vld1q_f32(row + i);
            float32x4_t x = vld1q_f32(input + i);
            sum0 = vfmaq_f32(sum0, r, x);
        }

        // Collapse 4 accumulators into one
        sum0 = vaddq_f32(sum0, sum1);
        sum2 = vaddq_f32(sum2, sum3);
        sum0 = vaddq_f32(sum0, sum2);

        // Horizontal reduce: sum all 4 lanes
        float result = vaddvq_f32(sum0);

        // Scalar tail
        for(; i < in_size; ++i){
            result += row[i] * input[i];
        }

        output[o] = bias[o] + result;
    }

    #elif defined(NNUE_AVX2)
    // -- AVX2: vectorized dot product per output row -------------------------
    for(int o = 0; o < out_size; ++o){
        const float* row = weight + o * in_size;

        // Accumulate in 4 vector accumulators for ILP
        __m256 sum0 = _mm256_setzero_ps();
        __m256 sum1 = _mm256_setzero_ps();
        __m256 sum2 = _mm256_setzero_ps();
        __m256 sum3 = _mm256_setzero_ps();

        int i = 0;

        // Unrolled main loop: 32 floats per iteration
        for(; i + 31 < in_size; i += 32){
            __m256 r0 = _mm256_loadu_ps(row + i);
            __m256 x0 = _mm256_loadu_ps(input + i);
            sum0 = _mm256_fmadd_ps(r0, x0, sum0);

            __m256 r1 = _mm256_loadu_ps(row + i + 8);
            __m256 x1 = _mm256_loadu_ps(input + i + 8);
            sum1 = _mm256_fmadd_ps(r1, x1, sum1);

            __m256 r2 = _mm256_loadu_ps(row + i + 16);
            __m256 x2 = _mm256_loadu_ps(input + i + 16);
            sum2 = _mm256_fmadd_ps(r2, x2, sum2);

            __m256 r3 = _mm256_loadu_ps(row + i + 24);
            __m256 x3 = _mm256_loadu_ps(input + i + 24);
            sum3 = _mm256_fmadd_ps(r3, x3, sum3);
        }

        // Remaining groups of 8
        for(; i + 7 < in_size; i += 8){
            __m256 r = _mm256_loadu_ps(row + i);
            __m256 x = _mm256_loadu_ps(input + i);
            sum0 = _mm256_fmadd_ps(r, x, sum0);
        }

        // Collapse 4 accumulators
        sum0 = _mm256_add_ps(sum0, sum1);
        sum2 = _mm256_add_ps(sum2, sum3);
        sum0 = _mm256_add_ps(sum0, sum2);

        // Horizontal sum of 8 floats in __m256
        // Step 1: high 128 + low 128
        __m128 hi  = _mm256_extractf128_ps(sum0, 1);
        __m128 lo  = _mm256_castps256_ps128(sum0);
        __m128 s   = _mm_add_ps(lo, hi);
        // Step 2: horizontal add pairs
        s = _mm_hadd_ps(s, s);
        s = _mm_hadd_ps(s, s);

        float result = _mm_cvtss_f32(s);

        // Remaining 4-wide (SSE)
        for(; i + 3 < in_size; i += 4){
            __m128 r = _mm_loadu_ps(row + i);
            __m128 x = _mm_loadu_ps(input + i);
            __m128 p = _mm_mul_ps(r, x);
            // Horizontal sum
            p = _mm_hadd_ps(p, p);
            p = _mm_hadd_ps(p, p);
            result += _mm_cvtss_f32(p);
        }

        // Scalar tail
        for(; i < in_size; ++i){
            result += row[i] * input[i];
        }

        output[o] = bias[o] + result;
    }

    #else
    // -- Scalar fallback -----------------------------------------------------
    linear_forward(input, weight, bias, output, in_size, out_size);
    #endif
}

// =========================================================================
// 3. screlu_simd  (in-place)
//
// x[i] = clamp(x[i], 0, 1) ^ 2
// =========================================================================
inline void screlu_simd(float* __restrict__ x, int size)
{
    #if defined(NNUE_NEON)
    // -- NEON ----------------------------------------------------------------
    const float32x4_t zero = vdupq_n_f32(0.0f);
    const float32x4_t one  = vdupq_n_f32(1.0f);

    int i = 0;
    for(; i + 3 < size; i += 4){
        float32x4_t v = vld1q_f32(x + i);
        v = vmaxq_f32(v, zero);    // clamp lower
        v = vminq_f32(v, one);     // clamp upper
        v = vmulq_f32(v, v);       // square
        vst1q_f32(x + i, v);
    }

    // Scalar remainder
    for(; i < size; ++i){
        float v = x[i] < 0.0f ? 0.0f : (x[i] > 1.0f ? 1.0f : x[i]);
        x[i] = v * v;
    }

    #elif defined(NNUE_AVX2)
    // -- AVX2 ----------------------------------------------------------------
    const __m256 zero = _mm256_setzero_ps();
    const __m256 one  = _mm256_set1_ps(1.0f);

    int i = 0;
    for(; i + 7 < size; i += 8){
        __m256 v = _mm256_loadu_ps(x + i);
        v = _mm256_max_ps(v, zero);    // clamp lower
        v = _mm256_min_ps(v, one);     // clamp upper
        v = _mm256_mul_ps(v, v);       // square
        _mm256_storeu_ps(x + i, v);
    }

    // SSE remainder (4 floats)
    for(; i + 3 < size; i += 4){
        __m128 v = _mm_loadu_ps(x + i);
        v = _mm_max_ps(v, _mm_setzero_ps());
        v = _mm_min_ps(v, _mm_set1_ps(1.0f));
        v = _mm_mul_ps(v, v);
        _mm_storeu_ps(x + i, v);
    }

    // Scalar tail
    for(; i < size; ++i){
        float v = x[i] < 0.0f ? 0.0f : (x[i] > 1.0f ? 1.0f : x[i]);
        x[i] = v * v;
    }

    #else
    // -- Scalar fallback -----------------------------------------------------
    screlu(x, size);
    #endif
}

// =========================================================================
// 4. screlu_copy_simd  (out-of-place)
//
// output[i] = clamp(input[i], 0, 1) ^ 2
// =========================================================================
inline void screlu_copy_simd(
    const float* __restrict__ input,
    float* __restrict__ output,
    int size)
{
    #if defined(NNUE_NEON)
    // -- NEON ----------------------------------------------------------------
    const float32x4_t zero = vdupq_n_f32(0.0f);
    const float32x4_t one  = vdupq_n_f32(1.0f);

    int i = 0;
    for(; i + 3 < size; i += 4){
        float32x4_t v = vld1q_f32(input + i);
        v = vmaxq_f32(v, zero);
        v = vminq_f32(v, one);
        v = vmulq_f32(v, v);
        vst1q_f32(output + i, v);
    }

    for(; i < size; ++i){
        float v = input[i] < 0.0f ? 0.0f : (input[i] > 1.0f ? 1.0f : input[i]);
        output[i] = v * v;
    }

    #elif defined(NNUE_AVX2)
    // -- AVX2 ----------------------------------------------------------------
    const __m256 zero = _mm256_setzero_ps();
    const __m256 one  = _mm256_set1_ps(1.0f);

    int i = 0;
    for(; i + 7 < size; i += 8){
        __m256 v = _mm256_loadu_ps(input + i);
        v = _mm256_max_ps(v, zero);
        v = _mm256_min_ps(v, one);
        v = _mm256_mul_ps(v, v);
        _mm256_storeu_ps(output + i, v);
    }

    for(; i + 3 < size; i += 4){
        __m128 v = _mm_loadu_ps(input + i);
        v = _mm_max_ps(v, _mm_setzero_ps());
        v = _mm_min_ps(v, _mm_set1_ps(1.0f));
        v = _mm_mul_ps(v, v);
        _mm_storeu_ps(output + i, v);
    }

    for(; i < size; ++i){
        float v = input[i] < 0.0f ? 0.0f : (input[i] > 1.0f ? 1.0f : input[i]);
        output[i] = v * v;
    }

    #else
    // -- Scalar fallback -----------------------------------------------------
    screlu_copy(input, output, size);
    #endif
}

} // namespace nnue

#endif // NNUE_COMPUTE_SIMD_HPP
