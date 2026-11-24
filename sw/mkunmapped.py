#!/usr/bin/env python3
"""mkunmapped.py — build test/unmapped.hex: loads, stores and a jump into
address space nothing answers (test/tb_unmapped.sv).

The data bus decodes flash (0x0), PSRAM (0x1), timing unit (0x2) and
peripherals (0x3); the boot ROM (0x4) is on the fetch side only, and 0x5 to
0xF are empty. A load or store there used to wait for an answer forever.
Now it reads 0 and is dropped, and a fetch there reads 0x00000000, an
illegal instruction.

PSRAM slots (word N at 0x10000000 + 4*N), each first filled with 0xBAD so a
0 really came from the load:
  0  lw  from the boot ROM          0x40000000   -> 0
  1  lw  from unmapped              0x50000000   -> 0 (after a store there)
  2  lw  from unmapped              0xF0000004   -> 0
  3  lbu from unmapped              0x7000000B   -> 0
  4  0x60D, written after all of the above (the core kept going)
Then it jumps to 0x50000000: ILLEGAL must rise.
"""

from mkprog import addi, lui, sw, lw
from mkisa import lbu, jalr

PROG = []


def e(w, c=""):
    PROG.append((w, c))


e(lui(7, 0x10000), "lui x7, 0x10000     ; PSRAM")
e(addi(6, 0, 0xBAD), "addi x6, x0, 0xbad")
for n in range(4):
    e(sw(6, 7, 4 * n), f"sw x6, {4 * n}(x7)   ; slot {n} = 0xbad")

e(lui(9, 0x40000), "lui x9, 0x40000     ; boot ROM")
e(lw(4, 9, 0), "lw x4, 0(x9)")
e(sw(4, 7, 0), "sw x4, 0(x7)        ; slot 0")

e(lui(10, 0x50000), "lui x10, 0x50000    ; unmapped")
e(sw(6, 10, 0), "sw x6, 0(x10)       ; dropped")
e(lw(4, 10, 0), "lw x4, 0(x10)")
e(sw(4, 7, 4), "sw x4, 4(x7)        ; slot 1")

e(lui(11, 0xF0000), "lui x11, 0xf0000    ; unmapped, top of the map")
e(lw(4, 11, 4), "lw x4, 4(x11)")
e(sw(4, 7, 8), "sw x4, 8(x7)        ; slot 2")

e(lui(12, 0x70000), "lui x12, 0x70000")
e(lbu(4, 12, 11), "lbu x4, 11(x12)")
e(sw(4, 7, 12), "sw x4, 12(x7)       ; slot 3")

e(addi(4, 0, 0x60D), "addi x4, x0, 0x60d")
e(sw(4, 7, 16), "sw x4, 16(x7)       ; slot 4 = 0x60d")

e(jalr(0, 10, 0), "jalr x0, 0(x10)     ; jump into unmapped space")

if __name__ == "__main__":
    import os, sys
    out = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test", "unmapped.hex")
    with open(out, "w") as f:
        for w, _ in PROG:
            f.write("%08x\n" % (w & 0xFFFFFFFF))
