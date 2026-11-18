"""Expected output of sw/examples/branch_mix.c, computed independently."""
import sys
M = 0xFFFFFFFF
TBL = [0x00000000, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF,
       0x12345678, 0x9ABCDEF0, 0x00000001, 0xC0000000]

def asm_mix(x, t):
    r = 0
    if x & 3:
        r += 1
    if not x & 8:
        r += 16
    if not t < x:
        r += 256
    return r

def expected():
    x, acc = 1, 0
    for i in range(160):
        x = (x * 1664525 + 1013904223) & M
        acc = (acc + x) & M if x & 1 else acc ^ (x >> 3)
        if x & 0x80000000:
            acc = ((acc << 1) | (acc >> 31)) & M
        if x & 6 == 2:
            acc = (acc + 7) & M
        acc = (acc + asm_mix(x, TBL[i & 7])) & M
    return "%08x" % acc

if __name__ == "__main__":
    print(expected())
