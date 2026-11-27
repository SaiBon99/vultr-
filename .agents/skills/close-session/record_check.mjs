#!/usr/bin/env node
// Record check (sk-init). Keeps the agent-first record small and true: byte budgets, links, the decisions
// Index, closure conditions on unverified items, every spec mapped. No dependencies; record_check.py is its twin.
//   node record_check.mjs [--warn]   (--warn prints problems and exits 0)
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";

const CTX = ".agents/context";
const BUDGETS = { "AGENTS.md": 6000, [`${CTX}/STATE.md`]: 8000, [`${CTX}/LEARNINGS.md`]: 12000, [`${CTX}/SPECS.md`]: 3000 };
const SPEC_BUDGET = 6000;
const READ_FIRST = 24000;
const ENTRY_LINES = 8;
const ROUTED = ["STATE.md", "DECISIONS.md", "LEARNINGS.md", "SPECS.md"];

const read = (p) => readFileSync(p, "utf8").replace(/\r\n/g, "\n");
const bytes = (p) => Buffer.byteLength(read(p));
const slash = (p) => p.replace(/\\/g, "/");
const walk = (d, keep) =>
  existsSync(d)
    ? readdirSync(d)
        .sort()
        .filter((n) => existsSync(join(d, n))) // a dangling link is skipped, as in record_check.py
        .flatMap((n) => (statSync(join(d, n)).isDirectory() ? walk(join(d, n), keep) : keep(n) ? [join(d, n)] : []))
    : [];

export function specFiles(root) {
  if (existsSync(join(root, "openspec"))) return walk(join(root, "openspec/specs"), (n) => n === "spec.md");
  return walk(join(root, CTX, "specs"), (n) => n.endsWith(".md"));
}

export function check(root) {
  const fails = [];
  const at = (r) => join(root, r);
  for (const [rel, max] of Object.entries(BUDGETS)) {
    if (existsSync(at(rel)) && bytes(at(rel)) > max) fails.push(`${rel}: ${bytes(at(rel))} bytes, budget ${max}`);
  }
  const decPath = at(`${CTX}/DECISIONS.md`);
  const dec = existsSync(decPath) ? read(decPath) : "";
  if (!dec) fails.push(`${CTX}/DECISIONS.md: missing`);
  const start = dec.indexOf("## Index");
  const stop = dec.indexOf("\n## D", start);
  const index = start < 0 ? "" : dec.slice(start, stop < 0 ? undefined : stop);
  const readFirst = ["AGENTS.md", `${CTX}/STATE.md`].filter((r) => existsSync(at(r))).reduce((s, r) => s + bytes(at(r)), Buffer.byteLength(index));
  if (readFirst > READ_FIRST) fails.push(`read-first: ${readFirst} bytes, budget ${READ_FIRST}`);
  const rows = [...index.matchAll(/^\| (D\d+) \|/gm)].map((m) => m[1]);
  const entries = [...dec.matchAll(/^## (D\d+):/gm)].map((m) => m[1]);
  for (const id of rows) if (!entries.includes(id)) fails.push(`${CTX}/DECISIONS.md: Index row ${id} has no entry`);
  for (const id of entries) if (!rows.includes(id)) fails.push(`${CTX}/DECISIONS.md: ${id} has no Index row`);
  for (const m of dec.matchAll(/superseded by (D\d+)/gi)) {
    if (!entries.includes(m[1])) fails.push(`${CTX}/DECISIONS.md: "${m[0]}" names no decision`);
  }
  for (const entry of dec.split(/\n(?=## D\d+:)/).slice(1)) {
    const n = entry.trimEnd().split("\n").length;
    if (n > ENTRY_LINES) fails.push(`${CTX}/DECISIONS.md: ${entry.split(":")[0].slice(3)} has ${n} lines, budget ${ENTRY_LINES}`);
  }
  if (existsSync(at(`${CTX}/STATE.md`))) {
    const m = read(at(`${CTX}/STATE.md`)).match(/^## [^\n]*unverified[^\n]*\n([\s\S]*?)(?=^## |(?![\s\S]))/im);
    for (const line of (m?.[1] ?? "").split("\n")) {
      if (line.startsWith("- ") && !/closed when:/i.test(line)) fails.push(`${CTX}/STATE.md: no "closed when:" in: ${line.slice(2, 60)}`);
    }
  }
  const map = existsSync(at(`${CTX}/SPECS.md`)) ? read(at(`${CTX}/SPECS.md`)) : "";
  for (const f of specFiles(root)) {
    const rel = slash(relative(root, f));
    if (bytes(f) > SPEC_BUDGET) fails.push(`${rel}: ${bytes(f)} bytes, budget ${SPEC_BUDGET}`);
    if (!map.includes(`(${slash(relative(at(CTX), f))})`)) fails.push(`${CTX}/SPECS.md: does not link ${rel}`);
  }
  // A doc that names a file in backticks goes stale silently when the file moves; history notes may name gone files.
  for (const f of [at("AGENTS.md"), at(`${CTX}/STATE.md`), at(`${CTX}/LEARNINGS.md`), ...specFiles(root)].filter(existsSync)) {
    for (const m of read(f).matchAll(/`((?:src|app|apps|packages|lib|scripts|tests?|docs|\.github|\.agents)\/[\w./-]+\.\w+)`/g)) {
      if (!existsSync(at(m[1]))) fails.push(`${slash(relative(root, f))}: names a missing file ${m[1]}`);
    }
  }
  const agents = existsSync(at("AGENTS.md")) ? read(at("AGENTS.md")) : "";
  for (const name of ROUTED) if (!agents.includes(name)) fails.push(`AGENTS.md: does not route to ${name}`);
  for (const f of [at("AGENTS.md"), ...walk(at(CTX), (n) => n.endsWith(".md"))].filter(existsSync)) {
    const text = read(f).replace(/```[\s\S]*?```/g, "").replace(/`[^`\n]*`/g, "");
    for (const m of text.matchAll(/\]\(([^)\s]+)\)/g)) {
      let target = m[1].split("#")[0];
      try {
        target = decodeURIComponent(target);
      } catch {} // a malformed escape is checked as written, as record_check.py does
      if (target && !/^[a-z]+:/i.test(target) && !existsSync(resolve(dirname(f), target))) {
        fails.push(`${slash(relative(root, f))}: broken link ${m[1]}`);
      }
    }
  }
  return { fails, readFirst };
}

if (process.argv[1] && resolve(process.argv[1]).endsWith("record_check.mjs")) {
  const { fails, readFirst } = check(process.cwd());
  for (const f of fails) console.log(`FAIL  ${f}`);
  console.log(`read-first: ${(readFirst / 1000).toFixed(1)} KB, about ${Math.round(readFirst / 4000)}k tokens (budget ${READ_FIRST / 1000} KB)`);
  console.log(fails.length ? `record check: ${fails.length} problem(s)` : "record check passed");
  process.exit(fails.length && !process.argv.includes("--warn") ? 1 : 0);
}
