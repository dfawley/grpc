#!/usr/bin/env python3
"""Check relative markdown links (files + anchors) under doc/spec.

Usage: check_links.py [subpath ...]   (paths relative to doc/spec; default all)
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # doc/spec
LINK = re.compile(r"\[(?:[^\[\]]|\[[^\]]*\])*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

def slug(h):
    h = re.sub(r"<[^>]+>", "", h.strip().lower())
    h = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", h)
    parts = re.split(r"(`[^`]*`)", h)
    for idx, part in enumerate(parts):
        if part.startswith("`") and part.endswith("`"):
            parts[idx] = part[1:-1]
        else:
            part = re.sub(r"[*~]", "", part)
            part = re.sub(r"(?<!\w)_+|_+(?!\w)", "", part)
            parts[idx] = part
    h = "".join(parts)
    h = re.sub(r"[^\w\- ]", "", h)
    return h.replace(" ", "-")

def anchors(path):
    out, seen = set(), {}
    fence = None
    for line in open(path, encoding="utf-8"):
        stripped = line.lstrip()
        fm = re.match(r"^(`{3,}|~{3,})", stripped)
        if fm:
            tok = fm.group(1)
            if fence is None:
                fence = tok
                continue
            elif tok[0] == fence[0] and len(tok) >= len(fence):
                fence = None
                continue
        if fence is not None:
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            s = slug(m.group(2))
            n = seen.get(s, 0)
            out.add(s if n == 0 else f"{s}-{n}")
            seen[s] = n + 1
        for a in re.findall(r'<a\s+(?:name|id)="([^"]+)"', line):
            out.add(a)
    return out

def files(args):
    targets = args or ["."]
    for t in targets:
        p = os.path.join(ROOT, t)
        if os.path.isfile(p):
            yield p
        else:
            for d, _, fs in os.walk(p):
                for f in fs:
                    if f.endswith(".md"):
                        yield os.path.join(d, f)

bad = 0
cache = {}
for f in sorted(files(sys.argv[1:])):
    fence = None
    in_comment = False
    for i, line in enumerate(open(f, encoding="utf-8"), 1):
        stripped = line.lstrip()
        fm = re.match(r"^(`{3,}|~{3,})", stripped)
        if fm and not in_comment:
            tok = fm.group(1)
            if fence is None:
                fence = tok
                continue
            elif tok[0] == fence[0] and len(tok) >= len(fence):
                fence = None
                continue
        if fence is not None:
            continue
        scan_line = line
        if in_comment:
            if "-->" in scan_line:
                scan_line = scan_line.split("-->", 1)[1]
                in_comment = False
            else:
                continue
        while "<!--" in scan_line:
            before, after = scan_line.split("<!--", 1)
            if "-->" in after:
                scan_line = before + after.split("-->", 1)[1]
            else:
                scan_line = before
                in_comment = True
                break
        for url in LINK.findall(scan_line):
            if re.match(r"^[a-z]+:", url):
                continue
            path, _, frag = url.partition("#")
            tgt = os.path.normpath(os.path.join(os.path.dirname(f), path)) if path else f
            rel = os.path.relpath(f, ROOT)
            tgt_md = os.path.join(tgt, "README.md") if os.path.isdir(tgt) else tgt
            if not os.path.isfile(tgt_md):
                print(f"{rel}:{i}: missing file: {url}"); bad += 1; continue
            if frag and tgt_md.endswith(".md"):
                if tgt_md not in cache:
                    cache[tgt_md] = anchors(tgt_md)
                if frag not in cache[tgt_md]:
                    print(f"{rel}:{i}: missing anchor: {url}"); bad += 1
print(f"{bad} problems", file=sys.stderr)
sys.exit(1 if bad else 0)
