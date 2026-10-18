#!/usr/bin/env python3
"""modes_model.py — independent Python reference model of Tiqora's CPU / GPU /
TPU modes (the TIQORA_MODES build).

Written from the instruction definitions in docs/MODES.md, not from the RTL:
lanes are Python integers, signed bytes are converted arithmetically, and
saturation, rounding and wrap-around are spelled out case by case. If the
hardware and this file agree, they are unlikely to be wrong the same way.

    from modes_model import Machine
    m = Machine()
    m.exec_word(word, regs)   # -> "ok" or "illegal"; updates regs, m.mode, m.acc
"""

MASK32 = 0xFFFFFFFF
CPU, GPU, TPU = 0, 1, 2
MODE_NAMES = {CPU: "CPU", GPU: "GPU", TPU: "TPU"}

OPC_CUSTOM1, OPC_CUSTOM2, OPC_CUSTOM3 = 0x2B, 0x5B, 0x7B

GPU_OPS = ["PADD.B", "PSUB.B", "PADDUS.B", "PMAXU.B", "PMINU.B", "PAVGU.B", "PMUL.B", "PABSD.B"]
TPU_OPS = {0: "TMAC", 1: "TRD", 2: "TRELU", 3: "TCLR", 4: "TSET"}


def lanes(v):
    """32-bit value -> list of four unsigned bytes, lane 0 first."""
    return [(v >> (8 * i)) & 0xFF for i in range(4)]


def pack(bs):
    out = 0
    for i, b in enumerate(bs):
        assert 0 <= b <= 255, b
        out |= b << (8 * i)
    return out


def sbyte(b):
    """unsigned byte -> signed integer -128..127"""
    return b - 256 if b >= 128 else b


def to_s32(v):
    v &= MASK32
    return v - (1 << 32) if v >> 31 else v


def gpu_lane(op, x, z):
    """One byte lane of a GPU-mode instruction, unsigned bytes in and out."""
    if op == 0: return (x + z) % 256
    if op == 1: return (x - z) % 256
    if op == 2: return min(x + z, 255)
    if op == 3: return x if x >= z else z
    if op == 4: return x if x <= z else z
    if op == 5: return (x + z + 1) // 2
    if op == 6: return (x * z) % 256
    if op == 7: return abs(x - z)
    raise ValueError(op)


def gpu(op, a, b):
    return pack([gpu_lane(op, x, z) for x, z in zip(lanes(a), lanes(b))])


def dot4(a, b):
    """signed int8 dot product of the four byte lanes (a Python integer)"""
    return sum(sbyte(x) * sbyte(z) for x, z in zip(lanes(a), lanes(b)))


def relu(acc):
    return 0 if to_s32(acc) < 0 else acc & MASK32


class Machine:
    """Architectural state the modes add: the mode and the TPU accumulator."""

    def __init__(self):
        self.mode = CPU
        self.acc = 0

    def exec_word(self, w, regs):
        """Execute one custom-1/2/3 instruction word. regs: list of 16 ints
        (x0 must stay 0). Returns "ok" or "illegal"; an illegal instruction
        changes nothing."""
        opc = w & 0x7F
        rd = (w >> 7) & 0x1F
        f3 = (w >> 12) & 7
        rs1 = (w >> 15) & 0x1F
        rs2 = (w >> 20) & 0x1F
        f7 = w >> 25
        imm = w >> 20

        def reg(n):
            return regs[n]

        def wr(n, v):
            if n != 0:
                regs[n] = v & MASK32

        if opc == OPC_CUSTOM1:
            if f3 == 0:                                    # MGET rd
                if (w >> 15) != 0 or rd >= 16:
                    return "illegal"
                wr(rd, self.mode)
                return "ok"
            if f3 == 1:                                    # MSET rd, imm
                if rs1 != 0 or imm > 2 or rd >= 16:
                    return "illegal"
                old = self.mode
                self.mode = imm
                wr(rd, old)
                return "ok"
            return "illegal"

        if opc == OPC_CUSTOM2:                             # GPU mode only
            if self.mode != GPU or f7 != 0 or rd >= 16 or rs1 >= 16 or rs2 >= 16:
                return "illegal"
            wr(rd, gpu(f3, reg(rs1), reg(rs2)))
            return "ok"

        if opc == OPC_CUSTOM3:                             # TPU mode only
            if self.mode != TPU or f7 != 0 or f3 > 4:
                return "illegal"
            uses_rd = f3 in (1, 2)
            uses_rs1 = f3 in (0, 4)
            uses_rs2 = f3 == 0
            if (uses_rd and rd >= 16) or (uses_rs1 and rs1 >= 16) or (uses_rs2 and rs2 >= 16):
                return "illegal"
            if f3 == 0:
                self.acc = (self.acc + dot4(reg(rs1), reg(rs2))) & MASK32
            elif f3 == 1:
                wr(rd, self.acc)
            elif f3 == 2:
                wr(rd, relu(self.acc))
            elif f3 == 3:
                self.acc = 0
            elif f3 == 4:
                self.acc = reg(rs1) & MASK32
            return "ok"

        raise ValueError("not a mode instruction: %08x" % w)


# ---- encoders ---------------------------------------------------------------
def _r(op, f3, f7, rd, rs1, rs2):
    return (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op


def MGET(rd):                 return _r(OPC_CUSTOM1, 0, 0, rd, 0, 0)
def MSET(rd, mode):           return ((mode & 0xFFF) << 20) | (1 << 12) | (rd << 7) | OPC_CUSTOM1
def GOP(op, rd, rs1, rs2):    return _r(OPC_CUSTOM2, op, 0, rd, rs1, rs2)
def TMAC(rs1, rs2):           return _r(OPC_CUSTOM3, 0, 0, 0, rs1, rs2)
def TRD(rd):                  return _r(OPC_CUSTOM3, 1, 0, rd, 0, 0)
def TRELU(rd):                return _r(OPC_CUSTOM3, 2, 0, rd, 0, 0)
def TCLR():                   return _r(OPC_CUSTOM3, 3, 0, 0, 0, 0)
def TSET(rs1):                return _r(OPC_CUSTOM3, 4, 0, 0, rs1, 0)


if __name__ == "__main__":
    # a few hand-checked values, so the model itself is tested
    assert gpu(0, 0xFF01807F, 0x01FF8081) == 0x00000000
    assert gpu(2, 0xFF01807F, 0x01FF8081) == 0xFFFFFFFF
    assert gpu(5, 0x00FF0102, 0x01FF0103) == 0x01FF0103
    assert gpu(7, 0x0010FF00, 0x1000_00FF) == 0x1010FFFF
    assert dot4(0x80808080, 0x80808080) == 4 * 16384
    assert dot4(0x7F7F7F7F, 0x81818181) == 4 * (127 * -127)
    m = Machine(); r = [0] * 16
    assert m.exec_word(GOP(0, 1, 2, 3), r) == "illegal"     # GPU op in CPU mode
    assert m.exec_word(MSET(1, TPU), r) == "ok" and r[1] == CPU and m.mode == TPU
    r[2], r[3] = 0x01020304, 0xFFFFFFFF
    m.exec_word(TMAC(2, 3), r); m.exec_word(TRD(4), r)
    assert to_s32(r[4]) == -10
    m.exec_word(TRELU(5), r); assert r[5] == 0
    assert m.exec_word(MSET(0, 3), r) == "illegal" and m.mode == TPU
    print("modes_model self-check passed")
