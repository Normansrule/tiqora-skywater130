#!/usr/bin/env python3
"""package_view.py: the packaged chip, every package pin, and what connects to it.

Run from the repo root:  python3 docs/tools/package_view.py [--sibling ../tinytapeout-tiqora]
                                                             [--status docs/status.json]

Writes, deterministically (same inputs, same bytes):
  docs/images/package_qfn64.svg   static top view of the Tiny Tapeout QFN-64 with
                                  this design's function on every pin
  docs/pin_atlas.html             the interactive version: package, system wiring,
                                  block diagram; keyboard operable, light and dark,
                                  reduced motion respected

Inputs, nothing hand-copied:
  info.yaml                       the pinout (this repo, and --sibling for Tiqora-Serial)
  docs/tools/connections.json     what each pin is wired to on the board
  docs/tools/tt_qfn64.json        Tiny Tapeout's package pin names and pad positions,
                                  copied from TinyTapeout/breakout-pcb (source inside)
  --status FILE                   optional evidence rows shown on the page

The die position of a project on the shuttle is assigned by Tiny Tapeout at tape-out,
so the package view shows signals at the pins and does not draw a project location.
"""
import argparse, base64, html, json, os, re

ap = argparse.ArgumentParser()
ap.add_argument("--sibling", help="path to the Tiqora-Serial repository (adds a product switch)")
ap.add_argument("--status", help="JSON list of {label, value, kind, evidence, product?} rows")
ap.add_argument("--layout", action="append", default=[], metavar="KEY=IMAGE=CAPTION",
                help="a rendered GDS (png/jpg) for product KEY (tiqora or serial), with its evidence caption")
ap.add_argument("--artifact", help="also write the page without <!doctype>/<html> to this path")
args = ap.parse_args()

PKG = json.load(open("docs/tools/tt_qfn64.json"))


def read_product(root):
    text = open(os.path.join(root, "info.yaml")).read()
    title = re.search(r'^\s*title:\s*"([^"]*)"', text, re.M).group(1)
    top = re.search(r'^\s*top_module:\s*"([^"]*)"', text, re.M).group(1)
    tiles = re.search(r'^\s*tiles:\s*"([^"]*)"', text, re.M).group(1)
    pins = {}
    for k, i, v in re.findall(r'^\s+(ui|uo|uio)\[(\d)\]:\s*"([^"]*)"', text, re.M):
        name = {"ui": "ui_in", "uo": "uo_out", "uio": "uio"}[k] + f"[{i}]"
        pins[name] = v
    conn = {}
    cj = os.path.join(root, "docs/tools/connections.json")
    devices = []
    if os.path.exists(cj):
        c = json.load(open(cj))
        for d in c["devices"]:
            devices.append({"name": d["name"], "note": d["note"], "color": d["color"],
                            "pins": d["pins"], "dir": d["dir"], "labels": d.get("labels", {})})
            for p, dr in zip(d["pins"], d["dir"]):
                q = (p.replace("ui[", "ui_in[").replace("uo[", "uo_out[")
                     if not p.startswith("uio") else p)
                conn.setdefault(q, []).append({"device": d["name"], "dir": dr,
                                               "label": d.get("labels", {}).get(p, "")})
    return {"title": title, "top": top, "tiles": tiles, "pins": pins, "conn": conn, "devices": devices}


def group(name):
    if name.startswith("ui_in"):  return "in"
    if name.startswith("uo_out"): return "out"
    if name.startswith("uio"):    return "bidir"
    if name in ("clk", "rst_n"):  return "clock"
    if name.startswith("ctrl_") or name == "resetb": return "mux"
    if name.startswith("analog"): return "analog"
    if name in ("NC", "reserved"): return "nc"
    return "power"


TT_ROLE = {
    "clk": "project clock, from the demo board",
    "rst_n": "project reset, active low",
    "ctrl_ena": "enables the selected project",
    "ctrl_sel_inc": "project-select counter: increment",
    "ctrl_sel_rst_n": "project-select counter: reset",
    "resetb": "chip power-on reset, active low",
    "NC": "not connected",
    "reserved": "reserved by Tiny Tapeout",
}


def power_role(n):
    if n.startswith("vdd") or n.startswith("vcc"):
        return "supply: " + {"vddio": "3.3 V I/O", "vccd": "1.8 V core", "vccd1": "1.8 V core",
                             "vccd2": "1.8 V core", "vdda": "3.3 V analog", "vdda1": "3.3 V analog",
                             "vdda2": "3.3 V analog"}.get(n, n)
    return "ground: " + n


