// basys3_demo.c — Tiqora on a Basys 3, talking over the board's USB port.
//
//   * LED 0 blinks once a second, timed by the hardware timebase
//   * BTNL, BTNR, BTNU are capture inputs: each press and release is
//     timestamped by the hardware to the exact 20 ns clock tick
//   * mechanical buttons bounce; the timestamps make debouncing exact:
//     edges less than 10 ms after the previous one on that button are ignored
//   * anything you type is echoed back
// Open a terminal at 115200 baud on the Basys 3's USB serial port.
#include <stdint.h>
#include "../tiqora.h"
#include "../tp_io.h"
#include "../tp_printf.h"

#ifndef BAUD_DIV
#define BAUD_DIV 434                     // 115200 baud at 50 MHz
#endif
#ifndef HALF_SECOND
#define HALF_SECOND 25000000u            // timebase ticks (50 MHz)
#endif
#ifndef DEBOUNCE
#define DEBOUNCE 500000u                 // 10 ms
#endif

static const char *const names[8] = {"", "", "", "", "BTNL", "BTNR", "BTNU", ""};

int main(void) {
    UART_DIV = BAUD_DIV;
    GPIO_SEL = 0xFE;                     // LED 0 becomes a GPIO; the rest keep their functions
    tp_cfg((1u << 4) | (1u << 5) | (1u << 6) | (1u << 16));   // channels 4-6, both edges
    tp_printf("\nTiqora on Basys 3. Press BTNL, BTNR or BTNU, or type something.\n");

    uint32_t last[8] = {0};
    uint32_t seen = 0;                   // which channels have had an edge yet
    uint32_t next = tp_time() + HALF_SECOND;
    for (;;) {
        if ((int32_t)(tp_time() - next) >= 0) {        // LED 0: 1 Hz from the timebase
            GPIO_XOR = 1u;
            next += HALF_SECOND;
        }
        if (!TP_STAT_EMPTY(tp_stat())) {
            uint32_t e  = tp_pop();
            uint32_t ch = TP_EVT_CHANNEL(e);
            uint32_t t  = TP_EVT_TIMESTAMP(e);
            uint32_t since = (t - last[ch]) & 0x07FFFFFFu;  // timestamps are 27 bits
            if (!((seen >> ch) & 1u) || since >= DEBOUNCE) {
                tp_printf("%s %s at tick %u\n", names[ch][0] ? names[ch] : "input",
                          TP_EVT_RISING(e) ? "pressed " : "released", t);
            }
            last[ch] = t;
            seen |= 1u << ch;
        }
        if (uart_ready()) {
            char c = uart_getc();
            tp_printf("you typed '%c'\n", c);
        }
    }
}
