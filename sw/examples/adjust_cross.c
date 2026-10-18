// adjust_cross.c — time steps (TADJ) must neither skip nor repeat a deadline.
//
//   A  TRIG0 armed 6,000 ticks ahead, then time stepped FORWARD past it by
//      20,000: the deadline must still fire, once (late).
//   B  then time stepped BACK 40,000, behind the deadline that already fired:
//      it must not fire again.
//   C  TRIG1 armed 6,000 ahead, then time stepped BACK 3,000 before it fires:
//      it must fire once, 3,000 ticks later than it otherwise would.
// The testbench counts the pulses at the pins: expect exactly one on each.
#include <stdint.h>
#include "../tiqora.h"
#include "../tp_io.h"
#include "../tp_printf.h"
#ifndef BAUD_DIV
#define BAUD_DIV 434
#endif
int main(void) {
    UART_DIV = BAUD_DIV;
    // A: forward step past an armed deadline
    uint32_t d0 = tp_time() + 6000u;
    tp_arm(d0, 0);
    tp_adj(20000);
    uint32_t after_a = tp_time();
    // It must have fired AT the step, not merely at some point: a pulse count
    // alone cannot tell, because step B below rewinds time through the same
    // deadline, where a broken (equality) comparator would fire it instead.
    uint32_t armed_after_a = TP_STAT_ARMED(tp_stat()) & 1u;
    // B: backward step behind it, then give it ample time to (wrongly) refire
    tp_adj(-40000);
    tp_wait(tp_time() + 30000u);
    // C: backward step before a deadline is reached
    uint32_t d1 = tp_time() + 6000u;
    tp_arm(d1, 1);
    tp_adj(-3000);
    tp_wait(d1);                                   // in adjusted time: 3,000 ticks later
    uint32_t woke = tp_time();
    tp_printf("A: time stepped %u ticks past the deadline; still armed after the step: %u\n",
              after_a - d0, armed_after_a);
    tp_printf("C: woke %u ticks after its deadline\n", woke - d1);
    tp_printf("adjust done\n");
    uart_flush();
    return 0;
}
