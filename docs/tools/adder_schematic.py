#!/usr/bin/env python3
"""adder_schematic.py — the core's one 4-bit adder, lit by the RTL's own signals.

    python3 docs/tools/adder_schematic.py              run make -C test tour, write the data and the drawings
    python3 docs/tools/adder_schematic.py --check      no simulation: fail if the data breaks the RTL's
                                                       equations, disagrees with the datapath tour, or any
                                                       drawing is out of date
    python3 docs/tools/adder_schematic.py --check-sim  simulate again and fail if the data differs
    python3 docs/tools/adder_schematic.py --mutants    break copies of the data and confirm --check catches each

Tiqora only (Tiqora-Serial has no core). test/tb_tour.sv writes
test/adder_probe.txt: one line per clock while an add or sub is in its pass,
every value read inside tp_ncore on the falling edge. Two instructions are
drawn, eight clocks each: the tour's add x11, x9, x10 (0x12345678 +
0x0fedcba9, a carry out of every nibble but the last) and the first sub that
borrows out of the top nibble (0x0000000f - 0x00000010: -1, the borrow runs all the way up).

Every clock is checked against the RTL's equations, written again here:

    bx_n        = b_n ^ {4{sub}}
    cin         = phase == 0 ? sub : carry_q
    {cout,sum}  = a_n + bx_n + cin
    carry_q'    = cout                      (every clock of the pass)
    rf_wd       = sum_n,  rf_we = rd != x0

and each whole instruction against Python's own 32-bit add or subtract of the
operands the nibbles spell, and against the datapath tour's recording in
docs/site/data/traces/nibble-add.json. Outputs: docs/site/data/adder.json (for
docs/site/lib/schematic.js) and docs/images/schematic_adder.svg (the README's
animation; a still of the add's last nibble under reduced motion).
"""
import copy, json, os, subprocess, sys, textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schematic import STYLE, esc, path, xml, mux  # noqa: E402

DATA = "docs/site/data/adder.json"
README_SVG = "docs/images/schematic_adder.svg"
PROBE = "test/adder_probe.txt"
FIXTURE = "docs/site/data/traces/nibble-add.json"
RTL = "src/core/tp_ncore.sv"
COLS = ["cycle", "phase", "ir", "sub", "rs1_n", "rs2_n", "a_n", "b_n", "bx_n", "cin", "carry_q", "cout",
        "sum_n", "rf_we", "rf_wd"]
M32 = 0xFFFFFFFF
W, H = 1120, 500

PARTS = {
    "rf":    ("register file read ports",       ".qa (rs1_n),     .qb(rs2_n),"),
    "sub":   ("sub: funct7 bit 5 of an OP",     "assign sub  = (is_op && f3 == 3'b000 && ir[30]) || is_slt || is_br;"),
    "xor":   ("invert B for a subtract",        "assign bx_n = b_n ^ {4{sub}};"),
    "cin":   ("carry in: sub at phase 0",       "assign cin  = (phase == 3'd0) ? sub : carry_q;"),
    "add":   ("the 4-bit adder",                "assign {cout, sum_n} = {1'b0, a_n} + {1'b0, bx_n} + {4'd0, cin};"),
    "carry": ("carry flip-flop",                "carry_q  <= cout;"),
    "phase": ("phase counter",                  "phase <= rst ? 3'd0 : phase + 3'd1;"),
    "we":    ("write rd, unless rd is x0",      "assign rf_we = in_pass && (ir[10:7] != 4'd0) && legal &&"),
    "wd":    ("the nibble written",             "assign rf_wd = second ? mdr[3:0] : res_n;"),
}


def rtl_lines():
    src = open(RTL).read().splitlines()
    out = {}
    for k, (_, text) in PARTS.items():
        hits = [i + 1 for i, ln in enumerate(src) if text in ln]
        if len(hits) != 1:
            raise ValueError(f"{RTL}: expected one line containing {text!r}, found {len(hits)}")
        out[k] = hits[0]
    return out


