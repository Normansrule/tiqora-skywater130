# Replace undefined (x) bits in cell parameters and tied cell inputs by 0:
# a configured FPGA powers up every flip-flop INIT, BRAM INIT/SRVAL and
# constant input at a defined value. Plain assigns are left untouched.
import re, sys
cell = re.compile(r"^\s*\.\w+\(\d+'[hb][0-9a-fx]+\),?$")
lit = re.compile(r"(\d+'[hb])([0-9a-fx]+)")
out = []
for line in open(sys.argv[1]):
    if cell.match(line.rstrip("\n")):
        line = lit.sub(lambda m: m.group(1) + m.group(2).replace("x", "0"), line)
    out.append(line)
open(sys.argv[2], "w").writelines(out)
