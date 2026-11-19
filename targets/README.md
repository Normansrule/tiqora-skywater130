# Tape-out targets

Tiqora has one register-transfer level (RTL) core and several ways to make it
into a chip. Tiny Tapeout is one of them. This folder describes the others,
and `syn/targets/tapeout.py` turns each description into a ready LibreLane
3.0.14 configuration, generates the frame wrappers, checks everything, and
applies the same signoff gates to every hardened run.

Current numbers for every target are in [STATUS.md](STATUS.md), which is
generated. Nothing there is estimated: each number names the command and
the tool version that produced it.

## The targets

| Target | What it is for | Top | Built by |
|---|---|---|---|
| `tt-sky130` | Tiny Tapeout shuttle tile (the current submission) | `tt_um_normansrule_tiqora` | `.github/workflows/gds.yaml` |
| `sky130-macro` | a hard macro for any sky130 chip: your own SoC, a multi-project die, another user area | `tiqora_macro` | `targets.yaml`, LibreLane |
| `caravel-sky130` | the Efabless Caravel user project area (the chipIgnite harness) | `user_project_wrapper` around `tiqora_caravel_core` | `targets.yaml`, two LibreLane stages |
| `openframe-sky130` | the Efabless Openframe padframe: Tiqora is the whole chip, 44 GPIO, no management core | `openframe_project_wrapper` around `tiqora_openframe_core` | `targets.yaml`, two LibreLane stages |
| `gf180-macro` | the same macro on GlobalFoundries gf180mcuD, 5 V cells | `tiqora_macro` | `targets.yaml`, LibreLane |

Every target builds the same core: the Tiny Tapeout source list in
`info.yaml` minus the Tiny Tapeout top (rule T2). What a target adds is a
top, a process design kit (PDK), a die, a clock and, for a frame, a pin map.

```
src/targets/tiqora_macro.sv          plain-pin macro (hand-written, small)
src/targets/tiqora_caravel_core.sv   generated: Caravel pad logic + the macro
src/targets/user_project_wrapper.sv  generated: Caravel's fixed wrapper, wiring only
src/targets/tiqora_openframe_core.sv generated: Openframe pad logic + the macro
src/targets/openframe_project_wrapper.sv  generated: Openframe's fixed wrapper
targets/<name>.toml                  one file per target: the only thing you edit
targets/<name>/config.json           generated LibreLane config (macros)
targets/<name>/core.json, wrapper.json    generated LibreLane configs (frames)
targets/caravel-sky130/user_defines.v     generated Caravel GPIO power-on modes
targets/results/<name>.json          measured synthesis and timing
targets/_mutants.toml                RTL mutants for the lockstep bench
syn/targets/                         the shared tool and PDK / frame facts
```

`syn/targets/` is byte-identical in this repo and in Tiqora-Serial
(`docs/shared_flow.sha256`, checked by `make -C test shared`).

## Commands

```bash
python3 syn/targets/tapeout.py list          # the targets
python3 syn/targets/tapeout.py check         # rules T1-T8 below
python3 syn/targets/tapeout.py generate      # after editing a targets/*.toml
make -C test targets                         # check + lint + lockstep bench + all mutants

# measured synthesis and pre-layout timing, with a real PDK:
python3 syn/targets/tapeout.py synth sky130-macro --pdk-root ~/pdk --pdk-label "open_pdks ..."
python3 syn/targets/tapeout.py sta   sky130-macro --pdk-root ~/pdk   # needs OpenSTA (`sta`)

# full hardening (what CI runs; Docker and an hour or more per target):
pip install librelane==3.0.14
python3 syn/targets/tapeout.py harden sky130-macro
python3 syn/targets/tapeout.py signoff sky130-macro targets/sky130-macro/runs/core/final/metrics.json
```

`--pdk-root` is the directory that holds `sky130A/` (and `gf180mcuD/`).

## What is checked, and how each check is itself tested

