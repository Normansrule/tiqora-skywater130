# build.tcl — Tiqora bitstream for the Digilent Basys 3 (XC7A35T-1CPG236C),
# Vivado non-project mode. Run from this directory:
#     vivado -mode batch -source build.tcl -tclargs 0     (0 = emulated memory, 1 = QSPI Pmod on JA)
# or simply `make bit` / `make bit PMOD=1`. Vivado ML Standard (free) supports this part.
# flash.mem (the program baked into the emulated flash) must exist: `make image`.
set use_pmod [expr {[llength $argv] > 0 ? [lindex $argv 0] : 0}]
set here [file normalize [file dirname [info script]]]
set root [file normalize "$here/../.."]
set part xc7a35tcpg236-1
set out  "$here/build"
file mkdir $out

if {!$use_pmod && ![file exists "$here/flash.mem"]} {
    puts "ERROR: flash.mem is missing. Run `make image` first."
    exit 1
}

set rtl {
    src/tp_pkg.sv src/accel/tp_simd.sv src/accel/tp_mac.sv
    src/core/tp_nregfile.sv src/core/tp_ncore.sv
    src/sync/sync_timebase.sv src/sync/sync_capture.sv src/sync/sync_event_fifo.sv
    src/sync/sync_compare.sv src/sync/sync_unit.sv src/periph/tp_uart.sv
    src/periph/tp_periph.sv src/boot/tp_bootrom.sv src/bus/tp_bus.sv
    src/bus/qspi_ctrl.sv src/tp_soc.sv src/tt_um_normansrule_tiqora.sv
    fpga/qspi_emu.sv fpga/basys3/basys3_top.sv
}
foreach f $rtl { read_verilog -sv "$root/$f" }
read_xdc "$here/basys3.xdc"
if {!$use_pmod} { read_mem "$here/flash.mem" }

cd $here                                  ;# $readmemh("flash.mem") resolves from here
# TIQORA_MODES: the FPGA build has the CPU / GPU / TPU modes (docs/MODES.md)
synth_design -top basys3_top -part $part -generic USE_PMOD=$use_pmod -verilog_define TIQORA_MODES
opt_design
place_design
phys_opt_design
route_design

report_utilization    -file "$out/utilization.txt"
report_timing_summary -file "$out/timing.txt"
set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
puts "worst setup slack at 50 MHz: $wns ns"
if {$wns < 0} {
    puts "ERROR: timing not met; see $out/timing.txt"
    exit 1
}
write_bitstream -force "$out/tiqora_basys3.bit"
puts "wrote $out/tiqora_basys3.bit — program it with: make prog"
