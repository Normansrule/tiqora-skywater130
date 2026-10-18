// tiqora_modes.h — CPU / GPU / TPU modes from C (TIQORA_MODES builds only:
// the Basys 3 FPGA and the full sky130 chip, not the Tiny Tapeout tile,
// where every instruction here is illegal).
//
// Stock toolchain, `.insn` directives, like tiqora.h. Opcodes:
//   custom-1 (0x2B)  MGET / MSET          legal in every mode
//   custom-2 (0x5B)  byte-lane SIMD       legal in GPU mode only
//   custom-3 (0x7B)  int8 dot-product MAC legal in TPU mode only
// An instruction outside its mode is skipped, leaves rd and the accumulator
// alone, and latches ILLEGAL (uo_out[6]). Semantics: docs/MODES.md.
#ifndef TIQORA_MODES_H
#define TIQORA_MODES_H

#include <stdint.h>

#define TP_MODE_CPU 0
#define TP_MODE_GPU 1
#define TP_MODE_TPU 2

// Current mode.
static inline uint32_t tp_mode(void) {
    uint32_t v;
    __asm__ volatile (".insn r 0x2B, 0, 0, %0, x0, x0" : "=r"(v));
    return v;
}

// Switch mode; returns the previous one. Commits at this instruction's
// boundary: the next instruction already runs in the new mode.
#define tp_mode_set(m) __extension__ ({                                          \
    uint32_t _old;                                                               \
    __asm__ volatile (".insn i 0x2B, 1, %0, x0, %1" : "=r"(_old) : "i"(m) : "memory"); \
    _old; })

// ---- GPU mode: four unsigned byte lanes per 32-bit word ----------------
#define TP_GPU_OP(name, f3)                                                      \
    static inline uint32_t name(uint32_t a, uint32_t b) {                        \
        uint32_t y;                                                              \
        __asm__ volatile (".insn r 0x5B, " #f3 ", 0, %0, %1, %2"                  \
                          : "=r"(y) : "r"(a), "r"(b));                           \
        return y;                                                                \
    }
TP_GPU_OP(tp_padd_b,   0)   // a + b        mod 256
TP_GPU_OP(tp_psub_b,   1)   // a - b        mod 256
TP_GPU_OP(tp_paddus_b, 2)   // a + b        saturating at 255
TP_GPU_OP(tp_pmaxu_b,  3)   // max(a, b)
TP_GPU_OP(tp_pminu_b,  4)   // min(a, b)
TP_GPU_OP(tp_pavgu_b,  5)   // (a + b + 1) / 2
TP_GPU_OP(tp_pmul_b,   6)   // low byte of a * b
TP_GPU_OP(tp_pabsd_b,  7)   // |a - b|
#undef TP_GPU_OP

// ---- TPU mode: one 32-bit accumulator, int8 x 4 dot products -------------
static inline void tp_tclr(void) {
    __asm__ volatile (".insn r 0x7B, 3, 0, x0, x0, x0" ::: "memory");
}
static inline void tp_tset(uint32_t v) {
    __asm__ volatile (".insn r 0x7B, 4, 0, x0, %0, x0" :: "r"(v) : "memory");
}
// acc += sum of signed(a.byte[i]) * signed(b.byte[i]), i = 0..3
static inline void tp_tmac(uint32_t a, uint32_t b) {
    __asm__ volatile (".insn r 0x7B, 0, 0, x0, %0, %1" :: "r"(a), "r"(b) : "memory");
}
static inline int32_t tp_trd(void) {
    int32_t v;
    __asm__ volatile (".insn r 0x7B, 1, 0, %0, x0, x0" : "=r"(v) :: "memory");
    return v;
}
static inline int32_t tp_trelu(void) {
    int32_t v;
    __asm__ volatile (".insn r 0x7B, 2, 0, %0, x0, x0" : "=r"(v) :: "memory");
    return v;
}

#endif
