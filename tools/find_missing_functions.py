#!/usr/bin/env python3
"""Find likely function entry points that codegen missed.

Scans the data sections of a dumped game image for 32-bit big-endian values
that point into the code section but are not known function starts, then
sorts them by how likely they are to be real functions.

Inputs:
  - an image dump made by SyndicateApp::OnPostLoadXexImage
    (run the game once with DUMP_IMAGE=<path>, then close it)
  - generated/default/ from the last codegen (known function starts, and
    loc_ labels = branch targets inside functions)
  - overrides.toml (addresses already declared)

Usage:
  python3 tools/find_missing_functions.py out/image_82000000.bin
"""

import argparse
import bisect
import json
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

IMAGE_BASE = 0x82000000

# PowerPC instruction words we recognise.
BLR = 0x4E800020          # return
BCTR = 0x4E800420         # jump through count register (tail call / switch)
MFLR_R12 = 0x7D8802A6     # typical first instruction of a non-leaf function
NOP = 0x60000000



def is_uncond_branch(w):  # b target (no link, relative)
    return (w >> 26) == 18 and (w & 3) == 0


def is_terminator(w):
    return w in (BLR, BCTR) or is_uncond_branch(w)


def is_import_thunk(words):
    """Xbox 360 import thunk (kernel call stub), on-disc or as patched by the loader."""
    if len(words) < 4:
        return False
    a, b, c, d = words[:4]
    if c != 0x7D6903A6 or d != BCTR:
        return False
    on_disc = (a & 0xFFFF0000) == 0x3D600000 and (b & 0xFFFF0000) == 0x816B0000
    # After loading, the first two words hold import records: 0x01LLOOOO / 0x02LLOOOO
    # (LL = library index, OOOO = ordinal).
    loaded = (a >> 24) == 0x01 and (b >> 24) == 0x02 and (a & 0xFFFFFF) == (b & 0xFFFFFF)
    return on_disc or loaded


