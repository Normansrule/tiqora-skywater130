#!/usr/bin/env python3
"""traces.py — the explorer's tour fixtures, cut from a real RTL simulation.

    python3 docs/tools/traces.py            run make -C test tour, write docs/site/data/traces/
    python3 docs/tools/traces.py --check    run it again and fail if any fixture differs
                                            (stale against the RTL, or not deterministic)

test/tb_tour.sv runs sw/mktour.py's program at the Tiny Tapeout pins and writes
one line per clock. This script picks the windows each tour shows, anchors every
caption to a cycle found in the data (never a hand-typed cycle number), and
checks the datapath against an independent Python model of RV32 add and sub:
if the RTL's nibbles disagree with Python, no fixture is written.
"""
import os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tracekit as tk

OUT = "docs/site/data/traces"
STATES = ["FETCH", "ALIGN", "PASS", "TWAIT", "HALT", "MEM", "XP", "SHIFT"]
QSTATES = ["IDLE", "PREFIX", "DUMMY", "DATA", "END", "DESEL", "WLOAD", "WSHIFT", "WGAP"]
WAKE = ["flash: all four lines high, 8 clocks (leave continuous read)",
        "flash: command 0xEB, one bit per clock (Fast Read Quad I/O)",
        "flash: address 0 and mode 0xA0, four bits per clock (stay in continuous read)",
        "flash: 4 dummy clocks and one byte, then chip select high",
        "both RAMs: 0xF5, four bits per clock (leave QPI if a previous run left it on)",
        "both RAMs: 0x35, one bit per clock (enter QPI)"]
RTL = ["src/tp_pkg.sv", "src/core/tp_nregfile.sv", "src/core/tp_ncore.sv", "src/sync/sync_timebase.sv",
       "src/sync/sync_capture.sv", "src/sync/sync_event_fifo.sv", "src/sync/sync_compare.sv",
       "src/sync/sync_unit.sv", "src/periph/tp_uart.sv", "src/periph/tp_periph.sv", "src/boot/tp_bootrom.sv",
       "src/bus/tp_bus.sv", "src/bus/qspi_ctrl.sv", "src/tp_soc.sv", "src/tt_um_normansrule_tiqora.sv"]
BENCH = ["test/tb_tour.sv", "test/qspi_model.sv", "sw/mktour.py", "sw/mkprog.py"]


def bit(col, n):
    return lambda r: None if r[col] is None else (r[col] >> n) & 1


def sd_bus(r):
    """The four QSPI data lines as the pins see them: driven by the chip, else by a memory."""
    if r["uio_oe"] is None:
        return None
    src = r["uio_out"] if r["uio_oe"] & 0x02 else r["uio_in"]
    return ((src >> 5) & 1) << 3 | ((src >> 4) & 1) << 2 | ((src >> 2) & 1) << 1 | ((src >> 1) & 1)


def run_sim():
    r = subprocess.run(["make", "-s", "-C", "test", "tour"], capture_output=True, text=True)
    if r.returncode:
        sys.exit("traces.py: make -C test tour failed:\n" + r.stdout[-3000:] + r.stderr[-2000:])
    return r.stdout


def instructions(rows):
    """Each instruction the core executed, in order: (cycle ir loaded, word, asm)."""
    asm = [ln.rstrip("\n").split(" ", 2) for ln in open("test/tour_asm.txt")]
    prog = [(int(a, 16), int(w, 16), t) for a, w, t in asm]
    out, k, last = [], 0, None
    for r in rows:
        if r["run"] or r["ir"] is None or r["cycle"] < 0:
            continue
        if r["ir"] != last and k < len(prog) and r["ir"] == prog[k][1]:
            out.append((r["cycle"], prog[k][0], prog[k][1], prog[k][2].split(";")[0].strip(), prog[k][2]))
            k += 1
        last = r["ir"]
    return out


