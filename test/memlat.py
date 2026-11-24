#!/usr/bin/env python3
"""memlat.py — how long loads and stores keep the core in S_MEM, over many random programs.

    python3 test/memlat.py [SEEDS] [FIRST]     (default 300 seeds from 1; also `make -C test views-memlat`)

Builds test/tb_memlat.sv (RTL only), generates SEEDS programs with
sw/mkrandmem.py, runs each one, and prints a histogram of
"<clocks in S_MEM> -> <next state>". Fails if any program did not halt, if
any stay in S_MEM did not start on phase 0, or if a stay left for S_PASS (2)
without being a whole number of 8-clock passes, or for S_ALIGN (1) while
being one. That last rule is the reading of the RTL that says S_MEM -> S_PASS
needs a latency that is a multiple of 8 (docs/views/NOTES.md).

This is evidence, not a proof: it shows which stay lengths the random
programs produced, not that no other length is possible.
"""
import collections, os, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST = os.path.join(ROOT, "test")
NAMES = {0: "S_FETCH", 1: "S_ALIGN", 2: "S_PASS", 3: "S_TWAIT", 4: "S_HALT", 5: "S_MEM", 6: "S_XP", 7: "S_SHIFT"}


def main():
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    tmp = tempfile.mkdtemp(prefix="memlat_")
    rtl = [os.path.join(ROOT, l.split()[-1]) for l in open(os.path.join(ROOT, "syn", "synth_check.ys"))
           if l.startswith("read_verilog")]
    vvp = os.path.join(tmp, "memlat.vvp")
    subprocess.run(["iverilog", "-g2012", "-o", vvp, "-s", "tb_memlat"] + rtl +
                   [os.path.join(TEST, "qspi_model.sv"), os.path.join(TEST, "tb_memlat.sv")], check=True,
                   stderr=subprocess.DEVNULL)

    def one(s):
        hexf = os.path.join(tmp, f"r{s}.hex")
        subprocess.run([sys.executable, os.path.join(ROOT, "sw", "mkrandmem.py"), str(s), hexf],
                       cwd=os.path.join(ROOT, "sw"), check=True)
        out = subprocess.run(["vvp", "-n", vvp, f"+PROG={hexf}"], capture_output=True, text=True).stdout
        return s, out

    hist, errors = collections.Counter(), []
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as ex:
        for s, out in ex.map(one, range(first, first + seeds)):
            if "MEMLAT PASSED" not in out:
                errors.append(f"seed {s}: " + "; ".join(l for l in out.splitlines() if l.startswith("FAIL")))
            for l in out.splitlines():
                p = l.split()
                if len(p) == 3 and p[0] == "MEMLAT":
                    n, nxt = int(p[1]), int(p[2])
                    hist[(n, nxt)] += 1
                    whole = n % 8 == 0
                    if (nxt == 2 and not whole) or (nxt == 1 and whole):
                        errors.append(f"seed {s}: {n} clocks in S_MEM then {NAMES[nxt]}")
    for (n, nxt), c in sorted(hist.items()):
        print(f"memlat {n:4d} clocks -> {NAMES[nxt]:8s} {c:7d} times")
    to_pass = sum(c for (n, nxt), c in hist.items() if nxt == 2)
    print(f"memlat: {seeds} programs (seeds {first}..{first + seeds - 1}), {sum(hist.values())} stays, "
          f"{to_pass} went to S_PASS, {len(errors)} errors")
    for e in errors[:20]:
        print("FAIL", e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
