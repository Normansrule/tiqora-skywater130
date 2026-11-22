#!/usr/bin/env python3
"""audit_mutants.py — break the RTL on purpose and show the audit checks fail.

Each mutant is one textual edit to one source file. The script copies the
repository to a scratch directory, applies the edit, runs the make target
that should catch it, and counts the mutant as caught only if that target
exits non-zero. The original tree is never touched.

    python3 audit_mutants.py            # run every mutant
    python3 audit_mutants.py -k late    # only mutants whose name contains "late"

A mutant whose edit no longer applies (the source changed) is a failure too,
so the list cannot rot silently.
"""
import os, shutil, subprocess, sys, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# (name, file, old text, new text, make target in test/)
#
# Not listed, because it is equivalent: keeping qspi_ctrl's stream_open
# through reset. A stream only continues when the address also equals
# next_seq_addr, which reset sets to 0xFFFFFF, and the wake-up read that
# follows every reset reopens the stream itself; no test can tell.
# Likewise the UART's tsh alone (the line shows it only while tbits is
# non-zero, and a new byte reloads it) or tbits alone (tsh resets to all
# ones, so the rest of the byte goes out as idle-high bits): the mutant
# below keeps both, which does put the half-sent byte back on the line.
MUTANTS = [
    ("reset: a deadline stays armed through reset",
     "src/sync/sync_compare.sv",
     "armed[i]     <= 1'b0;",
     "armed[i]     <= (armed[i] === 1'b1);",
     "reset"),
    ("reset: a trigger pulse carries on through reset",
     "src/sync/sync_compare.sv",
     "pulse_cnt[i] <= '0;",
     "pulse_cnt[i] <= $isunknown(pulse_cnt[i]) ? '0 : pulse_cnt[i];",
     "reset"),
    ("reset: the event queue keeps its contents",
     "src/sync/sync_event_fifo.sv",
     "cnt      <= '0;",
     "cnt      <= $isunknown(cnt) ? '0 : cnt;",
     "reset"),
    ("reset: the timebase keeps counting from where it was",
     "src/sync/sync_timebase.sv",
     "now      <= 32'd0;",
     "now      <= $isunknown(now) ? 32'd0 : now;",
     "reset"),
    ("reset: the UART keeps sending a half-sent byte",
     "src/periph/tp_uart.sv",
     "tbits <= 4'd0;\n            tsh   <= 10'h3FF;",
     "tbits <= $isunknown(tbits) ? 4'd0 : tbits;\n            tsh   <= $isunknown(tsh) ? 10'h3FF : tsh;",
     "reset"),
    ("reset: flash chip select stays where it was",
     "src/bus/qspi_ctrl.sv",
     "cs_flash_n    <= 1'b1;",
     "cs_flash_n    <= $isunknown(cs_flash_n) ? 1'b1 : cs_flash_n;",
     "reset"),
    ("reset: RAM chip select stays where it was",
     "src/bus/qspi_ctrl.sv",
     "cs_ram_n      <= 1'b1;\n            sck",
     "cs_ram_n      <= $isunknown(cs_ram_n) ? 1'b1 : cs_ram_n;\n            sck",
     "reset"),
    ("reset: pins keep the program's function select",
     "src/periph/tp_periph.sv",
     "gpio_sel <= 8'hFF;",
     "gpio_sel <= $isunknown(gpio_sel) ? 8'hFF : gpio_sel;",
     "reset"),
    ("syncdiff: trigger pulse one tick short",
     "src/sync/sync_compare.sv",
     "if (fire)                        pulse_cnt[i] <= pw;",
     "if (fire)                        pulse_cnt[i] <= pw - 1'b1;",
     "syncdiff"),
    ("syncdiff: TPOP returns the head even when the queue is empty",
     "src/sync/sync_unit.sv",
     "tp_pkg::TF3_POP:  t_rdata = fifo_empty ? 32'd0 : fifo_rdata;",
     "tp_pkg::TF3_POP:  t_rdata = fifo_rdata;",
     "syncdiff"),
]


def run(sel=None):
    caught = total = 0
    for name, path, old, new, target in MUTANTS:
        if sel and sel not in name:
            continue
        total += 1
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, "r")
            shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "*.vvp", "*.vcd", "runs"))
            f = os.path.join(dst, path)
            src = open(f).read()
            if src.count(old) != 1:
                print(f"  FAIL  {name}: the edit does not apply to {path} ({src.count(old)} matches)")
                continue
            open(f, "w").write(src.replace(old, new))
            r = subprocess.run(["make", "-C", os.path.join(dst, "test"), target],
                               capture_output=True, text=True, errors="replace")
            ok = r.returncode != 0
            caught += ok
            out = (r.stdout + r.stderr).splitlines()
            fl = [l.strip() for l in out if l.strip().startswith("FAIL")]
            why = "\n          ".join(fl[:4]) if fl else (out[-1].strip() if out else "")
            print(f"  {'caught' if ok else 'FAIL  missed'}: {name} (make {target})")
            if ok:
                print(f"          {why}")
    print(f"\naudit mutants: {caught} of {total} caught")
    print("AUDIT MUTANTS PASSED" if caught == total and total else "AUDIT MUTANTS FAILED")
    return caught == total and total > 0


if __name__ == "__main__":
    sel = sys.argv[2] if sys.argv[1:2] == ["-k"] else None
    sys.exit(0 if run(sel) else 1)
