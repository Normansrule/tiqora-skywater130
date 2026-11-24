#!/usr/bin/env python3
"""mkrandmem.py — random programs of loads, stores, ALU work and branches,
for test/tb_memlat.sv: how many clocks a load or store keeps the core in
S_MEM, over as many different QSPI situations as random code produces.

    python3 sw/mkrandmem.py <seed> <out.hex>

Addresses stay inside the first 4 KB of flash and PSRAM (what the models
hold), and the program ends with four ECALLs. Branches only jump forward,
over at most 3 instructions, so it always reaches one (with a single ECALL,
a branch near the end jumped past it: 32 of 300 seeds ran off the end).
"""
import random, sys
from mkprog import addi, lui, sw, lw, ecall
from mkisa import (lb, lh, lbu, lhu, sb, sh, add, sub, xor_, slli, srai, srl,
                   beq, bne, andi)

seed, out = int(sys.argv[1]), sys.argv[2]
rnd = random.Random(seed)
P = []
P += [lui(7, 0x10000), lui(8, 0x20000), addi(2, 0, 0x123), addi(3, 0, 7)]
N = 400
for i in range(N):
    k = rnd.randrange(10)
    off = rnd.randrange(0, 1024) & ~3
    if k == 0:   P.append(lw(4, 7, off))                          # PSRAM
    elif k == 1:                                                  # PSRAM, narrow
        op = rnd.choice([lb, lh, lbu, lhu])
        P.append(op(4, 7, off + (rnd.randrange(4) if op in (lb, lbu) else 2 * rnd.randrange(2))))
    elif k == 2: P.append(lw(5, 0, off))                          # flash (the program itself)
    elif k == 3: P.append(rnd.choice([sw, sh, sb])(2, 7, off))
    elif k == 4: P.append(lw(6, 8, 8))                            # timing unit status
    elif k == 5: P.append(rnd.choice([add, sub, xor_])(2, 2, 3))
    elif k == 6: P.append(rnd.choice([slli, srai])(3, 2, rnd.randrange(32)))
    elif k == 7: P.append(srl(3, 2, 3))
    elif k == 8: P.append(andi(3, 3, 31))
    else:
        skip = rnd.randrange(1, 4)                               # forward branch over 1..3
        P.append(rnd.choice([beq, bne])(0, rnd.choice([0, 2]), 4 * (skip + 1)))
P += [ecall()] * 4
with open(out, "w") as f:
    for w in P:
        f.write("%08x\n" % (w & 0xFFFFFFFF))
