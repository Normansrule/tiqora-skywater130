// modes_demo.c — one program, four modes: CPU -> GPU -> TPU -> CPU.
//
// Needs a TIQORA_MODES build (the Basys 3 bitstream, or `make -C fpga/basys3
// sim`). Every accelerated result is computed twice, once by the accelerator
// and once by plain C in CPU mode, and the program says whether they agree.
// The printed numbers are checked again, independently, by
// sw/check_modes_demo.py with sw/modes_model.py.
//
// What each mode does here:
//   GPU  four RGBA pixels from two images: average (blend), saturating add
//        (brighten) and absolute difference (motion), four channels per
//        instruction.
//   TPU  a 4-output, 8-input int8 neural-network layer: y = ReLU(W x), four
//        multiply-accumulates per TMAC.
#include <stdint.h>
#include "../tiqora.h"
#include "../tiqora_modes.h"
#include "../tp_io.h"

#ifndef BAUD_DIV
#define BAUD_DIV 434
#endif

static const uint32_t img_a[4] = {0x10204080u, 0xFF00FF00u, 0x7F7F7F7Fu, 0x01020304u};
static const uint32_t img_b[4] = {0x30604020u, 0x01FF0101u, 0x80808080u, 0xFFFEFDFCu};

// W is 4 rows x 8 int8 weights, packed 4 per word, lane 0 = lowest byte
static const uint32_t W[4][2] = {
    {0x04030201u, 0xFCFDFEFFu},
    {0x7F7F7F7Fu, 0x81818181u},
    {0x10F010F0u, 0x02020202u},
    {0x00000001u, 0x80000000u},
};
static const uint32_t X[2] = {0x05FB0A03u, 0x7F80017Fu};

static void hex_line(const char *what, uint32_t v) {
    uart_puts(what); uart_puthex(v); uart_putc('\n');
}

// ---- plain C references, run in CPU mode ----
static uint32_t ref_lane(int op, uint32_t a, uint32_t b) {
    uint32_t y = 0;
    for (int i = 0; i < 4; i++) {
        uint32_t x = (a >> (8 * i)) & 0xFF, z = (b >> (8 * i)) & 0xFF, r;
        if (op == 0)      r = (x + z + 1) >> 1;
        else if (op == 1) r = (x + z > 255) ? 255 : x + z;
        else              r = (x > z) ? x - z : z - x;
        y |= r << (8 * i);
    }
    return y;
}
static int32_t ref_dot(uint32_t a, uint32_t b) {
    int32_t s = 0;
    for (int i = 0; i < 4; i++) s += (int8_t)(a >> (8 * i)) * (int8_t)(b >> (8 * i));
    return s;
}

int main(void) {
    UART_DIV = BAUD_DIV;
    // TRIG0, UART TX, HALT and ILLEGAL on their pins (LEDs 0, 4, 5, 6)
    pins_use_function(PIN_TRIG0 | PIN_UART_TX | PIN_HALT | PIN_ILLEGAL);
    uart_puts("modes demo\n");
    uart_puts("cpu mode "); uart_putu(tp_mode()); uart_putc('\n');

    // references first, in CPU mode
    uint32_t want_gpu[3][4];
    int32_t  want_tpu[4];
    for (int p = 0; p < 4; p++)
        for (int op = 0; op < 3; op++) want_gpu[op][p] = ref_lane(op, img_a[p], img_b[p]);
    for (int j = 0; j < 4; j++) {
        int32_t s = ref_dot(W[j][0], X[0]) + ref_dot(W[j][1], X[1]);
        want_tpu[j] = s < 0 ? 0 : s;
    }

    // ---- GPU ----
    tp_mode_set(TP_MODE_GPU);
    uart_puts("gpu mode "); uart_putu(tp_mode()); uart_putc('\n');
    uint32_t got_gpu[3][4];
    for (int p = 0; p < 4; p++) {
        got_gpu[0][p] = tp_pavgu_b(img_a[p], img_b[p]);
        got_gpu[1][p] = tp_paddus_b(img_a[p], img_b[p]);
        got_gpu[2][p] = tp_pabsd_b(img_a[p], img_b[p]);
    }
    int gpu_ok = 1;
    for (int p = 0; p < 4; p++) {
        hex_line("blend ", got_gpu[0][p]);
        hex_line("bright ", got_gpu[1][p]);
        hex_line("motion ", got_gpu[2][p]);
        for (int op = 0; op < 3; op++) gpu_ok &= (got_gpu[op][p] == want_gpu[op][p]);
    }
    uart_puts(gpu_ok ? "gpu matches cpu\n" : "gpu MISMATCH\n");

    // ---- TPU ----
    tp_mode_set(TP_MODE_TPU);
    uart_puts("tpu mode "); uart_putu(tp_mode()); uart_putc('\n');
    int tpu_ok = 1;
    for (int j = 0; j < 4; j++) {
        tp_tclr();
        tp_tmac(W[j][0], X[0]);
        tp_tmac(W[j][1], X[1]);
        int32_t raw = tp_trd(), y = tp_trelu();
        uart_puts("y"); uart_putu(j); uart_puts(" raw "); uart_puti(raw);
        uart_puts(" relu "); uart_puti(y); uart_putc('\n');
        tpu_ok &= (y == want_tpu[j]);
    }
    uart_puts(tpu_ok ? "tpu matches cpu\n" : "tpu MISMATCH\n");

    // ---- back to CPU, with a deadline armed across the switch ----
    // Nothing is printed between tp_arm and tp_wait: a printed line takes
    // longer than the deadline at simulation baud rates.
    uint32_t t0 = tp_time();
    tp_arm(t0 + 300, 0);
    tp_mode_set(TP_MODE_CPU);
    uint32_t m = tp_mode();
    tp_wait(t0 + 300);
    uint32_t dt = tp_time() - t0;
    uart_puts("cpu mode "); uart_putu(m); uart_putc('\n');
    uart_puts("deadline "); uart_putc(dt >= 300 && dt < 400 ? 'Y' : 'N'); uart_putc('\n');

    uart_puts("done\n");
    uart_flush();
    return 0;
}