def read_probe(p):
    lines = open(p).read().split("\n")
    if lines[0].split() != COLS:
        raise ValueError(f"{p}: columns are {lines[0].split()}, expected {COLS}")
    return [{c: (int(v) if c == "cycle" else int(v, 16)) for c, v in zip(COLS, ln.split())} for ln in lines[1:] if ln.strip()]


def instructions(rows):
    """Group the probe into passes: eight consecutive clocks, phase 0 to 7."""
    out, cur = [], []
    for r in rows:
        if r["phase"] == 0:
            cur = [r]
            out.append(cur)
        elif cur and r["cycle"] == cur[-1]["cycle"] + 1:
            cur.append(r)
    return out


def value(rs, k):
    return sum(r[k] << (4 * r["phase"]) for r in rs)


def asm(ir):
    rd, rs1, rs2 = (ir >> 7) & 31, (ir >> 15) & 31, (ir >> 20) & 31
    return f"{'sub' if ir >> 30 & 1 else 'add'} x{rd}, x{rs1}, x{rs2}"


def model_errors(rows):
    err = []
    for i, r in enumerate(rows):
        c, ir = r["cycle"], r["ir"]
        if r["sub"] != (ir >> 30) & 1:
            err.append(f"cycle {c}: sub is {r['sub']} for ir {ir:08x}")
        if r["a_n"] != r["rs1_n"] or r["b_n"] != r["rs2_n"]:
            err.append(f"cycle {c}: an OP's adder inputs are not the register file's read ports")
        if r["bx_n"] != r["b_n"] ^ (15 if r["sub"] else 0):
            err.append(f"cycle {c}: bx_n is {r['bx_n']:x}, b_n ^ sub gives {r['b_n'] ^ (15 if r['sub'] else 0):x}")
        if r["cin"] != (r["sub"] if r["phase"] == 0 else r["carry_q"]):
            err.append(f"cycle {c}: cin is {r['cin']} at phase {r['phase']}")
        t = r["a_n"] + r["bx_n"] + r["cin"]
        if (r["cout"], r["sum_n"]) != (t >> 4, t & 15):
            err.append(f"cycle {c}: {r['a_n']} + {r['bx_n']} + {r['cin']} = {t}, recorded carry {r['cout']} nibble {r['sum_n']:x}")
        if r["rf_wd"] != r["sum_n"] or r["rf_we"] != (1 if (ir >> 7) & 15 else 0):
            err.append(f"cycle {c}: rd is written {r['rf_wd']:x} (we {r['rf_we']}), not the sum")
        if i + 1 < len(rows) and rows[i + 1]["cycle"] == c + 1:
            n = rows[i + 1]
            if n["carry_q"] != r["cout"]:
                err.append(f"cycle {c + 1}: carry_q is {n['carry_q']}, the flip-flop took {r['cout']}")
            if n["phase"] != (r["phase"] + 1) & 7:
                err.append(f"cycle {c + 1}: phase {n['phase']} after {r['phase']}")
    return err


def instr_errors(rs):
    """A whole pass against Python's own arithmetic on the operands the nibbles spell."""
    if [r["phase"] for r in rs] != list(range(8)) or any(rs[k]["cycle"] != rs[0]["cycle"] + k for k in range(8)):
        return [f"cycle {rs[0]['cycle']}: not eight consecutive clocks, phase 0 to 7"]
    a, b, res = value(rs, "a_n"), value(rs, "b_n"), value(rs, "rf_wd")
    want = (a - b if rs[0]["sub"] else a + b) & M32
    return [] if res == want else [f"cycle {rs[0]['cycle']}: {asm(rs[0]['ir'])} wrote {res:08x}, Python gives {want:08x}"]


