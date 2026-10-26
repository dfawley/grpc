#!/usr/bin/env python3
"""Check relative markdown links (files + anchors) under doc/spec.

Usage: check_links.py [subpath ...]   (paths relative to doc/spec; default all)
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # doc/spec
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

def slug(h):
    h = re.sub(r"<[^>]+>", "", h.strip().lower())
    h = re.sub(r"[`*_~]", "", h) if False else h.replace("`", "")
    h = re.sub(r"[^\w\- ]", "", h)
    return h.replace(" ", "-")

def anchors(path):
    out, seen = set(), {}
    in_code = False
    for line in open(path, encoding="utf-8"):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
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
    in_code = False
    for i, line in enumerate(open(f, encoding="utf-8"), 1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
        if in_code:
            continue
        for url in LINK.findall(line):
            if re.match(r"^[a-z]+:", url):
                continue
            path, _, frag = url.partition("#")
            tgt = os.path.normpath(os.path.join(os.path.dirname(f), path)) if path else f
            rel = os.path.relpath(f, ROOT)
            if not os.path.exists(tgt):
                print(f"{rel}:{i}: missing file: {url}"); bad += 1; continue
            if frag and tgt.endswith(".md"):
                if tgt not in cache:
                    cache[tgt] = anchors(tgt)
                if frag not in cache[tgt]:
                    print(f"{rel}:{i}: missing anchor: {url}"); bad += 1
print(f"{bad} problems", file=sys.stderr)
