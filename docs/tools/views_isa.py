#!/usr/bin/env python3
"""views_isa.py — the RISC-V / x86-64 lens, assembled for real.

    python3 docs/tools/views_isa.py           docs/views/isa_lens.json -> docs/views/isa.json
    python3 docs/tools/views_isa.py --check   fail if isa.json is out of date or a row is wrong

Each row of docs/views/isa_lens.json pairs one RV32E instruction with the
nearest x86-64 instruction(s). Both columns go through a real assembler:

  RISC-V   the Clang inside `pip install ziglang`, the compiler `make c` already
           uses (-target riscv32-freestanding-none -mcpu=generic_rv32+e-i; -g0,
           because with debug info on, LLVM rejects a bare `.insn` line with
           "Undefined temporary symbol")
  x86-64   GNU as (binutils), Intel syntax

and the bytes they produce are stored next to the text. Every RISC-V word is
then checked: its opcode field (bits 6:0) must equal the tp_pkg constant
the row names, which is the value src/core/tp_ncore.sv decodes. A row whose
assembly fails, or whose opcode is not what the core decodes, fails the run.
"""
import json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "docs", "views", "isa_lens.json")
OUT = os.path.join(ROOT, "docs", "views", "isa.json")


def text_bytes(obj):
    from elftools.elf.elffile import ELFFile
    with open(obj, "rb") as fh:
        return ELFFile(fh).get_section_by_name(".text").data()


def assemble_rv(src, tmp):
    s, o = os.path.join(tmp, "rv.s"), os.path.join(tmp, "rv.o")
    open(s, "w").write(".option norelax\n" + src + "\n")
    env = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=os.path.join(tmp, "zc"), ZIG_LOCAL_CACHE_DIR=os.path.join(tmp, "zc"))
    r = subprocess.run([sys.executable, "-m", "ziglang", "cc", "-target", "riscv32-freestanding-none",
                        "-mcpu=generic_rv32+e-i", "-mabi=ilp32e", "-g0", "-c", s, "-o", o],
                       capture_output=True, text=True, env=env)
    if r.returncode:
        raise ValueError(r.stderr.strip())
    return text_bytes(o)


def assemble_x86(src, tmp):
    s, o = os.path.join(tmp, "x.s"), os.path.join(tmp, "x.o")
    open(s, "w").write(".intel_syntax noprefix\n" + src + "\n")
    r = subprocess.run(["as", "--64", "-o", o, s], capture_output=True, text=True)
    if r.returncode:
        raise ValueError(r.stderr.strip())
    return text_bytes(o)


def opcodes():
    txt = open(os.path.join(ROOT, "src", "tp_pkg.sv")).read()
    return {m.group(1): int(m.group(2), 2) for m in re.finditer(r"localparam logic \[6:0\] (OPC_\w+)\s*=\s*7'b([01]+)", txt)}


def fields(word):
    return {"opcode": word & 0x7F, "rd": (word >> 7) & 31, "funct3": (word >> 12) & 7,
            "rs1": (word >> 15) & 31, "rs2": (word >> 20) & 31, "funct7": word >> 25}


def build():
    lens = json.load(open(SRC))
    opc = opcodes()
    rows, errors = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for i, r in enumerate(lens["rows"]):
            try:
                rb = assemble_rv(r["rv"], tmp)
                xb = assemble_x86(r["x86"], tmp)
            except ValueError as e:
                errors.append(f"row {i} ({r['rv']}): {e}")
                continue
            if len(rb) != 4:
                errors.append(f"row {i} ({r['rv']}): {len(rb)} bytes, expected one 32-bit instruction")
                continue
            word = int.from_bytes(rb, "little")
            f = fields(word)
            if r["opc"] not in opc:
                errors.append(f"row {i}: {r['opc']} is not a tp_pkg opcode")
            elif f["opcode"] != opc[r["opc"]]:
                errors.append(f"row {i} ({r['rv']}): opcode {f['opcode']:07b}, but {r['opc']} is {opc[r['opc']]:07b}")
            rows.append(dict(r, rv_hex=f"{word:08x}", rv_fields=f, x86_hex=xb.hex(" "), x86_bytes=len(xb)))
    return {"about": lens["about"], "assemblers": tool_versions(), "rows": rows}, errors


def tool_versions():
    asv = subprocess.run(["as", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
    asv = re.sub(r"\s*\(.*?\)", "", asv)
    zv = subprocess.run([sys.executable, "-m", "ziglang", "version"], capture_output=True, text=True).stdout.strip()
    return {"riscv": f"zig {zv} (clang)", "x86": asv}


def dump(o):
    return json.dumps(o, indent=1, sort_keys=True) + "\n"


def main():
    data, errors = build()
    for e in errors:
        print("FAIL", e)
    if errors:
        sys.exit(1)
    text = dump(data)
    if "--check" in sys.argv:
        # the bytes and fields must match exactly; the assembler versions that
        # wrote the stored file are kept as a record, and a different version
        # that gives the same bytes is reported, not failed
        old = json.load(open(OUT)) if os.path.exists(OUT) else None
        if old is None or dump(dict(old, assemblers=None)) != dump(dict(data, assemblers=None)):
            sys.exit("views_isa --check: docs/views/isa.json is out of date")
        if old["assemblers"] != data["assemblers"]:
            print(f"views_isa --check: same bytes from {data['assemblers']} (stored file made with {old['assemblers']})")
        print(f"views_isa --check: {len(data['rows'])} rows assembled, opcodes match the decoder")
        return
    open(OUT, "w").write(text)
    print(f"docs/views/isa.json: {len(data['rows'])} rows, opcodes match tp_pkg")


if __name__ == "__main__":
    main()
