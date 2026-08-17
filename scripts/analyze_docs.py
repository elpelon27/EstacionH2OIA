#!/usr/bin/env python3
import glob
import os

fs = [
    f
    for f in glob.glob("docs/*/*.md") + glob.glob("docs/*.md")
    if not f.startswith("docs/obsidian")
]
fs = sorted(set(fs))
print("canonical .md:", len(fs))
tot = sum(len(open(f, encoding="utf-8", errors="ignore").read()) for f in fs)
print("total chars:", tot)
print("chunks a 12000:", -(-tot // 12000))
big = [(len(open(f, encoding="utf-8", errors="ignore").read()), f) for f in fs]
big.sort(reverse=True)
print("top-3:", [(s, os.path.basename(f)) for s, f in big[:3]])
print(
    "distribucion:",
    {
        ">12k": sum(1 for s, _ in big if s > 12000),
        "4k-12k": sum(1 for s, _ in big if 4000 <= s <= 12000),
        "<4k": sum(1 for s, _ in big if s < 4000),
    },
)
