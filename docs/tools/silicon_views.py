#!/usr/bin/env python3
"""silicon_views.py — pin-by-pin and board-to-silicon visuals from real data.

  python3 docs/tools/silicon_views.py

Reads info.yaml (pin functions), docs/tile_template.json (the Tiny Tapeout
tile outline and the exact position of all 43 pins, extracted from Tiny
Tapeout's own tt_block_*_pg.def with --from-def) and docs/tools/connections.json
(which pins go to which device), plus docs/images/layout_blocks.png. Writes
animated SVGs to docs/images: pin_map.svg, board_to_silicon.svg, connections.svg.

  python3 docs/tools/silicon_views.py --from-def <tt-support-tools>/tech/sky130A/def/tt_block_2x2_pg.def
"""
import base64, io, json, re, sys
BG, CARD, FG, DIM, RULE = "#0b0e14", "#161b22", "#e9ecef", "#8b949e", "#30363d"
IN_C, OUT_C, BI_C, SYS_C, GOLD = "#4f8cff", "#3ddc97", "#ff9f1c", "#c77dff", "#ffd23f"
FONT = "font-family='Inter,Segoe UI,Helvetica,Arial,sans-serif'"
MONO = "font-family='JetBrains Mono,SFMono-Regular,Consolas,monospace'"
RM = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"

def esc(t): return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ---------------------------------------------------------------- template
def from_def(path):
    s = open(path).read()
    units = float(re.search(r"UNITS DISTANCE MICRONS (\d+)", s).group(1))
    x0, y0, x1, y1 = map(float, re.search(r"DIEAREA \( (\d+) (\d+) \) \( (\d+) (\d+) \)", s).groups())
    pins = []
    for m in re.finditer(r"- (\S+) \+ NET \S+ \+ DIRECTION (\w+).*?LAYER (\w+).*?PLACED \( (-?\d+) (-?\d+) \)", s, re.S):
        name, d, layer, x, y = m.groups()
        pins.append({"name": name, "dir": d.lower(), "layer": layer, "x": float(x) / units, "y": float(y) / units})
    pins.sort(key=lambda p: p["x"])
    out = {"source": path.split("/")[-1], "die_um": [(x1 - x0) / units, (y1 - y0) / units], "pins": pins}
    json.dump(out, open("docs/tile_template.json", "w"), indent=1)
    print(f"docs/tile_template.json: {len(pins)} pins, die {out['die_um'][0]} x {out['die_um'][1]} um")

# ---------------------------------------------------------------- inputs
def load_info():
    info, pin = {}, {}
    txt = open("info.yaml").read()
    for k in ("title", "tiles", "top_module"):
        m = re.search(rf'^\s*{k}:\s*"([^"]*)"', txt, re.M)
        info[k] = m.group(1) if m else ""
    for m in re.finditer(r'^\s*(ui|uo|uio)\[(\d)\]:\s*"([^"]*)"', txt, re.M):
        pin[f"{m.group(1)}[{m.group(2)}]"] = m.group(3)
    return info, pin

def pin_function(name, pinfo):
    m = re.match(r"(ui_in|uo_out|uio_in|uio_out|uio_oe)\[(\d)\]", name)
    if not m:
        return {"clk": "system clock", "rst_n": "reset (active low)", "ena": "design enabled"}.get(name, "")
    group = {"ui_in": "ui", "uo_out": "uo"}.get(m.group(1), "uio")
    return pinfo.get(f"{group}[{m.group(2)}]", "")

def short(t, n=26):
    t = re.split(r"[(;,]", t)[0].strip()
    return t if len(t) <= n else t[: n - 1] + "…"

def thumb(width):
    from PIL import Image
    im = Image.open("docs/images/layout_blocks.png").convert("RGB")
    im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, "JPEG", quality=72, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode(), im.size

def kind(name):
    if name.startswith("ui_in"): return "in"
    if name.startswith("uo_out"): return "out"
    if name.startswith("uio"): return "bi"
    return "sys"
COL = {"in": IN_C, "out": OUT_C, "bi": BI_C, "sys": SYS_C}

def svg(w, h, title, css, body):
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {w} {h}' {FONT}><title>{esc(title)}</title>"
            f"<style>{css}{RM}</style><rect width='{w}' height='{h}' rx='16' fill='{BG}'/>{body}</svg>")