def main():
    check = "--check" in sys.argv
    log = run_sim()
    rows = tk.read_trace("test/tour_trace.txt")
    main_rows = [r for r in rows if not r["run"]]
    hang_rows = [r for r in rows if r["run"] == "h"]
    checks = tk.checks_from("test/tour_out.txt")
    if not checks or not all(c["ok"] for c in checks):
        sys.exit("traces.py: the tour testbench did not pass every check")
    prov = {"testbench": "test/tb_tour.sv", "program": "sw/mktour.py",
            "command": "make -C test tour  (then python3 docs/tools/traces.py)",
            "simulator": tk.tool_version(["iverilog", "-V"]),
            "sources": {f: tk.sha(f) for f in RTL + BENCH},
            "sampling": "one sample per clock, on the falling edge, after every flip-flop has updated; cycle 0 is the first rising edge after reset is released; 1 cycle = 20 ns at 50 MHz"}
    ins = instructions(main_rows)
    at = lambda text: next(c for c, a, w, s, full in ins if s.startswith(text))
    def ins_label(r):
        cur = None
        for c, a, w, s, full in ins:
            if c <= r["cycle"]:
                cur = f"{a:04x} {s}"
        return cur or "(reset)"
    state = {"id": "state", "label": "core state", "width": 3, "kind": "enum", "enum": STATES, "fn": lambda r: r["state"],
             "block": "tp_ncore", "meaning": "tp_ncore's state register"}
    instr = {"id": "instr", "label": "instruction", "width": 0, "kind": "text", "fn": ins_label, "block": "tp_ncore",
             "meaning": "the instruction in ir, labelled from sw/mktour.py's listing"}
    fixtures = []

    # ---------------------------------------------------------- 1 reset and wake-up
    rel = tk.first(main_rows, lambda r: r["rst_n"] == 1)
    done = tk.first(main_rows, lambda r: r["waking"] == 0)
    first_ins = tk.first(main_rows, lambda r: r["imem_rvalid"] == 1)
    caps = [{"at": -4, "text": "Reset held: rst_n is low, every uio pin is an input (uio_oe = 0x00), so the demo board could program the flash now. ui_in[2:0] are being latched as the QSPI read latency (0 here).", "blocks": ["tt_um_normansrule_tiqora", "tp_soc"]},
            {"at": rel, "text": "Reset released. qspi_ctrl starts its wake-up sequence before the core may fetch anything: neither memory understands four-bit transactions yet.", "blocks": ["qspi_ctrl"]}]
    wake_clocks = int(re.search(r"wake-up (\d+) clocks", log).group(1))
    lastw = None
    for r in main_rows:
        if rel <= r["cycle"] < done and r["wstep"] != lastw and r["q_state"] == 6:
            if r["cycle"] == rel:
                caps[-1]["text"] += f" Step 1 of 6 starts at once: {WAKE[0]}."
                lastw = r["wstep"]
                continue
            caps.append({"at": r["cycle"], "text": f"Wake-up step {r['wstep'] + 1} of 6, {WAKE[r['wstep']]}.", "blocks": ["qspi_ctrl"]})
            lastw = r["wstep"]
    caps.append({"at": done, "text": f"Both memories awake: the testbench counts {wake_clocks} clocks from reset release ({wake_clocks * 0.02:.2f} us at 50 MHz). The flash is in continuous read and the RAMs in QPI mode; the core's first fetch goes out.", "blocks": ["qspi_ctrl", "tp_bus"]})
    caps.append({"at": first_ins, "text": f"Cycle {first_ins}: the first instruction word arrives (imem_rvalid). The program starts at flash address 0.", "blocks": ["tp_ncore"]})
    fixtures.append(tk.fixture("reset", "Reset and memory wake-up",
        "From reset to the first instruction: the chip wakes its own flash and RAMs, in six steps that work whatever state the chips were left in.",
        main_rows, -4, first_ins + 6,
        [{"id": "rst_n", "label": "rst_n", "width": 1, "kind": "bit", "fn": lambda r: r["rst_n"], "block": "tt_um_normansrule_tiqora", "meaning": "reset pin, active low"},
         {"id": "uio_oe", "label": "uio_oe", "width": 8, "kind": "bus", "fn": lambda r: r["uio_oe"], "block": "tt_um_normansrule_tiqora", "meaning": "which uio pins the chip drives"},
         {"id": "cs_f", "label": "CS0 flash (uio[0])", "width": 1, "kind": "bit", "fn": bit("uio_out", 0), "block": "qspi_ctrl", "meaning": "flash chip select, active low"},
         {"id": "cs_r", "label": "CS1 RAM A (uio[6])", "width": 1, "kind": "bit", "fn": bit("uio_out", 6), "block": "qspi_ctrl", "meaning": "RAM chip select, active low (both RAMs selected during wake-up)"},
         {"id": "sck", "label": "SCK (uio[3])", "width": 1, "kind": "bit", "fn": bit("uio_out", 3), "block": "qspi_ctrl", "meaning": "QSPI clock, clk/2"},
         {"id": "sd", "label": "SD3..SD0", "width": 4, "kind": "bus", "fn": sd_bus, "block": "qspi_ctrl", "meaning": "the four data lines at the pins"},
         {"id": "q_state", "label": "qspi state", "width": 4, "kind": "enum", "enum": QSTATES, "fn": lambda r: r["q_state"], "block": "qspi_ctrl", "meaning": "qspi_ctrl's sequencer"},
         {"id": "wstep", "label": "wake step", "width": 3, "kind": "bus", "fn": lambda r: r["wstep"], "block": "qspi_ctrl", "meaning": "wake-up step 0..5"},
         {"id": "waking", "label": "waking", "width": 1, "kind": "bit", "fn": lambda r: r["waking"], "block": "qspi_ctrl", "meaning": "wake-up running"},
         state,
         {"id": "imem_rvalid", "label": "imem_rvalid", "width": 1, "kind": "bit", "fn": lambda r: r["imem_rvalid"], "block": "tp_bus", "meaning": "an instruction word is delivered"}],
        caps, [{"at": done, "label": "awake"}],
        [c for c in checks if "wake" in c["text"] or "continuous" in c["text"]], prov))

    # ---------------------------------------------------------- 2 instruction fetch over QSPI
    f0 = tk.first(main_rows, lambda r: r["q_state"] == 1, after=done - 1)
    f0v = tk.first(main_rows, lambda r: r["imem_rvalid"] == 1, after=f0)
    f1 = tk.first(main_rows, lambda r: r["q_state"] == 3, after=f0v)
    f1v = tk.first(main_rows, lambda r: r["imem_rvalid"] == 1, after=f1)
    word0 = next(r for r in main_rows if r["cycle"] == f0v)["imem_rdata"]
    word1 = next(r for r in main_rows if r["cycle"] == f1v)["imem_rdata"]
    nib = lambda w: [(w >> (8 * (i // 2) + (4 if i % 2 == 0 else 0))) & 0xF for i in range(8)]
    d0 = tk.first(main_rows, lambda r: r["q_state"] == 3, after=f0)
    caps = [{"at": f0, "text": "A fetch from a new address: chip select falls and the controller sends 8 nibbles, address bits 23..0 and the mode byte 0xA0, which keeps the flash in continuous read.", "blocks": ["qspi_ctrl", "tp_bus"]},
            {"at": tk.first(main_rows, lambda r: r["q_state"] == 2, after=f0), "text": "Four dummy clocks: the flash turns the bus around. uio_oe drops, so the SD pins become inputs.", "blocks": ["qspi_ctrl"]},
            {"at": d0, "text": "Eight data nibbles in. RV32 is little endian and the flash streams ascending addresses, so the first byte on the wire is the least significant; within a byte the high nibble comes first: " + " ".join(f"{n:x}" for n in nib(word0)) + f" is 0x{word0:08x}.", "blocks": ["qspi_ctrl"]},
            {"at": f0v, "text": f"imem_rvalid: 0x{word0:08x} (lui x5, 0x30000) reaches the core.", "blocks": ["tp_bus", "tp_ncore"]},
            {"at": f1, "text": "The next fetch is sequential, so chip select stayed low and there is no preamble at all: the flash simply clocks out the next word, 8 nibbles instead of 20. This is the streaming that makes straight-line code fast.", "blocks": ["qspi_ctrl"]},
            {"at": f1v, "text": f"0x{word1:08x} (addi x6, x0, 8) delivered, {f1v - f1 + 1} clocks after its data phase began.", "blocks": ["tp_ncore"]}]
    fixtures.append(tk.fixture("fetch", "Instruction fetch over QSPI",
        "Two instruction fetches at the pins: one with a full address preamble, one streamed. Watch the byte order: least significant byte first, high nibble first.",
        main_rows, f0 - 2, f1v + 2,
        [{"id": "cs_f", "label": "CS0 flash (uio[0])", "width": 1, "kind": "bit", "fn": bit("uio_out", 0), "block": "qspi_ctrl", "meaning": "flash chip select, active low"},
         {"id": "sck", "label": "SCK (uio[3])", "width": 1, "kind": "bit", "fn": bit("uio_out", 3), "block": "qspi_ctrl", "meaning": "QSPI clock"},
         {"id": "sd_oe", "label": "chip drives SD", "width": 1, "kind": "bit", "fn": bit("uio_oe", 1), "block": "qspi_ctrl", "meaning": "1: the chip drives the data lines; 0: the flash does"},
         {"id": "sd", "label": "SD3..SD0", "width": 4, "kind": "bus", "fn": sd_bus, "block": "qspi_ctrl", "meaning": "the four data lines at the pins"},
         {"id": "q_state", "label": "qspi state", "width": 4, "kind": "enum", "enum": QSTATES, "fn": lambda r: r["q_state"], "block": "qspi_ctrl", "meaning": "qspi_ctrl's sequencer"},
         {"id": "imem_rvalid", "label": "imem_rvalid", "width": 1, "kind": "bit", "fn": lambda r: r["imem_rvalid"], "block": "tp_bus", "meaning": "word delivered to the core"},
         {"id": "imem_rdata", "label": "imem_rdata", "width": 32, "kind": "bus", "fn": lambda r: r["imem_rdata"] if r["imem_rvalid"] else None, "block": "tp_bus", "meaning": "the word, shown when valid"},
         state],
        caps, [], [c for c in checks if "ECALL" in c["text"]], prov,
        {"protocol": {"flash_read": "addr[23:0] + mode 0xA0 (8 nibbles), 4 dummy clocks, 8 data nibbles", "streamed_read": "8 data nibbles, chip select held low",
                      "ram_read": "0xEB + addr[23:0], 6 dummy clocks, 8 data nibbles", "ram_write": "0x38 + addr[23:0], 2 nibbles per byte",
                      "byte_order": "least significant byte first; high nibble first within a byte", "source": "src/bus/qspi_ctrl.sv header"}}))

    # ---------------------------------------------------------- 3 the nibble adder
    def pass_of(cyc):
        p0 = tk.first(main_rows, lambda r: r["state"] == 2 and r["phase"] == 0, after=cyc - 1)
        return [r for r in main_rows if p0 <= r["cycle"] < p0 + 8]
    ops = [(at("add  x11"), 0x12345678, 0x0FEDCBA9, "add")]
    import re as _re
    for c, a, w, s, full in ins:
        m = _re.search(r"datapath: 0x([0-9a-f]+) ([+-]) 0x([0-9a-f]+)", full)
        if m:
            ops.append((c, int(m.group(1), 16), int(m.group(3), 16), "add" if m.group(2) == "+" else "sub"))
    recorded = []
    for c, a, b, op in ops:
        rs = pass_of(c)
        res = sum(r["rf_wd"] << (4 * i) for i, r in enumerate(rs))
        want = (a + b) & 0xFFFFFFFF if op == "add" else (a - b) & 0xFFFFFFFF
        if res != want or not all(r["rf_we"] for r in rs):
            sys.exit(f"traces.py: RTL {op} 0x{a:08x}, 0x{b:08x} wrote 0x{res:08x}; the Python model says 0x{want:08x}")
        recorded.append({"op": op, "a": a, "b": b, "result": res, "phases": [
            {"phase": r["phase"], "a_n": r["a_n"], "bx_n": r["bx_n"], "cin": r["cin"], "sum_n": r["sum_n"], "cout": r["cout"], "rf_wd": r["rf_wd"]} for r in rs]})
    c_add = ops[0][0]
    rs = pass_of(c_add)
    p0 = rs[0]["cycle"]
    caps = [{"at": c_add, "text": "add x11, x9, x10 has arrived. The core waits in ALIGN until the register file's phase counter comes round to 0: every pass starts there.", "blocks": ["tp_ncore", "tp_nregfile"]}]
    for r in rs:
        caps.append({"at": r["cycle"], "text": f"Phase {r['phase']}: nibble {r['phase']} of x9 is {r['a_n']:x}, of x10 {r['bx_n']:x}; with carry-in {r['cin']} the 4-bit adder gives {r['sum_n']:x}, carry-out {r['cout']}. That nibble is written into x11 as it leaves the bottom of the rotation.", "blocks": ["tp_ncore", "tp_nregfile"]})
    fixtures.append(tk.fixture("nibble-add", "A 32-bit add, four bits per clock",
        "One add through the single 4-bit adder: eight clocks, least significant nibble first, the carry held in a flip-flop between them.",
        main_rows, c_add - 2, p0 + 10,
        [state, {"id": "phase", "label": "phase", "width": 3, "kind": "bus", "fn": lambda r: r["phase"], "block": "tp_nregfile", "meaning": "register-file rotation phase 0..7"},
         {"id": "a_n", "label": "a nibble (rs1)", "width": 4, "kind": "bus", "fn": lambda r: r["a_n"], "block": "tp_ncore", "meaning": "adder input A"},
         {"id": "bx_n", "label": "b nibble (rs2)", "width": 4, "kind": "bus", "fn": lambda r: r["bx_n"], "block": "tp_ncore", "meaning": "adder input B (inverted for sub)"},
         {"id": "cin", "label": "carry in", "width": 1, "kind": "bit", "fn": lambda r: r["cin"], "block": "tp_ncore", "meaning": "sub at phase 0, else the carry flip-flop"},
         {"id": "sum_n", "label": "sum nibble", "width": 4, "kind": "bus", "fn": lambda r: r["sum_n"], "block": "tp_ncore", "meaning": "adder output"},
         {"id": "cout", "label": "carry out", "width": 1, "kind": "bit", "fn": lambda r: r["cout"], "block": "tp_ncore", "meaning": "into the carry flip-flop"},
         {"id": "rf_we", "label": "rf_we", "width": 1, "kind": "bit", "fn": lambda r: r["rf_we"], "block": "tp_nregfile", "meaning": "register-file write enable"},
         {"id": "rf_wd", "label": "rf_wd", "width": 4, "kind": "bus", "fn": lambda r: r["rf_wd"], "block": "tp_nregfile", "meaning": "nibble written into rd"}],
        caps, [{"at": p0, "label": "phase 0"}, {"at": p0 + 7, "label": "phase 7"}],
        [c for c in checks if "0x22222221" in c["text"]], prov,
        {"model": {"what": "the browser recomputes any operands with the same nibble recurrence; docs/tools/check_site.py checks it against every recorded operation below",
                   "recorded": recorded}}))

    # ---------------------------------------------------------- 4 deadline, UART, exact tick
    c_sw = at("sw   x14")
    c_time = at("time x1")
    c_arm = at("tarm")
    c_twait = at("twait x1")
    tw = tk.first(main_rows, lambda r: r["state"] == 3, after=c_twait)
    rise = tk.first(main_rows, lambda r: r["uo_out"] is not None and r["uo_out"] & 1, after=tw)
    rrow = next(r for r in main_rows if r["cycle"] == rise)
    leave = tk.first(main_rows, lambda r: r["state"] != 3, after=tw)
    nxt = tk.first(main_rows, lambda r: r["state"] == 2, after=leave)
    txs = tk.first(main_rows, lambda r: r["uo_out"] is not None and not (r["uo_out"] >> 4) & 1, after=c_sw)
    time_row = next(r for r in main_rows if r["cycle"] >= c_time and r["state"] == 6)
    if time_row["t_rdata"] + 200 != rrow["deadline0"]:
        sys.exit("traces.py: TIME + 200 does not match the armed deadline")
    caps = [{"at": c_sw, "text": "sw x14, 0x0c(x5) writes 'K' (0x4B) to UART_DATA. The timing tour set UART_DIV to 8 clocks per bit so the frame fits on screen; the reset value is 434.", "blocks": ["tp_periph", "tp_uart"]},
            {"at": txs, "text": "uo_out[4] drops: the start bit. Then 8 data bits, least significant first: 1,1,0,1,0,0,1,0 for 0x4B, and a high stop bit. The core does not wait for it.", "blocks": ["tp_uart"]},
            {"at": time_row["cycle"], "text": f"TIME x1 reads the timebase in its XP clock: {time_row['t_rdata']}. No bus access: the timing unit answers in the same clock.", "blocks": ["sync_unit", "sync_timebase"]},
            {"at": c_arm, "text": f"tarm x1, x0 arms TRIG0 for tick {rrow['deadline0']} (the TIME value + 200).", "blocks": ["sync_compare"]},
            {"at": tw, "text": "twait x1: the deadline has not come, so the core parks in TWAIT. Nothing is fetched; the trigger needs no software.", "blocks": ["tp_ncore"]},
            {"at": rise, "text": f"Tick {rrow['now']}: TRIG0 rises at the pin on exactly the deadline tick. The comparator fires one tick early because its output is registered, which puts the pin edge on the programmed tick.", "blocks": ["sync_compare", "tp_soc"]},
            {"at": leave, "text": f"The core leaves TWAIT {leave - rise} clock{'s' if leave - rise != 1 else ''} after the deadline and fetches the next instruction.", "blocks": ["tp_ncore"]},
            {"at": nxt, "text": f"The next instruction starts its pass {nxt - rise} clocks after the deadline: inside the 10 to 17 clocks that make latency measures over all eight rotation phases. The pin was exact; software resumes inside a window.", "blocks": ["tp_ncore", "tp_nregfile"]}]
    fixtures.append(tk.fixture("deadline", "A deadline fired on the exact tick",
        "TIME, TARM and TWAIT: the trigger pin lands on the programmed tick with no software in the path, while a UART byte goes out on its own.",
        main_rows, c_sw - 2, nxt + 12,
        [instr, state,
         {"id": "uart_tx", "label": "UART TX (uo_out[4])", "width": 1, "kind": "bit", "fn": bit("uo_out", 4), "block": "tp_uart", "meaning": "serial output, idle high"},
         {"id": "now", "label": "timebase", "width": 32, "kind": "bus", "fn": lambda r: r["now"], "block": "sync_timebase", "meaning": "sync_timebase now", "every": 8},
         {"id": "deadline0", "label": "deadline 0", "width": 32, "kind": "bus", "fn": lambda r: r["deadline0"], "block": "sync_compare", "meaning": "the armed tick"},
         {"id": "armed0", "label": "armed 0", "width": 1, "kind": "bit", "fn": lambda r: r["armed0"], "block": "sync_compare", "meaning": "channel 0 armed"},
         {"id": "trig0", "label": "TRIG0 (uo_out[0])", "width": 1, "kind": "bit", "fn": bit("uo_out", 0), "block": "sync_compare", "meaning": "trigger pin"}],
        caps, [{"at": rise, "label": "deadline tick"}],
        [c for c in checks if "TRIG0" in c["text"] or "TWAIT" in c["text"] or "UART" in c["text"]], prov))

    # ---------------------------------------------------------- 5 capture, queue, overflow
    c_ill = at(".word 0")
    ill = tk.first(main_rows, lambda r: r["uo_out"] is not None and (r["uo_out"] >> 6) & 1, after=c_ill - 1)
    e = [tk.first(main_rows, lambda r, k=k: r["ui_in"] is not None and (r["ui_in"] >> k) & 1, after=ill) for k in range(3)]
    q = lambda r: None if r["qcount1"] is None else r["qcount1"] * 2 + r["qcount0"]
    ovf = tk.first(main_rows, lambda r: r["ovf"] == 1, after=ill)
    pops = [r for r in main_rows if r["cycle"] > ovf and r["t_valid"] and r["ir"] is not None and (r["ir"] & 0x707f) == 0x100b]
    halt = tk.first(main_rows, lambda r: r["state"] == 4)
    def ev(v):
        return "empty (0)" if v == 0 else f"{'TMARK' if v >> 31 else 'pin'} channel {(v >> 28) & 7}, {'rising' if (v >> 27) & 1 else 'falling'}, timestamp {v & 0x7FFFFFF}"
    caps = [{"at": c_ill, "text": "The word 0x00000000 arrives. No RV32E or Xpulse instruction has opcode 0, so the core runs one pass without writing anything, latches ILLEGAL and moves on.", "blocks": ["tp_ncore"]},
            {"at": ill, "text": "ILLEGAL (uo_out[6]) is high and stays high until reset. Execution continues with the next instruction.", "blocks": ["tp_ncore", "tp_soc"]},
            {"at": e[0], "text": "ui_in[0] rises. Two synchronizer flip-flops later the edge is an event, stamped with the timebase.", "blocks": ["sync_capture", "sync_unit"]},
            {"at": e[1], "text": "ui_in[1] rises 4 clocks later: the second event, stamped exactly 4 ticks after the first.", "blocks": ["sync_capture", "sync_event_fifo"]},
            {"at": e[2], "text": "ui_in[2] rises, but the queue is already full (2 of 2). This event is lost.", "blocks": ["sync_event_fifo"]},
            {"at": ovf, "text": "OVF (uo_out[3]) goes high and stays high: software can tell an event was dropped.", "blocks": ["sync_event_fifo", "tp_soc"]}]
    for i, r in enumerate(pops):
        caps.append({"at": r["cycle"], "text": f"tpop x{2 + i}: {ev(r['t_rdata'])}.", "blocks": ["sync_unit", "sync_event_fifo"]})
    caps.append({"at": halt, "text": "ecall: the core halts and raises HALT (uo_out[5]).", "blocks": ["tp_ncore"]})
    fixtures.append(tk.fixture("capture", "Capture, queue, overflow",
        "An illegal instruction raises its pin and is skipped; then three edges arrive at a two-deep queue: two are kept in order with exact timestamps, the third is lost and OVF says so.",
        main_rows, c_ill - 4, halt + 6,
        [instr, state,
         {"id": "ui0", "label": "ui_in[0] IN0", "width": 1, "kind": "bit", "fn": bit("ui_in", 0), "block": "sync_capture", "meaning": "capture channel 0"},
         {"id": "ui1", "label": "ui_in[1] IN1", "width": 1, "kind": "bit", "fn": bit("ui_in", 1), "block": "sync_capture", "meaning": "capture channel 1"},
         {"id": "ui2", "label": "ui_in[2] IN2", "width": 1, "kind": "bit", "fn": bit("ui_in", 2), "block": "sync_capture", "meaning": "capture channel 2"},
         {"id": "qcount", "label": "queue count", "width": 2, "kind": "bus", "fn": q, "block": "sync_event_fifo", "meaning": "entries in the event queue"},
         {"id": "evt", "label": "EVT (uo_out[2])", "width": 1, "kind": "bit", "fn": bit("uo_out", 2), "block": "sync_unit", "meaning": "queue not empty"},
         {"id": "ovf", "label": "OVF (uo_out[3])", "width": 1, "kind": "bit", "fn": bit("uo_out", 3), "block": "sync_event_fifo", "meaning": "an event was lost"},
         {"id": "ill", "label": "ILLEGAL (uo_out[6])", "width": 1, "kind": "bit", "fn": bit("uo_out", 6), "block": "tp_ncore", "meaning": "illegal instruction seen"},
         {"id": "halt", "label": "HALT (uo_out[5])", "width": 1, "kind": "bit", "fn": bit("uo_out", 5), "block": "tp_ncore", "meaning": "ECALL/EBREAK reached"},
         {"id": "t_rdata", "label": "Xpulse result", "width": 32, "kind": "bus", "fn": lambda r: r["t_rdata"] if r["t_valid"] else None, "block": "sync_unit", "meaning": "t_rdata when an Xpulse op is valid"}],
        caps, [{"at": ovf, "label": "overflow"}],
        [c for c in checks if any(k in c["text"] for k in ("TPOP", "queue", "ILLEGAL"))], prov,
        {"event_format": {"31": "source: 0 pin, 1 TMARK", "30:28": "channel or tag", "27": "1 = rising edge", "26:0": "timestamp, low 27 bits of the timebase"}}))

    # ---------------------------------------------------------- 6 stall and recovery
    hrel = tk.first(hang_rows, lambda r: r["rst_n"] == 1)
    hmem = tk.first(hang_rows, lambda r: r["state"] == 5)
    hres = tk.first(hang_rows, lambda r: r["rst_n"] == 0, after=hmem)
    hwake = tk.first(hang_rows, lambda r: r["waking"] == 1, after=hres - 1)
    last_c = max(r["cycle"] for r in hang_rows)
    caps = [{"at": hrel, "text": "A second program, run from reset: lui x1, 0x50000 then lw x2, 0(x1). Device 5 does not exist on this chip.", "blocks": ["tp_ncore"]},
            {"at": hmem, "text": "The load enters MEM with dmem_addr = 0x50000000. tp_bus decodes devices 0 to 4 only, so nothing will ever answer.", "blocks": ["tp_ncore", "tp_bus"]},
            {"at": hmem + 400, "text": "Still in MEM 400 clocks later. No HALT, no ILLEGAL: from the pins this looks like a chip that stopped. There is no bus timeout or bus-error trap in this design.", "blocks": ["tp_bus"]},
            {"at": hres, "text": "Reset is the only way out: the core returns to FETCH and the memory wake-up starts again.", "blocks": ["tp_ncore", "qspi_ctrl"]}]
    fixtures.append(tk.fixture("stall", "A stall, and the only recovery",
        "A load from an unmapped address waits forever; only reset recovers. The test that records this also found that ui_in[2:0] must be 0 while reset is held.",
        hang_rows, hang_rows[0]["cycle"], last_c,
        [state, {"id": "rst_n", "label": "rst_n", "width": 1, "kind": "bit", "fn": lambda r: r["rst_n"], "block": "tt_um_normansrule_tiqora", "meaning": "reset pin"},
         {"id": "dmem_req", "label": "dmem_req", "width": 1, "kind": "bit", "fn": lambda r: r["dmem_req"], "block": "tp_ncore", "meaning": "data request waiting"},
         {"id": "dmem_addr", "label": "dmem_addr", "width": 32, "kind": "bus", "fn": lambda r: r["dmem_addr"] if r["dmem_req"] else None, "block": "tp_ncore", "meaning": "address of the waiting load"},
         {"id": "halt", "label": "HALT (uo_out[5])", "width": 1, "kind": "bit", "fn": bit("uo_out", 5), "block": "tp_ncore", "meaning": "ECALL/EBREAK reached"},
         {"id": "ill", "label": "ILLEGAL (uo_out[6])", "width": 1, "kind": "bit", "fn": bit("uo_out", 6), "block": "tp_ncore", "meaning": "illegal instruction seen"},
         {"id": "waking", "label": "waking", "width": 1, "kind": "bit", "fn": lambda r: r["waking"], "block": "qspi_ctrl", "meaning": "memory wake-up running"}],
        caps, [{"at": hmem, "label": "stalled"}, {"at": hres, "label": "reset"}],
        [c for c in checks if "stall" in c["text"] or "recovers" in c["text"]], prov))

    # ---------------------------------------------------------- overview: the whole run
    caps = [{"at": first_ins, "text": "Program starts from flash address 0.", "blocks": ["tp_ncore"]},
            {"at": rise, "text": "TRIG0 on the deadline tick.", "blocks": ["sync_compare"]},
            {"at": ill, "text": "Illegal word: ILLEGAL latched, skipped.", "blocks": ["tp_ncore"]},
            {"at": ovf, "text": "Third event lost: OVF.", "blocks": ["sync_event_fifo"]},
            {"at": halt, "text": "ecall: HALT.", "blocks": ["tp_ncore"]}]
    fixtures.append(tk.fixture("overview", "The whole tour program, reset to HALT",
        "Every instruction of sw/mktour.py, the state it spent each clock in, and the pins.",
        main_rows, -4, halt + 4,
        [instr, state, {"id": "trig0", "label": "TRIG0", "width": 1, "kind": "bit", "fn": bit("uo_out", 0), "block": "sync_compare", "meaning": "uo_out[0]"},
         {"id": "uart_tx", "label": "UART TX", "width": 1, "kind": "bit", "fn": bit("uo_out", 4), "block": "tp_uart", "meaning": "uo_out[4]"},
         {"id": "ill", "label": "ILLEGAL", "width": 1, "kind": "bit", "fn": bit("uo_out", 6), "block": "tp_ncore", "meaning": "uo_out[6]"},
         {"id": "ovf", "label": "OVF", "width": 1, "kind": "bit", "fn": bit("uo_out", 3), "block": "sync_event_fifo", "meaning": "uo_out[3]"},
         {"id": "halt", "label": "HALT", "width": 1, "kind": "bit", "fn": bit("uo_out", 5), "block": "tp_ncore", "meaning": "uo_out[5]"}],
        caps, [], checks, prov,
        {"program": [{"addr": a, "word": f"{w:08x}", "asm": s, "cycle": c} for c, a, w, s, full in ins]}))

    texts = tk.write_all(fixtures, OUT, {"chip": "Tiqora", "tour_checks": len(checks)})
    bad = tk.compare_or_write(texts, check)
    if check:
        for b in bad:
            print("  differs: " + b)
        print(f"traces: {len(fixtures)} fixtures from {len(checks)} passing testbench checks, " +
              ("identical to a fresh simulation" if not bad else f"{len(bad)} files differ: run python3 docs/tools/traces.py"))
        sys.exit(1 if bad else 0)
    print(f"wrote {len(texts)} files to {OUT}")


if __name__ == "__main__":
    main()
