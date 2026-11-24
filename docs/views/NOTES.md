# Inside a gate: notes

The "Inside a gate" page (`docs/site/views.html`) shows Tiqora at four depths
(RTL, sky130 gates, transistors, layout) plus a state-machine and connection
view, all linked: choosing a register, gate, transistor, state or
instruction shows it in every view that can. This file records how it is
built, how each view is checked, and what was found on the way. Dates are
when a result was measured; every number says how it was obtained.

## Reading of the request

Tiqora is an RV32E core. The first version of the page also showed each
RISC-V instruction beside the nearest x86-64 one, as a reading aid; Alek
dropped that on 2026-11-23 ("scratch the x86 stuff"), so the table is now
RISC-V only: each instruction kind the core decodes, its encoding and
fields, and the decoder line that handles it.

FinFETs: SkyWater 130 nm is a planar process. The page's FinFET drawing is a
labelled comparison sketch (`illustrative` badge), not part of the chip.

## Pipeline

| stage | tool | needs | output |
|---|---|---|---|
| A | `docs/tools/views_synth.py <sc_hd dir>` | Yosys 0.33, the sky130 PDK, KLayout | `docs/views/netlist.json`, `docs/views/cells.json` |
| instructions | `docs/tools/views_isa.py` | ziglang, pyelftools | `docs/views/isa.json` (from `isa_lens.json`) |
| B | `docs/tools/views_build.py` | Python only | `docs/site/data/views.json`, `docs/site/pages/views.html` |
| site | `docs/tools/build_site.py` | Python only | `docs/site/views.html` |

The page's words live in `docs/views/page.html`, its style in `views.css`,
its code in `views.js`. `views_build.py` assembles them into the page
template, with the numbers and a no-JavaScript fallback (module, state
machine and ISA tables) filled in from the same data. Never edit the
generated files.

Regenerate after an RTL change (stage A needs the PDK, so it runs locally):

    python3 docs/tools/views_synth.py $PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd
    python3 docs/tools/views_isa.py
    python3 docs/tools/views_build.py
    python3 docs/tools/build_site.py
    make -C test views

## How each view is checked (`make -C test views`, also `.github/workflows/views.yaml`)

Measured 2026-11-23 in the cloud container (Yosys 0.33, KLayout 0.30.14,
Icarus 12.0, ziglang 0.17.1, Playwright 1.63.0 / Chromium):

| link | command | result |
|---|---|---|
| layout == transistors | `python3 docs/tools/views_lvs.py` | 72 cells, 707 transistors matched, 0 mismatches |
| (independent) | `python3 test/views/mini_lvs.py` | every channel's type, W, L matches SPICE, 0 mismatches |
| transistors == liberty gate | `python3 docs/tools/views_switch.py` | 72 cells, 2,526 input states, 0 mismatches |
| gates == RTL | `make -C test views-lockstep` | 10 runs × 40,000 clocks (prog, xpulse, wrap, isa, c_flash, prog from the boot ROM, c_flash and xpulse with random mid-run resets, the FSM coverage program `fsmcov`, and its looping copy with hunted resets), all 24 output and enable pins equal every clock |
| diagrams == behaviour | `python3 test/views/fsm_check.py` | 800,000 per-clock state samples (2 machines × 400,000 clocks), 0 errors; qspi_ctrl 28/28 edges, 9/9 states; tp_ncore 26/28 edges, 8/8 states; the 2 untaken edges are exactly the ones `chip.json` `fsm_gaps` gives a reason for |
| instruction table == machine code | `python3 docs/tools/views_isa.py --check` | 25 rows, every RISC-V opcode equals the tp_pkg constant the core decodes |
| page links | `python3 test/views/check_views.py` | 28,543 references, 0 errors, build is deterministic |
| S_MEM stay lengths | `python3 test/memlat.py 3000` | 3,000 programs, 545,837 stays in S_MEM, all 1, 18, 26, 30, 38, 45 or 50 clocks; 0 went to S_PASS, 0 errors (14 min 45 s on 4 cores; `make -C test views-memlat` runs 300) |
| page in a browser | `node test/views/page_test.js` | 348 checks: page simulator equals Python on all 2,548 states node by node; all 127 groups draw; every link, keyboard, light/dark, reduced motion, no-JS fallback |
| mutants | `python3 test/views/mutants.py` | 18 mutants, 21 check-failures expected, 21 caught, 0 survived (2026-11-24; new: `fsm-coverage`, caught as qspi_ctrl edge 4->6 untaken) |

