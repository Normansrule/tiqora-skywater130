# fpga/basys3/Makefile — Tiqora on a Digilent Basys 3 (Artix-7 XC7A35T)
#
#   make sim            simulate the whole board design (four runs, ~6 min)
#   make image          build the program baked into the emulated flash (flash.mem)
#   make bit            build the bitstream with Vivado (WebPACK is free for this part)
#   make prog           program the board over USB with Vivado
#   make resources      Yosys synthesis for Xilinx 7-series: LUT / FF / BRAM count
#   make bit-open       bitstream without Vivado: Yosys + nextpnr-xilinx + prjxray (build/open)
#   make netlist        C self-test on the synthesized netlist, board pins only (~10 min)
#   make record         the demo run again, recorded by rec_basys3.sv for docs/tools/fpga_media.py
#
#   PROG=../../sw/examples/basys3_demo.c   the program for `make image`
#   PMOD=1                                 use the real QSPI Pmod on JA instead of the emulator
SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -ec    # a failing vvp fails make, even behind | grep
ROOT   = ../..
SRC    = $(ROOT)/src
# The FPGA build includes the CPU / GPU / TPU modes (src/accel, TIQORA_MODES).
DEFS   = -DTIQORA_MODES
RTL    = $(SRC)/tp_pkg.sv $(SRC)/accel/tp_simd.sv $(SRC)/accel/tp_mac.sv $(SRC)/core/tp_nregfile.sv $(SRC)/core/tp_ncore.sv \
         $(SRC)/sync/sync_timebase.sv $(SRC)/sync/sync_capture.sv $(SRC)/sync/sync_event_fifo.sv \
         $(SRC)/sync/sync_compare.sv $(SRC)/sync/sync_unit.sv $(SRC)/periph/tp_uart.sv \
         $(SRC)/periph/tp_periph.sv $(SRC)/boot/tp_bootrom.sv $(SRC)/bus/tp_bus.sv \
         $(SRC)/bus/qspi_ctrl.sv $(SRC)/tp_soc.sv $(SRC)/tt_um_normansrule_tiqora.sv
FPGA   = ../qspi_emu.sv basys3_top.sv
PROG  ?= $(ROOT)/sw/examples/basys3_demo.c
PMOD  ?= 0

ZIG_CACHE = $(CURDIR)/.zig-cache-fpga/$$$$          # per process: parallel builds never collide
ZCC  = rm -rf $(ZIG_CACHE) && ZIG_GLOBAL_CACHE_DIR=$(ZIG_CACHE) ZIG_LOCAL_CACHE_DIR=$(ZIG_CACHE) \
       python3 -m ziglang cc -target riscv32-freestanding-none -mcpu=generic_rv32+e-i -mabi=ilp32e
ZOBJ = python3 -m ziglang objcopy
CF   = -Os -g -fno-unwind-tables -fno-asynchronous-unwind-tables -ffreestanding -nostdlib \
       -fno-builtin -ffunction-sections -fdata-sections -Wall -Wextra
LIBS = $(ROOT)/sw/crt0.S $(ROOT)/sw/lib/rt.c $(ROOT)/sw/lib/tp_printf.c
TOBYTES = python3 -c "import sys; d=open(sys.argv[1],'rb').read(); assert len(d)<=32768, 'image larger than the 32 KiB flash'; d+=b'\\xff'*(32768-len(d)); open(sys.argv[2],'w').write('\n'.join('%02x'%b for b in d)+'\n')"
TOWORDS = python3 -c "import sys; d=open(sys.argv[1],'rb').read(); d+=b'\0'*((-len(d))%4); open(sys.argv[2],'w').write('\n'.join('%08x'%int.from_bytes(d[i:i+4],'little') for i in range(0,len(d),4))+'\n')"

.PHONY: sim-modes netlist-modes sim image bit prog resources clean bit-open netlist record
image:
	$(ZCC) $(CF) -T $(ROOT)/sw/link.ld -Wl,--gc-sections -o flash.elf $(LIBS) $(PROG)
	python3 $(ROOT)/sw/rv32e_check.py --modes flash.elf
	$(ZOBJ) -O binary flash.elf flash.bin && $(TOBYTES) flash.bin flash.mem
	@echo "flash.mem: $$(stat -c %s flash.bin) bytes of program, padded to 32 KiB, baked into the bitstream by make bit"

