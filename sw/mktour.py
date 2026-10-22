#!/usr/bin/env python3
"""mktour.py — build test/tour.hex, the program behind the explorer's guided tours.

One short program that walks through every part of the chip the tours explain,
in order: the reset and memory wake-up (done by the hardware before word 0),
a UART byte, a deadline armed and waited on, a 32-bit add whose carry ripples
through all eight nibbles, a store and load to QSPI RAM, an illegal
instruction, three capture events into a two-deep queue (the third overflows),
and the queue read back. test/tb_tour.sv runs it from the flash model at the
real pins, checks every step, and writes the per-clock trace that
docs/tools/traces.py turns into the explorer's fixtures.

    python3 sw/mktour.py [out.hex]          (make -C test tour runs it)
"""
from mkprog import (addi, add, lui, sw, lw, bne, ecall, R, OPC_OP,
                    TIME, TPOP, TSTAT, TWAIT, TARM, TCFG, TPW)

PERIPH, RAM = 5, 12            # x5 = 0x3000_0000, x12 = 0x1000_0000
A, B = 0x12345678, 0x0FEDCBA9  # every nibble pair carries: sum 0x22222221
# More operand pairs for the datapath explorer: the browser's nibble model is
# checked against what the RTL computed for every one of these.
EXTRA = [(0xFFFFFFFF, 0x00000001), (0x80000000, 0x80000000), (0x0000000F, 0x00000010)]


def sub(rd, rs1, rs2):
    return R(OPC_OP, 0, 0x20, rd, rs1, rs2)


def extra_ops():
    out = []
    for a, b in EXTRA:
        out += li_hi_lo(3, a) + li_hi_lo(4, b)
        out += [(add(6, 3, 4), f"add  x6, x3, x4       ; datapath: 0x{a:08x} + 0x{b:08x}"),
                (sub(7, 3, 4), f"sub  x7, x3, x4       ; datapath: 0x{a:08x} - 0x{b:08x}")]
    return out


def li_hi_lo(rd, value):
    """lui + addi for any 32-bit constant (addi sign-extends its 12 bits)."""
    lo = value & 0xFFF
    hi = (value >> 12) + (1 if lo & 0x800 else 0)
    return [(lui(rd, hi & 0xFFFFF), f"lui  x{rd}, 0x{hi & 0xFFFFF:05x}"),
            (addi(rd, rd, lo - 0x1000 if lo & 0x800 else lo), f"addi x{rd}, x{rd}, {lo - 0x1000 if lo & 0x800 else lo:#x}")]


PROG = [
    (lui(PERIPH, 0x30000),  "lui  x5, 0x30000      ; x5 = GPIO/UART registers"),
    (addi(6, 0, 8),         "addi x6, x0, 8"),
    (sw(6, PERIPH, 0x14),   "sw   x6, 0x14(x5)     ; UART_DIV = 8 clocks per bit, so a frame fits the tour"),
    (addi(7, 0, 7),         "addi x7, x0, 7"),
    (TCFG(7),               "tcfg x7               ; capture channels 0-2, rising edges"),
    (addi(8, 0, 8),         "addi x8, x0, 8"),
    (TPW(8),                "tpw  x8               ; trigger pulse width 8 ticks"),
    (addi(14, 0, ord("K")), "addi x14, x0, 'K'"),
    (sw(14, PERIPH, 0x0C),  "sw   x14, 0x0c(x5)    ; UART_DATA: send 'K' on uo_out[4]"),
    (TIME(1),               "time x1               ; read the timebase"),
    (addi(1, 1, 200),       "addi x1, x1, 200      ; deadline = now + 200 ticks (4 us)"),
    (TARM(1, 0),            "tarm x1, x0           ; TRIG0 fires on that tick"),
    (TWAIT(1),              "twait x1              ; the core parks until then"),
    *li_hi_lo(9, A),
    *li_hi_lo(10, B),
    (add(11, 9, 10),        "add  x11, x9, x10     ; 0x12345678 + 0x0fedcba9, nibble by nibble"),
    *extra_ops(),
    (lui(RAM, 0x10000),     "lui  x12, 0x10000     ; x12 = QSPI RAM A"),
    (sw(11, RAM, 0),        "sw   x11, 0(x12)      ; QSPI write, command 0x38"),
    (lw(13, RAM, 0),        "lw   x13, 0(x12)      ; QSPI read, command 0xEB"),
    (bne(13, 11, 16 * 4),   "bne  x13, x11, fail   ; not taken when RAM kept the word"),
    (0x00000000,            ".word 0               ; illegal: skipped, ILLEGAL pin latches"),
    (TIME(1),               "time x1"),
    (addi(1, 1, 96),        "addi x1, x1, 96"),
    (TWAIT(1),              "twait x1              ; the testbench drives three capture edges meanwhile"),
    (TPOP(2),               "tpop x2               ; oldest event"),
    (TPOP(3),               "tpop x3               ; second event"),
    (TPOP(4),               "tpop x4               ; queue empty: reads 0"),
    (TSTAT(15),             "tstat x15             ; status: overflow flag still set"),
    (ecall(),               "ecall                 ; HALT"),
]
FAIL = PROG.index(next(p for p in PROG if p[1].startswith("bne"))) + 16
# The error tour: a load from an address no device decodes (0x5000_0000).
# tp_bus answers only flash, RAM, the timing unit, GPIO/UART and the boot ROM,
# so the core waits in MEM for an answer that never comes; only reset ends it.
HANG = [
    (lui(1, 0x50000),       "lui  x1, 0x50000      ; device 5: nothing is mapped there"),
    (lw(2, 1, 0),           "lw   x2, 0(x1)        ; the bus never answers: the core stalls in MEM"),
    (ecall(),               "ecall                 ; never reached"),
]
ECALL = PROG.index(next(p for p in PROG if p[1].startswith("ecall")))

if __name__ == "__main__":
    import os, sys
    if sys.argv[1:] == ["--ecall"]:            # the word index test/tb_tour.sv expects HALT at
        print(ECALL); sys.exit(0)
    out = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test", "tour.hex")
    words = [w for w, _ in PROG]
    words += [0x00000013] * (FAIL - len(words)) + [0x00100073]   # nop padding, then fail: ebreak
    words += [0x00100073] * (512 - len(words))                    # the rest of the flash model: ebreak
    with open(out, "w") as f:
        for w in words:
            f.write("%08x\n" % (w & 0xFFFFFFFF))
    with open(os.path.splitext(out)[0] + "_asm.txt", "w") as f:
        for i, (w, asm) in enumerate(PROG):
            f.write("%04x %08x %s\n" % (i * 4, w & 0xFFFFFFFF, asm))
        f.write("%04x %08x fail: ebreak\n" % (FAIL * 4, 0x00100073))
    hang = os.path.splitext(out)[0] + "_hang.hex"
    with open(hang, "w") as f:
        for w in [w for w, _ in HANG] + [0x00100073] * (512 - len(HANG)):
            f.write("%08x\n" % (w & 0xFFFFFFFF))
    with open(os.path.splitext(out)[0] + "_hang_asm.txt", "w") as f:
        for i, (w, asm) in enumerate(HANG):
            f.write("%04x %08x %s\n" % (i * 4, w & 0xFFFFFFFF, asm))
    print("wrote %s (%d instructions, fail handler at 0x%04x)" % (out, len(PROG), FAIL * 4))