def fixture_errors(parts, fx):
    """The datapath tour recorded the same simulation: the same nibbles at the same clocks."""
    err = []
    pc = next((s["changes"] for s in fx["signals"] if s["id"] == "phase"), [])
    for rs in parts:
        a, b, op = value(rs, "a_n"), value(rs, "b_n"), "sub" if rs[0]["sub"] else "add"
        m = [x for x in fx["model"]["recorded"] if (x["a"], x["b"], x["op"]) == (a, b, op)]
        if not m:
            err.append(f"the datapath tour has no {op} of {a:08x}, {b:08x}")
            continue
        got = [{k: r[k] for k in ("a_n", "bx_n", "cin", "cout", "phase", "rf_wd", "sum_n")} for r in rs]
        if got != m[0]["phases"] or value(rs, "rf_wd") != m[0]["result"]:
            err.append(f"{op} {a:08x}, {b:08x}: the nibbles differ from the datapath tour's")
        if rs[0]["ir"] == 0x00A485B3 and [rs[0]["cycle"], 0] not in pc:
            err.append(f"the add's pass starts at cycle {rs[0]['cycle']}, not where the datapath tour's phase 0 is")
    return err


def pick(rows):
    ins = [rs for rs in instructions(rows) if len(rs) == 8]
    add = next(rs for rs in ins if not rs[0]["sub"] and all(r["cout"] for r in rs[:7]))
    sub = next(rs for rs in ins if rs[0]["sub"] and not rs[7]["cout"])
    return [add, sub]


def caption(r, rs):
    k = r["phase"]
    rd, A, B = asm(r["ir"]).replace(",", "").split()[1:]
    t = r["a_n"] + r["bx_n"] + r["cin"]
    s = f"Phase {k}: nibble {k} of {A} is {r['a_n']:x} and of {B} is {r['b_n']:x}"
    if r["sub"]:
        s += f", inverted to {r['bx_n']:x} because this is a subtract"
    if k == 0:
        s += (". The carry starts at 1, the sub bit itself: a − b is done as a + ~b + 1."
              if r["sub"] else ". The carry starts at 0, the sub bit.")
    else:
        s += f". The carry flip-flop brings in {r['cin']}."
    s += f" In hex, {r['a_n']:x} + {r['bx_n']:x} + {r['cin']} = {t:02x}: nibble {r['sum_n']:x} goes into {rd}, {r['cout']} into the carry flip-flop" + (": in a subtract, a carry of 0 is a borrow." if r["sub"] and not r["cout"] else ".")
    if k == 7:
        res = value(rs, "rf_wd")
        s += f" {rd} now holds 0x{res:08x}"
        s += (", −1: the borrow ran through all eight nibbles." if r["sub"] and res == M32 else
              ", eight clocks through one 4-bit adder." if not r["sub"] else ".")
    return s


def build(rows, site):
    parts = pick(rows)
    steps = []
    for p, rs in enumerate(parts):
        A, B, R = value(rs, "a_n"), value(rs, "b_n"), value(rs, "rf_wd")
        for r in rs:
            k = r["phase"]
            s = dict(r)
            s["part"] = p
            s["label"] = f"{asm(r['ir'])} · phase {k} · cycle {r['cycle']:,}"
            s["asm"], s["irhex"] = asm(r["ir"]), f"ir 0x{r['ir']:08x}"
            rd, r1, r2 = asm(r["ir"]).replace(",", "").split()[1:]
            s["rs1"], s["rs2"], s["rd"] = f"{r1} · rs1", f"{r2} · rs2", f"{rd} · rd"
            s["ph0"] = 1 if k == 0 else 0
            for j in range(8):
                s[f"p{j}"] = 1 if j == k else 0
                s[f"a{j}"], s[f"b{j}"] = f"{A >> 4 * j & 15:x}", f"{B >> 4 * j & 15:x}"
                s[f"r{j}"] = f"{R >> 4 * j & 15:x}" if j <= k else ""
            for f in ("a_n", "b_n", "bx_n", "sum_n"):
                s[f + "x"] = f"{r[f]:x}"
            s["eq"] = f"{r['a_n']:x} + {r['bx_n']:x} + {r['cin']} = {r['a_n'] + r['bx_n'] + r['cin']:02x}"
            s["hold"] = 1 if k in (0, 7) else 0
            s["text"] = caption(r, rs)
            steps.append(s)
    return {"schema": 1, "chip": site["chip"], "repo": site["repo"], "ref": site["ref"], "rtl": RTL,
            "lines": rtl_lines(), "parts": {k: v[0] for k, v in PARTS.items()},
            "gap": parts[1][0]["cycle"] - parts[0][-1]["cycle"] - 1, "edge": 7, "steps": steps,
            "provenance": {"command": "make -C test tour  (then python3 docs/tools/adder_schematic.py)",
                           "probe": "test/tb_tour.sv writes test/adder_probe.txt, read inside tp_ncore on each falling clock edge",
                           "computed": "the sum written beside the adder (a + bx + cin) is arithmetic on recorded values; every other value is recorded"}}


