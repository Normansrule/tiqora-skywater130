// wake_latency.c — how long after a TWAIT deadline does software resume?
//
// The deadline TRIGGER is exact: the comparator drives the pin on the deadline
// tick, whatever the CPU is doing. The CPU's own resumption is different: the
// nibble-serial core starts every instruction on phase 0 of its 8-clock
// register rotation, so the time from deadline to the next instruction depends
// on which phase the deadline falls on. This program measures it for deadlines
// on all 8 phases, twice each, and prints the spread.
#include <stdint.h>
#include "../tiqora.h"
#include "../tp_io.h"
#include "../tp_printf.h"
#ifndef BAUD_DIV
#define BAUD_DIV 434
#endif
int main(void) {
    UART_DIV = BAUD_DIV;
    pins_use_gpio(0xEF);
    uint32_t lo = 0xFFFFFFFFu, hi = 0, seen = 0;
    uint32_t t0 = tp_time();
    for (uint32_t i = 0; i < 16; i++) {
        uint32_t deadline = t0 + 20000u * (i + 1) + (i & 7u);   // every phase, twice
        tp_wait(deadline);
        uint32_t late = tp_time() - deadline;
        if (late < lo) lo = late;
        if (late > hi) hi = late;
        seen |= 1u << (late & 31u);
    }
    tp_printf("wake latency over 16 deadlines on all 8 phases: min %u, max %u clocks\n", lo, hi);
    uart_flush();
    return 0;
}
