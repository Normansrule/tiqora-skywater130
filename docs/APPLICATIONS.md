# What Tiqora is good for

Tiqora is a small RISC-V microcontroller whose strength is **time**: it stamps pin edges with a
20 ns tick and drives outputs on an exact programmed tick, without software jitter. It is weak
at **throughput**: it runs about 1.2 to 2.7 million instructions per second (measured in
simulation at 50 MHz, `bench_kernel` and `bench_alu`), with no on-chip program memory. Choose
it for jobs that are mostly waiting and then must act on the right nanosecond.

## Best uses at 130 nm today (Tiny Tapeout, sky130)

| Use | Why Tiqora fits | Limit to know |
|---|---|---|
| Time-interval and pulse-width measurement (lab instruments, teaching labs) | 8 capture inputs, each edge stamped to the 20 ns clock in hardware and queued | resolution is one clock period; the queue holds 2 events, so bursts faster than software drains them set the `OVF` flag |
| Exact-tick pulse and pattern generation (stepper/servo pulses, camera and laser triggers, sampling strobes) | 2 deadline triggers drive the pin on the exact tick, independent of what the CPU is doing (checked at the pins, `make -C test latency`) | outputs are limited by the pads to 33 MHz (Tiny Tapeout spec) |
| Coincidence and ordering of events (sensor fusion triggers, physics coincidence counters, encoder edges) | timestamps from one timebase make "which came first, by how much" a subtraction | inputs are synchronised first, so the stamp lags the edge by a fixed 3 clocks |
| GPS PPS or reference-clock timestamping for clock discipline | 32-bit timebase with a fractional rate register (`TADJ`) to trim the tick rate | the timebase wraps after 2^32 ticks (86 s at 50 MHz); the comparator is wrap-safe within 2^31 ticks |
| Teaching RISC-V and timing hardware together | small, readable RTL; official RV32E tests pass (37/37); C toolchain and UART bootloader included | RV32E only (16 registers, no multiply instruction) |
| A protocol helper next to a bigger processor | UART, GPIO and the timing unit; a host can load code over USB serial | not a replacement for an RP2040-class part when you need compute or memory (README, "Honest comparison") |

What it is not good at: signal processing, machine learning, anything needing large memory or
more than a few MIPS, or analog front ends (it has none).

## What it could be best at on a smaller process

The same RTL does not change behaviour when made in another process; only area, speed and power
change. None of the following is measured; it is what the architecture implies.

- **Finer timestamps.** Resolution equals one clock period. At 200 MHz it would be 5 ns
  (arithmetic, not a claim that the design reaches 200 MHz). On sky130 the slowest corner allows
  about 53 MHz (estimate from measured slack, run 44119238814) and the Tiny Tapeout pads cap the clock at 66 MHz.
- **A timing peripheral inside a larger chip.** The timing unit (`src/sync/`) has no CPU
  dependence; Tiqora-Serial already uses it without one. In a system-on-chip it fits as a
  hardware timestamping and trigger block next to an application processor, for example for
  time-sensitive networking timestamps, sensor-fusion triggers or motor-control PWM edges.
- **On-chip memory instead of QSPI.** The core fetches over a narrow bus; with an on-chip SRAM
  macro (which smaller nodes and their compilers provide) the flash wait states, the largest
  cost in the measured CPI, would go.
- **Many cores per mm².** The nibble-serial core trades speed for area. On a dense node, several
  such cores, each owning one timing unit, could serve independent channels.

## Portability: keeping the RTL ready for other processes

Checked on 2026-11-15 on branch `tapeout-audit`:

| Rule | State | How it was checked |
|---|---|---|
| No process-specific cells instantiated in the RTL | met: no `sky130_` instance anywhere in `src/` (one mention is a comment) | `grep -rn "sky130_" src --include=*.sv` |
| Memories are plain flip-flop arrays or inferable RAM, no hard macros | met: register file and queues are flip-flops; `design__instance__area__macros: 0` | flow metrics |
| No latches | met: `design__inferred_latch__count: 0` | flow metrics |
| Synchronous reset only, no `negedge` resets, no `initial` blocks in synthesised RTL | met | `grep -rln negedge src`, `grep -rn initial src` |
| Single clock domain; pin inputs synchronised before use | met (the timing unit's capture lanes have two-flop synchronisers and an optional glitch filter, `FILTW`) | `src/sync/sync_capture.sv`, formal proof on PR #14 |
| Sizes are parameters, not constants | partly: channel count `NCH`, comparators `NCMP`, queue `DEPTH`, fraction width `FRACW` are parameters of `tp_soc`; the bus and core widths are fixed | `src/tp_soc.sv` |
| Process-specific settings kept out of the RTL | met: they live in `src/config.json`, `src/synth_exclude.cells`, `src/pnr_exclude.cells` and the Tiny Tapeout wrapper `tt_um_normansrule_tiqora.sv` | file review |

To move to another process, keep `src/` and replace the process layer:

1. **Wrapper.** `tt_um_normansrule_tiqora.sv` maps `tp_soc` onto Tiny Tapeout's 24 pins. A
   different chip needs its own pad wrapper; `tp_soc` itself stays.
2. **Flow configuration.** `src/config.json` (die size, placement density, PDN pitch, timing
   repair) and the cell exclusion lists are sky130-specific. Tiny Tapeout already offers
   GF180MCU (`gf180mcuD`, 1x1 tile 346.64 × 160.72 µm) and IHP SG13G2 (130 nm SiGe BiCMOS,
   1x1 tile 202.08 × 154.98 µm), per `tech/*/tile_sizes.yaml` in tt-support-tools; those are the
   cheapest next targets, and the same `tt-gds-action` builds them (`pdk:` input).
3. **Timing constraints.** The pad delays assumed in the sky130 template change with the pad
   library. Re-time `rst_n`→output paths, which set the typical-corner slack today.
4. **Memories.** If an SRAM compiler exists (OpenRAM for sky130 and gf180; vendor compilers on
   commercial nodes), replace external QSPI program storage with an on-chip macro behind
   `tp_bus`. Write new memories with a synchronous read, so the same RTL infers block RAM on an
   FPGA and maps to an SRAM macro on an ASIC (EE290C Lecture 3, "FPGA Resource Inference").
5. **Verification.** Every suite drives the top through its pins (`make -C test sim`, the
   official RISC-V tests, gate-level tests), so it carries over unchanged; re-run gate-level
   simulation with the new library's cell models.

See [MANUFACTURING.md](MANUFACTURING.md) for the sky130 facts and [LIBRARY.md](LIBRARY.md) for
guides to other processes and FPGAs.
