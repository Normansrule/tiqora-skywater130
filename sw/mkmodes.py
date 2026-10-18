#!/usr/bin/env python3
"""mkmodes.py — build test/modes.hex, the CPU / GPU / TPU mode test program,
and test/modes_expect.txt, what every result slot and trap must be.

    python3 mkmodes.py [seed]          (default seed 1; the seed is printed)

The program runs from flash and stores each result into PSRAM slot N
(0x10000000 + 4*N). Expected values come from sw/modes_model.py, an
independent model. Sections, in order:

  1. CPU mode: MGET, then every GPU and TPU instruction must trap.
  2. GPU mode: directed edge cases and seeded random operands for all eight
     byte-lane instructions; TPU instructions must trap.
  3. TPU mode: directed and seeded random TMAC chains read back with TRD
     and TRELU; GPU instructions must trap, and a trapped TMAC must not
     have touched the accumulator.
  4. Back to CPU: both accelerators trap again; malformed MGET/MSET trap and
     leave the mode alone.
  5. Timing: arm TRIG0, switch CPU -> GPU -> TPU -> CPU repeatedly while the
     deadline passes; the testbench checks the pin edge is on the exact tick.

modes_expect.txt lines:
    (numbers are hexadecimal, so the testbench reads every field with %h)
    slot <n> <value> <label>      PSRAM word n must equal value
    trap <pc> 0 <label>           an illegal-instruction trap at this PC, in order
    deadline <slot> 0 deadline    slot holding the armed deadline (section 5)
    msets <count> 0 msets         how many MSETs must commit
"""
import os, random, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mkprog import addi, lui, sw, ecall, TIME, TARM, TPW, TWAIT
import modes_model as mm

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 1
rng = random.Random(SEED)
BASE = 15                       # x15 = PSRAM base
SENT = 0x5EA7CAFE               # sentinel a trapped instruction must not overwrite

words, notes, expect, traps = [], [], [], []
regs = [0] * 16
m = mm.Machine()
slot = [0]


def emit(w, note=""):
    words.append(w & 0xFFFFFFFF)
    notes.append(note)


def li(rd, v):
    v &= 0xFFFFFFFF
    lo = v & 0xFFF
    lo = lo - 0x1000 if lo >= 0x800 else lo
    hi = ((v - lo) >> 12) & 0xFFFFF
    emit(lui(rd, hi), f"li x{rd}, {v:#x}")
    emit(addi(rd, rd, lo))
    regs[rd] = v


def store(r, label):
    n = slot[0]
    assert n < 500
    emit(sw(r, BASE, 4 * n), f"store x{r} -> slot {n}")
    expect.append(("slot", n, regs[r], label))
    slot[0] = n + 1


n_msets = 0


def mode_op(w, label, want=None):
    """Emit a mode instruction, run it on the model, record a trap if any."""
    global n_msets
    pc = 4 * len(words)
    got = m.exec_word(w, regs)
    if got == "ok" and (w & 0x707F) == 0x102B:
        n_msets += 1
    if want is not None:
        assert got == want, (label, got, want)
    if got == "illegal":
        traps.append((pc, f"{label} in {mm.MODE_NAMES[m.mode]} mode"))
    emit(w, label)
    return got


def wrong_mode_checks(tag):
    """Every accelerator instruction that is not legal in the current mode traps,
    and its destination keeps the sentinel."""
    cur = m.mode
    if cur != mm.GPU:
        for op in range(8):
            li(3, SENT)
            mode_op(mm.GOP(op, 3, 1, 2), f"{mm.GPU_OPS[op]} (wrong mode)", "illegal")
            store(3, f"{tag}: {mm.GPU_OPS[op]} trapped, rd kept")
    if cur != mm.TPU:
        for f3, name in mm.TPU_OPS.items():
            li(3, SENT)
            w = {0: mm.TMAC(1, 2), 1: mm.TRD(3), 2: mm.TRELU(3), 3: mm.TCLR(), 4: mm.TSET(1)}[f3]
            mode_op(w, f"{name} (wrong mode)", "illegal")
            store(3, f"{tag}: {name} trapped, rd kept")