Edge coverage, run by run (measured 2026-11-24, same tools). Without
mid-run resets the first five runs took 21/28 (qspi_ctrl) and 22/28
(tp_ncore) edges: every missed qspi_ctrl edge was a reset out of a busy
state, which no program does. The two `RESETS` runs raised that to 25/28 and
24/28. Two runs added on 2026-11-24 close the rest:

- `sw/mkfsmcov.py` writes `fsmcov.hex`: every shift amount 0 to 31 with
  slli, srai and srl (S_SHIFT leaves for S_PASS only at amounts 19 and 28,
  where its step count floor(s/4) + s mod 4 ends on phase 7), and every load
  width after 0 to 7 padding instructions, so the memory answers on every
  phase. qspi_ctrl 27/28, tp_ncore 25/28 with the earlier runs.
- `fsmcov_loop.hex` (the same program, looping) runs with `+RESETHUNT`: the
  bench pulls reset while a short-lived state is current (S_SHIFT, Q_PREFIX,
  Q_END, Q_DESEL), and every other hunted reset waits for Q_END, which lasts
  one clock. That takes the last reset arrows: qspi_ctrl 28/28, tp_ncore
  26/28.

The two tp_ncore edges still untaken are listed, with reasons, under
`fsm_gaps` in `docs/views/chip.json`, and `fsm_check.py` now fails if the
untaken set differs from that list in either direction (a lost edge, or a
listed edge that is now taken). The `fsm-coverage` mutant leaves out a run
that alone takes some arrow and must be caught by that gate.

- **S_XP → S_PASS (6→2): NOT APPLICABLE WITH REASON, unreachable.** S_XP is
  entered on phase 0 and always leaves after one clock, so it leaves on
  phase 0 and `to_wb` picks S_ALIGN. Read from `src/core/tp_ncore.sv`, not
  proved by a tool.
- **S_MEM → S_PASS (5→2): BLOCKED BY MISSING EVIDENCE.** S_MEM is entered
  on phase 0 (`tb_memlat.sv` checks it every stay) and leaves for S_PASS
  only when the answer comes on phase 7, that is, a stay of a multiple of 8
  clocks. `test/memlat.py` runs random load/store programs
  (`sw/mkrandmem.py`) through `test/tb_memlat.sv`, RTL only, and fails if a
  stay leaves for S_PASS when it is not a multiple of 8 clocks, or for S_ALIGN
  when it is. In 3,000 (545,837 stays) programs every stay was 1, 18, 26, 30, 38, 45 or
  50 clocks, so the edge was never taken. That is evidence, not a proof that
  no stay can be a multiple of 8; no SMT solver is installed here to try one
  (only `yosys-smtbmc`). Mutant check: with the RTL changed to write back on
  phase 0, `memlat.py` fails at the first 1-clock stay.

## Decisions and findings

- **Hierarchical synthesis.** The page keeps the module hierarchy so a gate
  can be traced to its module. That costs area: 52,984.6 µm² hierarchical
  against 50,965 µm² flat (`make area`), measured, Yosys 0.33, typical
  liberty. The page states the hierarchical number.
- **One-hot state recoding.** Yosys's `fsm` pass recodes both state machines
  one-hot (tp_ncore 3 bits → 8 flip-flops, qspi_ctrl 4 bits → 9). So the
  gate netlist's state register does not equal the RTL's; lockstep compares
  pins, and `fsm_check.py` checks the one-hot mapping every clock.
- **Formal equivalence was tried and not used.** A flattened Yosys `equiv`
  run took 7 min 52 s and left 1,518 of 3,531 points unproven (renamed
  registers and the FSM recoding). It is not evidence; the lockstep runs are.
- **LVS by topology alone was too weak.** KLayout's NetlistComparer matches
  nets by topology. With an input's polysilicon contact deleted, the
  unconnected gate net still matched the pin through an unnamed net, so LVS
  passed. `views_lvs.py` now also requires each pin to land on the layout
  net carrying its label. Before: mutant `gds-drop-licon` survived; after:
  caught. Dropping one of a row of source/drain contacts still passes, which
  is right: those contacts are redundant.
- **A short lockstep run missed a gate swap.** Swapping one NAND for a NOR
  in the UART's output cone survived 3,000 clocks of `prog.hex`, which never
  sends; it is caught at clock 2,743 of the C self-test. The mutant uses that
  run.