# ---------------------------------------------------------------- 1. pin map
def pin_map(info, pinfo, tpl):
    tw, th = tpl["die_um"]; pins = tpl["pins"]
    W = 1500
    scale = 760 / max(tw, th * 1.6)
    TW, TH = tw * scale, th * scale
    tx, ty = (W - TW) / 2, 575
    uri, _ = thumb(int(TW * 2))
    body = [f"<text x='40' y='46' fill='{FG}' font-size='26' font-weight='800'>Every pin, where it really is</text>",
            f"<text x='40' y='74' fill='{DIM}' font-size='15'>The {info['tiles']} tile at true scale ({tw:.2f} × {th:.2f} µm), "
            f"with its {len(pins)} pins on metal 4 along the top edge, exactly where Tiny Tapeout's own template "
            f"({esc(tpl['source'])}) puts them.</text>"
            f"<text x='40' y='96' fill='{DIM}' font-size='15'>The band spreads them out so each one can be named with its function.</text>",
            f"<image href='{uri}' x='{tx}' y='{ty}' width='{TW}' height='{TH}' preserveAspectRatio='none' opacity='.95'/>",
            f"<rect x='{tx}' y='{ty}' width='{TW}' height='{TH}' fill='none' stroke='{FG}' stroke-width='1.5'/>",
            f"<text x='{tx + TW / 2}' y='{ty + TH + 26}' text-anchor='middle' fill='{DIM}' font-size='13'>"
            f"the design's real sky130 cells, placed by block (routing is added by the hardening flow)</text>"]
    css = []
    n = len(pins)
    band_x0, band_x1, band_y = 70, W - 70, 345
    step = (band_x1 - band_x0) / (n - 1)
    pmin, pmax = min(p["x"] for p in pins), max(p["x"] for p in pins)
    body.append(f"<path d='M{tx + pmin * scale - 4},{ty} L{band_x0 - 10},{band_y + 22} L{band_x1 + 10},{band_y + 22} "
                f"L{tx + pmax * scale + 4},{ty} Z' fill='{GOLD}' opacity='.06'/>")
    for i, p in enumerate(pins):
        k = kind(p["name"]); c = COL[k]
        px = tx + p["x"] * scale
        bx = band_x0 + i * step
        body.append(f"<rect x='{px - 0.8}' y='{ty - 7}' width='1.6' height='9' fill='{c}'/>"
                    f"<line x1='{px}' y1='{ty - 7}' x2='{bx}' y2='{band_y + 18}' stroke='{c}' stroke-width='.8' opacity='.45'/>"
                    f"<rect x='{bx - 5}' y='{band_y}' width='10' height='18' rx='2' fill='{c}'/>")
        fn = short(pin_function(p["name"], pinfo))
        body.append(f"<g transform='translate({bx + 4},{band_y - 8}) rotate(-62)'>"
                    f"<text fill='{FG}' font-size='12.5' font-weight='700' {MONO}>{esc(p['name'])}</text>"
                    f"<text x='{len(p['name']) * 7.6 + 8}' fill='{DIM}' font-size='12'>{esc(fn)}</text></g>")
        # a pulse travelling along the lead: into the tile for inputs, out of it for outputs
        d = 2.4; delay = (i * 0.11) % d
        going_in = k in ("in", "sys")
        y_from, y_to = (band_y + 18, ty - 7) if going_in else (ty - 7, band_y + 18)
        x_from, x_to = (bx, px) if going_in else (px, bx)
        css.append(f"@keyframes m{i}{{0%{{transform:translate({x_from}px,{y_from}px);opacity:0}}15%{{opacity:1}}"
                   f"85%{{opacity:1}}100%{{transform:translate({x_to}px,{y_to}px);opacity:0}}}}"
                   f".m{i}{{animation:m{i} {d}s linear {delay:.2f}s infinite;opacity:0}}")
        body.append(f"<circle class='m{i}' r='2.6' fill='{c}'/>")
    lx = 40
    for k, label in (("sys", "clock, reset, enable"), ("in", "inputs ui_in"), ("out", "outputs uo_out"),
                     ("bi", "bidirectional uio (in, out, output-enable)")):
        body.append(f"<rect x='{lx}' y='{ty + TH + 50}' width='14' height='14' rx='3' fill='{COL[k]}'/>"
                    f"<text x='{lx + 22}' y='{ty + TH + 62}' fill='{FG}' font-size='14'>{label}</text>")
        lx += 30 + len(label) * 8.2
    H = int(ty + TH + 90)
    open("docs/images/pin_map.svg", "w").write(svg(W, H, "Every pin of the tile, at its real position", "".join(css), "".join(body)))