# ---- 0. setup ------------------------------------------------------------
emit(lui(BASE, 0x10000), "x15 = PSRAM base")
regs[BASE] = 0x10000000
li(1, 0x80FF7F01)
li(2, 0x01800102)

# ---- 1. CPU mode ---------------------------------------------------------
mode_op(mm.MGET(4), "MGET")
store(4, "reset mode is CPU (0)")
wrong_mode_checks("CPU")

# ---- 2. GPU mode ---------------------------------------------------------
mode_op(mm.MSET(5, mm.GPU), "MSET GPU", "ok")
store(5, "MSET returns the old mode (CPU)")
mode_op(mm.MGET(6), "MGET", "ok")
store(6, "MGET after MSET GPU")

EDGE = [0x00000000, 0xFFFFFFFF, 0x80808080, 0x7F7F7F7F, 0x01FF8000, 0xFF0180FE, 0x12345678, 0xFEDCBA98]
for op in range(8):
    for a, b in [(EDGE[0], EDGE[1]), (EDGE[1], EDGE[1]), (EDGE[2], EDGE[3]),
                 (EDGE[3], EDGE[2]), (EDGE[4], EDGE[5]), (EDGE[6], EDGE[7])]:
        li(7, a); li(8, b)
        mode_op(mm.GOP(op, 9, 7, 8), mm.GPU_OPS[op], "ok")
        store(9, f"{mm.GPU_OPS[op]} {a:08x},{b:08x}")
for op in range(8):
    for _ in range(6):
        a, b = rng.getrandbits(32), rng.getrandbits(32)
        li(7, a); li(8, b)
        mode_op(mm.GOP(op, 9, 7, 8), mm.GPU_OPS[op], "ok")
        store(9, f"{mm.GPU_OPS[op]} random {a:08x},{b:08x}")
# rd == rs1 == rs2, and writes to x0 are dropped
li(10, 0x01020304)
mode_op(mm.GOP(0, 10, 10, 10), "PADD.B x10,x10,x10", "ok")
store(10, "PADD.B with rd = rs1 = rs2")
mode_op(mm.GOP(0, 0, 10, 10), "PADD.B x0,...", "ok")
store(0, "x0 stays 0 after a GPU write")
wrong_mode_checks("GPU")

# ---- 3. TPU mode ---------------------------------------------------------
mode_op(mm.MSET(5, mm.TPU), "MSET TPU", "ok")
store(5, "MSET returns the old mode (GPU)")
mode_op(mm.TCLR(), "TCLR", "ok")
mode_op(mm.TRD(6), "TRD", "ok")
store(6, "TCLR then TRD = 0")
TPU_DIRECT = [(0x01020304, 0x01010101), (0x80808080, 0x80808080), (0x7F7F7F7F, 0x81818181),
              (0xFFFFFFFF, 0x01010101), (0x7F7F7F7F, 0x7F7F7F7F)]
for a, b in TPU_DIRECT:
    li(7, a); li(8, b)
    mode_op(mm.TMAC(7, 8), "TMAC", "ok")
    mode_op(mm.TRD(9), "TRD", "ok")
    store(9, f"TMAC {a:08x},{b:08x} accumulates")
mode_op(mm.TRELU(9), "TRELU", "ok")
store(9, "TRELU of a positive accumulator")
li(7, 0x80000005)
mode_op(mm.TSET(7), "TSET", "ok")
mode_op(mm.TRELU(9), "TRELU", "ok")
store(9, "TRELU of a negative accumulator is 0")
mode_op(mm.TRD(9), "TRD", "ok")
store(9, "TRD after TSET")
li(7, 0x7FFFFFFF); mode_op(mm.TSET(7), "TSET", "ok")
li(7, 0x7F7F7F7F); li(8, 0x7F7F7F7F)
mode_op(mm.TMAC(7, 8), "TMAC", "ok"); mode_op(mm.TRD(9), "TRD", "ok")
store(9, "TMAC wraps at 2^32")
for k in range(10):
    mode_op(mm.TCLR(), "TCLR", "ok")
    for _ in range(rng.randint(1, 6)):
        a, b = rng.getrandbits(32), rng.getrandbits(32)
        li(7, a); li(8, b)
        mode_op(mm.TMAC(7, 8), "TMAC", "ok")
    mode_op(mm.TRD(9), "TRD", "ok")
    store(9, f"random TMAC chain {k}")
    mode_op(mm.TRELU(10), "TRELU", "ok")
    store(10, f"random TMAC chain {k}, TRELU")