# --------------------------------------------------------------- the drawing
CSS = """
.sc .cell{fill:var(--sch-lane,#12161a);stroke:var(--sch-edge,#3a4247);stroke-width:1.2}
.sc .cell.on{fill:var(--sch-box,#161a1d);stroke:var(--sch-hi,#ffb000);stroke-width:2.4}
.sc .nib{fill:var(--sch-ink,#e8ebe9);font-family:var(--mono,ui-monospace,SFMono-Regular,Consolas,Menlo,monospace);font-size:19px;font-weight:600}
.sc .va{fill:var(--sch-ink,#e8ebe9);font-family:var(--mono,ui-monospace,SFMono-Regular,Consolas,Menlo,monospace);font-size:18px;font-weight:600}
"""
CELL, RX = 36, {"a": (40, 148), "b": (40, 278), "r": (780, 320)}   # operand rows: x of nibble 7, top
BITS = [
    ("sub", "sub", [(422, 88), (422, 280)]),
    ("sub_c", "sub", [(422, 240), (470, 240), (470, 375), (500, 375)]),
    ("ph0", "ph0", [(518, 342), (518, 364)]),
    ("cin", "cin", [(536, 394), (660, 394), (660, 340)]),
    ("cout", "cout", [(720, 290), (746, 290), (746, 440), (720, 440)]),
    ("carry_q", "carry_q", [(580, 440), (490, 440), (490, 413), (500, 413)]),
    ("rf_we", "rf_we", [(810, 132), (810, 226)]),
]
BUSES = [("a", [(328, 170), (600, 170)]), ("b", [(328, 300), (392, 300)]), ("bx", [(452, 300), (600, 300)]),
         ("sum", [(720, 250), (770, 250)]), ("wd", [(850, 250), (924, 250), (924, 318)])]
VALS = [("v", 520, 162, "middle", "a_nx"), ("v", 360, 292, "middle", "b_nx"), ("v", 548, 292, "middle", "bx_nx"),
        ("v", 745, 242, "middle", "sum_nx"), ("vb", 400, 72, "start", "sub"), ("vb", 620, 72, "start", "phase"),
        ("vb", 594, 466, "start", "carry_q"), ("va", 34, 66, "start", "asm"), ("m", 34, 84, "start", "irhex"),
        ("va", 780, 420, "start", "eq"), ("k", 40, 136, "start", "rs1"), ("k", 40, 266, "start", "rs2"),
        ("k", 780, 308, "start", "rd")]


def part(k, lines, body):
    return f"<g class=part data-part={k}><title>{esc(PARTS[k][0])} · {RTL} line {lines[k]}</title>{body}</g>"


