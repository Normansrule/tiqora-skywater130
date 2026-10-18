#!/usr/bin/env python3
"""readme_check.py — the README's minimal program must do what the README says.

  extract README OUT.c   copy the first C block after "A minimal program" verbatim
  verify  LOG ...        check each simulation log for the promised behaviour:
                           the greeting on the UART, exactly one TRIG0 pulse of
                           the default 8 ticks at the uo_out[0] PIN, uo_out[7]
                           toggled high, a clean return, and where it ran from
Exits non-zero on any failure, printing every check."""
import re, sys

def extract(readme, out):
    text = open(readme).read()
    i = text.index("A minimal program")
    m = re.search(r"```c\n(.*?)```", text[i:], re.S)
    open(out, "w").write(m.group(1))
    print(f"extracted {len(m.group(1).splitlines())} lines of C from {readme}")

def verify(logs):
    checks = fails = 0
    for log in logs:
        t = open(log).read()
        where = re.search(r"ran from\s+(\w+)", t)          # %s pads to the widest value
        pins = re.search(r"TRIG0 pulses=(\d+) first-width=(\d+) clocks, TRIG1 pulses=\d+, uo_out\[7\]=([01xz])", t)
        tests = [
            ("prints Hi Tiqora on the UART", "Hi Tiqora\n" in t),
            ("returns cleanly from main()", "main() returned" in t and "ILLEGAL" not in t),
            ("exactly one pulse reaches the TRIG0 pin", bool(pins) and pins.group(1) == "1"),
            ("the pulse is the default 8 ticks wide", bool(pins) and pins.group(2) == "8"),
            ("uo_out[7] was toggled high as a GPIO", bool(pins) and pins.group(3) == "1"),
        ]
        label = where.group(1) if where else "?"
        for name, ok in tests:
            checks += 1; fails += (not ok)
            print(f"  {'ok  ' if ok else 'FAIL'}  [{label}] {name}")
        if pins: print(f"        pins: {pins.group(0)}")
    print(f"\n{checks} checks, {fails} failures")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    if sys.argv[1] == "extract": extract(sys.argv[2], sys.argv[3])
    else: verify(sys.argv[2:])