# ---------------------------------------------------------------- 2. board to silicon
def board_to_silicon(info, tpl):
    W, H = 1500, 620
    cols, rows = map(int, info["tiles"].split("x"))
    uri, (iw, ih) = thumb(330)
    body, css = [], []
    body.append(f"<text x='40' y='46' fill='{FG}' font-size='26' font-weight='800'>From the board to the silicon</text>"
                f"<text x='40' y='74' fill='{DIM}' font-size='15'>Tiny Tapeout chips arrive in a QFN package on a carrier board that "
                f"plugs into the demo board. Every project on the shuttle shares one die, behind a multiplexer.</text>")
    P = [(40, 120), (400, 120), (760, 120), (1120, 120)]; PW, PH = 340, 420
    titles = ["1  The demo board", "2  The carrier board", "3  The die", "4  This project's tiles"]
    tw_, th_ = tpl["die_um"]
    notes = [("RP2350 and USB-C; the Pmod headers", "carry the QSPI memory and I/O"),
             ("the chip in its QFN package,", "on a socket you can swap"),
             ("the pad ring, the multiplexer,", "and every project's tiles"),
             (f"{info['tiles']} tiles, {tw_:.2f} × {th_:.2f} µm:", "the design's real sky130 cells")]
    for k, ((x, y), t, n) in enumerate(zip(P, titles, notes)):
        body.append(f"<rect class='p{k}' x='{x}' y='{y}' width='{PW}' height='{PH}' rx='14' fill='{CARD}' stroke='{RULE}' stroke-width='2'/>"
                    f"<text x='{x + 18}' y='{y + 34}' fill='{FG}' font-size='17' font-weight='800'>{t}</text>"
                    f"<text x='{x + 18}' y='{y + PH - 34}' fill='{DIM}' font-size='12.5'>{esc(n[0])}</text>"
                    f"<text x='{x + 18}' y='{y + PH - 16}' fill='{DIM}' font-size='12.5'>{esc(n[1])}</text>")
        css.append(f"@keyframes p{k}{{0%,{k * 25}%{{stroke:{RULE}}}{k * 25 + 2}%,{k * 25 + 22}%{{stroke:{GOLD}}}"
                   f"{k * 25 + 24}%,100%{{stroke:{RULE}}}}}.p{k}{{animation:p{k} 10s infinite}}")
    # 1: demo board
    x, y = P[0]
    body.append(f"<rect x='{x + 30}' y='{y + 60}' width='280' height='300' rx='10' fill='#1d5c3a'/>"
                f"<rect x='{x + 120}' y='{y + 330}' width='60' height='22' rx='4' fill='#adb5bd'/>"
                f"<text x='{x + 150}' y='{y + 345}' text-anchor='middle' fill='#111' font-size='10' font-weight='700'>USB-C</text>"
                f"<rect x='{x + 50}' y='{y + 250}' width='70' height='70' rx='4' fill='#222'/>"
                f"<text x='{x + 85}' y='{y + 290}' text-anchor='middle' fill='#ddd' font-size='11'>RP2350</text>"
                f"<rect x='{x + 205}' y='{y + 250}' width='90' height='40' rx='4' fill='#300' stroke='#a33'/>"
                f"<text x='{x + 250}' y='{y + 276}' text-anchor='middle' fill='#f66' font-size='20' {MONO}>8.</text>"
                + "".join(f"<rect x='{x + 45 + i * 64}' y='{y + 72}' width='54' height='18' rx='3' fill='#111'/>"
                          f"<text x='{x + 72 + i * 64}' y='{y + 86}' text-anchor='middle' fill='#aaa' font-size='10'>Pmod</text>" for i in range(4))
                + f"<rect id='sock' x='{x + 110}' y='{y + 130}' width='120' height='100' rx='6' fill='#0f3d25' stroke='{GOLD}' stroke-width='2'/>"
                f"<text x='{x + 170}' y='{y + 185}' text-anchor='middle' fill='{GOLD}' font-size='11'>carrier board</text>")
    # 2: carrier with QFN
    x, y = P[1]
    body.append(f"<rect x='{x + 40}' y='{y + 70}' width='260' height='280' rx='10' fill='#1d5c3a'/>"
                f"<rect x='{x + 105}' y='{y + 135}' width='130' height='130' rx='6' fill='#1b1b1b'/>"
                + "".join(f"<rect x='{x + 112 + i * 7.6}' y='{y + 129}' width='4' height='7' fill='#c9c9c9'/>"
                          f"<rect x='{x + 112 + i * 7.6}' y='{y + 264}' width='4' height='7' fill='#c9c9c9'/>"
                          f"<rect x='{x + 99}' y='{y + 142 + i * 7.6}' width='7' height='4' fill='#c9c9c9'/>"
                          f"<rect x='{x + 234}' y='{y + 142 + i * 7.6}' width='7' height='4' fill='#c9c9c9'/>" for i in range(16))
                + f"<circle cx='{x + 117}' cy='{y + 147}' r='3' fill='#555'/>"
                f"<text x='{x + 170}' y='{y + 205}' text-anchor='middle' fill='#ccc' font-size='13' font-weight='700'>QFN</text>")
    # 3: die
    x, y = P[2]
    dx, dy, dw, dh = x + 40, y + 60, 260, 300
    body.append(f"<rect x='{dx}' y='{dy}' width='{dw}' height='{dh}' fill='#2b2440' stroke='#7a6aa8'/>"
                + "".join(f"<rect x='{dx + 6 + i * 15.6}' y='{dy + 4}' width='10' height='10' fill='#c9a227'/>"
                          f"<rect x='{dx + 6 + i * 15.6}' y='{dy + dh - 14}' width='10' height='10' fill='#c9a227'/>" for i in range(16))
                + f"<rect x='{dx + 20}' y='{dy + 136}' width='{dw - 40}' height='22' fill='#4a3f6b'/>"
                f"<text x='{dx + dw / 2}' y='{dy + 151}' text-anchor='middle' fill='#cfc4ef' font-size='10'>multiplexer spine</text>")
    gx, gy, gc, gr, cw, ch = dx + 22, dy + 26, 16, 4, (dw - 44) / 16, 26
    mine = {(c, r) for c in range(2, 2 + cols) for r in range(rows)}
    for half, oy in ((0, gy), (1, dy + 166)):
        for r in range(gr):
            for c in range(gc):
                own = half == 0 and (c, r) in mine
                body.append(f"<rect {'class=\"me\" ' if own else ''}x='{gx + c * cw + 1}' y='{oy + r * ch + 1}' width='{cw - 2}' height='{ch - 2}' "
                            f"fill='{GOLD if own else '#3a3358'}'/>")
    css.append(f"@keyframes me{{0%,50%,100%{{opacity:1}}25%,75%{{opacity:.45}}}}.me{{animation:me 2.5s infinite}}")
    # 4: our tiles, real cells
    x, y = P[3]
    sc = min(300 / iw, 330 / ih)
    body.append(f"<image href='{uri}' x='{x + 20 + (300 - iw * sc) / 2}' y='{y + 60}' width='{iw * sc}' height='{ih * sc}'/>")
    # zoom connectors
    for (ax, ay), (bx, by) in (((P[0][0] + 230, P[0][1] + 180), (P[1][0], P[1][1] + 210)),
                               ((P[1][0] + 235, P[1][1] + 200), (P[2][0], P[2][1] + 210)),
                               ((P[2][0] + 70, P[2][1] + 100), (P[3][0], P[3][1] + 210))):
        body.append(f"<path class='zl' d='M{ax},{ay} C{(ax + bx) / 2},{ay} {(ax + bx) / 2},{by} {bx},{by}' fill='none' "
                    f"stroke='{GOLD}' stroke-width='1.6' stroke-dasharray='6 6'/>")
    css.append(f"@keyframes zl{{to{{stroke-dashoffset:-48}}}}.zl{{animation:zl 1.6s linear infinite}}")
    body.append(f"<text x='40' y='{H - 22}' fill='{DIM}' font-size='12.5'>Panels 1–3 are illustrations, not to scale. "
                f"Panel 4 is the design's real standard cells. The routed layout appears after the GitHub hardening run.</text>")
    open("docs/images/board_to_silicon.svg", "w").write(svg(W, H, "From the demo board to the silicon", "".join(css), "".join(body)))