sim:
	@sh $(ROOT)/test/iv.sh -g2012 $(DEFS) -o tb_basys3.vvp -s tb_basys3 $(RTL) $(FPGA) tb_basys3.sv
	$(ZCC) $(CF) -DBAUD_DIV=8 -T $(ROOT)/sw/link.ld -Wl,--gc-sections -o sim.elf $(LIBS) $(ROOT)/sw/examples/c_selftest.c
	$(ZOBJ) -O binary sim.elf sim.bin && $(TOBYTES) sim.bin sim_flash.mem
	vvp -n tb_basys3.vvp +MODE=selftest | grep -v "^VCD\|readmemh"
	$(ZCC) $(CF) -DBAUD_DIV=8 -T $(ROOT)/sw/link_ram.ld -Wl,--gc-sections -o sim.elf $(LIBS) $(ROOT)/sw/examples/c_selftest.c
	$(ZOBJ) -O binary sim.elf sim.bin && $(TOWORDS) sim.bin sim_ram.hex && : > empty.bin && $(TOBYTES) empty.bin sim_flash.mem
	vvp -n tb_basys3.vvp +MODE=boot | grep -v "^VCD\|readmemh"
	$(ZCC) $(CF) -DBAUD_DIV=8 -DHALF_SECOND=40000u -DDEBOUNCE=200u -T $(ROOT)/sw/link.ld -Wl,--gc-sections \
	    -o sim.elf $(LIBS) $(ROOT)/sw/examples/basys3_demo.c
	$(ZOBJ) -O binary sim.elf sim.bin && $(TOBYTES) sim.bin sim_flash.mem
	vvp -n tb_basys3.vvp +MODE=demo | grep -v "^VCD\|readmemh"
	$(MAKE) --no-print-directory sim-modes

# the demo run of `make sim`, with rec_basys3.sv writing down what the board shows
record:
	@sh $(ROOT)/test/iv.sh -g2012 $(DEFS) -o rec_basys3.vvp -s tb_basys3 -s rec_basys3 $(RTL) $(FPGA) tb_basys3.sv rec_basys3.sv
	$(ZCC) $(CF) -DBAUD_DIV=8 -DHALF_SECOND=40000u -DDEBOUNCE=200u -T $(ROOT)/sw/link.ld -Wl,--gc-sections \
	    -o sim.elf $(LIBS) $(ROOT)/sw/examples/basys3_demo.c
	$(ZOBJ) -O binary sim.elf sim.bin && $(TOBYTES) sim.bin sim_flash.mem
	vvp -n rec_basys3.vvp +MODE=demo +REC=$(ROOT)/docs/fpga/basys3_demo.rec | grep -v "^VCD\|readmemh"

# CPU -> GPU -> TPU -> CPU demo alone (sw/examples/modes_demo.c), checked at
# the pins and again against sw/modes_model.py
sim-modes:
	@sh $(ROOT)/test/iv.sh -g2012 $(DEFS) -o tb_basys3.vvp -s tb_basys3 $(RTL) $(FPGA) tb_basys3.sv
	$(ZCC) $(CF) -DBAUD_DIV=8 -T $(ROOT)/sw/link.ld -Wl,--gc-sections -o sim.elf $(LIBS) $(ROOT)/sw/examples/modes_demo.c
	$(ZOBJ) -O binary sim.elf sim.bin && $(TOBYTES) sim.bin sim_flash.mem
	vvp -n tb_basys3.vvp +MODE=modes | grep -v "^VCD\|readmemh"
	python3 $(ROOT)/sw/check_modes_demo.py modes_uart.txt

bit: flash.mem
	vivado -mode batch -nojournal -nolog -source build.tcl -tclargs $(PMOD)
flash.mem:
	$(MAKE) image

prog:
	vivado -mode batch -nojournal -nolog -source program.tcl

resources:
	@echo 'read_verilog -sv -DSYNTHESIS $(DEFS) $(RTL) $(FPGA)' > /tmp/tp_xc7.ys
	@echo 'synth_xilinx -family xc7 -top basys3_top -flatten' >> /tmp/tp_xc7.ys
	@echo 'stat' >> /tmp/tp_xc7.ys
	yosys -q -l /tmp/tp_xc7.log -s /tmp/tp_xc7.ys >/dev/null; \
	  python3 resources.py /tmp/tp_xc7.log

clean:
	rm -rf *.vvp *.elf *.bin modes_uart.txt sim_flash.mem sim_ram.hex .zig-cache-fpga build

# ---- open-source flow (no Vivado) ----------------------------------------
# Tool locations; the defaults assume everything is on PATH or next to this file.
# CHIPDB: nextpnr-xilinx chip database for xc7a35tcpg236-1. PRJXRAY: a checkout
# with build/tools/xc7frames2bit built. UNISIMS: Xilinx's simulation models
# (RAMB18E1, RAMB36E1, glbl) from github.com/Xilinx/XilinxUnisimLibrary.
YOSYS      ?= yosys
NEXTPNR    ?= nextpnr-xilinx
CHIPDB     ?= xc7a35t.bin
PRJXRAY    ?= prjxray
PRJXRAY_DB ?= $(PRJXRAY)/database/artix7
# FASM_PYTHON: a Python that has prjxray's fasm package (pip install fasm)
FASM_PYTHON ?= python3
UNISIMS    ?= XilinxUnisimLibrary/verilog/src
YSHARE      = $(shell $(YOSYS)-config --datdir)
PART        = xc7a35tcpg236-1
ABS         = $(abspath $(RTL) $(FPGA))

