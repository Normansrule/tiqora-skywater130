#!/usr/bin/env bash
# tile_identity.sh — prove the Tiny Tapeout tile is unchanged by a newer tree.
#
# Synthesizes tt_um_normansrule_tiqora onto sky130_fd_sc_hd from two source
# trees with the same Yosys script and compares the gate-level netlists byte
# for byte. The CPU / GPU / TPU modes are behind `ifdef TIQORA_MODES`, which
# the tile build never defines, so the netlist must not move.
#
# usage:  bash syn/tile_identity.sh REF [LIB] [DEFINES]
#   REF      a git revision (e.g. v20) or a directory holding a reference tree
#   LIB      sky130_fd_sc_hd__tt_025C_1v80.lib (default: as syn/area_sky130.sh)
#   DEFINES  extra Yosys defines for THIS tree only, e.g. "-DTIQORA_MODES"
#            (used to show the check fails when the tile does change)
# Exit 0 only when the two netlists are identical.
set -euo pipefail
cd "$(dirname "$0")/.."

REF=${1:?usage: bash syn/tile_identity.sh REF [LIB] [DEFINES]}
LIB=${2:-}
DEFS=${3:-}
if [ -z "$LIB" ]; then
    LIB=$(find "$HOME" ${PDK_ROOT:+"$PDK_ROOT"} -name 'sky130_fd_sc_hd__tt_025C_1v80.lib' -path '*sky130A*' 2>/dev/null | head -1)
fi
[ -f "$LIB" ] || { echo "error: no sky130_fd_sc_hd__tt_025C_1v80.lib found; pass it as the 2nd argument" >&2; exit 2; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
if [ -d "$REF" ]; then
    cp -r "$REF/src" "$WORK/ref_src"; cp "$REF/test/Makefile" "$WORK/ref_Makefile"
else
    mkdir -p "$WORK/ref_src"
    git archive "$REF" src | tar -x -C "$WORK" && mv "$WORK/src"/* "$WORK/ref_src/"
    git show "$REF:test/Makefile" > "$WORK/ref_Makefile"
fi

# the tile's own file list, in the tile's own order, from each tree's test/Makefile
files() { sed -n 's/^RTL *+\?= *\$(SRC)\//'"$2"'\//p' "$1" | tr '\n' ' '; }

net() {   # net SRC_DIR MAKEFILE OUT DEFINES
    local extra=""
    case "$4" in *TIQORA_MODES*) extra="$(basename "$1")/accel/tp_simd.sv $(basename "$1")/accel/tp_mac.sv" ;; esac
    ( cd "$1/.." && yosys -q -p "read_verilog -sv -DSYNTHESIS $4 $(files "$2" "$(basename "$1")") $extra;
        synth -top tt_um_normansrule_tiqora -flatten; dfflibmap -liberty $LIB; abc -liberty $LIB;
        opt_clean -purge; write_verilog -noattr $3" >/dev/null 2>&1 )
    sha256sum "$3" | cut -d' ' -f1
}

mkdir -p "$WORK/cur"; cp -r src "$WORK/cur/src"
A=$(net "$WORK/ref_src" "$WORK/ref_Makefile" "$WORK/ref.v" "")
B=$(net "$WORK/cur/src" "$PWD/test/Makefile" "$WORK/cur.v" "$DEFS")
CELLS_A=$(grep -c 'sky130_fd_sc_hd__' "$WORK/ref.v")
CELLS_B=$(grep -c 'sky130_fd_sc_hd__' "$WORK/cur.v")
echo "reference ($REF): $A  $CELLS_A cells"
echo "this tree ${DEFS:+($DEFS)}: $B  $CELLS_B cells"
if [ "$A" = "$B" ]; then
    echo "TILE NETLIST IDENTICAL"
else
    echo "TILE NETLIST CHANGED"; exit 1
fi
