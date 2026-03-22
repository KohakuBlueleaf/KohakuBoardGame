#pragma once

/*
 * Quantized NNUE compute kernels (int16/int8) with NEON and AVX2 support.
 *
 * Quantization scheme (following Stockfish conventions):
 *
 *   QA        = 255   FT accumulator scale (int16)
 *   QA_HIDDEN = 127   Hidden activation scale (uint8)
 *   QB        = 64    Weight scale (WeightScaleBits = 6)
 *
 *   FT:    int16 weights/bias (scale QA=255), int16 accumulator
 *   SCReLU(FT):   clamp(x, 0, 255)^2 >> 9  → uint8 [0, 127]
 *   Dense: uint8 input (scale 127) × int8 weight (scale 64) → int32 (scale 8128)
 *          bias: int32 (scale 8128)
 *   SCReLU(dense): clamp(x, 0, 8128)^2 >> 19 → uint8 [0, 127]
 *   Output: int32 / 8128 → centipawns
 *
 * Key principle: downscaling happens INSIDE the activation function.
 * The >> 9 and >> 19 shifts cancel the accumulated scale factors.
 */

#include <cstdint>
#include <cstring>

#if defined(__ARM_NEON) || defined(__ARM_NEON__)
#include <arm_neon.h>
#ifndef NNUE_NEON
#define NNUE_NEON
#endif
#elif defined(__AVX2__)
#include <immintrin.h>
#ifndef NNUE_AVX2
#define NNUE_AVX2
#endif
#endif