# a wrong-mode TMAC must not touch the accumulator: remember it, trap, read back
li(7, 0x11223344); mode_op(mm.TSET(7), "TSET", "ok")
wrong_mode_checks("TPU")
mode_op(mm.MSET(5, mm.GPU), "MSET GPU", "ok")
li(1, 0x01010101); li(2, 0x01010101)
mode_op(mm.TMAC(1, 2), "TMAC (wrong mode)", "illegal")
mode_op(mm.MSET(5, mm.TPU), "MSET TPU", "ok")
mode_op(mm.TRD(9), "TRD", "ok")
store(9, "a trapped TMAC left the accumulator alone")
mode_op(mm.TSET(0) | (5 << 12), "custom-3 funct3 5 (undefined)", "illegal")
mode_op(mm.GOP(0, 3, 1, 2) | (1 << 25), "custom-2 funct7 1 (undefined)", "illegal")

# ---- 4. back to CPU --------------------------------------------------------
mode_op(mm.MSET(5, mm.CPU), "MSET CPU", "ok")
store(5, "MSET returns the old mode (TPU)")
wrong_mode_checks("CPU again")
mode_op(mm.MSET(5, 3), "MSET 3 (undefined mode)", "illegal")
mode_op(mm.MSET(5, mm.GPU) | (1 << 15), "MSET with rs1 != 0", "illegal")
mode_op(mm.MGET(5) | (2 << 20), "MGET with rs2 != 0", "illegal")
mode_op(mm.MSET(5, mm.GPU) | (1 << 11), "MSET with rd = x16 (not in RV32E)", "illegal")
mode_op(mm.MGET(6), "MGET", "ok")
store(6, "mode still CPU after the malformed switches")

# ---- 5. timing across switches -------------------------------------------
li(11, 8); emit(TPW(11), "tpw x11 ; 8-tick trigger pulses")
emit(TIME(12), "time x12")
emit(addi(13, 12, 400), "x13 = now + 400 : the deadline")
emit(TARM(13, 0), "tarm x13, x0 ; TRIG0")
cycle = [mm.GPU, mm.TPU, mm.CPU] * 8
for k, md in enumerate(cycle):
    mode_op(mm.MSET(14, md), f"MSET {mm.MODE_NAMES[md]} (timing)", "ok")
emit(TWAIT(13), "twait x13")
regs[12] = regs[13] = None
n_dead = slot[0]
emit(sw(13, BASE, 4 * n_dead), "store the deadline")
slot[0] += 1
mode_op(mm.MGET(6), "MGET", "ok")
store(6, "mode is CPU after the timing loop")
emit(ecall(), "ecall")

# ---- write -----------------------------------------------------------------
here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(here, "..", "test")
with open(os.path.join(out, "modes.hex"), "w") as f:
    for w in words:
        f.write(f"{w:08x}\n")
with open(os.path.join(out, "modes_expect.txt"), "w") as f:
    for _, n, v, label in expect:
        f.write(f"slot {n:x} {v:08x} {label.replace(' ', '_')}\n")
    for pc, label in traps:
        f.write(f"trap {pc:08x} 0 {label.replace(' ', '_')}\n")
    f.write(f"deadline {n_dead:x} 0 deadline\n")
    f.write(f"msets {n_msets:x} 0 msets\n")
print(f"mkmodes: seed {SEED}, {len(words)} instructions, {len(expect)} result slots, "
      f"{len(traps)} expected traps")