def pin_rows(prod):
    rows = []
    for p in PKG["pins"]:
        n, g = p["name"], group(p["name"])
        if g in ("in", "out", "bidir"):
            fn = prod["pins"].get(n, "")
            tt = {"in": "dedicated input", "out": "dedicated output", "bidir": "bidirectional I/O"}[g]
        elif g == "clock":
            fn, tt = ("clock" if n == "clk" else "reset, active low"), TT_ROLE[n]
        elif g == "analog":
            fn, tt = "not used by this design", "analog pin, for analog projects"
        elif g in ("mux", "nc"):
            fn, tt = "not part of this design", TT_ROLE.get(n, n)
        else:
            fn, tt = "power", power_role(n)
        rows.append({"n": p["n"], "name": n, "g": g, "x": p["x"], "y": p["y"], "fn": fn, "tt": tt,
                     "conn": prod["conn"].get(n, [])})
    return rows


here = read_product(".")
products = {"tiqora": here}
if args.sibling:
    products["serial"] = read_product(args.sibling)
PRODUCT_NAMES = {"tiqora": "Tiqora", "serial": "Tiqora-Serial"}
status = json.load(open(args.status)) if args.status else []

# ---------------------------------------------------------------- geometry
# 1 mm = S px. The package is drawn top view, pin 1 at the top of the left side,
# numbering counter-clockwise, exactly as the footprint's pad coordinates say.
S, BODY, PAD_L, PAD_W = 46, 9.0, 0.85, 0.3
CX = CY = 560
W = H = 1120


def side(p):
    x, y = p["x"], p["y"]
    if abs(x) > abs(y): return "L" if x < 0 else "R"
    return "T" if y < 0 else "B"


SHORT = {"in": "in", "out": "out", "bidir": "io", "clock": "clk", "mux": "mux",
         "analog": "ana", "power": "pwr", "nc": "nc"}


def short_fn(r):
    """The pin's function in a few characters: the first part before a slash,
    without a leading 'QSPI', cut at a word boundary."""
    if r["g"] in ("in", "out", "bidir"):
        t = r["fn"].split(" / ")[0].split(" (")[0]
        if t.startswith("QSPI "): t = t[5:]
        words, out = t.split(), ""
        for w in words:
            if len(out) + len(w) + (1 if out else 0) > 13: break
            out = (out + " " + w).strip()
        return out or t[:13]
    return ""


def package_svg(rows, standalone):
    o = []
    if standalone:
        o.append(f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {W} {H}' "
                 "font-family='JetBrains Mono,Consolas,monospace'>")
        o.append("<title>Tiqora in the Tiny Tapeout QFN-64 package: every pin</title>")
        o.append(f"<rect width='{W}' height='{H}' fill='#0d0f12'/>")
    else:
        o.append(f"<svg id='pkg' viewBox='0 0 {W} {H}' role='group' "
                 "aria-label='QFN-64 package, top view. Use arrow keys to move between pins.'>")
    o.append("<defs><linearGradient id='mold' x1='0' y1='0' x2='1' y2='1'>"
             "<stop offset='0' stop-color='#2a2d33'/><stop offset='1' stop-color='#141619'/></linearGradient>"
             "<linearGradient id='gold' x1='0' y1='0' x2='0' y2='1'>"
             "<stop offset='0' stop-color='#f1d27a'/><stop offset='1' stop-color='#b8913a'/></linearGradient></defs>")
    half = BODY / 2 * S
    o.append(f"<rect class='mold' x='{CX-half}' y='{CY-half}' width='{2*half}' height='{2*half}' rx='10' fill='url(#mold)'/>")
    o.append(f"<rect x='{CX-half+10}' y='{CY-half+10}' width='{2*half-20}' height='{2*half-20}' rx='6' "
             "fill='none' stroke='#ffffff' stroke-opacity='.06'/>")
    o.append(f"<circle cx='{CX-half+30}' cy='{CY-half+30}' r='9' fill='#0a0b0d' stroke='#ffffff' stroke-opacity='.18'/>")
    mk = "fill='#c9ccd1' fill-opacity='.78' text-anchor='middle'"
    o.append(f"<text x='{CX}' y='{CY-42}' {mk} font-size='30' letter-spacing='6' font-weight='700'>TINY TAPEOUT</text>")
    o.append(f"<text x='{CX}' y='{CY-4}' {mk} font-size='19' letter-spacing='3'>SKY130 · QFN-64</text>")
    o.append(f"<text x='{CX}' y='{CY+40}' {mk} font-size='15' letter-spacing='2'>9 × 9 mm · 0.5 mm pitch</text>")
    o.append(f"<text x='{CX}' y='{CY+96}' fill='#c9ccd1' fill-opacity='.45' text-anchor='middle' font-size='13'>"
             "illustration · marking not the real one</text>")
    for r in rows:
        sd = side(r)
        x, y = CX + r["x"] * S, CY + r["y"] * S
        if sd in "LR":
            w, h = PAD_L * S, PAD_W * S
            px = CX - half - w * 0.55 if sd == "L" else CX + half - w * 0.45
            py = y - h / 2
        else:
            w, h = PAD_W * S, PAD_L * S
            px = x - w / 2
            py = CY - half - h * 0.55 if sd == "T" else CY + half - h * 0.45
        # leader to the label
        far = 190
        if sd == "L":   lx, ly, anchor, rot = CX - half - 26, y, "end", 0
        elif sd == "R": lx, ly, anchor, rot = CX + half + 26, y, "start", 0
        elif sd == "T": lx, ly, anchor, rot = x, CY - half - 26, "start", -90
        else:           lx, ly, anchor, rot = x, CY + half + 26, "end", -90
        label = short_fn(r)
        lbl = f"{r['n']} {r['name']}"
        attrs = (f"class='pin g-{r['g']}' data-n='{r['n']}' tabindex='0' role='button' "
                 f"aria-label='Pin {r['n']}, {html.escape(r['name'])}: {html.escape(r['fn'])}'") if not standalone \
            else f"class='pin g-{r['g']}'"
        o.append(f"<g {attrs}>")
        o.append(f"<rect class='pad' x='{px:.1f}' y='{py:.1f}' width='{w:.1f}' height='{h:.1f}' rx='2' fill='url(#gold)'/>")
        tr = f" transform='rotate({rot} {lx:.1f} {ly:.1f})'" if rot else ""
        o.append(f"<text class='pl' x='{lx:.1f}' y='{ly+4:.1f}' text-anchor='{anchor}' font-size='15'{tr}>"
                 f"<tspan class='pn'>{lbl}</tspan>"
                 + (f"<tspan class='pf' dx='8'>{html.escape(label)}</tspan>" if label else "")
                 + "</text>")
        o.append("</g>")
    o.append("</svg>")
    return "".join(o)