namespace nnue {

// Quantization constants
constexpr int16_t QA        = 255;
constexpr int16_t QA_HIDDEN = 127;
constexpr int     QB        = 64;           // 1 << 6
constexpr int     WEIGHT_SCALE_BITS = 6;
constexpr int     QAH_QB    = QA_HIDDEN * QB;  // 8128

// =========================================================================
// Quantization helpers (called once at load time, scalar is fine)
// =========================================================================

inline void quantize_ft(const float* src, int16_t* dst, int count){
    for(int i = 0; i < count; ++i){
        int v = (int)(src[i] * QA + (src[i] >= 0 ? 0.5f : -0.5f));
        if(v > 32767){
            v = 32767;
        }
        if(v < -32768){
            v = -32768;
        }
        dst[i] = (int16_t)v;
    }
}

inline void quantize_dense_weight(const float* src, int8_t* dst, int count){
    for(int i = 0; i < count; ++i){
        int v = (int)(src[i] * QB + (src[i] >= 0 ? 0.5f : -0.5f));
        if(v > 127){
            v = 127;
        }
        if(v < -128){
            v = -128;
        }
        dst[i] = (int8_t)v;
    }
}

inline void quantize_dense_bias(const float* src, int32_t* dst, int count){
    for(int i = 0; i < count; ++i){
        dst[i] = (int32_t)(src[i] * QAH_QB + (src[i] >= 0 ? 0.5f : -0.5f));
    }
}

// Transpose (out_size, in_size) → (in_size, out_size) and quantize to int8
inline void transpose_and_quantize(
    const float* src,
    int8_t* dst,
    int out_size,
    int in_size
){
    for(int i = 0; i < in_size; ++i){
        for(int o = 0; o < out_size; ++o){
            float v = src[o * in_size + i];
            int q = (int)(v * QB + (v >= 0 ? 0.5f : -0.5f));
            if(q > 127){
                q = 127;
            }
            if(q < -128){
                q = -128;
            }
            dst[i * out_size + o] = (int8_t)q;
        }
    }
}

// =========================================================================
// FT sparse accumulation: int16 bias + sum of int16 weight rows
// =========================================================================
inline void accumulate_sparse_q(
    const int* __restrict__ features,
    int num_features,
    const int16_t* __restrict__ weight,
    const int16_t* __restrict__ bias,
    int16_t* __restrict__ output,
    int accum_size
){
    std::memcpy(output, bias, accum_size * sizeof(int16_t));

#ifdef NNUE_NEON
    for(int f = 0; f < num_features; ++f){
        const int16_t* row = weight + features[f] * accum_size;
        int j = 0;
        for(; j + 8 <= accum_size; j += 8){
            int16x8_t o = vld1q_s16(output + j);
            int16x8_t w = vld1q_s16(row + j);
            vst1q_s16(output + j, vaddq_s16(o, w));
        }
        for(; j < accum_size; ++j){
            output[j] += row[j];
        }
    }
#elif defined(NNUE_AVX2)
    for(int f = 0; f < num_features; ++f){
        const int16_t* row = weight + features[f] * accum_size;
        int j = 0;
        for(; j + 16 <= accum_size; j += 16){
            __m256i o = _mm256_loadu_si256((__m256i*)(output + j));
            __m256i w = _mm256_loadu_si256((__m256i*)(row + j));
            _mm256_storeu_si256((__m256i*)(output + j), _mm256_add_epi16(o, w));
        }
        for(; j < accum_size; ++j){
            output[j] += row[j];
        }
    }
#else
    for(int f = 0; f < num_features; ++f){
        const int16_t* row = weight + features[f] * accum_size;
        for(int j = 0; j < accum_size; ++j){
            output[j] += row[j];
        }
    }
#endif
}

// =========================================================================
// SCReLU after FT: int16 (scale QA=255) → uint8 (scale QA_HIDDEN=127)
//   output = min(127, clamp(x, 0, 255)^2 >> 9)
// =========================================================================
inline void screlu_ft_q(
    const int16_t* __restrict__ input,
    uint8_t* __restrict__ output,
    int size
){
#ifdef NNUE_NEON
    const int16x8_t zero = vdupq_n_s16(0);
    const int16x8_t qa = vdupq_n_s16(QA);
    const uint16x8_t max_out = vdupq_n_u16(QA_HIDDEN);
    int i = 0;
    for(; i + 8 <= size; i += 8){
        int16x8_t x = vld1q_s16(input + i);
        x = vmaxq_s16(x, zero);
        x = vminq_s16(x, qa);
        uint16x8_t xu = vreinterpretq_u16_s16(x);
        uint16x8_t sq = vmulq_u16(xu, xu);
        uint16x8_t shifted = vshrq_n_u16(sq, 9);
        shifted = vminq_u16(shifted, max_out);
        uint8x8_t narrow = vmovn_u16(shifted);
        vst1_u8(output + i, narrow);
    }
    for(; i < size; ++i){
        int v = input[i];
        if(v < 0){
            v = 0;
        }
        if(v > QA){
            v = QA;
        }
        int sq = (v * v) >> 9;
        output[i] = (uint8_t)(sq > QA_HIDDEN ? QA_HIDDEN : sq);
    }
#elif defined(NNUE_AVX2)
    const __m256i zero = _mm256_setzero_si256();
    const __m256i qa = _mm256_set1_epi16(QA);
    const __m256i max_out = _mm256_set1_epi16(QA_HIDDEN);
    int i = 0;
    for(; i + 16 <= size; i += 16){
        __m256i x = _mm256_loadu_si256((__m256i*)(input + i));
        x = _mm256_max_epi16(x, zero);
        x = _mm256_min_epi16(x, qa);
        __m256i sq = _mm256_mullo_epi16(x, x);
        __m256i shifted = _mm256_srli_epi16(sq, 9);
        shifted = _mm256_min_epi16(shifted, max_out);
        __m256i packed = _mm256_packus_epi16(shifted, zero);
        packed = _mm256_permute4x64_epi64(packed, 0xD8);
        _mm_storeu_si128(
            (__m128i*)(output + i),
            _mm256_castsi256_si128(packed)
        );
    }
    for(; i < size; ++i){
        int v = input[i];
        if(v < 0){
            v = 0;
        }
        if(v > QA){
            v = QA;
        }
        int sq = (v * v) >> 9;
        output[i] = (uint8_t)(sq > QA_HIDDEN ? QA_HIDDEN : sq);
    }
#else
    for(int i = 0; i < size; ++i){
        int v = input[i];
        if(v < 0){
            v = 0;
        }
        if(v > QA){
            v = QA;
        }
        int sq = (v * v) >> 9;
        output[i] = (uint8_t)(sq > QA_HIDDEN ? QA_HIDDEN : sq);
    }
#endif
}

// =========================================================================
// Dense linear: uint8 input × int8 weight → int32 output
// Weight layout: (in_size, out_size) — TRANSPOSED for ikj "loop depack"
// =========================================================================
inline void linear_q(
    const uint8_t* __restrict__ input,
    const int8_t* __restrict__ weight,
    const int32_t* __restrict__ bias,
    int32_t* __restrict__ output,
    int in_size,
    int out_size
){
    std::memcpy(output, bias, out_size * sizeof(int32_t));

#ifdef NNUE_NEON
    for(int k = 0; k < in_size; ++k){
        int16_t val = (int16_t)input[k];
        const int8_t* wk = weight + k * out_size;
        int16x8_t vval = vdupq_n_s16(val);
        int j = 0;
        for(; j + 8 <= out_size; j += 8){
            int8x8_t w8 = vld1_s8(wk + j);
            int16x8_t w16 = vmovl_s8(w8);
            int16x8_t prod = vmulq_s16(vval, w16);
            int32x4_t lo = vld1q_s32(output + j);
            int32x4_t hi = vld1q_s32(output + j + 4);
            lo = vaddw_s16(lo, vget_low_s16(prod));
            hi = vaddw_s16(hi, vget_high_s16(prod));
            vst1q_s32(output + j, lo);
            vst1q_s32(output + j + 4, hi);
        }
        for(; j < out_size; ++j){
            output[j] += val * (int16_t)wk[j];
        }
    }
#elif defined(NNUE_AVX2)
    for(int k = 0; k < in_size; ++k){
        int16_t val = (int16_t)input[k];
        const int8_t* wk = weight + k * out_size;
        __m256i vval = _mm256_set1_epi16(val);
        int j = 0;
        for(; j + 16 <= out_size; j += 16){
            __m128i w8 = _mm_loadu_si128((__m128i*)(wk + j));
            __m256i w16 = _mm256_cvtepi8_epi16(w8);
            __m256i prod = _mm256_mullo_epi16(vval, w16);
            __m128i prod_lo = _mm256_castsi256_si128(prod);
            __m128i prod_hi = _mm256_extracti128_si256(prod, 1);
            __m256i p32_lo = _mm256_cvtepi16_epi32(prod_lo);
            __m256i p32_hi = _mm256_cvtepi16_epi32(prod_hi);
            __m256i o_lo = _mm256_loadu_si256((__m256i*)(output + j));
            __m256i o_hi = _mm256_loadu_si256((__m256i*)(output + j + 8));
            _mm256_storeu_si256((__m256i*)(output + j), _mm256_add_epi32(o_lo, p32_lo));
            _mm256_storeu_si256((__m256i*)(output + j + 8), _mm256_add_epi32(o_hi, p32_hi));
        }
        for(; j < out_size; ++j){
            output[j] += val * (int16_t)wk[j];
        }
    }
#else
    for(int k = 0; k < in_size; ++k){
        int16_t val = (int16_t)input[k];
        const int8_t* wk = weight + k * out_size;
        for(int j = 0; j < out_size; ++j){
            output[j] += val * (int16_t)wk[j];
        }
    }
#endif
}

// =========================================================================
// SCReLU after dense: int32 (scale 8128) → uint8 (scale 127)
//   output = min(127, clamp(x, 0, 8128)^2 >> 19)
// Size is small (32), scalar is fine.
// =========================================================================
inline void screlu_dense_q(
    const int32_t* __restrict__ input,
    uint8_t* __restrict__ output,
    int size
){
    for(int i = 0; i < size; ++i){
        int32_t v = input[i];
        if(v < 0){
            v = 0;
        }
        if(v > QAH_QB){
            v = QAH_QB;
        }
        int32_t sq = ((int64_t)v * v) >> 19;
        if(sq > QA_HIDDEN){
            sq = QA_HIDDEN;
        }
        output[i] = (uint8_t)sq;
    }
}

// =========================================================================
// Dequantize final output: int32 (scale QAH_QB=8128) → centipawns
// =========================================================================
inline int dequant_output(int32_t raw){
    return (int)(raw / QAH_QB);
}

} // namespace nnue
