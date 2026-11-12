#!/bin/sh
# qspi_rx_formal.sh — prove that dropping the stream-start clear of the QSPI
# controller's rx register changes nothing it delivers (syn/formal/qspi_rx_props.svh).
# The properties are spliced into a scratch copy of src/bus/qspi_ctrl.sv and
# checked with Yosys + yosys-smtbmc + z3: a bounded check of 24 clocks from
# reset, then 12-induction. Run from the repository root; exits non-zero on a
# counterexample or an unproven property.
set -eu
OUT=${FORMAL_OUT:-/tmp/tp_qspi_rx}
mkdir -p "$OUT"
m=qspi_ctrl
awk -v inc="$(cat syn/formal/qspi_rx_props.svh)" '/^endmodule/ { print inc } { print }' src/bus/$m.sv > "$OUT/$m.sv"
grep -q 'rx_ref' "$OUT/$m.sv" || { echo "FAIL  could not splice the properties"; exit 1; }
yosys -q -l "$OUT/yosys.log" -p "read_verilog -formal -sv src/tp_pkg.sv $OUT/$m.sv; prep -top $m; async2sync; dffunmap; write_smt2 -wires $OUT/$m.smt2" >/dev/null 2>&1 \
  || { tail -5 "$OUT/yosys.log"; echo "FAIL  Yosys"; exit 1; }
yosys-smtbmc -s z3 -t 24 "$OUT/$m.smt2" > "$OUT/bmc.log" 2>&1 \
  || { grep -E 'Assert failed|failed' "$OUT/bmc.log" | head -5; echo "FAIL  counterexample within 24 clocks"; exit 1; }
yosys-smtbmc -s z3 -i -t 12 "$OUT/$m.smt2" > "$OUT/ind.log" 2>&1 \
  || { grep -E 'Assert failed|failed' "$OUT/ind.log" | head -5; echo "FAIL  induction did not close"; exit 1; }
echo "qspi rx: proven (bounded 24 clocks, then 12-induction)"
