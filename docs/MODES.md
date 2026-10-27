# CPU, GPU and TPU modes

Tiqora can run in three modes. In each one the core is the same nibble-serial
RV32E processor (RISC-V, 32-bit, embedded profile with 16 registers). What
changes is which extra instructions are legal:

| Mode | Value | Extra instructions | What it is for |
|---|---|---|---|
| CPU | 0 | none | ordinary control code |
| GPU (graphics processing unit) | 1 | 8 byte-lane SIMD (single instruction, multiple data) operations on custom-2 | pixels: four 8-bit channels per instruction |
| TPU (tensor processing unit) | 2 | int8 dot-product multiply-accumulate on custom-3 | neural-network layers: four multiplies per instruction |

RV32E and the Xpulse timing instructions (custom-0) are legal in every mode.

**Where the modes exist.** They are in the Basys 3 FPGA build and the full
sky130 chip, both compiled with `TIQORA_MODES` defined. They are not in the
Tiny Tapeout tile. With the define off, the tile's gate netlist is
byte-for-byte the v20 netlist: `bash syn/tile_identity.sh v20` checks this.
The modes use a define rather than a parameter for a reason. Yosys changes the
netlist even for a parameter left at 0, because module names and the order of
ABC's (the logic optimiser's) output both move.

## Instructions

All of these are R-type or I-type with funct7 = 0. Any other funct7 or an
undefined funct3 is illegal.

| Opcode | funct3 | Name | Result in rd |
|---|---|---|---|
| custom-1 `0x2B` | 0 | `MGET rd` | the current mode. rs1, rs2 and the immediate must be 0 |
| custom-1 `0x2B` | 1 | `MSET rd, imm` | the old mode. Switches to imm (0 to 2). rs1 must be x0 |
| custom-2 `0x5B` | 0 to 7 | `PADD.B` `PSUB.B` `PADDUS.B` `PMAXU.B` `PMINU.B` `PAVGU.B` `PMUL.B` `PABSD.B` | per byte: a+b, a−b, a+b saturating at 255, max, min, (a+b+1)/2, low byte of a×b, \|a−b\| |
| custom-3 `0x7B` | 0 | `TMAC rs1, rs2` | none: acc += Σ signed(a.byte[i]) × signed(b.byte[i]), wrapping at 2³² |
| custom-3 `0x7B` | 1 | `TRD rd` | acc |
| custom-3 `0x7B` | 2 | `TRELU rd` | acc, or 0 if acc is negative |
| custom-3 `0x7B` | 3 | `TCLR` | none: acc = 0 |
| custom-3 `0x7B` | 4 | `TSET rs1` | none: acc = rs1 |

**Wrong mode.** A GPU or TPU instruction outside its mode, or a malformed
MGET or MSET, is skipped like every other illegal instruction. It leaves rd
and the accumulator alone and latches ILLEGAL (`uo_out[6]`, LED 6 on the
Basys 3). This happens in every mode.

**Switching.** MSET commits at its own instruction boundary, so the next
instruction already runs in the new mode. The timing unit is untouched by a
switch. A deadline armed before a switch fires on its exact tick, and the
tests check this at the TRIG0 pin.

## Cost and speed

| | Without modes | With modes | Source |
|---|---|---|---|
| sky130 cells | 6,047 | 8,755 | measured (main 2026-10-25, Yosys 0.33, `bash syn/area_sky130.sh` and `MODES=1 bash syn/area_sky130.sh`, with the cells this design's flow excludes (src/synth_exclude.cells) removed) |
| sky130 cell area | 50,880 µm² | 70,679 µm² (+39%) | same |
| flip-flops | 1,191 | 1,225 (2 mode bits, 32 accumulator bits) | same |
| MSET issue to commit | | 12 to 16 clocks over 29 switches | measured (v20 modes, `make -C test modes SEED=1`) |
| MSET issue to next issue | | 28 to 32 clocks (ADDI: 18 at best) | same |

At 70,679 µm² the modes build would be 62% of the 3x2 tile, against 44%
without it, and it has never been through layout. That is the reason it is
kept out of the tile. Most of the
added area is the eight 8×8 multipliers (four in `PMUL.B`, four in `TMAC`).

## From C

`sw/tiqora_modes.h` wraps every instruction with `.insn`, so a stock compiler
works:

```c
#include "tiqora_modes.h"
tp_mode_set(TP_MODE_GPU);
uint32_t blend = tp_pavgu_b(a, b);     // four pixels' channels at once
tp_mode_set(TP_MODE_TPU);
tp_tclr(); tp_tmac(w0, x0); tp_tmac(w1, x1);
int32_t y = tp_trelu();                // one neuron, 8 inputs
tp_mode_set(TP_MODE_CPU);
```

`sw/examples/modes_demo.c` runs CPU → GPU → TPU → CPU. It checks every result
against plain C and arms a deadline across the last switch.

## Evidence

| Check | Command | Result |
|---|---|---|
| Model, directed, random and wrong-mode tests through the tile pins | `make -C test modes SEED=1` (any seed) | 230 checks, 0 failures, seeds 1 to 6. measured (v20 modes) |
| The demo at the Basys 3 pins, with each printed line checked against `sw/modes_model.py` | `make -C fpga/basys3 sim-modes` | 9 checks, 25 of 25 lines. measured (v20 modes) |
| The same demo on the Basys 3 gate netlist (Yosys 0.70 `synth_xilinx`, the bitstream's synthesis), board pins only | `make -C fpga/basys3 netlist-modes` | 4 of 4: HALT on, ILLEGAL off, every serial character matches the model. measured (v20 modes) |
| Tile unchanged | `bash syn/tile_identity.sh v20` | identical, 6,047 cells. With `-DTIQORA_MODES` it reports CHANGED and exits 1. measured (v20 modes) |
| Lint, with and without the define | `make -C test lint` | clean. measured (v20 modes) |

Each check was confirmed to fail on a broken design, then the design was
restored:

* GPU saturation removed
* TPU sign extension removed
* GPU legal in any mode
* TPU legal in any mode
* MSET never commits
* timing-unit write leaking from an accelerator instruction
* ReLU sign test inverted
* mode 3 accepted
* the FPGA built without the modes
* `PAVGU.B` rounding removed

The model, `sw/modes_model.py`, is written separately from the RTL and checks
itself when run: `python3 sw/modes_model.py`.