# ---------------------------------------------------------------- static SVG
GCOL = {"in": "#34c3b0", "out": "#ff7a59", "bidir": "#f2b134", "clock": "#a58cff",
        "mux": "#5aa9ff", "analog": "#7d8590", "power": "#565d66", "nc": "#3d434b"}
rows_here = pin_rows(here)
svg = package_svg(rows_here, True)
style = "".join(f".g-{g} .pf{{fill:{c}}} .g-{g} .pn{{fill:#d7dbe0}}" for g, c in GCOL.items())
svg = svg.replace("<rect width=", f"<style>.pn{{fill:#d7dbe0}}{style}.g-power .pn,.g-nc .pn,.g-analog .pn{{fill:#7d8590}}</style><rect width=", 1)
os.makedirs("docs/images", exist_ok=True)
open("docs/images/package_qfn64.svg", "w").write(svg + "\n")

# ---------------------------------------------------------------- interactive page
data = {k: {"name": PRODUCT_NAMES[k], "title": p["title"], "top": p["top"], "tiles": p["tiles"],
            "rows": pin_rows(p), "devices": p["devices"]} for k, p in products.items()}
page_svg = package_svg(rows_here, False)
layouts = {}
for spec in args.layout:   # images are embedded, so the page stays one self-contained file
    key, path, caption = spec.split("=", 2)
    mime = "image/png" if path.endswith(".png") else "image/jpeg"
    layouts[key] = {"src": f"data:{mime};base64," + base64.b64encode(open(path, "rb").read()).decode(),
                    "caption": caption, "alt": f"Rendered layout of {PRODUCT_NAMES[key]}: {caption}"}
tmpl = open("docs/tools/pin_atlas_template.html").read()
out = (tmpl.replace("/*DATA*/", json.dumps(data, separators=(",", ":"), sort_keys=True))
           .replace("/*LAYOUT*/", json.dumps(layouts, separators=(",", ":"), sort_keys=True))
           .replace("/*STATUS*/", json.dumps(status, separators=(",", ":")))
           .replace("<!--PACKAGE-->", page_svg)
           .replace("<!--SOURCE-->", html.escape(PKG["_source"].split(". Regenerate")[0])))
head = ("<!doctype html>\n<html lang=\"en\"><meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n")
open("docs/pin_atlas.html", "w").write(head + out + "</html>\n")
if args.artifact:      # the same page without the document skeleton, for hosts that add their own
    open(args.artifact, "w").write(out)
print(f"package_qfn64.svg and pin_atlas.html: 64 package pins, {len(products)} product(s)")