`tapeout.py check` (rule numbers are in the tool's header):

- **T1** each target file has the keys its kind needs and a known PDK.
- **T2** every target builds the shared core first.
- **T3** the Tiny Tapeout target agrees with `info.yaml` and `src/config.json`.
- **T4** a frame's pin map: pads exist, none is reserved (Caravel pads 0-4),
  none is used twice, every macro pin reaches a pad, the clock pad is an input.
- **T5** every generated file matches what the tool generates now.
- **T6** every LibreLane variable is a current LibreLane 3.0.14 name
  (`syn/targets/librelane_vars.json`, taken from the pinned wheel). The
  upstream Caravel and Openframe configs use OpenLane 2 names, several of
  which LibreLane 3 has dropped or renamed; the generated configs use the
  new names.
- **T7** a generated wrapper has exactly the ports of the pinned upstream
  wrapper (`syn/targets/frames.json`, extracted by `tapeout.py
  refresh-frames` from efabless/caravel_user_project f534826 and
  efabless/caravel_openframe_project c3946a4).
- **T8** synthesised cell area fits the die under the target's cap.

`make -C test targets` also runs `test/tb_targets.sv`: the plain macro, the
generated Caravel top and the generated Openframe top run in lockstep with
the Tiny Tapeout top on three programs (Xpulse, every RV32E instruction, the
timebase wrap), with random capture inputs, and every output pin and output
enable is compared on every clock from reset on. It also checks pad rules:
input pads never drive, an Openframe pad that drives is in a driving mode.

Each check has mutants (`tapeout.py mutants`, `tapeout.py rtl-mutants`):
22 broken target descriptions, 440 broken or missing signoff metrics and 8
broken RTL lines or pin maps, each of which must make the check fail.

## Signoff gates

`tapeout.py signoff` reads a LibreLane `final/metrics.json`. A missing metric
fails its gate: an unreported number is not a passing one.

| Gate | Passes when |
|---|---|
| G1 | setup slack ≥ the target's floor at **every** STA corner (LibreLane itself only fails on typical corners by default) |
| G2 | hold slack ≥ the floor at every corner |
| G3 | router DRC, Magic DRC, KLayout DRC, illegal overlaps, LVS errors and antenna nets are all 0 |
| G4 | max slew, capacitance and fanout violations within the target's allowance at every corner |
| G5 | no unmapped cells, synthesis check errors or power-grid violations |
| G6 | placed utilisation under the target's cap |

The `harden` job in `.github/workflows/targets.yaml` runs LibreLane for each
target and then these gates; the job fails when a gate fails, and its log ends
with the whole metrics file and the gate table.

## Choices made for each target, and why

- **Clock.** `sky130-macro` and `openframe-sky130` use 25 ns: the same RTL on
  main missed 20 ns at the slow corner by 2.30 ns after routing (Tiny Tapeout
  gds run 40624722131, branch real-numbers-main). Caravel uses 25 ns because that is caravel_user_project's
  own setting for `wb_clk_i`. `gf180-macro` uses 60 ns, an estimate from its
  pre-layout timing (see its file). Pre-layout timing in STATUS.md has no
  wires and an ideal clock, so it is a bound, not a rating.
- **Routing and timing repair** copy the settings the Tiny Tapeout 3x2 run
  converged with (`src/config.json` explains each). Macros stop at met4 with
  a single-layer power grid so a frame can route met5 over them.
- **Caravel** takes its clock from `wb_clk_i` and its reset from `wb_rst_i`,
  and puts the Tiny Tapeout pins in order on pads 8-31 (ui, uo, then the QSPI
  Pmod). The Wishbone, logic-analyser and interrupt outputs are left
  undriven, as in the upstream example. `user_defines.v` sets each used pad's
  power-on mode; unused pads stay with the management core.
- **Openframe** takes its clock from pad 38 and puts flash and UART where the
  upstream example SoC has them. Every pad's digital mode comes from the
  example's own encodings; the analog and hold controls are tied to
  `gpio_loopback_zero` in the wrapper, as upstream does, and so are the
  input-buffer mode, trip-point and slew controls, which upstream's example
  SoC drives. Those ties are port-to-port wires, so the Openframe wrapper
  stage allows assign statements in its netlist; its LVS gate still checks
  the wiring.
- **gf180** changes nothing in the RTL: the core has no technology cells.

## Adding a target

1. Copy the closest `targets/*.toml` and edit it. For a new frame, add it to
   `syn/targets/frames.toml` (with its pinned source) and run
   `tapeout.py refresh-frames`; for a new PDK, add it to `pdks.toml` with the
   files its numbers come from.
2. `python3 syn/targets/tapeout.py generate`, then `check`.
3. Add the new top to `test/tb_targets.sv` and `make -C test targets`.
4. Add the target to the `harden` matrix in `.github/workflows/targets.yaml`.

## Not done yet

- No target other than Tiny Tapeout has a signed-off layout until its
  `harden` job is green; STATUS.md says so per target.
- The frame stage of Caravel and Openframe follows the upstream configs
  translated to LibreLane 3 names; it has not been run before this change.
  Neither upstream precheck (Caravel's mpw_precheck, the Openframe checks) is
  run here.
- Pad timing: input and output delays are 20% of the period at every target,
  not values from a pad datasheet.