def base(lines, wires):
    """What does not change with the clock."""
    o = [f"<rect class=bg width={W} height={H} rx=14/>"]
    o.append("<g class=part data-part=ir><rect class=box x=20 y=24 width=310 height=72 rx=8/>"
             "<text class=k x=34 y=42>instruction</text></g>")
    o.append(part("sub", lines, "<rect class=box x=380 y=24 width=170 height=64 rx=8/><text class=k x=394 y=42>sub · ir[30]</text>"))
    o.append(part("phase", lines, "<rect class=ff x=600 y=24 width=170 height=64 rx=6/>"
                  "<path class=clk d='M600,70 L610,77 L600,84'/><text class=k x=614 y=42>phase · nibble</text>"
                  "<text class=m x=760 y=72 text-anchor=end>+1 each clock</text>"))
    rows = [part("rf", lines, "".join(f"<rect class=cell data-c={c}{j} x={RX[c][0] + (7 - j) * CELL} y={RX[c][1]} width={CELL - 4} height=44 rx=5/>"
                                       for c in "ab" for j in range(8)))]
    rows.append(part("wd", lines, "".join(f"<rect class=cell data-c=r{j} x={RX['r'][0] + (7 - j) * CELL} y={RX['r'][1]} width={CELL - 4} height=44 rx=5/>"
                                          for j in range(8))))
    o += rows
    for c in "abr":
        x, y = RX[c]
        o.append(f"<text class=m x={x} y={y + 60}>nibble 7</text><text class=m x={x + 8 * CELL - 4} y={y + 60} text-anchor=end>nibble 0</text>")
    o.append(part("xor", lines, "<rect class=box x=392 y=280 width=60 height=40 rx=8/><text class=t x=422 y=305 text-anchor=middle>⊕ sub</text>"))
    o.append(part("cin", lines, "<rect class=box x=486 y=318 width=70 height=24 rx=6/><text class=m x=521 y=334 text-anchor=middle>phase = 0</text>"
                  + mux(500, 356, 36, 76) + "<text class=m x=505 y=380>1</text><text class=m x=505 y=418>0</text>"))
    o.append(part("add", lines, "<path class=gate d='M600,130 L720,190 L720,310 L600,370 L600,280 L616,250 L600,220 Z'/>"
                  "<text class=t x=668 y=256 text-anchor=middle style='font-size:26px;font-weight:400'>+</text>"
                  "<text class=m x=606 y=176>A</text><text class=m x=606 y=306>B</text><text class=m x=640 y=330>cin</text>"
                  "<text class=k x=622 y=216>4-bit</text>"))
    o.append(part("carry", lines, "<rect class=ff x=580 y=414 width=140 height=60 rx=6/>"
                  "<path class=clk d='M580,456 L590,463 L580,470'/><text class=k x=594 y=432>carry flip-flop</text>"))
    o.append("<text class=k x=724 y=284>cout</text><text class=k x=496 y=460 text-anchor=end>carry_q</text>")
    o.append(part("we", lines, "<rect class=box x=770 y=226 width=80 height=48 rx=8/><text class=m x=810 y=246 text-anchor=middle>write rd</text>"
                  "<text class=m x=810 y=264 text-anchor=middle>this nibble</text>"))
    o.append("<text class=k x=820 y=124>rf_we</text><text class=m x=820 y=140>rd ≠ x0, in the pass</text>")
    o.append("<text class=m x=780 y=444>in hex: the carry, then the nibble</text>")
    o.append("<text class=m x=20 y=480>every register in the file turns one nibble each clock; nibble k of all of them sits on the read ports at phase k</text>")
    for wid, pts in BUSES:
        o.append(f"<path class='w bus hot' data-w={wid} d='{path(pts)}'/>")
    if wires:
        for wid, sig, pts in BITS:
            o.append(f"<path class=w d='{path(pts)}'/>")
    return "".join(o)


