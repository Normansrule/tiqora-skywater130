// bench_kernel.c — a fixed workload for measuring the core's speed.
// A mix typical of control code: a checksum loop (loads, adds, shifts,
// branches), a sort (loads, stores, compares), and a CRC (shifts, XOR,
// branches). It prints one line so the run can be checked for correctness.
#include <stdint.h>
#include "../tiqora.h"
#include "../tp_io.h"
#ifndef BAUD_DIV
#define BAUD_DIV 434
#endif
static uint8_t data[64];
static uint32_t crc32(const uint8_t *p, int n) {
    uint32_t c = 0xFFFFFFFFu;
    for (int i = 0; i < n; i++) {
        c ^= p[i];
        for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1u)));
    }
    return ~c;
}
int main(void) {
    UART_DIV = BAUD_DIV;
    pins_use_gpio(0xEF);                         // keep UART TX only (and nothing is armed)
    uint32_t x = 12345;
    for (int i = 0; i < 64; i++) { x = x * 1103515245u + 12345u; data[i] = (uint8_t)(x >> 16); }
    for (int i = 1; i < 64; i++) {               // insertion sort
        uint8_t v = data[i]; int j = i - 1;
        while (j >= 0 && data[j] > v) { data[j + 1] = data[j]; j--; }
        data[j + 1] = v;
    }
    uint32_t sum = 0;
    for (int i = 0; i < 64; i++) sum = (sum << 1) + data[i] + (sum >> 31);
    uint32_t c = crc32(data, 64);
    uart_puthex(sum); uart_putc(' '); uart_puthex(c); uart_putc('\n');
    uart_flush();
    return 0;
}
