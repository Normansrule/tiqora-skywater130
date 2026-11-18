// branch_mix.c — forward branches, taken and not taken, for the branch
// prefetch check (make branch). A forward branch prefetches its fall-through
// word; when it is taken the fetch in flight is aborted. The inline assembly
// pins down the cases the compiler might not produce on its own: a taken
// branch to the very next word (the target is where the aborted stream
// stood), a taken branch over one instruction, and a branch right after a
// load. test/branch_check.py computes the expected checksum in Python.
#include <stdint.h>
#include "../tiqora.h"
#include "../tp_io.h"
#ifndef BAUD_DIV
#define BAUD_DIV 434
#endif
static volatile uint32_t tbl[8] = {
    0x00000000u, 0x7FFFFFFFu, 0x80000000u, 0xFFFFFFFFu,
    0x12345678u, 0x9ABCDEF0u, 0x00000001u, 0xC0000000u };

static uint32_t asm_mix(uint32_t x, const volatile uint32_t *p) {
    uint32_t r = 0;
    __asm__ volatile (
        "andi t0, %[x], 3\n"
        "beqz t0, 1f\n"          // forward, taken one time in four
        "addi %[r], %[r], 1\n"
        "1:\n"
        "beq  zero, zero, 2f\n"  // always taken, target = the next word
        "2:\n"
        "andi t0, %[x], 8\n"
        "bnez t0, 3f\n"          // taken half the time, skips one instruction
        "addi %[r], %[r], 16\n"
        "3:\n"
        "lw   t1, 0(%[p])\n"
        "bltu t1, %[x], 4f\n"    // a branch right after a load
        "addi %[r], %[r], 256\n"
        "4:\n"
        : [r] "+r" (r)
        : [x] "r" (x), [p] "r" (p)
        : "t0", "t1", "memory");
    return r;
}

int main(void) {
    UART_DIV = BAUD_DIV;
    pins_use_gpio(0xEF);
    uint32_t x = 1, acc = 0;
    for (uint32_t i = 0; i < 160; i++) {
        x = x * 1664525u + 1013904223u;
        if (x & 1u) acc += x; else acc ^= x >> 3;
        if ((int32_t)x < 0) acc = (acc << 1) | (acc >> 31);
        if ((x & 6u) == 2u) acc += 7u;
        acc += asm_mix(x, &tbl[i & 7u]);
    }
    uart_puthex(acc); uart_putc('\n');
    uart_flush();
    return 0;
}