- **Switch-level model.** Binary values, unit delay, no strengths: rails and
  inputs are endpoints, never bridges; a node with no path keeps its charge;
  a fight keeps the old value and, if it lasts, is reported as `C`. A loop
  that rings when every node moves at once (the flip-flop's latches at power
  up) falls back to updating nodes one at a time. Every cell is run from
  internal nodes at 0 and at 1. This is a logic check, not timing or power.
- **SPICE units.** `w=420000u` in the SkyWater netlists means 0.42 µm.
- **zig `.insn`.** With debug info on, LLVM rejects a bare `.insn` line
  ("Undefined temporary symbol"); `views_isa.py` assembles with `-g0`.
- **Gate drawings are cut at 180 cells.** Larger cones (the core's) show the
  180 gates nearest their flip-flops and say how many more there are.
- **Isolation cells.** Synthesis used `lpflow_inputiso1p_1` cells as plain
  logic (11 in tp_uart alone); they are ordinary liberty cells and are
  checked like the rest.
- **Bugs found porting the page to Tiqora-Serial** (2026-11-23), fixed in
  both repositories: only the 2-pixel lines of a transistor symbol took a
  click (on Serial's first gate, `a211oi_1`, the centre hit the
  background); and the connections box for `g_cpu.u_core` (inside a generate
  block) matched no hierarchy path, so the CPU core could not be opened from
  it. The old check ("at least 3 boxes") passed anyway; it now wants exactly
  one working box per submodule (old lookup: 1 failure; fixed: 348/348).
- **Mutant baseline includes lockstep.** Before a mutant counts as caught by
  lockstep, the unmutated copy must pass both lockstep runs.
- **Per-chip facts in `docs/views/chip.json`.** Every tool and check is shared
  byte for byte with Tiqora-Serial; only `chip.json`, `page.html` and
  `test/views/tb_lockstep.sv` differ.
- **c_flash.hex does not rebuild byte-identical here.** Rebuilding it (the
  `c` target of `make -C test`) with ziglang 0.17.1 changes 28 lines of the
  committed `test/c_flash.hex`. Not
  investigated; the views runs use the committed file.

- **Testbench bug: random latency pins during mid-run resets.** `ui[2:0]`
  set the QSPI read latency while reset is held (`tp_soc.sv`:
  `if (rst) rd_latency <= ui[2:0];`). `tb_lockstep.sv` wiggled `ui_in[5:0]`
  at random every clock, so after a mid-run reset the latency was random,
  every fetch landed off by some nibbles, and the program ran garbage. Gates
  and RTL still agreed, so the runs passed, but the coverage the `RESETS`
  runs reported after each reset came from garbage execution, and with
  `+RESETHUNT` the gate side read X from unreset registers and failed. Fixed:
  the bench holds `ui_in[2:0]` at 0 from a reset until 8 clocks after it.
  FIXED AND VERIFIED (all 10 lockstep runs pass, 0 mismatches).
- **Generator bug in `mkrandmem.py`.** A forward branch near the end could
  jump over the single final ECALL: 32 of the first 300 seeds ran off the
  end of the program. It now ends with four ECALLs (a branch skips at most
  three). FIXED AND VERIFIED (`memlat.py` fails on a program that does not
  halt; 0 such programs now).
- **The functional benches do not see the core's pass timing.** With
  `to_wb` changed to write back on phase 6 instead of 7, `make -C test isa`,
  `soc` and `unit` all still pass: a pass that waits a little longer in
  S_ALIGN gives the same results. `memlat.py` does not see it either (no stay
  ends on phase 6). DEFERRED WITH TECHNICAL JUSTIFICATION: timing is the
  lockstep runs' job (pins compared every clock against the committed gate
  netlist); this mutant was not run through lockstep here.
- **Unmapped data addresses stall the core for ever** (found while writing
  `fsmcov`: a load from the boot ROM's address, which is fetch-only, never
  got an answer). `tp_bus.sv` answers data reads and writes only for flash,
  PSRAM, the timing unit and peripherals. A fix (answer 0 at once for every
  other address; measured area 52,105 µm² with it against 52,110 µm² without,
  `syn/area_sky130.sh`, Yosys 0.33) and a test `make -C test unmapped`
  (8/8 with the fix, 0/8 and hung without) are on branch `bus-unmapped`,
  not merged: the README documents the stall and a tour shows it, so the
  choice is the owner's. `fsmcov` stays off the ROM.

## Not covered

- The layout view shows standard cells, not the routed chip (that is the
  Physical design page).
- No timing, power or analog behaviour; no claim about silicon.
- Bulk terminals are left out of LVS (every PMOS body is VPB, every NMOS
  body VNB in these cells).
