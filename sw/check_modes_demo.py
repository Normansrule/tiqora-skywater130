#!/usr/bin/env python3
"""check_modes_demo.py UART_LOG — check the text sw/examples/modes_demo.c
printed, line by line, against sw/modes_model.py.

The program already compares each accelerator result with plain C; this is
the independent second opinion. The inputs below are copied from
modes_demo.c (img_a, img_b, W, X). Exit status 0 only on an exact match.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modes_model as mm

IMG_A = [0x10204080, 0xFF00FF00, 0x7F7F7F7F, 0x01020304]
IMG_B = [0x30604020, 0x01FF0101, 0x80808080, 0xFFFEFDFC]
W = [(0x04030201, 0xFCFDFEFF), (0x7F7F7F7F, 0x81818181),
     (0x10F010F0, 0x02020202), (0x00000001, 0x80000000)]
X = (0x05FB0A03, 0x7F80017F)


def expected():
    out = ["modes demo", "cpu mode 0", "gpu mode 1"]
    for a, b in zip(IMG_A, IMG_B):
        out.append("blend %08x" % mm.gpu(5, a, b))
        out.append("bright %08x" % mm.gpu(2, a, b))
        out.append("motion %08x" % mm.gpu(7, a, b))
    out += ["gpu matches cpu", "tpu mode 2"]
    m = mm.Machine(); m.mode = mm.TPU; r = [0] * 16
    for j, (w0, w1) in enumerate(W):
        m.exec_word(mm.TCLR(), r)
        r[1], r[2] = w0, X[0]; m.exec_word(mm.TMAC(1, 2), r)
        r[1], r[2] = w1, X[1]; m.exec_word(mm.TMAC(1, 2), r)
        m.exec_word(mm.TRD(3), r); m.exec_word(mm.TRELU(4), r)
        out.append("y%d raw %d relu %d" % (j, mm.to_s32(r[3]), mm.to_s32(r[4])))
    out += ["tpu matches cpu", "cpu mode 0", "deadline Y", "done"]
    return out


if __name__ == "__main__":
    got = open(sys.argv[1]).read().splitlines()
    want = expected()
    bad = 0
    for i in range(max(len(got), len(want))):
        g = got[i] if i < len(got) else "<missing>"
        w = want[i] if i < len(want) else "<none>"
        ok = g == w
        bad += not ok
        print(("  ok    " if ok else "  FAIL  ") + g + ("" if ok else "   (model: %s)" % w))
    print("%d lines, %d differ from sw/modes_model.py" % (len(want), bad))
    sys.exit(1 if bad else 0)
