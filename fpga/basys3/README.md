# Tiqora on a Digilent Basys 3

Run the exact RTL that goes to silicon on a [Digilent Basys 3](https://digilent.com/reference/programmable-logic/basys-3/start)
(Artix-7 XC7A35T), with no other hardware. The board's USB port powers it, programs the FPGA,
and is Tiqora's serial port — so you program Tiqora in C, over USB, exactly the way you
will program the chip.

## What you need

- a Basys 3 and a micro-USB cable
- [Vivado ML Standard](https://www.xilinx.com/support/download.html) (free; the XC7A35T is supported)
- optionally, the Tiny Tapeout **QSPI Pmod** on port JA to test with the real memory chips
  (`make bit PMOD=1`). Without it, the flash and both RAMs are emulated in the FPGA's block RAM
  by `fpga/qspi_emu.sv`, which follows the same datasheet rules as the real chips: they ignore
  fast transactions until Tiqora's own wake-up sequence sets them up.

## The board, as Tiqora sees it

| Board | Tiqora | Notes |
|---|---|---|
| 100 MHz oscillator | `clk` | divided to 50 MHz, the chip's target |
| BTNC | reset | press and release to restart |
| SW0–SW2 | `ui_in[2:0]` read latency | sampled during reset; **leave down (000)** with the emulator |
| SW7 | `ui_in[7]` BOOT | up while pressing BTNC → UART bootloader prints `TP>` |
| BTNL / BTNR / BTNU (or SW4–6) | `ui_in[4..6]` capture inputs 4–6 | every edge is timestamped |
| USB serial (RX) | `ui_in[3]` UART RX | 115,200 baud |
| USB serial (TX) | `uo_out[4]` UART TX | also on LED 4 |
| LED 0–7 | `uo_out[7:0]` | TRIG0, TRIG1, EVT, OVF, UART TX, HALT, ILLEGAL, HEARTBEAT |
| LED 8 / 9 / 10 | flash / RAM A / RAM B selected | memory activity |
| LED 15 | reset released | |
| 7-segment | `uo_out` · `ui_in` in hex | the dot separates them |
| Pmod JA (with `PMOD=1`) | `uio[7:0]` | the QSPI Pmod plugs straight in |

## Build and load

From `fpga/basys3` (on Windows, run the same Tcl from the Vivado Tcl shell in this folder):

```bash
make image        # compile sw/examples/basys3_demo.c into flash.mem (already done; redo after edits)
make bit          # Vivado: synthesis, place and route, timing check, bitstream (~5–10 min)
make prog         # load it into the board over USB
```

`make bit` stops with an error if timing at 50 MHz is not met. Reports land in `build/`.

## What you should see

Open a serial terminal at **115,200 baud** on the board's serial port (the second of the two
ports the board creates: `/dev/ttyUSB1` on Linux, a `COM` port in Windows Device Manager):

```
Tiqora on Basys 3. Press BTNL, BTNR or BTNU, or type something.
BTNL pressed  at tick 152337402
BTNL released at tick 157902118
you typed 'x'
```

LED 0 blinks once a second, timed by the hardware timebase. Ticks are 20 ns. Mechanical buttons
bounce; the demo ignores edges less than 10 ms after the previous one on that button, using the
hardware timestamps, so each press prints once. LED 7 (HEARTBEAT) blinks on its own, with no
software at all — if it doesn't, the bitstream isn't running.

## Run your own programs

Three ways, as on the real chip:

1. **Over USB, no rebuild:** put SW7 up, press BTNC (the terminal shows `TP>`), close the
   terminal, then from the repository root:
   ```bash
   cd sw && make TOOLCHAIN=zig RAM=1                      # builds camera_sync.bin for RAM
   python3 tpload.py -p /dev/ttyUSB1 camera_sync.bin --monitor
   ```
   (`-p COM5` or similar on Windows.) The program runs from emulated RAM A.
2. **Baked into the bitstream:** `make image PROG=path/to/your.c && make bit && make prog`.
   It runs from emulated flash on every reset, with SW7 down.
3. **The real Pmod:** `make bit PMOD=1`, and write programs to its flash with the Tiny Tapeout
   flasher, as on the demo board.

The emulated memories are smaller than the real ones: programs must fit in 32 KB of flash, and
each RAM holds 64 KB (addresses wrap, so the stack at the top of RAM A still works).

## Simulation, before you have a board

```bash
make sim          # the whole board design at 100 MHz: three runs, about five minutes
```

1. the C self-test from emulated flash, with data and stack in emulated RAM: every character checked
2. the bootloader over the USB serial pin, then the same program from emulated RAM
3. the demo: a button press, a bouncing press reported once, and an echo

All pass. `make resources` gives a Yosys estimate for the XC7A35T: about 1,800 LUTs (9%),
750 flip-flops (2%) and 40 of 50 block RAMs (80%, nearly all of it the memory emulator).

## If something is wrong

| Symptom | Likely cause |
|---|---|
| LED 7 not blinking | bitstream not loaded, or BTNC held down |
| nothing in the terminal | wrong serial port (try the other one), or wrong baud rate |
| garbage in the terminal | baud rate is not 115,200, or `flash.mem` came from a simulation build: run `make image` again |
| LED 6 (ILLEGAL) on | SW0–SW2 not all down during reset, with the emulator |
| `TP>` never appears | SW7 must be up *while* BTNC is pressed and released |

## Status

Verified here: Verilator lint of the whole FPGA design, the three board-level simulations above,
Yosys synthesis for Artix-7, and the Tcl scripts' flow (run with stand-ins for Vivado's
commands). Not yet run: Vivado itself and a real board — the first `make bit` and `make prog` are
the real test. Report what they print.
