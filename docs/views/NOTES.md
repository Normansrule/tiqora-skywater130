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
| gates == RTL | `make -C test views-lockstep` | 8 runs × 40,000 clocks (prog, xpulse, wrap, isa, c_flash, prog from the boot ROM, and c_flash and xpulse with 10 and 8 random mid-run resets), all 24 output and enable pins equal every clock |
| diagrams == behaviour | `python3 test/views/fsm_check.py` | 640,000 per-clock state samples (2 machines × 320,000 clocks), 0 errors; qspi_ctrl 25/28 edges, 9/9 states; tp_ncore 24/28 edges, 8/8 states |
| instruction table == machine code | `python3 docs/tools/views_isa.py --check` | 25 rows, every RISC-V opcode equals the tp_pkg constant the core decodes |
| page links | `python3 test/views/check_views.py` | 28,543 references, 0 errors, build is deterministic |
| page in a browser | `node test/views/page_test.js` | 348 checks: page simulator equals Python on all 2,548 states node by node; all 127 groups draw; every link, keyboard, light/dark, reduced motion, no-JS fallback |
| mutants | `python3 test/views/mutants.py` | 17 mutants, 20 check-failures expected, 20 caught, 0 survived |

The edge coverage is not 100%. Without mid-run resets the runs took 21/28
and 22/28 edges: every missed qspi_ctrl edge was a reset out of a busy
state, which no program does. The two `RESETS` runs raised that to 25/28
and 24/28. Still untaken (`fsm_check.py` lists them): three qspi_ctrl
resets from short-lived states, and four tp_ncore edges (three into
S_PASS from S_MEM, S_XP and S_SHIFT, and a reset from S_SHIFT).

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
- **c_flash.hex does not rebuild byte-identical here.** Rebuilding it (the
  `c` target of `make -C test`) with ziglang 0.17.1 changes 28 lines of the
  committed `test/c_flash.hex`. Not
  investigated; the views runs use the committed file.

## Not covered

- The layout view shows standard cells, not the routed chip (that is the
  Physical design page).
- No timing, power or analog behaviour; no claim about silicon.
- Bulk terminals are left out of LVS (every PMOS body is VPB, every NMOS
  body VNB in these cells).
