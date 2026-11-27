#!/usr/bin/env node
// Unified project check (sk-init). Runs lint, format, types and tests in parallel.
// Package-manager neutral: resolves tools from node_modules/.bin, so npm, pnpm, bun and deno all work.
// Usage: node check.mjs [--full]   (--full adds build and e2e, sequentially)
import { spawn } from 'node:child_process';
import path from 'node:path';

const FULL = process.argv.includes('--full');
const STEPS = [
  {"name": "lint", "cmd": "eslint ."},
  {"name": "format", "cmd": "prettier --check ."},
  {"name": "types", "cmd": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json"},
  {"name": "test", "cmd": "vitest run --passWithNoTests"},
  {"name": "tokens", "cmd": "pnpm run tokens:check"},
  {"name": "record", "cmd": "pnpm run record:check"}
];
const FULL_STEPS = [
  {"name": "build", "cmd": "pnpm run build"},
  {"name": "e2e", "cmd": "pnpm run test:e2e"}
];

const root = process.cwd();
const pathKey = Object.keys(process.env).find((k) => k.toLowerCase() === 'path') ?? 'PATH';
const env = {
  ...process.env,
  [pathKey]: [path.join(root, 'node_modules', '.bin'), process.env[pathKey] ?? ''].join(path.delimiter),
  FORCE_COLOR: '0',
};

const run = ({ name, cmd }) =>
  new Promise((resolve) => {
    const started = Date.now();
    const child = spawn(cmd, { cwd: root, env, shell: true });
    let out = '';
    child.stdout.on('data', (d) => (out += d));
    child.stderr.on('data', (d) => (out += d));
    child.on('close', (code) => resolve({ name, cmd, code: code ?? 1, ms: Date.now() - started, out }));
  });

if (STEPS.length === 0) {
  console.log('check: no steps configured');
  process.exit(0);
}

const results = await Promise.all(STEPS.map(run));
if (FULL) for (const step of FULL_STEPS) results.push(await run(step));

for (const r of results) {
  console.log(`${r.code === 0 ? 'PASS' : 'FAIL'}  ${r.name.padEnd(8)} ${(r.ms / 1000).toFixed(1)}s  ${r.cmd}`);
}
const failed = results.filter((r) => r.code !== 0);
for (const r of failed) {
  const tail = r.out.trim().split('\n').slice(-40).join('\n');
  console.log(`\n--- ${r.name} output (last 40 lines) ---\n${tail}`);
}
console.log(failed.length ? `\ncheck failed: ${failed.map((r) => r.name).join(', ')}` : '\ncheck passed');
process.exit(failed.length ? 1 : 0);
