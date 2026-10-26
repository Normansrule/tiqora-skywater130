# Tiqora — a RISC-V microcontroller the size of a grain of salt

**RISC-V RV32E · Tiny Tapeout 2×2 tiles · SkyWater 130 nm · runs on a Basys 3 FPGA (Artix-7)**

![Zooming from the whole Tiqora chip down to single transistors: the whole tile, one block, single cells](images/zoom_steps.png)

<sub>From the whole chip to single transistors: the design's ~5,500 real sky130 logic cells,
drawn from SkyWater's own cell geometry with KLayout (`docs/tools/zoom_animation.py`, stills by `docs/tools/datasheet_stills.py`).</sub>

> **Tiqora was called TinyPulse until October 2026.** Old links redirect; the C API, opcodes,
> register map and bootloader protocol are unchanged, and `#include "tinypulse.h"` still works.

**A complete 32-bit microcontroller in 0.115 mm² of silicon — six Tiny Tapeout tiles (a 3 × 2 block), 420 €.**
It runs RISC-V code from a 16 MB flash chip — or straight from a USB serial link, no
programmer needed — has 16 MB of RAM, 8 inputs, 8 outputs, a
UART for `printf`, and something no ordinary microcontroller has: **instructions that treat
time as an operand.** It timestamps pin edges in hardware, fires output pulses on the exact
clock tick it was told to (cycle-exact relative to the supplied clock; oscillator error and pad
delay are separate matters), and can be disciplined to an external reference.