def layer(s, live):
    """What changes with the clock: lit wires, highlighted nibbles, values. live: every slot, ids for schematic.js."""
    o = []
    for wid, sig, pts in BITS:
        on = bool(s[sig])
        if live:
            o.append(f"<path class='glow' data-g={wid} d='{path(pts)}' style='opacity:{.18 if on else 0}'/>"
                     f"<path class='w{' on' if on else ''}' data-w={wid} data-s={sig} pathLength=1 d='{path(pts)}'/>")
        elif on:
            o.append(f"<path class=glow d='{path(pts)}'/><path class='w on' d='{path(pts)}'/>")
    on = s["sub"]
    o.append(f"<circle class='dot{' on' if on else ''}' cx=422 cy=240 r=4{' data-s=sub' if live else ''}/>")
    for c in "abr":
        x0, y0 = RX[c]
        for j in range(8):
            x = x0 + (7 - j) * CELL
            if live:
                o.append(f"<rect class='cell{' on' if s[f'p{j}'] else ''}' data-on=p{j} x={x} y={y0} width={CELL - 4} height=44 rx=5/>")
            elif s[f"p{j}"]:
                o.append(f"<rect class='cell on' x={x} y={y0} width={CELL - 4} height=44 rx=5/>")
            o.append(f"<text class=nib x={x + (CELL - 4) / 2} y={y0 + 29} text-anchor=middle{f' data-v={c}{j}' if live else ''}>{esc(s[f'{c}{j}'])}</text>")
    for cls, x, y, anc, k in VALS:
        o.append(f"<text class={cls} x={x} y={y} text-anchor={anc}{f' data-v={k}' if live else ''}>{esc(s[k])}</text>")
    return "".join(o)


STRIP = [("sub", "sub"), ("cin", "cin"), ("cout", "cout"), ("carry_q", "carry_q"), ("rf_we", "rf_we")]


def strip(d, x0, y0, w):
    steps = d["steps"]
    n, gapw, rh = len(steps), 70, 20
    cw = (w - gapw) / n
    xs, x = [], x0
    for i, s in enumerate(steps):
        if i and steps[i - 1]["part"] != s["part"]:
            x += gapw
        xs.append(x)
        x += cw
    o = []
    for k, (lab, sig) in enumerate(STRIP):
        y = y0 + 22 + k * rh
        o.append(f"<rect class=lane x={x0 - 4} y={y - 13} width={w + 8} height={rh - 4} rx=3/>")
        o.append(f"<text class=rowl x={x0 - 12} y={y} text-anchor=end>{lab}</text>")
        pts = []
        for i, s in enumerate(steps):
            if i and steps[i - 1]["part"] != s["part"]:
                o.append(f"<path class='w on' d='{path(pts)}'/>")
                pts = []
            hi = y - 10 if s[sig] else y
            pts += [(round(xs[i], 1), hi), (round(xs[i] + cw, 1), hi)]
        o.append(f"<path class='w on' d='{path(pts)}'/>")
    yl = y0 + 22 + len(STRIP) * rh
    o.append(f"<text class=rowl x={x0 - 12} y={yl + 2} text-anchor=end>nibble</text>")
    for i, s in enumerate(steps):
        o.append(f"<text class=gapt x={xs[i] + cw / 2:.1f} y={yl + 2} text-anchor=middle>{s['sum_n']:x}</text>")
    gx = xs[8] - gapw
    o.append(f"<text class=gapt x={gx + gapw / 2:.1f} y={y0 + 22 + 2 * rh - 4} text-anchor=middle>{d['gap']:,}</text>"
             f"<text class=gapt x={gx + gapw / 2:.1f} y={y0 + 22 + 3 * rh - 8} text-anchor=middle>clocks</text>")
    for p in (0, 1):
        i = p * 8
        o.append(f"<text class=rowl x={xs[i]:.1f} y={y0 + 6}>{esc(steps[i]['asm'])}</text>")
    return o, xs, cw, yl + 10


def site_svg(d, still):
    s = d["steps"][still]
    return xml(f"<svg class=sc viewBox='0 0 {W} {H}' role=img aria-labelledby=ad-title ad-desc xmlns='http://www.w3.org/2000/svg'>"
               f"<title id=ad-title>The core's 4-bit adder, drawn as logic</title><desc id=ad-desc>{esc(s['text'])}</desc>"
               f"<style>{STYLE}{CSS}</style>{base(d['lines'], False)}{layer(s, True)}</svg>")


