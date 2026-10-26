#!/usr/bin/env python3
"""Check GFM tables: header/delimiter column counts must match; body rows with
more cells than the header lose content (often an unescaped | in a cell)."""
import os, re, glob, sys
def cells(line):
    s = line.strip()
    if s.startswith("|"): s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"): s = s[:-1]
    return re.split(r"(?<!\\)\|", s)   # GFM splits on unescaped pipes, even inside code spans
delim = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
probs = []
for f in sorted(glob.glob(root + "/**/*.md", recursive=True)) + [os.path.join(os.path.dirname(os.path.abspath(root)), "spec-optionality-notes.md")]:
    L = open(f).read().split("\n"); incode = False; i = 0
    while i < len(L):
        if L[i].lstrip().startswith("```"): incode = not incode
        if not incode and i + 1 < len(L) and "|" in L[i] and delim.match(L[i+1]) and "-" in L[i+1]:
            h, d = len(cells(L[i])), len(cells(L[i+1]))
            if h != d: probs.append(f"{f}:{i+1}: header has {h} columns, delimiter has {d}")
            j = i + 2
            while j < len(L) and L[j].strip().startswith("|"):
                n = len(cells(L[j]))
                if n > h: probs.append(f"{f}:{j+1}: row has {n} cells, header {h}: {L[j][:90]}")
                j += 1
            i = j; continue
        i += 1
print("\n".join(probs)); print(len(probs), "problems")
