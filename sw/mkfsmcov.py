#!/usr/bin/env python3
"""mkfsmcov.py — build test/fsmcov.hex: a program written to take the state-
diagram arrows that ordinary programs miss (docs/views/NOTES.md).

The core runs every instruction as 8-clock passes on a free-running 3-bit
phase. After a shift or a load it goes straight back to S_PASS only if it
finishes exactly as phase 7 comes round, otherwise it waits in S_ALIGN. A
shift by s takes floor(s/4) + s%4 steps, so only s = 19 and s = 28 finish on
phase 7 (S_SHIFT -> S_PASS), and no test program shifted by either. This one
shifts by every amount 0..31 three ways (SLLI, SRAI, SRL by register), and
loads from PSRAM and the timing unit at every width, with 0..7 instructions
of padding before each, so their latency meets as many phases as it can.

Every result is stored to PSRAM, so a wrong value shows on the QSPI pins and
the RTL-versus-gates lockstep sees it.
"""

from mkprog import addi, lui, sw, lw, ecall
from mkisa import slli, srai, srl, lb, lh, lbu, lhu, sb, sh

PSRAM = 7      # x7 = 0x10000000
SYNC = 8       # x8 = 0x20000000 (timing unit registers)

PROG = []


def e(w, c=""):
    PROG.append((w, c))


def nop():
    e(addi(0, 0, 0), "nop")


e(lui(PSRAM, 0x10000), "lui x7, 0x10000      ; PSRAM")
e(lui(SYNC, 0x20000), "lui x8, 0x20000      ; timing unit")
e(lui(2, 0x80000), "lui x2, 0x80000      ; shift operand, sign bit set")
e(addi(2, 2, 0x5A5), "addi x2, x2, 0x5a5")

slot = 0
for s in range(32):
    e(slli(1, 2, s), f"slli x1, x2, {s}")
    e(sw(1, PSRAM, 4 * slot), f"sw x1, {4 * slot}(x7)"); slot += 1
    e(srai(1, 2, s), f"srai x1, x2, {s}")
    e(sw(1, PSRAM, 4 * slot), f"sw x1, {4 * slot}(x7)"); slot += 1
    e(addi(3, 0, s), f"addi x3, x0, {s}")
    e(srl(1, 2, 3), "srl x1, x2, x3")
    e(sw(1, PSRAM, 4 * slot), f"sw x1, {4 * slot}(x7)"); slot += 1

# loads of every width from PSRAM (the words just written) and from the
# timing unit's status register, each after 0..7 instructions of padding
loads = [(lw, "lw"), (lh, "lh"), (lhu, "lhu"), (lb, "lb"), (lbu, "lbu")]
for pad in range(8):
    for k, (op, name) in enumerate(loads):
        for _ in range(pad):
            nop()
        off = 4 * ((pad * 5 + k) % slot) + (0 if name == "lw" else (2 if name.startswith("lh") else 3))
        e(op(4, PSRAM, off), f"{name} x4, {off}(x7)")
        e(lw(5, SYNC, 8), "lw x5, 8(x8)         ; timing unit status")
        e(sb(4, PSRAM, 4 * slot), f"sb x4, {4 * slot}(x7)")
        e(sh(4, PSRAM, 4 * slot + 2), f"sh x4, {4 * slot + 2}(x7)"); slot += 1

# loads from the flash the program runs from, after 0..7 instructions of
# padding, after a store, and right after a taken branch (which cancels the
# instruction prefetch), so the QSPI port starts each load from as many states
# as possible. (Not the boot ROM: it has no data port, and a load there stalls
# the core until reset, as the README's memory map says.)
from mkisa import beq
for pad in range(8):
    for base, name in ((0, "flash"),):
        for _ in range(pad):
            nop()
        e(lw(4, base, 4 * pad), f"lw x4, {4 * pad}(x{base})   ; {name}")
        e(sw(4, PSRAM, 4 * slot), f"sw x4, {4 * slot}(x7)")
        e(lw(4, base, 4 * pad + 8), f"lw x4, {4 * pad + 8}(x{base})   ; {name}, straight after a store")
        e(beq(0, 0, 8), "beq x0, x0, +8        ; taken: skips one")
        nop()
        e(lw(4, base, 4 * pad + 16), f"lw x4, {4 * pad + 16}(x{base})  ; {name}, straight after a taken branch")
        e(sw(4, PSRAM, 4 * slot + 4), f"sw x4, {4 * slot + 4}(x7)"); slot += 2

LOOP = "--loop" in __import__("sys").argv     # fsmcov_loop.hex: run forever (for reset hunting)
if LOOP:
    from mkprog import jal
    e(jal(0, -4 * len(PROG)), "jal x0, start          ; again, forever")
else:
    e(ecall(), "ecall")

if __name__ == "__main__":
    import os, sys
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test", "fsmcov.hex")
    with open(out, "w") as f:
        for w, _ in PROG:
            f.write("%08x\n" % (w & 0xFFFFFFFF))
    print(f"{out}: {len(PROG)} instructions, {slot} result slots")