def strip_svg(d, still):
    o, xs, cw, h = strip(d, 70, 10, W - 100)
    o.append(f"<g class=cursor data-xs='{json.dumps([round(x, 1) for x in xs])}' data-cw='{cw:.2f}'>"
             f"<rect class=cur x={xs[still]:.1f} y=18 width={cw:.1f} height={h - 18}/></g>")
    return xml(f"<svg class='sc strip' viewBox='0 0 {W - 20} {h + 4}' aria-hidden=true xmlns='http://www.w3.org/2000/svg'>"
               f"<style>{STYLE}</style>{''.join(o)}</svg>")


def readme_svg(d):
    steps, edge = d["steps"], d["edge"]
    T = [2.6 if s["hold"] else 1.3 for s in steps]
    total = sum(T)
    capy = H + 24
    o, xs, cw, sh = strip(d, 150, H + 88, W - 190)
    HH = sh + 16
    css = [STYLE, CSS, ".fr{opacity:0}.fr.still{opacity:1}"]
    frames, t0 = [], 0
    for i, s in enumerate(steps):
        a, b = t0 / total * 100, (t0 + T[i]) / total * 100
        css.append(f"@keyframes f{i}{{0%,{a:.3f}%{{opacity:0}}{a + .001:.3f}%,{b:.3f}%{{opacity:1}}{b + .001:.3f}%,100%{{opacity:0}}}}")
        t0 += T[i]
        g = [f"<g class='fr{' still' if i == edge else ''}' style='--a:f{i}'>", layer(s, False),
             f"<text class=k x=20 y={capy}>{esc(s['label'])}</text>"]
        for k, ln in enumerate(textwrap.wrap(s["text"], 150)):
            g.append(f"<text class=cap x=20 y={capy + 22 + k * 19}>{esc(ln)}</text>")
        g.append(f"<rect class=cur x={xs[i]:.1f} y={H + 98} width={cw:.1f} height={sh - H - 98}/></g>")
        frames.append("".join(g))
    css.append("@media (prefers-reduced-motion:no-preference){.fr,.fr.still{opacity:0;animation:" + f"var(--a) {total:.2f}s infinite" + "}}")
    return (f"<svg xmlns='http://www.w3.org/2000/svg' class=sc viewBox='0 0 {W} {HH}' width={W} height={HH} role=img "
            f"aria-label='The core&#39;s 4-bit adder drawn as logic, lit clock by clock from the RTL simulation: add x11, x9, x10 "
            f"takes eight clocks, one nibble each, the carry held in a flip-flop between them; then a subtract inverts B and "
            f"starts the carry at 1'>"
            f"<style>{''.join(css)}</style>{base(d['lines'], True)}"
            f"<text class=m x={W - 20} y={capy} text-anchor=end>recorded: make -C test tour · drawn by docs/tools/adder_schematic.py</text>"
            f"{''.join(o)}{''.join(frames)}</svg>\n")


# ------------------------------------------------------------------- checks
def check_errors(d, fx, site):
    rows = [{k: s[k] for k in COLS} for s in d["steps"]]
    err = model_errors(rows)
    parts = [rows[:8], rows[8:]]
    if len(rows) != 16:
        return err + [f"{len(rows)} clocks drawn, expected two passes of eight"]
    for rs in parts:
        err += instr_errors(rs)
    if not err:
        err += fixture_errors(parts, fx)
    try:
        if d["lines"] != rtl_lines():
            err.append(f"the RTL line numbers are stale against {RTL}")
        if not err and build(rows, site) != d:
            err.append("a drawn value, caption or the gap is not what the recorded clocks give")
    except (ValueError, StopIteration) as x:
        err.append(str(x) or "the two instructions are not the ones drawn")
    return err


def outputs(d):
    return {DATA: json.dumps(d, indent=1, sort_keys=True) + "\n", README_SVG: xml(readme_svg(d))}


