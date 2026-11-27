#!/usr/bin/env python3
"""Record check (sk-init). Keeps the agent-first record small and true: byte budgets, links, the decisions
Index, closure conditions on unverified items, every spec mapped. Standard library only; record_check.mjs is its twin.

    python record_check.py [--warn]   (--warn prints problems and exits 0)
"""

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

CTX = '.agents/context'
BUDGETS = {'AGENTS.md': 6000, f'{CTX}/STATE.md': 8000, f'{CTX}/LEARNINGS.md': 12000, f'{CTX}/SPECS.md': 3000}
SPEC_BUDGET = 6000
READ_FIRST = 24000
ENTRY_LINES = 8
ROUTED = ['STATE.md', 'DECISIONS.md', 'LEARNINGS.md', 'SPECS.md']


def read(p: Path) -> str:
    return p.read_text(encoding='utf-8').replace('\r\n', '\n')


def size(p: Path) -> int:
    return len(read(p).encode('utf-8'))


def rel(p: Path, base: Path) -> str:
    return os.path.relpath(p, base).replace('\\', '/')


def walk(d: Path, keep) -> list:
    if not d.is_dir():
        return []
    out = []
    for n in sorted(os.listdir(d)):
        p = d / n
        if not p.exists():  # a dangling link is skipped, as in record_check.mjs
            continue
        out += walk(p, keep) if p.is_dir() else ([p] if keep(n) else [])
    return out


def spec_files(root: Path) -> list:
    if (root / 'openspec').exists():
        return walk(root / 'openspec' / 'specs', lambda n: n == 'spec.md')
    return walk(root / CTX / 'specs', lambda n: n.endswith('.md'))


def check(root: Path):
    root = Path(root)
    fails = []
    for r, mx in BUDGETS.items():
        if (root / r).exists() and size(root / r) > mx:
            fails.append(f'{r}: {size(root / r)} bytes, budget {mx}')
    dec_path = root / CTX / 'DECISIONS.md'
    dec = read(dec_path) if dec_path.exists() else ''
    if not dec:
        fails.append(f'{CTX}/DECISIONS.md: missing')
    start = dec.find('## Index')
    stop = dec.find('\n## D', start)
    index = '' if start < 0 else dec[start:stop if stop >= 0 else None]
    read_first = len(index.encode('utf-8')) + sum(size(root / r) for r in ('AGENTS.md', f'{CTX}/STATE.md') if (root / r).exists())
    if read_first > READ_FIRST:
        fails.append(f'read-first: {read_first} bytes, budget {READ_FIRST}')
    rows = re.findall(r'^\| (D\d+) \|', index, re.M)
    entries = re.findall(r'^## (D\d+):', dec, re.M)
    fails += [f'{CTX}/DECISIONS.md: Index row {i} has no entry' for i in rows if i not in entries]
    fails += [f'{CTX}/DECISIONS.md: {i} has no Index row' for i in entries if i not in rows]
    for m in re.finditer(r'superseded by (D\d+)', dec, re.I):
        if m.group(1) not in entries:
            fails.append(f'{CTX}/DECISIONS.md: "{m.group(0)}" names no decision')
    for entry in re.split(r'\n(?=## D\d+:)', dec)[1:]:
        n = len(entry.rstrip().split('\n'))
        if n > ENTRY_LINES:
            fails.append(f'{CTX}/DECISIONS.md: {entry.split(":")[0][3:]} has {n} lines, budget {ENTRY_LINES}')
    state = root / CTX / 'STATE.md'
    if state.exists():
        m = re.search(r'^## [^\n]*unverified[^\n]*\n([\s\S]*?)(?=^## |\Z)', read(state), re.I | re.M)
        for line in (m.group(1) if m else '').split('\n'):
            if line.startswith('- ') and not re.search('closed when:', line, re.I):
                fails.append(f'{CTX}/STATE.md: no "closed when:" in: {line[2:60]}')
    smap = root / CTX / 'SPECS.md'
    spec_map = read(smap) if smap.exists() else ''
    for f in spec_files(root):
        if size(f) > SPEC_BUDGET:
            fails.append(f'{rel(f, root)}: {size(f)} bytes, budget {SPEC_BUDGET}')
        if f'({rel(f, root / CTX)})' not in spec_map:
            fails.append(f'{CTX}/SPECS.md: does not link {rel(f, root)}')
    # A doc that names a file in backticks goes stale silently when the file moves; history notes may name gone files.
    for f in [p for p in [root / 'AGENTS.md', root / CTX / 'STATE.md', root / CTX / 'LEARNINGS.md', *spec_files(root)] if p.exists()]:
        for m in re.finditer(r'`((?:src|app|apps|packages|lib|scripts|tests?|docs|\.github|\.agents)/[\w./-]+\.\w+)`', read(f)):
            if not (root / m.group(1)).exists():
                fails.append(f'{rel(f, root)}: names a missing file {m.group(1)}')
    agents = read(root / 'AGENTS.md') if (root / 'AGENTS.md').exists() else ''
    fails += [f'AGENTS.md: does not route to {n}' for n in ROUTED if n not in agents]
    for f in [p for p in [root / 'AGENTS.md', *walk(root / CTX, lambda n: n.endswith('.md'))] if p.exists()]:
        text = re.sub(r'`[^`\n]*`', '', re.sub(r'```[\s\S]*?```', '', read(f)))
        for m in re.finditer(r'\]\(([^)\s]+)\)', text):
            target = unquote(m.group(1).split('#')[0])
            if target and not re.match(r'^[a-z]+:', target, re.I) and not (f.parent / target).exists():
                fails.append(f'{rel(f, root)}: broken link {m.group(1)}')
    return fails, read_first


if __name__ == '__main__':
    problems, total = check(Path.cwd())
    for p in problems:
        print(f'FAIL  {p}')
    print(f'read-first: {total / 1000:.1f} KB, about {round(total / 4000)}k tokens (budget {READ_FIRST // 1000} KB)')
    print(f'record check: {len(problems)} problem(s)' if problems else 'record check passed')
    sys.exit(1 if problems and '--warn' not in sys.argv else 0)