# ---------------------------------------------------------------- 3. connections
def connections(info, pinfo):
    cfg = json.load(open("docs/tools/connections.json"))
    rows = [(d, p) for d in cfg["devices"] for p in d["pins"]]
    W = 1500; top = 120; rh = 26
    H = top + len(rows) * rh + 24 * len(cfg["devices"]) + 70
    cx, cw = 70, 240
    body, css = [], []
    body.append(f"<text x='40' y='46' fill='{FG}' font-size='26' font-weight='800'>What every pin connects to</text>"
                f"<text x='40' y='74' fill='{DIM}' font-size='15'>{esc(cfg['subtitle'])}</text>")
    y = top; chip_top = top - 10
    for di, d in enumerate(cfg["devices"]):
        y0 = y
        for pi, pn in enumerate(d["pins"]):
            k = "bi" if pn.startswith("uio") else "in" if pn.startswith("ui") else "out" if pn.startswith("uo") else "sys"
            out = d["dir"][pi] == "out"
            c = COL[k]
            fn = d.get("labels", {}).get(pn) or short(pin_function(pn.replace("uio[", "uio_in[").replace("ui[", "ui_in[").replace("uo[", "uo_out["), pinfo), 40)
            body.append(f"<text x='{cx + cw - 12}' y='{y + 17}' text-anchor='end' fill='{FG}' font-size='13' {MONO}>{esc(pn)}</text>"
                        f"<line x1='{cx + cw}' y1='{y + 12}' x2='{cx + cw + 18}' y2='{y + 12}' stroke='{c}' stroke-width='3'/>"
                        f"<path class='{'fo' if out else 'fi'}' d='M{cx + cw + 18},{y + 12} L1010,{y + 12}' stroke='{c}' stroke-width='2' "
                        f"stroke-dasharray='5 9' fill='none'/>"
                        f"<text x='{cx + cw + 30}' y='{y + 8}' fill='{DIM}' font-size='11.5'>{esc(fn)}</text>")
            y += rh
        body.append(f"<rect x='1010' y='{y0 - 4}' width='450' height='{y - y0 + 6}' rx='10' fill='{CARD}' stroke='{d.get('color', RULE)}' stroke-width='2'/>"
                    f"<text x='1030' y='{y0 + 22}' fill='{FG}' font-size='16' font-weight='800'>{esc(d['name'])}</text>"
                    f"<text x='1030' y='{y0 + 42}' fill='{DIM}' font-size='12.5'>{esc(d['note'])}</text>")
        y += 24
    body.insert(1, f"<rect x='{cx}' y='{chip_top}' width='{cw}' height='{y - chip_top - 14}' rx='14' fill='#1b1b1b' stroke='#555' stroke-width='2'/>"
                   f"<text x='{cx + 24}' y='{chip_top + 34}' fill='{FG}' font-size='{20 if len(cfg['chip']) <= 10 else 15}' font-weight='800'>{esc(cfg['chip'])}</text>"
                   f"<text x='{cx + 24}' y='{chip_top + 56}' fill='{DIM}' font-size='13'>{info['tiles']} Tiny Tapeout tiles</text>")
    css.append("@keyframes fo{to{stroke-dashoffset:-28}}@keyframes fi{to{stroke-dashoffset:28}}"
               ".fo{animation:fo 1.2s linear infinite}.fi{animation:fi 1.2s linear infinite}")
    body.append(f"<text x='40' y='{H - 26}' fill='{DIM}' font-size='13'>Signal flow: the dashes move toward the chip on inputs "
                f"and away from it on outputs. Colours: purple clock/reset, blue inputs, green outputs, orange bidirectional.</text>")
    open("docs/images/connections.svg", "w").write(svg(W, int(H), "What every pin connects to", "".join(css), "".join(body)))

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--from-def":
        from_def(sys.argv[2]); sys.exit()
    info, pinfo = load_info()
    tpl = json.load(open("docs/tile_template.json"))
    pin_map(info, pinfo, tpl); board_to_silicon(info, tpl); connections(info, pinfo)
    import xml.dom.minidom as m
    for f in ("pin_map", "board_to_silicon", "connections"):
        m.parse(f"docs/images/{f}.svg")
    print("wrote pin_map.svg, board_to_silicon.svg, connections.svg (all well-formed)")