MUTANTS = [
    ("a carry flip-flop that drops the carry", lambda d: d["steps"][3].update(carry_q=0)),
    ("carry in from the flip-flop at phase 0", lambda d: d["steps"][0].update(cin=d["steps"][0]["carry_q"])),
    ("a subtract that does not invert B", lambda d: d["steps"][10].update(bx_n=d["steps"][10]["b_n"])),
    ("an adder off by one", lambda d: d["steps"][4].update(sum_n=(d["steps"][4]["sum_n"] + 1) & 15, rf_wd=(d["steps"][4]["sum_n"] + 1) & 15)),
    ("a nibble that is not written", lambda d: d["steps"][5].update(rf_we=0)),
    ("a skipped phase", lambda d: d["steps"][6].update(phase=7)),
    ("a pass at other clocks than the datapath tour's", lambda d: [s.update(cycle=s["cycle"] + 1) for s in d["steps"][:8]]),
    ("a drawn nibble that is not the recorded one", lambda d: d["steps"][2].update(a3="0")),
    ("a wrong gap between the two passes", lambda d: d.update(gap=d["gap"] + 1)),
    ("a stale RTL line", lambda d: d["lines"].update(add=d["lines"]["add"] + 1)),
]


def main():
    args = sys.argv[1:]
    site = json.load(open("docs/site/site.json"))
    fx = json.load(open(FIXTURE))
    if "--check" in args or "--mutants" in args:
        if not os.path.exists(DATA):
            sys.exit(f"adder_schematic: {DATA} is missing; run python3 docs/tools/adder_schematic.py")
        d = json.load(open(DATA))
        if "--mutants" in args:
            caught = 0
            for name, f in MUTANTS:
                m = copy.deepcopy(d)
                f(m)
                hit = bool(check_errors(m, fx, site))
                caught += hit
                print(f"  {'caught' if hit else 'MISSED'}: {name}")
            print(f"adder_schematic: --check caught {caught} of {len(MUTANTS)} broken copies")
            sys.exit(0 if caught == len(MUTANTS) else 1)
        err = check_errors(d, fx, site)
        if err:
            sys.exit("adder_schematic: " + "\n  ".join(["the data fails its checks:"] + err))
        stale = [p for p, t in outputs(d).items() if not os.path.exists(p) or open(p).read() != t]
        if stale:
            sys.exit("adder_schematic: out of date, run python3 docs/tools/adder_schematic.py: " + ", ".join(stale))
        print(f"adder_schematic: {len(d['steps'])} recorded clocks of the 4-bit adder obey the RTL's equations; "
              f"both results match Python's arithmetic and the datapath tour; {len(d['lines'])} RTL lines current")
        return
    r = subprocess.run(["make", "-s", "-C", "test", "tour"], capture_output=True, text=True)
    if r.returncode:
        sys.exit("adder_schematic: make -C test tour failed:\n" + r.stdout[-3000:] + r.stderr[-2000:])
    rows = read_probe(PROBE)
    err = model_errors(rows) + [e for rs in instructions(rows) for e in instr_errors(rs)]
    if err:
        sys.exit("adder_schematic: " + "\n  ".join(["the recording disagrees with the RTL's equations, nothing written:"] + err[:20]))
    d = build(rows, site)
    err = check_errors(d, fx, site)
    if err:
        sys.exit("adder_schematic: " + "\n  ".join(["the built data fails its own check:"] + err))
    out = outputs(d)
    if "--check-sim" in args:
        if not os.path.exists(DATA) or open(DATA).read() != out[DATA]:
            sys.exit(f"adder_schematic: {DATA} differs from a fresh simulation; run python3 docs/tools/adder_schematic.py")
        print(f"adder_schematic: a fresh simulation gives the same {len(d['steps'])} clocks ({len(rows)} probed)")
        return
    for p, t in out.items():
        open(p, "w").write(t)
        print(f"wrote {p} ({len(t) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
