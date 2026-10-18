# fpga/basys3/Makefile — Tiqora on a Digilent Basys 3 (Artix-7 XC7A35T)
#
#   make sim            simulate the whole board design (three runs, ~5 min)
#   make image          build the program baked into the emulated flash (flash.mem)
#   make bit            build the bitstream with Vivado (WebPACK is free for this part)
#   make prog           program the board over USB with Vivado
#   make resources      Yosys synthesis for Xilinx 7-series: LUT / FF / BRAM count
#
#   PROG=../../sw/examples/basys3_demo.c   the program for `make image`
#   PMOD=1                                 use the real QSPI Pmod on JA instead of the emulator
ROOT   = ../..
SRC    = $(ROOT)/src
RTL    = $(SRC)/tp_pkg.sv $(SRC)/core/tp_nregfile.sv $(SRC)/core/tp_ncore.sv \
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
TOBYTES = python3 -c "import sys; d=open(sys.argv[1],'rb').read(); open(sys.argv[2],'w').write('\n'.join('%02x'%b for b in d)+'\n')"
TOWORDS = python3 -c "import sys; d=open(sys.argv[1],'rb').read(); d+=b'\0'*((-len(d))%4); open(sys.argv[2],'w').write('\n'.join('%08x'%int.from_bytes(d[i:i+4],'little') for i in range(0,len(d),4))+'\n')"

.PHONY: sim image bit prog resources clean
image:
	$(ZCC) $(CF) -T $(ROOT)/sw/link.ld -Wl,--gc-sections -o flash.elf $(LIBS) $(PROG)
	python3 $(ROOT)/sw/rv32e_check.py flash.elf
	$(ZOBJ) -O binary flash.elf flash.bin && $(TOBYTES) flash.bin flash.mem
	@echo "flash.mem: $$(wc -l < flash.mem) bytes, baked into the bitstream by make bit"

sim:
	@sh $(ROOT)/test/iv.sh -g2012 -o tb_basys3.vvp -s tb_basys3 $(RTL) $(FPGA) tb_basys3.sv
	$(ZCC) $(CF) -DBAUD_DIV=8 -T $(ROOT)/sw/link.ld -Wl,--gc-sections -o sim.elf $(LIBS) $(ROOT)/sw/examples/c_selftest.c
	$(ZOBJ) -O binary sim.elf sim.bin && $(TOBYTES) sim.bin sim_flash.mem
	vvp -n tb_basys3.vvp +MODE=selftest | grep -v "^VCD\|readmemh"
	$(ZCC) $(CF) -DBAUD_DIV=8 -T $(ROOT)/sw/link_ram.ld -Wl,--gc-sections -o sim.elf $(LIBS) $(ROOT)/sw/examples/c_selftest.c
	$(ZOBJ) -O binary sim.elf sim.bin && $(TOWORDS) sim.bin sim_ram.hex && printf 'ff\n' > sim_flash.mem
	vvp -n tb_basys3.vvp +MODE=boot | grep -v "^VCD\|readmemh"
	$(ZCC) $(CF) -DBAUD_DIV=8 -DHALF_SECOND=40000u -DDEBOUNCE=200u -T $(ROOT)/sw/link.ld -Wl,--gc-sections \
	    -o sim.elf $(LIBS) $(ROOT)/sw/examples/basys3_demo.c
	$(ZOBJ) -O binary sim.elf sim.bin && $(TOBYTES) sim.bin sim_flash.mem
	vvp -n tb_basys3.vvp +MODE=demo | grep -v "^VCD\|readmemh"

bit: flash.mem
	vivado -mode batch -nojournal -nolog -source build.tcl -tclargs $(PMOD)
flash.mem:
	$(MAKE) image

prog:
	vivado -mode batch -nojournal -nolog -source program.tcl

resources:
	@echo 'read_verilog -sv -DSYNTHESIS $(RTL) $(FPGA)' > /tmp/tp_xc7.ys
	@echo 'synth_xilinx -family xc7 -top basys3_top -flatten' >> /tmp/tp_xc7.ys
	@echo 'stat' >> /tmp/tp_xc7.ys
	yosys -q -l /tmp/tp_xc7.log -s /tmp/tp_xc7.ys >/dev/null; \
	  python3 resources.py /tmp/tp_xc7.log

clean:
	rm -rf *.vvp *.elf *.bin sim_flash.mem sim_ram.hex .zig-cache-fpga build