bit-open: flash.mem
	mkdir -p build/open
	{ echo 'read_verilog -sv -DSYNTHESIS $(DEFS) $(ABS)'; cat open/map.ys; echo 'tee -o utilization.txt stat'; echo 'write_json basys3.json'; } > build/open/bit.ys
	cp flash.mem build/open/flash.mem
	cd build/open && $(YOSYS) -q -l synth.log bit.ys > /dev/null
	$(NEXTPNR) --chipdb $(CHIPDB) --xdc basys3.xdc --json build/open/basys3.json --fasm build/open/basys3.fasm --seed 1 -l build/open/pnr.log
	$(FASM_PYTHON) $(PRJXRAY)/utils/fasm2frames.py --db-root $(PRJXRAY_DB) --part $(PART) --sparse build/open/basys3.fasm build/open/basys3.frames
	$(PRJXRAY)/build/tools/xc7frames2bit --part_file $(PRJXRAY_DB)/$(PART)/part.yaml --part_name $(PART) \
	    --frm_file build/open/basys3.frames --output_file build/open/tiqora_basys3.bit
	@grep "Max frequency" build/open/pnr.log | tail -1
	@echo "build/open/tiqora_basys3.bit: open-source flow, not Vivado sign-off"

# The same synthesis as bit-open, but with the C self-test in flash; the
# netlist is simulated with only the board pins visible (tb_pins.sv).
netlist:
	mkdir -p build/netlist
	$(ZCC) $(CF) -DBAUD_DIV=8 -T $(ROOT)/sw/link.ld -Wl,--gc-sections -o build/netlist/st.elf $(LIBS) $(ROOT)/sw/examples/c_selftest.c
	$(ZOBJ) -O binary build/netlist/st.elf build/netlist/st.bin && $(TOBYTES) build/netlist/st.bin build/netlist/flash.mem
	{ echo 'read_verilog -sv -DSYNTHESIS $(DEFS) $(ABS)'; cat open/map.ys; echo 'write_verilog -noattr netlist.v'; } > build/netlist/sim.ys
	cd build/netlist && $(YOSYS) -q -l synth.log sim.ys > /dev/null
	python3 open/xfix.py build/netlist/netlist.v build/netlist/netlist_hw.v
	python3 open/strip_cells.py $(YSHARE)/xilinx/cells_sim.v build/netlist/cells_sim.v RAMB18E1 RAMB36E1
	python3 open/strip_cells.py $(YSHARE)/xilinx/cells_xtra.v build/netlist/cells_xtra.v RAMB18E1 RAMB36E1
	@sh $(ROOT)/test/iv.sh -g2012 -o build/netlist/gls.vvp -s tb_pins -s glbl open/tb_pins.sv build/netlist/netlist_hw.v \
	    build/netlist/cells_sim.v build/netlist/cells_xtra.v $(UNISIMS)/unisims/RAMB18E1.v $(UNISIMS)/unisims/RAMB36E1.v $(UNISIMS)/glbl.v
	vvp -n build/netlist/gls.vvp

# The CPU -> GPU -> TPU -> CPU demo on the same netlist, at the board pins.
# The expected transcript comes from sw/modes_model.py, not from the RTL.
netlist-modes:
	mkdir -p build/netlist_modes
	$(ZCC) $(CF) -DBAUD_DIV=8 -T $(ROOT)/sw/link.ld -Wl,--gc-sections -o build/netlist_modes/md.elf $(LIBS) $(ROOT)/sw/examples/modes_demo.c
	python3 $(ROOT)/sw/rv32e_check.py --modes build/netlist_modes/md.elf
	$(ZOBJ) -O binary build/netlist_modes/md.elf build/netlist_modes/md.bin && $(TOBYTES) build/netlist_modes/md.bin build/netlist_modes/flash.mem
	python3 -c "import sys; sys.path.insert(0, '$(ROOT)/sw'); import check_modes_demo as c; open('build/netlist_modes/expect.txt', 'w').write(chr(10).join(c.expected()) + chr(10))"
	{ echo 'read_verilog -sv -DSYNTHESIS $(DEFS) $(ABS)'; cat open/map.ys; echo 'write_verilog -noattr netlist.v'; } > build/netlist_modes/sim.ys
	cd build/netlist_modes && $(YOSYS) -q -l synth.log sim.ys > /dev/null
	python3 open/xfix.py build/netlist_modes/netlist.v build/netlist_modes/netlist_hw.v
	python3 open/strip_cells.py $(YSHARE)/xilinx/cells_sim.v build/netlist_modes/cells_sim.v RAMB18E1 RAMB36E1
	python3 open/strip_cells.py $(YSHARE)/xilinx/cells_xtra.v build/netlist_modes/cells_xtra.v RAMB18E1 RAMB36E1
	@sh $(ROOT)/test/iv.sh -g2012 -o build/netlist_modes/gls.vvp -s tb_pins -s glbl open/tb_pins.sv build/netlist_modes/netlist_hw.v \
	    build/netlist_modes/cells_sim.v build/netlist_modes/cells_xtra.v $(UNISIMS)/unisims/RAMB18E1.v $(UNISIMS)/unisims/RAMB36E1.v $(UNISIMS)/glbl.v
	vvp -n build/netlist_modes/gls.vvp +EXPECT=build/netlist_modes/expect.txt

