// mcu_e2e.c — the chip used the way a microcontroller is used.
//
// One C program, run from flash with a host on the serial line, that does
// what a first RP2040 project does: talk over the UART in both directions,
// read input pins, drive output pins, keep data in RAM, and time things.
// test/tb_mcu.sv is the host: it answers, moves pins, and checks every
// reply against what it saw on the pins (make mcu).
//
// The conversation, one line each way:
//   chip: ready                     host: any line of text
//   chip: the line, upper-cased     host: sets the input pins, sends 'g'
//   chip: in <hex>                  (then the output pins change 3 times)
//   chip: out                       (trigger 0 armed 20,000 ticks ahead)
//   chip: arm <tick>                host: checked the pin edge's tick
//   chip: cap?                      host: raises input 5 once
//   chip: cap <channel> <rising> <tick>
//   chip: mark <Y|N>   ram <Y|N>   done
#include <stdint.h>
#include "../tiqora.h"
#include "../tp_io.h"

#ifndef BAUD_DIV
#define BAUD_DIV 434                 // simulation builds pass 8
#endif

static uint32_t buf[256];            // .bss: lives in RAM A

int main(void) {
    UART_DIV = BAUD_DIV;
    GPIO_OUT = 0;
    GPIO_SEL = PIN_UART_TX | PIN_TRIG0;   // UART and trigger 0 on their pins, the rest GPIO

    // 1. UART both ways: echo one line, upper-cased
    uart_puts("ready\n");
    char c;
    while ((c = uart_getc()) != '\n')
        uart_putc(c >= 'a' && c <= 'z' ? c - 32 : c);
    uart_putc('\n');

    // 2. input pins
    (void)uart_getc();
    uart_puts("in "); uart_puthex(GPIO_IN & 0xFFu); uart_putc('\n');

    // 3. output pins: set, toggle, clear
    GPIO_SET = 0x81;                 // 0x81
    GPIO_XOR = 0x8A;                 // 0x0B: bits 7, 3 and 1 flip
    GPIO_CLR = 0x08;                 // 0x03
    uart_puts("out\n");

    // 4. a trigger edge on an exact tick, from C
    tp_pw(10);
    uint32_t d = tp_time() + 20000;
    tp_arm(d, 0);
    tp_wait(d + 50);
    uart_puts("arm "); uart_putu(d); uart_putc('\n');

    // 5. timestamp an input edge
    tp_cfg(1u << 5);                         // channel 5, rising edge only
    while (!TP_STAT_EMPTY(tp_stat())) (void)tp_pop();   // drop older captures
    uart_puts("cap?\n");
    while (TP_STAT_EMPTY(tp_stat())) { }
    uint32_t e = tp_pop();
    uart_puts("cap "); uart_putu(TP_EVT_CHANNEL(e)); uart_putc(' ');
    uart_putu(TP_EVT_RISING(e)); uart_putc(' ');
    uart_putu(TP_EVT_TIMESTAMP(e)); uart_putc('\n');

    // 6. a software mark goes through the same queue
    uint32_t m = tp_mark(3);
    e = tp_pop();
    uart_puts("mark ");
    uart_putc(TP_EVT_IS_SOFTWARE(e) && TP_EVT_CHANNEL(e) == 3 &&
              TP_EVT_TIMESTAMP(e) == (m & 0x07FFFFFFu) ? 'Y' : 'N');
    uart_putc('\n');

    // 7. RAM: 1 KB written and read back
    for (uint32_t i = 0; i < 256; i++) buf[i] = i * 0x01010101u ^ 0xA5A5A5A5u;
    uint32_t bad = 0;
    for (uint32_t i = 0; i < 256; i++) bad |= buf[i] ^ (i * 0x01010101u ^ 0xA5A5A5A5u);
    uart_puts("ram "); uart_putc(bad == 0 ? 'Y' : 'N'); uart_putc('\n');

    uart_puts("done\n");
    uart_flush();
    return 0;
}
