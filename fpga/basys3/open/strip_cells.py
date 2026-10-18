# Copy a Yosys Xilinx cell library without the given modules. Yosys declares
# RAMB18E1/RAMB36E1 without behaviour (outputs float), so the netlist test
# takes those two from Xilinx's own unisim models instead.
import re, sys
src, dst, *names = sys.argv[1:]
s = open(src).read()
for m in names:
    s = re.sub(r"(\(\*[^)]*\*\)\s*)*module\s+%s\b.*?\nendmodule\b" % m, "", s, flags=re.S)
    assert not re.search(r"module\s+%s\b" % m, s), m
open(dst, "w").write(s)