| | |
|---|---|
| **Instruction set** | RV32E (all 37 base instructions) + 11 **Xpulse** timing instructions |
| **Core** | nibble-serial: 4 bits per clock, 15 × 32-bit registers |
| **Clock** | 50 MHz target; 20 ns timestamp resolution |
| **Memory** | 16 MB QSPI flash (code) + 2 × 8 MB QSPI RAM (data), via the Tiny Tapeout QSPI Pmod |
| **I/O** | 8 inputs · 8 outputs · UART on the demo board's USB bridge |
| **Timing** | 32-bit timebase with rate trim · 2 deadline triggers · 8 capture channels · event queue |
| **Programming** | through the demo board's own USB-C port, a USB-UART adapter, or the flasher |
| **Speed** | 18.3 clocks per instruction on straight-line code, 40.3 on a mixed sort/checksum/CRC benchmark (measured, RTL simulation) — 2.7 and 1.2 million instructions/s at 50 MHz |
| **Logic timing** | 12.57 ns worst path at the slow corner against 20 ns (estimate before wires, `make timing`, main 2026-10-25) |
| **Area** | 50,880 µm² of standard cells, 44% of the 3 × 2 die (measured, `make area`, Yosys 0.33, main 2026-10-25, with the cells this design's flow excludes (src/synth_exclude.cells) removed; before placement) |
| **Cost** | 3 × 2 Tiny Tapeout tiles = 420 € (70 € a tile) |
| **Verification** | 490 checks in 17 suites and 6 cocotb tests on RTL; the official RISC-V tests 37/37; cocotb on a sky130 gate netlist (measured, main 2026-10-25) |


## Status

Each row names the revision it applies to. Results from v19 that the v20 core change could
affect are marked for re-run rather than carried forward.

| | |
|---|---|
| ✅ **RTL simulation (main 2026-10-25)** | 490 checks across seventeen suites, including 230 for the CPU, GPU and TPU modes (`cd test && make sim`), plus 6 cocotb tests from the pins only |
| ✅ **README example (v20)** | the minimal program below, compiled verbatim from this file, run from flash and RAM: one 8-tick pulse at the TRIG0 pin (`make readme`) |
| ✅ **Software (v20)** | Clang-compiled C, the UART bootloader, `printf`, software SPI, all run on the simulated chip |
| ✅ **FPGA, simulated (v20)** | the whole Digilent Basys 3 design at 100 MHz: 26 checks over four programs, including the CPU, GPU, TPU mode demo (`make -C fpga/basys3 sim`) |
| ✅ **Docs (v20)** | every link, image, `make` target and script mentioned exists (`make docs`, part of `make sim`) |
| ✅ **Official RISC-V tests (v20)** | 37/37 (`make act`) |
| ✅ **Gate level (v20)** | cocotb on a sky130 netlist: 5 pass, 1 skipped by design (`make gl`) |
| ✅ **Area (main 2026-10-25)** | 50,880 µm², 1,191 flip-flops, 44% of the 3 × 2 die (`make area`); logic timing 12.57 ns, an estimate before wires (`make timing`) |
| ✅ **Layout** | 3 × 2, density 50: `gds`, `precheck` and `gl_test` pass (GitHub run 40213473443, LibreLane 3.0.14, 7bee2a9) |
| ⚠️ **Routed timing** | +6.45 ns setup slack at the typical corner, −0.75 ns at the worst slow corner (22 paths); hold met everywhere (measured, local LibreLane 3.0.14 run of `src/config.json`, 2026-10-26: DRC 0, LVS 0, antenna 0) |
| ⏳ **FPGA board** | open-tool bitstream built and checked at the pins in simulation; not built with Vivado, not run on a real Basys 3 |
| ⏳ **Silicon** | after submission to a Tiny Tapeout shuttle |

## What it looks like

**From the board to the silicon.** The chip arrives in a QFN package on a carrier board that
plugs into the demo board; inside, every project on the shuttle shares one die behind a
multiplexer, and Tiqora is one 3 × 2 block of tiles on it:

![From the demo board to Tiqora's tiles on the die](images/board_to_silicon.svg)


**An illustration, not a placement.** There is no routed layout yet. This is every real sky130
cell of the synthesized design, drawn with its real geometry but packed into rows block by
block by a simple script (`docs/tools/layout_preview.py`) inside the 334.9 × 225.8 µm tile:

![Illustration: Tiqora's real sky130 cells packed into rows block by block, not a placement](images/layout_blocks.png)

**One flip-flop, taken apart.** The register file is 480 copies of this cell. Its real
manufacturing layers — N-well, diffusion, polysilicon gates, contacts, local interconnect, vias,
metal 1 — separate and rejoin:

![One sky130 D flip-flop exploded into its manufacturing layers](images/flipflop_exploded.svg)

## Explore it interactively

[**Open the explorer site**](https://htmlpreview.github.io/?https://github.com/Normansrule/tiqora-skywater130/blob/main/docs/site/index.html)
(or open `docs/site/index.html` from a clone): six sequences recorded from the RTL with play,
step and captions, a chip atlas of every block, measured area against the die, and the evidence
behind every status line.

## How small?

![Tiqora next to a human hair, a grain of salt and a red blood cell](images/scale.svg)

The whole chip — CPU, 480 flip-flops of registers, memory controller, timing unit, UART and
GPIO — is about 335 µm across. A strand of hair is about 70 µm wide; a grain of table salt is
about 300 µm.

![Transistor-level close-up of the register file](images/layout_zoom.png)

<sub>A 24 × 14 µm window into the register file: real sky130 D flip-flops. Red is
polysilicon (transistor gates), green is diffusion, white squares are contacts, blue
hatching is local interconnect. Every other row is mirrored so neighbours share a power rail.</sub>

## Pinout

**Every pin, where it really is.** All 43 pins of the tile sit on metal 4 along its top edge, at
the exact positions from Tiny Tapeout's own 3 × 2 template, above the design's real cells. The
band names each one with its function; the pulses show which way signals flow:

![All 43 pins of the 3x2 tile at their real positions](images/pin_map.svg)

**What each pin connects to.** The complete system — the QSPI memory Pmod, the demo board's
RP2350 as clock, reset and USB-serial bridge, plus sensors in and triggers out:

![Every Tiqora pin wired to the device it connects to](images/connections.svg)

The same pins, by function:

![Tiqora pinout](images/pinout.svg)

| Pin | Function | Pin | Function (reset) / GPIO |
|---|---|---|---|
| `ui[0]` | IN0 · capture 0 · QSPI latency bit 0 at reset | `uo[0]` | TRIG0 deadline trigger / OUT0 |
| `ui[1]` | IN1 · capture 1 · latency bit 1 | `uo[1]` | TRIG1 deadline trigger / OUT1 |
| `ui[2]` | IN2 · capture 2 · latency bit 2 | `uo[2]` | EVT — an event is waiting / OUT2 |
| `ui[3]` | **UART RX** · capture 3 | `uo[3]` | OVF — event queue overflowed / OUT3 |
| `ui[4]` | IN4 · capture 4 | `uo[4]` | **UART TX** / OUT4 |
| `ui[5]` | IN5 · capture 5 | `uo[5]` | HALT — ECALL/EBREAK reached / OUT5 |
| `ui[6]` | IN6 · capture 6 | `uo[6]` | ILLEGAL instruction seen / OUT6 |
| `ui[7]` | IN7 · capture 7 · **BOOT**: high during reset runs the UART bootloader | `uo[7]` | HEARTBEAT ≈ 3 Hz / OUT7 |

**Every output pin is either a GPIO or its built-in function, chosen per pin by `GPIO_SEL`.**
At reset all eight show their functions, so a freshly powered chip is observable with no
software: the heartbeat blinks, UART TX idles high, HALT lights when a program ends.

`uio[0..7]` connect to the **Tiny Tapeout QSPI Pmod** in its standard pinout (CS0 flash, SD0,
SD1, SCK, SD2, SD3, CS1 RAM A, CS2 RAM B). While reset is held, all eight are released so the
demo board's RP2040 can program the flash without unplugging anything.

**No setup script needed.** The Pmod's flash (W25Q128JV) and RAMs (APS6404L) power up in slow
single-bit mode. Two microseconds after every reset, Tiqora wakes them itself: it puts the
flash into continuous quad read and both RAMs into quad (QPI) mode, and it does this correctly
whether the chips are fresh from power-up or were left in fast mode by a previous run.

## Inside

![Block diagram](images/block_diagram.svg)

### Why nibble-serial

The biggest block on a small RISC-V chip is the register file, and most of its area isn't
storage — it's the multiplexers that pick one of 16 registers, 32 bits at a time. Tiqora
reads registers **4 bits at a time**, so those multiplexers shrink eightfold. Measured against
the real sky130 library:

| Register file design | Area |
|---|---:|
| Conventional: two 32-bit read ports | 21,837 µm² |
| One 32-bit read port | 18,155 µm² |
| **Tiqora: two 4-bit ports, rotating** | **11,322 µm²** |

Every register rotates by one nibble on every clock, in lockstep with a 3-bit phase counter,
so at phase *k* every register presents its *k*-th nibble on the same four wires:

![The rotating register file](images/regfile_rotation.svg)

An addition is eight clocks through one 4-bit adder, the carry held in a flip-flop between them:

![A 32-bit add, four bits per clock](images/nibble_add.svg)

That sounds slow until you remember that instructions arrive over a 4-bit QSPI bus, at least
16 clocks per word. An 8-clock execute isn't the bottleneck. The same idea lets TinyQV (Michael
Bell) fit a RISC-V microcontroller in 2 × 2 tiles; this is an independent implementation.

### Where the area goes

| Block | Area (µm²) |
|---|---:|
| Register file (15 × 32 bits) | 11,286 |
| CPU core (decode, datapath, control) | 10,157 |
| QSPI memory controller (with power-up wake-up) | 6,226 |
| Deadline comparators (2) | 5,313 |
| Timebase + rate trim | 4,539 |
| Timing unit control | 4,383 |
| UART | 2,706 |
| Event queue | 2,529 |
| GPIO registers | 1,403 |
| Bus | 1,300 |
| Boot ROM (43-instruction UART bootloader) | 1,010 |
| Capture channels (8) | 891 |

<sub>Per-block numbers come from the hierarchical netlist (52,000 µm² total). The flattened netlist
the flow actually builds is smaller, because synthesis optimizes across block boundaries: 50,880 µm²
with Yosys 0.33 (<code>make area</code>) and 48,763 µm² in LibreLane 3.0.14's own synthesis, 44% of the
3 × 2 die. <code>src/config.json</code> sets the placement density to 50. Reproduce with <code>cd test && make area</code>.</sub>

The previous version of this chip had a conventional 32-bit core and measured 69,866 µm² —
it needed 4 × 2 tiles (560 €). The rewrite added the UART and GPIO and fits 3 × 2 (420 €).

## Memory map

| Address | Size | What |
|---|---|---|
| `0x0000_0000` | 16 MB | QSPI flash (CS0) — code and constants, executes in place |
| `0x1000_0000` | 8 MB | QSPI RAM A (CS1) |
| `0x1080_0000` | 8 MB | QSPI RAM B (CS2) |
| `0x2000_0000` | 44 B | timing unit registers, the same ones the Xpulse instructions reach |
| `0x3000_0000` | — | GPIO and UART registers |
| `0x4000_0000` | 172 B | boot ROM: the UART bootloader (`sw/mkboot.py`) |

Only address bits 31:28 (device) and 23:0 (offset) are decoded, so each device repeats every
16 MB inside its 256 MB slot: `0x1100_0000` is RAM A again.

### GPIO and UART registers (`0x3000_0000` + offset)

| Offset | Name | Access | Meaning |
|---|---|---|---|
| `0x00` | `GPIO_OUT` | RW | value on output pins in GPIO mode |
| `0x04` | `GPIO_IN` | R | the eight input pins, synchronized |
| `0x08` | `GPIO_SEL` | RW | per pin: 1 = built-in function, 0 = GPIO (reset `0xFF`) |
| `0x0C` | `UART_DATA` | W / R | write: send a byte · read: last byte received (clears `RX_VALID`) |
| `0x10` | `UART_STAT` | R | bit 0 `TX_BUSY` · bit 1 `RX_VALID` · bit 2 `RX_OVERRUN` |
| `0x14` | `UART_DIV` | RW | clocks per bit (reset 434 = 115,200 baud at 50 MHz) |
| `0x18` | `GPIO_SET` | W | `GPIO_OUT |= value` |
| `0x1C` | `GPIO_CLR` | W | `GPIO_OUT &= ~value` |
| `0x20` | `GPIO_XOR` | W | `GPIO_OUT ^= value` |

`SET`/`CLR`/`XOR` are the RP2040's trick: changing one pin is a single store, with no
read-modify-write race against other code.

## Instruction set

**RV32E** — the full base integer set with 16 registers (`x0`–`x15`), so a stock
`riscv32-unknown-elf-gcc -march=rv32e -mabi=ilp32e` compiles for it:

| Group | Instructions |
|---|---|
| Arithmetic / logic | `ADD SUB AND OR XOR SLT SLTU` and the `-I` immediate forms, `LUI AUIPC` |
| Shifts | `SLL SRL SRA SLLI SRLI SRAI` |
| Loads / stores | `LB LH LW LBU LHU SB SH SW` |
| Control | `JAL JALR BEQ BNE BLT BGE BLTU BGEU` |
| System | `FENCE` (no-op) · `ECALL`/`EBREAK` halt the core and raise `HALT` |

**Xpulse** — eleven timing instructions on the custom-0 opcode (`0001011`), wrapped as C
functions in `sw/tiqora.h`:

| Instruction | C | What it does |
|---|---|---|
| `TIME rd` | `tp_time()` | read the 32-bit timebase |
| `TPOP rd` | `tp_pop()` | pop the oldest timestamped event (0 if empty) |
| `TSTAT rd` | `tp_stat()` | queue count, flags, armed channels, live pin levels |
| `TWAIT rs1` | `tp_wait(t)` | park the core until time `t` (wrap-safe) |
| `TARM rs1, rs2` | `tp_arm(t, ch)` | fire trigger `ch` exactly at tick `t` |
| `TPULSE rs1` | `tp_pulse(mask)` | fire the triggers in `mask` now |
| `TMARK rd, rs1` | `tp_mark(tag)` | queue a software event; returns its timestamp |
| `TADJ rs1` | `tp_adj(d)` | step the timebase by a signed amount |
| `TRATE rs1` | `tp_rate(r)` | trim the timebase rate (clock discipline) |
| `TCFG rs1` | `tp_cfg(c)` | enable capture channels and pick edges |
| `TPW rs1` | `tp_pw(n)` | set trigger pulse width in clocks |

Not implemented, by design: interrupts, CSRs, compressed instructions, misaligned-access
traps. An illegal instruction is skipped and latches the `ILLEGAL` pin.

## Try it today, on the simulated chip

No board and no silicon needed. The simulator runs the real RTL — the same design that gets
fabricated — booting from a model of the QSPI flash exactly as the chip will:

```bash
cd tiqora-skywater130/test
python -m pip install ziglang pyelftools          # a C compiler, no cross-toolchain needed
make run PROG=../sw/examples/hello.c
```

```
--- Tiqora (simulated RTL, 50 MHz) ---
Hello from Tiqora!
tick 1: deadline t0+100000, woke 16 clocks after
tick 2: deadline t0+200000, woke 16 clocks after
tick 3: deadline t0+300000, woke 16 clocks after
...
```

Two different things are deterministic here, and they are worth keeping apart:

- **The trigger pin is exact.** A deadline armed with `tp_arm` drives its pin on the programmed
  tick, whatever the CPU is doing (checked at the pin by `make soc`). Exact relative to the
  supplied clock; oscillator error and pad delay are separate.
- **Software resumes within a fixed window.** After `tp_wait`, the next instruction runs 10 to 17
  clocks after the deadline. The spread is not noise: every instruction starts on phase 0 of the
  register file's 8-clock rotation, so the delay depends on which phase the deadline falls on.
  For deadlines on the same phase, as in this demo, it repeats exactly. `make latency` measures
  all eight phases and checks the bound.

![Deadlines and trigger edges: the trigger pin lands on the deadline tick](images/deterministic_timing.svg)

Point `PROG=` at any C file of your own.

**Speed, measured** (RTL simulation at 50 MHz, `make run PROG=... RUNARGS=+PROFILE`):

| Program | v19 | v20 | |
|---|---:|---:|---|
| Straight-line ALU code (`bench_alu.c`) | 32.2 clocks/instr | **18.3** | 1.76× |
| Sort + checksum + CRC-32 (`bench_kernel.c`) | 50.2 | **40.3** | 1.24× |
| The C self-test, from flash | 406,049 clocks | **337,417** | 1.20× |

v20 starts fetching the next instruction while the current one executes, for every instruction
that cannot change the flow or use the bus (63% of a typical stream). The word is held in the
QSPI controller's own receive register until the core is ready, so the speedup costs one
flip-flop, one 30-bit address mux and about 1.7% more logic. Two thirds of the remaining time is
still the QSPI bus: loads, stores and taken branches each restart a memory transaction.

Printing a line with three numbers costs about 30,000 clocks, so `tp_io.h`'s `uart_putu` avoids
division entirely — the core has no hardware divider, and the usual `v % 10, v / 10` loop would
cost tens of thousands of clocks per number.

## Run it on an FPGA today: Digilent Basys 3

The same RTL runs on a [Digilent Basys 3](../fpga/basys3/README.md) (Artix-7) with nothing else
attached. The QSPI flash and RAMs are emulated in block RAM, following the same datasheet rules as
the real chips, and the board's own USB port is Tiqora's serial port, so you load C programs
with the bootloader exactly as on the chip:

```bash
cd fpga/basys3
make sim          # simulate the whole board first: three runs, all checked
make bit && make prog                 # Vivado: build and load
```

Then a terminal at 115,200 baud shows the demo: buttons timestamped to the 20 ns tick, LED 0
blinking from the timebase, and an echo. With the real QSPI Pmod on port JA, `make bit PMOD=1`
tests the actual memory chips. Full guide: [fpga/basys3/README.md](../fpga/basys3/README.md).

## Using it

**Hardware:** a Tiny Tapeout demo board and the Tiny Tapeout QSPI Pmod on the bidirectional
Pmod header.

1. **Flash your program** into the Pmod with the
   [Tiny Tapeout Flasher](https://github.com/TinyTapeout/tinytapeout-flasher) while the design
   is held in reset — the chip releases the Pmod pins for exactly this.
2. **Select** `tt_um_normansrule_tiqora` on the demo board. `ui_in[2:0]` set the QSPI read
   latency while reset is held (0 works for the Pmod at 50 MHz in simulation; raise it if
   reads come back shifted).
3. **Release reset.** The heartbeat on `uo_out[7]` starts blinking, and the program runs from
   flash address 0.
4. **Talk to it:** `uo_out[4]`/`ui_in[3]` are wired to the RP2040's UART, 115,200 baud by default.

A minimal program (see `sw/mkhello.py` for the exact instruction stream the tests run):

```c
#include "tiqora.h"
#define PERIPH ((volatile uint32_t *)0x30000000)
#ifndef ONE_SECOND
#define ONE_SECOND 50000000u                // timebase ticks per second at 50 MHz
#endif
void uart_putc(char c) { while (PERIPH[4] & 1); PERIPH[3] = c; }   // UART_STAT, UART_DATA
int main(void) {
    // GPIO_SEL: 1 = the pin keeps its built-in function, 0 = it becomes GPIO.
    // Keep UART TX (uo_out[4]) and TRIG0 (uo_out[0]); uo_out[7] becomes a GPIO.
    PERIPH[2] = (1u << 4) | (1u << 0);
    for (const char *s = "Hi Tiqora\n"; *s; s++) uart_putc(*s);
    uint32_t t = tp_time() + ONE_SECOND;    // one second from now
    tp_arm(t, 0);                           // TRIG0 fires on that exact tick
    tp_wait(t);
    PERIPH[8] = 0x80;                       // GPIO_XOR: toggle uo_out[7], now a GPIO
    return 0;
}
```

### Write C for it

Any RV32E C compiler works. If you don't have a RISC-V toolchain installed, the Clang inside
the `ziglang` pip package does the job, and it's what this repository's own tests use:

```bash
pip install ziglang pyelftools pyserial
cd sw
make TOOLCHAIN=zig            # camera_sync.bin, for flash
make TOOLCHAIN=zig RAM=1      # the same program linked for RAM, for the bootloader
```

(With a GNU toolchain, drop `TOOLCHAIN=zig`.) Include `tiqora.h` for the timing
instructions and `tp_io.h` for the UART and GPIO (`uart_puts`, `uart_putu`, `GPIO_OUT`, ...).
`sw/lib/rt.c` supplies the multiply and divide routines the compiler calls, since the core
has no hardware multiplier.

Two more libraries cover what you reach for first on any microcontroller:

- **`tp_printf.h`**: `tp_printf("t=%u id=%08x\n", t, id)` — `%d %i %u %x %X %c %s %%` with
  widths and zero padding, checked character for character against Python's `%` formatting.
  It prints numbers without dividing, so it stays fast on a core with no divider.
- **`tp_spi.h`**: an SPI master in software on the GPIO pins (mode 0, about 100 kHz at 50 MHz),
  for sensors, flash chips and small displays. Tiqora spends its silicon on the core and the
  timing unit instead of SPI hardware; the RP2040-style `GPIO_SET`/`GPIO_CLR` registers make
  a software SPI short and race-free. Tested against a simulated W25Q128 flash, whose JEDEC ID
  it reads correctly (`sw/examples/spi_flash_id.c`).

Every build is checked by `sw/rv32e_check.py`, which decodes each instruction and refuses
anything Tiqora doesn't implement — a multiply, a CSR access, a compressed instruction, a
register above x15 — so a wrong compiler flag fails at build time, not on the board.

`sw/examples/c_selftest.c` is the proof it all works: initialized and zeroed globals, strings in
flash, recursion on the stack, software multiply and divide, function pointers and a timed
`tp_wait`. The testbench runs it from flash and again over the UART bootloader, and checks every
character it prints.

### Program it through the demo board's USB-C port

No adapter needed: `sw/demoboard/tpboot.py` runs on the demo board and becomes the serial cable.
It clocks Tiqora at 4.17 MHz so the chip's UART lands at 9600 baud without changing
anything on the chip, holds the boot pin, sends your program and shows what it prints:

```bash
pip install mpremote
mpremote cp sw/demoboard/tpboot.py :tpboot.py && mpremote cp app.bin :app.bin
mpremote exec "import tpboot; tpboot.load('app.bin')"
```

Its protocol and bit timing are tested on a PC against a simulated chip with timing jitter, clock
error and counter wrap-around. **[docs/BRINGUP.md](../docs/BRINGUP.md)** walks through a real board
from first power-up, including what each status pin means when something's wrong.

### Program it over USB serial — no flasher

Tiqora has a boot ROM, the way an RP2040 does. **Hold `ui_in[7]` high while you release
reset** and, instead of running flash, the chip runs a 43-instruction bootloader that takes a
program over the UART:

```
chip → PC   TP>                               ready
PC → chip   length (4 bytes, little endian), then the program
chip → PC   checksum byte, then K              verified
            the program runs from RAM at 0x1000_0000
```

On the PC side, `sw/tpload.py` does all of it (it only needs `pyserial`):

```bash
cd sw && make TOOLCHAIN=zig RAM=1                  # camera_sync.bin, linked for RAM
python3 tpload.py -p /dev/ttyUSB0 camera_sync.bin --monitor
```

Any 3.3 V USB-to-UART bridge works: its TX to `ui_in[3]`, its RX to `uo_out[4]`, and ground.
A program loaded this way runs from RAM and is gone at power-off; to keep one permanently,
put it in flash with the Tiny Tapeout flasher. Code can also jump to `0x4000_0000` at any time to
re-enter the bootloader, like `reset_usb_boot()` on an RP2040.

### Honest comparison with an RP2040

| | Tiqora | RP2040 |
|---|---|---|
| Cores | 1 × RV32E, nibble-serial | 2 × Cortex-M0+ |
| Speed | 1.2–2.7 million instructions/s at 50 MHz (measured) | ~133 MHz, ~1 instruction/clock |
| Memory | 16 MB flash + 16 MB RAM (external, QSPI) | 264 KB SRAM + external flash |
| I/O | 8 in, 8 out, UART | 30 GPIO, USB, ADC, SPI, I2C, PWM, PIO |
| Hardware timestamping | 20 ns, 8 channels, queued | — (software or PIO) |
| Cycle-exact deadline outputs | yes, 2 | via PIO |
| You designed the silicon | **yes** | no |

Tiqora is not a replacement for an RP2040. It is a working RISC-V microcontroller you can
read every line of, down to the transistors, with a timing unit most microcontrollers don't have.

## Verification

**Every command to test everything is in [docs/TESTING.md](../docs/TESTING.md).**

| Test | What it proves | Checks |
|---|---|---:|
| `make isa` | every RV32E base instruction, vs. Python-computed results | 51 |
| `make unit` | timing unit blocks, rotating register file, UART, GPIO | 48 |
| `make stress` | 8 simultaneous captures, queue overflow, 2³² rollover | 18 |
| `make xpulse` | all eleven Xpulse instructions | 15 |
| `make soc` | boots, arms a deadline, trigger lands on the exact tick | 12 |
| `make wrap` | `TWAIT` held correctly across the timebase rollover | 10 |
| `make boot` | UART bootloader: a program sent over serial lands in RAM and runs | 11 |
| `make wake` | the chip wakes the flash and RAM itself, from cold, warm and pre-set states | 14 |
| `make c` | Clang-compiled C, run from flash and over the UART bootloader, output checked | 12 |
| `make mcu` | the chip as a microcontroller: C from flash talks to a host over the UART both ways, reads and drives pins, fires a trigger on an exact tick, timestamps an input edge, uses RAM | 16 |
| `make act` | **the official RISC-V architecture tests** (riscv-arch-test, RV32E): signatures vs the golden model, run from RAM | **37 / 37** (v20) |
| `make bridge` | the demo-board bridge vs a simulated chip: jitter, ±2% clock error, counter wrap | 10 |
| `make -C ../fpga/basys3 sim` | the whole Basys 3 design at 100 MHz: C from emulated flash, the bootloader over USB serial, the button demo | 26 |
| `make printf` | `tp_printf` against Python's `%` formatting, 23 cases | 23 |
| `make spi` | software SPI reads a simulated W25Q128's JEDEC ID | 2 |
| `make readme` | this README's minimal program, compiled verbatim, from flash and RAM: one 8-tick pulse at the TRIG0 pin, the greeting, the GPIO toggle | 10 |
| `make latency` | software resumes 10–17 clocks after a `TWAIT` deadline, for deadlines on all 8 rotation phases | 1 |
| `make adjust` | a time step neither skips nor repeats a deadline (fires at the step; a broken equality comparator fails it) | 3 |
| `make shared` | the timing unit is byte-identical to Tiqora-Serial's (SHA-256 manifest in both repositories) | 5 files |
| Tiny Tapeout pre-flight | CI's own project checker (`tt_tool.py`) | not yet: needs a placed and routed layout |
| `make timing` | critical-path estimate from real sky130 cell delays | 12.57 ns / 20 ns, slow corner, estimate before wires (main 2026-10-25) |
| `make` (cocotb) | from the pins only: firmware printing over the UART, the boot strap | 6 |
| `make gl` | the same cocotb tests on a netlist synthesized to sky130 cells (`make GATES=yes` on the post-layout one) | 5 + 1 skipped (v20) |
| `tpload.py selftest` | the PC-side loader: framing, checksum, error cases | 7 |
| `make lint` | Verilator `-Wall`, no waivers | clean |

Tiqora was cross-checked against the RISC-V conformance suite and against TinyQV, the
closest silicon-proven design; [docs/REFERENCES.md](../docs/REFERENCES.md) lists what matched and
what changed. One item stands out: TinyQV avoids the RAM's 8 µs refresh rule by never running
code from RAM, while Tiqora deliberately does (for the bootloader), so the RAM model now
enforces the datasheet's chip-select timing and every test that runs code from RAM checks it.

The memory models are strict: like the real chips, they ignore fast transactions until they
have been woken up properly. An earlier version of the models was forgiving, and hid the fact
that the chip never woke its memories — it simulated perfectly and would not have run a single
instruction on a real board. Making the models strict exposed that, and the wake-up sequence
fixed it.

Compiling real C for the first time found two more bugs that no hand-assembled test could:
the flash linker script put initialized globals in RAM with no copy stored in flash, and the
start-up code never copied them. Any program with `int x = 5;` at file scope would have been
broken on the board. Both are fixed, and putting the bug back makes `make c` fail loudly: the
program prints `data 1` instead of `data 42`, then calls a function pointer that was never
initialized and restarts itself forever.

The tests were checked against themselves: six deliberate bugs were injected (a register-file
nibble mis-write, UART sampling at the bit edge, `GPIO_CLR` acting as toggle, signed compares
treated as unsigned, arithmetic shifts losing the sign, a dropped carry between nibbles), and
the suite caught every one. One test was too weak to catch the `GPIO_CLR` bug at first; it was
strengthened.

## Repository

```
src/core/      tp_ncore.sv (the CPU), tp_nregfile.sv (rotating register file)
src/sync/      timebase, capture, event queue, deadline comparators, Xpulse port
src/periph/    tp_uart.sv, tp_periph.sv (GPIO + UART registers)
src/boot/      tp_bootrom.sv, generated by sw/mkboot.py
src/bus/       address decode, QSPI controller
src/tp_soc.sv  the microcontroller;  tt_um_normansrule_tiqora.sv  pin wrapper
src/config.json  hardening configuration
sw/demoboard/  tpboot.py: program Tiqora through the demo board's USB-C port
sw/            tiqora.h (timing), tp_io.h (UART/GPIO), tp_printf.h, tp_spi.h, crt0.S, link.ld, link_ram.ld,
               lib/rt.c, rv32e_check.py, tpload.py (UART loader), examples/, program generators
test/          every testbench above
docs/tools/    layout_preview.py, figures.py, build_explorer.py — regenerate every image
               and the interactive explorer
syn/           synthesis and area scripts
.github/       Tiny Tapeout CI: gds (hardening + 3D viewer), test, docs, fpga
```

Sister project: [tinytapeout-tiqora](https://github.com/Normansrule/tinytapeout-tiqora)
— the same timing unit with no CPU, controlled over USB serial, in 1 × 2 tiles (140 €).

Apache 2.0 licensed. Credits: the nibble-serial approach follows TinyQV by Michael Bell;
the sky130 PDK is by SkyWater and Google; fabrication via Tiny Tapeout.
