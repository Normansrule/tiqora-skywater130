#!/usr/bin/env node
/* page_test.js — the "Inside a gate" page in a real browser (Playwright, Chromium).

     node test/views/page_test.js [docs/site/views.html]

   1. the page's switch-level simulator gives exactly the node values the
      Python one does (test/views/switch_ref.py), for every cell, every input,
      from both starting values, and through the flip-flop clocking pattern;
   2. every register and output group of every module draws, with one shape
      per gate and one wire per connection the data lists;
   3. the viewing points link: RTL line -> gates, gate -> transistors ->
      layout, input -> its source register, state -> RTL arm and flip-flop,
      ISA row -> its decode line, connections -> module, and the address bar
      round-trips;
   4. it works from the keyboard alone;
   5. light, dark and reduced motion render, and nothing logs an error;
   6. without JavaScript the static tables are there.
   Exit status 1 on any failure. */
"use strict";
const path = require("path");
const { execFileSync } = require("child_process");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "..", "..");
const PAGE = path.resolve(process.argv[2] || path.join(ROOT, "docs/site/views.html"));
const URL = "file://" + PAGE;
let fails = 0, checks = 0;
function ok(cond, what) { checks++; if (!cond) { fails++; console.log("FAIL " + what); } }

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(URL);
  await page.waitForSelector("#views.ready");

  // ---- 1. switch level: page == Python, node by node
  const ref = JSON.parse(execFileSync("python3", [path.join(__dirname, "switch_ref.py")], { maxBuffer: 1 << 28 }).toString());
  const diff = await page.evaluate(ref => {
    const V = TQViews.data, out = [];
    let n = 0;
    for (const ct of Object.keys(ref)) {
      const T = V.celltypes[ct];
      if (!T) { out.push(ct + ": not in the page's data"); continue; }
      for (const init of ["0", "1"]) {
        let prev = null;
        for (const [fixed, want] of ref[ct].runs[init]) {
          const got = TQViews.settle(T.fets, fixed, +init, ref[ct].seq ? prev : undefined);
          prev = got;
          n++;
          for (const k of Object.keys(want)) {
            if (got[k] !== want[k]) { out.push(ct + " init " + init + " " + JSON.stringify(fixed) + ": node " + k + " page " + got[k] + " python " + want[k]); break; }
          }
          if (Object.keys(got).length !== Object.keys(want).length) out.push(ct + ": node sets differ");
        }
      }
    }
    return { out, n };
  }, ref);
  ok(diff.out.length === 0, "switch level differs from Python: " + diff.out.slice(0, 5).join("; "));
  ok(diff.n > 2000, "only " + diff.n + " switch-level states compared");
  console.log("page_test: switch level, " + diff.n + " states x every node, page equals Python");

  // liberty evaluator: same answer as the truth table column in Python (combinational cells)
  const libBad = await page.evaluate(ref => {
    const V = TQViews.data, bad = [];
    for (const ct of Object.keys(ref)) {
      const T = V.celltypes[ct];
      if (ref[ct].seq) continue;
      for (const [fixed, want] of ref[ct].runs["0"]) {
        for (const o of Object.keys(T.function)) {
          const env = {}; Object.keys(fixed).forEach(k => { if (T.pins[k] === "input") env[k] = fixed[k]; });
          if (TQViews.libEval(T.function[o], env) !== want[o]) bad.push(ct + "." + o + " " + JSON.stringify(env));
        }
      }
    }
    return bad;
  }, ref);
  ok(libBad.length === 0, "page's liberty evaluator disagrees with the transistors: " + libBad.slice(0, 5).join("; "));

  // ---- 2. every group draws
  const groups = await page.evaluate(() => Object.keys(TQViews.data.groups));
  let drawn = 0;
  for (const gid of groups) {
    const mod = gid.split("/")[0];
    await page.evaluate(h => { location.hash = h; }, "#m=" + encodeURIComponent(mod) + "&g=" + encodeURIComponent(gid));
    const r = await page.evaluate(gid => {
      const g = TQViews.data.groups[gid];
      const svg = document.querySelector("#vw-gate-body svg.gates");
      if (!svg) return { err: "no svg" };
      return { gates: svg.querySelectorAll("g.gate").length, wires: svg.querySelectorAll("path.wire").length,
        wantG: g.nodes.filter(n => n[1] === "c").length, wantW: g.edges.length,
        rtl: document.querySelectorAll("#vw-rtl-body .vw-ln.on-g").length, wantR: g.rtl.length };
    }, gid);
    ok(!r.err && r.gates === r.wantG && r.wires === r.wantW, gid + ": drew " + JSON.stringify(r));
    ok(r.rtl === r.wantR, gid + ": " + r.rtl + " RTL lines lit, data lists " + r.wantR);
    drawn++;
  }
  console.log("page_test: " + drawn + " register and output groups drawn and checked");

  // ---- 3. viewing points link
  await page.goto(URL + "#m=tp_uart&g=tp_uart%2Ftcnt");
  await page.waitForSelector("#views.ready");
  // a gate -> its transistors and layout
  const gate = page.locator("#vw-gate-body g.gate:not(.ff)").nth(3);
  await gate.click();
  ok(/[?#&]c=/.test(await page.evaluate(() => location.hash)), "choosing a gate puts it in the address");
  const nf = await page.locator("#vw-cell-body g.fet").count();
  const ct = await page.evaluate(() => { const c = decodeURIComponent(location.hash.match(/c=([^&]+)/)[1]); return TQViews.data.groups["tp_uart/tcnt"].ctypes[TQViews.data.groups["tp_uart/tcnt"].nodes.findIndex(n => n[0] === c)]; });
  ok(nf > 0 && nf === (await page.evaluate(ct => TQViews.data.celltypes[ct].fets.length, ct)), "transistor view draws every transistor of " + ct);
  ok(await page.locator("#vw-lay-body svg.lay polygon").count() > 10, "layout view draws polygons");
  ok(await page.locator("#vw-lay-body g.gm").count() === nf, "every transistor is marked in the layout");
  // flipping an input changes which transistors conduct, and the output agrees with liberty
  const before = await page.locator("#vw-cell-body g.fet.on").count();
  await page.locator("#vw-cell-body button.pin").first().click();
  const after = await page.locator("#vw-cell-body g.fet.on").count();
  const outTxt = await page.locator("#vw-cell-body .vw-out").allTextContents();
  ok(outTxt.length && outTxt.every(t => /matches liberty/.test(t)), "outputs match liberty after a flip: " + outTxt.join(" | "));
  ok(await page.locator("#vw-cell-body g.fet.on").count() > 0, "some transistors conduct (" + before + " -> " + after + ")");
  // a transistor -> selected in both the schematic and the layout
  await page.locator("#vw-cell-body g.fet").first().click();
  ok(await page.locator("#vw-cell-body g.fet.sel").count() === 1 && await page.locator("#vw-lay-body g.gm.sel").count() === 1, "a transistor is selected in schematic and layout together");
  // layer toggles hide a layer
  const polyBefore = await page.locator("#vw-lay-body .ly-poly polygon").count();
  await page.locator("#vw-lay-body button.lay", { hasText: "polysilicon" }).click();
  ok(polyBefore > 0 && await page.locator("#vw-lay-body .ly-poly polygon").count() === 0, "polysilicon layer toggles off");
  await page.locator("#vw-lay-body button.lay", { hasText: "polysilicon" }).click();
  // FinFET comparison is labelled illustrative
  await page.locator("#vw-lay-body button", { hasText: "FinFET" }).click();
  ok(await page.locator("#vw-lay-body figure .ev.illustrative").count() === 1, "FinFET figure carries the illustrative badge");
  ok(/no FinFETs/.test(await page.locator("#vw-lay-body figure").textContent()), "FinFET figure says sky130 has none");

  // an input terminal -> the register that drives it
  const ins = page.locator("#vw-gate-body svg.gates g[role=button]");
  if (await ins.count()) {
    const lbl = await ins.first().getAttribute("aria-label");
    await ins.first().click();
    ok(/c=/.test(await page.evaluate(() => location.hash)), "an input terminal jumps to its source flip-flop (" + lbl + ")");
    ok(await page.locator("#vw-gate-body g.gate.sel").count() === 1, "the source flip-flop is selected in the schematic");
  }

  // an RTL line -> its group
  await page.goto(URL + "#m=tp_uart");
  await page.waitForSelector("#views.ready");
  const mk = page.locator("#vw-rtl-body .vw-ln.mk").first();
  await mk.click();
  ok(/g=/.test(await page.evaluate(() => location.hash)), "a marked RTL line opens its register's gates");
  ok(await page.locator("#vw-gate-body svg.gates").count() === 1, "gates are drawn after choosing a line");

  // FSMs: each state -> RTL arm lit, its one-hot flip-flop selected; each edge selectable
  const nfsm = await page.evaluate(() => TQViews.data.fsms.length);
  ok(nfsm === 2, "two state machines in the data");
  for (let fi = 0; fi < nfsm; fi++) {
    await page.locator("#vw-fsm-body button[role=tab]", { hasText: "State machines" }).click();
    await page.locator("#vw-fsm-body .vw-chips button").nth(fi).click();
    const F = await page.evaluate(fi => TQViews.data.fsms[fi], fi);
    const states = page.locator("#vw-fsm-body svg.fsm g.st");
    ok(await states.count() === F.states.length, F.module + ": every state drawn");
    for (let i = 0; i < F.states.length; i++) {
      await page.locator("#vw-fsm-body svg.fsm g.st").nth(i).click();
      const st = F.states[i];
      const lit = await page.locator("#vw-rtl-body .vw-ln.on-s").count();
      ok(!st.arm || lit === st.arm[1] - st.arm[0] + 1, F.module + "." + st.name + ": case arm lit (" + lit + " lines)");
      const selC = await page.evaluate(() => decodeURIComponent((location.hash.match(/c=([^&]+)/) || [])[1] || ""));
      ok(selC === st.flop, F.module + "." + st.name + ": one-hot flip-flop " + st.flop + " selected, got " + selC);
      ok(await page.locator("#vw-gate-body g.gate.sel").count() === 1, F.module + "." + st.name + ": flip-flop shown in the schematic");
    }
    const tr = page.locator("#vw-fsm-body svg.fsm g[role=button]:not(.st)");
    ok(await tr.count() === F.edges.length, F.module + ": every transition drawn and clickable");
    await tr.first().focus();
    await page.keyboard.press("Enter");          // a curve's bounding-box centre is not on the curve
    ok(await page.locator("#vw-fsm-body .vw-fsminfo li").count() > 0, F.module + ": a transition lists its conditions");
  }
  // connections -> module
  await page.locator("#vw-fsm-body button[role=tab]", { hasText: "Connections" }).click();
  const boxes = page.locator("#vw-fsm-body svg.links g.mb[role=button]");
  ok(await boxes.count() >= 3, "connections view shows submodules");
  await boxes.first().click();
  ok(/m=/.test(await page.evaluate(() => location.hash)), "a connections box opens its module");
  // ISA -> decode line
  await page.locator("#vw-fsm-body button[role=tab]", { hasText: "RISC-V" }).click();
  const rows = await page.locator("#vw-fsm-body table.vw-isa tr").count();
  const nisa = await page.evaluate(() => TQViews.data.isa.rows.length);
  ok(rows === nisa + 1, "ISA table has every row (" + (rows - 1) + "/" + nisa + ")");
  await page.locator("#vw-fsm-body .vw-link").first().click();
  const line = await page.evaluate(() => TQViews.data.isa.rows[0].rtl[1][0]);
  ok(await page.locator("#vw-rtl-body .vw-ln.on-x[data-line='" + line + "']").count() === 1, "ISA row lights its decode line " + line + " in tp_ncore");

  // the address bar round-trips
  await page.goto(URL + "#m=qspi_ctrl&f=0&st=0");
  await page.waitForSelector("#views.ready");
  ok(await page.locator(".vw-crumb", { hasText: "qspi_ctrl" }).count() >= 1, "deep link opens the module");

  // a flip-flop in the transistor view: CLK 0 -> 1 loads D, D alone does not change Q
  await page.goto(URL + "#m=tp_uart&g=tp_uart%2Ftcnt");
  await page.waitForSelector("#views.ready");
  await page.locator("#vw-gate-body g.gate.ff").first().click();
  const pin = n => page.locator("#vw-cell-body button.pin", { hasText: new RegExp("^" + n + " =") });
  const q = async () => (await page.locator("#vw-cell-body .vw-out").first().textContent()).trim();
  const qs = [];
  if (/= 1/.test(await pin("CLK").textContent())) await pin("CLK").click();       // CLK 0
  if (/= 0/.test(await pin("D").textContent())) await pin("D").click();           // D 1
  await pin("CLK").click(); qs.push(await q());                                     // rise: Q 1
  await pin("D").click(); qs.push(await q());                                       // D 0, CLK high: hold 1
  await pin("CLK").click(); qs.push(await q());                                     // fall: hold 1
  await pin("CLK").click(); qs.push(await q());                                     // rise: Q 0
  ok(JSON.stringify(qs) === JSON.stringify(["Q = 1", "Q = 1", "Q = 1", "Q = 0"]), "flip-flop in the page loads on the rising edge only: " + qs.join(", "));

  // ---- 4. keyboard only
  await page.goto(URL + "#m=tp_uart&g=tp_uart%2Ftcnt");
  await page.waitForSelector("#views.ready");
  await page.locator("#vw-gate-body g.gate").nth(2).focus();
  await page.keyboard.press("Enter");
  ok(await page.locator("#vw-cell-body g.fet").count() > 0, "Enter on a focused gate opens its transistors");
  await page.locator("#vw-cell-body g.fet").first().focus();
  await page.keyboard.press(" ");
  ok(await page.locator("#vw-lay-body g.gm.sel").count() === 1, "Space on a focused transistor selects it in the layout");
  const focusables = await page.evaluate(() => [...document.querySelectorAll("#views [role=button]")].every(e => e.getAttribute("tabindex") === "0" && e.getAttribute("aria-label")));
  ok(focusables, "every clickable drawing is focusable and labelled");

  // ---- 5. themes and reduced motion
  for (const scheme of ["light", "dark"]) {
    for (const motion of ["no-preference", "reduce"]) {
      const p = await browser.newPage({ colorScheme: scheme, reducedMotion: motion });
      const errs = [];
      p.on("pageerror", e => errs.push(String(e)));
      await p.goto(URL + "#m=tp_uart&g=tp_uart%2Ftcnt");
      await p.waitForSelector("#views.ready");
      const bg = await p.evaluate(() => getComputedStyle(document.querySelector(".vw-pane")).backgroundColor);
      const nwell = await p.evaluate(() => getComputedStyle(document.getElementById("views")).getPropertyValue("--ly-nwell").trim());
      ok(errs.length === 0, scheme + "/" + motion + ": errors " + errs.join("; "));
      ok(scheme === "light" ? nwell === "#c9e3c3" : nwell === "#24402a", scheme + ": layer colours follow the theme (" + nwell + ", panes " + bg + ")");
      await p.close();
    }
  }

  // ---- 6. no JavaScript
  const nojs = await browser.newContext({ javaScriptEnabled: false });
  const p2 = await nojs.newPage();
  await p2.goto(URL);
  const txt = await p2.locator("noscript").first().textContent().catch(() => "");
  const staticTables = await p2.locator(".vw-static table").count();
  ok(staticTables >= 3 || /tp_ncore/.test(txt), "static fallback has the module, state machine and ISA tables");
  await nojs.close();

  ok(errors.length === 0, "console errors: " + errors.slice(0, 5).join("; "));
  await browser.close();
  console.log("page_test: " + checks + " checks, " + fails + " failures");
  process.exit(fails ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
