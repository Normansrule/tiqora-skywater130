"""mkreenter.py — a RAM program that re-enters the bootloader, as test/reenter.hex.

The README and sw/mkboot.py promise that user code can jump back into the
boot ROM at 0x4000_0000 at any time, without a reset, and load a new
program. On that path nothing is reset: the registers still hold whatever
the last program left there. This program makes that worst case explicit:

  1. fill every register the bootloader uses (length, pointer, sum, shift,
     return address, scratch) with values that would break it if the
     bootloader relied on them instead of setting them itself
  2. jump to 0x4000_0000 with JALR

test/tb_boot.sv loads this first, then expects "TP>" again and loads the
hello-world program through the re-entered bootloader.

Encoders are the same hand-written ones mkprog.py uses.
"""
import sys
from mkprog import addi, lui, I

def jalr(rd, rs1, imm): return I(0x67, 0, rd, rs1, imm)

prog, notes = [], []
def emit(word, note):
    prog.append(word); notes.append(note)

# The bootloader's registers (sw/mkboot.py): x1 ra, x7 t, x8 length,
# x9 ptr, x10 a0, x11 sum, x12 shift. x5 and x6 are its base addresses.
emit(addi(8, 0, -1),          "x8  length = 0xFFFF_FFFF (would never finish)")
emit(lui(9, 0x10000),         "x9  ptr    = 0x1000_0000 ...")
emit(addi(9, 9, 0x400),       "            ... + 0x400 (would load to the wrong place)")
emit(addi(11, 0, 0x5A),       "x11 sum    = 0x5A (would offset the checksum)")
emit(addi(12, 0, 13),         "x12 shift  = 13 (would garble the length)")
emit(addi(10, 0, 0x7F),       "x10 a0     = 0x7F")
emit(addi(7, 0, -1),          "x7  t      = 0xFFFF_FFFF")
emit(addi(1, 0, -4),          "x1  ra     = 0xFFFF_FFFC")
emit(addi(5, 0, 0x123),       "x5  = 0x123 (not the peripheral base)")
emit(addi(6, 0, 0x456),       "x6  = 0x456 (not RAM)")
emit(lui(13, 0x40000),        "x13 = 0x4000_0000, the boot ROM")
emit(jalr(0, 13, 0),          "jump there, no reset")

out = sys.argv[1] if len(sys.argv) > 1 else "reenter.hex"
with open(out, "w") as f:
    for w in prog:
        f.write(f"{w:08x}\n")
for i, (w, n) in enumerate(zip(prog, notes)):
    print(f"{0x10000000 + 4*i:08x}: {w:08x}   {n}")
print(f"\nwrote {out} ({len(prog)} words)")