def parse_sections(img):
    """Return [(name, start_va, end_va, is_code)] from the PE header at the image base."""
    if img[:2] != b"MZ":
        return None
    e_lfanew = struct.unpack_from("<I", img, 0x3C)[0]
    if img[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        return None
    coff = e_lfanew + 4
    num_sections = struct.unpack_from("<H", img, coff + 2)[0]
    opt_size = struct.unpack_from("<H", img, coff + 16)[0]
    sec = coff + 20 + opt_size
    out = []
    for i in range(num_sections):
        h = sec + i * 40
        name = img[h:h + 8].rstrip(b"\0").decode("latin1")
        vsize, vaddr = struct.unpack_from("<II", img, h + 8)
        chars = struct.unpack_from("<I", img, h + 36)[0]
        is_code = bool(chars & 0x20000000)  # IMAGE_SCN_MEM_EXECUTE
        out.append((name, IMAGE_BASE + vaddr, IMAGE_BASE + vaddr + vsize, is_code))
    return out


def load_known_starts(gen_dir, name):
    init = gen_dir / f"{name}_init.cpp"
    if init.exists():
        txt = init.read_text(errors="replace")
        return {int(m, 16) for m in re.findall(r"\{\s*0x([0-9A-Fa-f]{8}),\s*sub_", txt)}
    part = gen_dir / "codegen.partition.json"
    return {int(k, 16) for k in json.loads(part.read_text())["assignments"]}


def load_internal_labels(gen_dir, name):
    """loc_XXXXXXXX labels = branch targets inside a function body."""
    labels = set()
    rx = re.compile(r"^loc_([0-9A-F]{8}):", re.M)
    for f in sorted(gen_dir.glob(f"{name}_recomp.*.cpp")):
        labels.update(int(m, 16) for m in rx.findall(f.read_text(errors="replace")))
    return labels


def load_overrides(path):
    if not path.exists():
        return set()
    return {int(m, 16) for m in re.findall(r"^\s*0x([0-9A-Fa-f]{8})\s*=", path.read_text(), re.M)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path)
    ap.add_argument("--generated", type=Path, default=Path("generated/default"))
    ap.add_argument("--overrides", type=Path, default=Path("overrides.toml"))
    ap.add_argument("--out", type=Path, default=Path("out/missing_functions"))
    ap.add_argument("--name", default="syndicate", help="project name (prefix of generated files)")
    ap.add_argument("--seh-tables", type=lambda v: int(v, 16), nargs=2, metavar=("START", "END"),
                    help="hex range of .rdata holding SEH scope tables, excluded from the scan")
    ap.add_argument("--code-range", type=lambda v: int(v, 16), nargs=2, metavar=("START", "END"),
                    help="hex code range, used only if the dump has no readable PE header")
    args = ap.parse_args()

    img = args.image.read_bytes()
    word = lambda va: struct.unpack_from(">I", img, va - IMAGE_BASE)[0]

    sections = parse_sections(img)
    if not sections:
        if not args.code_range:
            sys.exit("No readable PE header in the dump; pass --code-range START END")
        cs, ce = args.code_range
        print(f"No readable PE header; using code={cs:08X}-{ce:08X}")
        end = IMAGE_BASE + len(img)
        sections = [("pre", IMAGE_BASE, cs, False), ("code", cs, ce, True), ("post", ce, end, False)]
    code = [(s, e) for _, s, e, x in sections if x]
    # .reloc holds relocation records (offsets), not pointers: matches there are coincidences.
    data = [(n, s, e) for n, s, e, x in sections if not x and n != ".reloc"]
    # SEH scope tables (records of count, try_begin, try_end, handler, continuation)
    # point at labels INSIDE functions; exclude them when their range is known.
    if args.seh_tables:
        lo, hi = args.seh_tables
        cut = []
        for n, s, e in data:
            if s < hi and lo < e:
                if s < lo: cut.append((n, s, lo))
                if hi < e: cut.append((n, hi, e))
            else:
                cut.append((n, s, e))
        data = cut
    print("Sections:")
    for n, s, e, x in sections:
        print(f"  {n:10s} {s:08X}-{e:08X} {'code' if x else 'data'}")
    in_code = lambda va: any(s <= va < e for s, e in code)

    known = load_known_starts(args.generated, args.name) | load_overrides(args.overrides)
    labels = load_internal_labels(args.generated, args.name)
    print(f"Known function starts: {len(known)}; internal labels: {len(labels)}"
          + ("" if labels else "  (no generated .cpp found: label check disabled)"))
    starts_sorted = sorted(known)

    # 1. Collect every aligned code pointer stored in a data section.
    refs = defaultdict(list)  # target -> [(section, address of the pointer)]
    for name, s, e in data:
        e = min(e, IMAGE_BASE + len(img))
        for va in range(s, e - 3, 4):
            v = word(va)
            if v & 3 == 0 and in_code(v) and v not in known:
                refs[v].append((name, va))

    # 1b. Addresses built by code: lis rD,HI followed (within a few instructions)
    #     by addi rX,rD,LO. That is how PowerPC loads a 32-bit constant such as
    #     a function pointer that is not stored anywhere in data.
    for s, e in code:
        e = min(e, IMAGE_BASE + len(img))
        for va in range(s, e - 3, 4):
            w = word(va)
            if (w >> 26) != 15 or (w >> 16) & 31 != 0:  # lis = addis rD,0,HI
                continue
            rd, hi = (w >> 21) & 31, w & 0xFFFF
            for k in range(1, 9):
                if va + 4 * k >= e:
                    break
                w2 = word(va + 4 * k)
                if (w2 >> 26) == 14 and (w2 >> 16) & 31 == rd:  # addi rX,rD,LO
                    lo = w2 & 0xFFFF
                    v = ((hi << 16) + (lo - 0x10000 if lo & 0x8000 else lo)) & 0xFFFFFFFF
                    if v & 3 == 0 and in_code(v) and v not in known:
                        refs[v].append(("code", va))
                    break
                if (w2 >> 21) & 31 == rd and (w2 >> 26) not in (36, 37, 38, 44, 45, 47, 54, 55):
                    break  # rD overwritten by something other than a store

    def in_vtable_run(va):
        """True if a neighbouring word is also a pointer to a known function start."""
        return any(word(va + d) in known for d in (-4, 4) if IMAGE_BASE <= va + d < IMAGE_BASE + len(img) - 4)

    # 2. Classify.
    rows = {"strong": [], "review": [], "rejected": []}
    for t, rs in sorted(refs.items()):
        i = bisect.bisect_left(starts_sorted, t)
        prev_start = starts_sorted[i - 1] if i else None
        prev = word(t - 4)
        first = [word(t + 4 * k) for k in range(4)]
        reasons = []
        if t in labels:
            cat, reasons = "rejected", ["branch target inside a known function (jump table/EH)"]
        elif is_import_thunk(first):
            cat, reasons = "rejected", ["import thunk"]
        else:
            after_end = is_terminator(prev) or prev in (0, NOP)
            vt = any(in_vtable_run(va) for _, va in rs)
            if after_end:
                reasons.append("previous instruction ends code (blr/bctr/b/padding)")
            if first[0] == MFLR_R12:
                reasons.append("starts with mflr r12 (prologue)")
            if vt:
                reasons.append("stored next to known function pointers (vtable-like)")
            in_pdata = any(sec == ".pdata" for sec, _ in rs)
            if in_pdata:
                reasons.append(".pdata (unwind table) lists a function starting here")
            # Built by code only from inside the preceding function: likely a computed
            # jump within that function (switch via bctr), not a separate function.
            self_ref = prev_start is not None and all(
                sec == "code" and prev_start <= va < t for sec, va in rs)
            if self_ref:
                reasons.append("only referenced from inside the preceding function (computed jump?)")
            cat = "strong" if (after_end or in_pdata) and not self_ref else "review"
        rows[cat].append((t, prev_start, len(rs), rs[0], reasons))

    # 3. Report.
    args.out.mkdir(parents=True, exist_ok=True)
    for cat, items in rows.items():
        with open(args.out / f"{cat}.txt", "w") as f:
            for t, ps, n, (sec, va), reasons in items:
                pstr = f"sub_{ps:08X}+0x{t - ps:X}" if ps else "-"
                f.write(f"0x{t:08X}  after {pstr:24s} refs={n:<3d} first={sec}@0x{va:08X}  {'; '.join(reasons)}\n")
    with open(args.out / "strong_overrides.toml", "w") as f:
        f.write("# Candidates from tools/find_missing_functions.py (category: strong)\n")
        for t, _, n, (sec, va), _ in rows["strong"]:
            f.write(f"0x{t:08X} = {{}}  # data ptr in {sec} @0x{va:08X}, refs={n}\n")

    print(f"\nCandidate targets: {len(refs)}")
    for cat in rows:
        print(f"  {cat:9s} {len(rows[cat]):6d}  -> {args.out / (cat + '.txt')}")
    print(f"TOML for strong candidates -> {args.out / 'strong_overrides.toml'}")


if __name__ == "__main__":
    main()
