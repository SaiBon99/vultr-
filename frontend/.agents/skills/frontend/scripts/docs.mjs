#!/usr/bin/env node
// Context docs guard (sk-init). Package-manager neutral, no dependencies.
//   node docs.mjs check   verifies budgets, links, router completeness and generated blocks
//   node docs.mjs regen   rewrites the Tokens block in .agents/context/UI.md from tokens/
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

const BUDGET = {
  'AGENTS.md': 40,
  'DESIGN.md': 60,
  'tokens/README.md': 20,
  '.agents/context/ARCHITECTURE.md': 80,
  '.agents/context/UI.md': 90,
  '.agents/context/STACK.md': 80,
};
const OPTIONAL_BUDGET = { '.agents/context/SOUND.md': 40 };
// STATE, DECISIONS, LEARNINGS and the specs belong to the record check (close-session/record_check.mjs).
const RECORD = ['STATE.md', 'DECISIONS.md', 'LEARNINGS.md', 'SPECS.md'];
const UI = '.agents/context/UI.md';
const START = '<!-- tokens:start -->';
const END = '<!-- tokens:end -->';
const read = (p) => readFileSync(p, 'utf8').replace(/\r\n/g, '\n');
const json = (p) => JSON.parse(read(p));
const sha = (t) => createHash('sha256').update(t).digest('hex');

function flat(node, path = [], type = null, out = {}) {
  const t = node.$type ?? type;
  for (const [k, v] of Object.entries(node)) {
    if (k.startsWith('$') || !v || typeof v !== 'object') continue;
    if ('$value' in v) out[[...path, k].join('.')] = { ...v, $type: v.$type ?? t };
    else flat(v, [...path, k], t, out);
  }
  return out;
}
const dir = (d) => (existsSync(d) ? readdirSync(d).filter((f) => f.endsWith('.tokens.json')).sort().map((f) => join(d, f)) : []);
const merge = (files) => Object.assign({}, ...files.map((f) => flat(json(f))));

function show(v, all) {
  if (typeof v === 'string' && v.startsWith('{')) return show(all[v.slice(1, -1)]?.$value ?? '?', all);
  if (Array.isArray(v)) return typeof v[0] === 'string' ? v[0] : `cubic-bezier(${v.join(', ')})`;
  if (v && typeof v === 'object') {
    if ('hex' in v) return v.hex;
    if ('components' in v) return `oklch(${v.components.join(' ')})`;
    if ('value' in v) return `${v.value}${v.unit}`;
  }
  return String(v);
}

function tokenBlock() {
  const prim = merge(dir('tokens/primitive'));
  const sem = merge([...dir('tokens/semantic'), ...dir('tokens/component')]);
  const light = merge(['tokens/themes/light.tokens.json']);
  const dark = merge(['tokens/themes/dark.tokens.json']);
  const all = { ...prim, ...sem, ...light };
  const tailwind = existsSync('.agents/context/stack.json') && json('.agents/context/stack.json').styling === 'tailwind';
  const use = tailwind ? 'Tailwind utilities (`bg-primary`, `text-muted-foreground`, `rounded-md`, `font-title`, `p-md`, `h-control`)' : 'CSS variables (`var(--color-primary)`, `var(--radius-md)`, `var(--font-title)`)';
  const rows = Object.keys(light).map((k) => {
    const name = k.replace(/^color\./, '');
    const d = dark[k] ? show(dark[k].$value, { ...prim, ...dark }) : '';
    return `| ${name} | ${show(light[k].$value, all)} | ${d} | ${light[k].$description ?? ''} |`;
  });
  const names = (g) => Object.keys(sem).filter((k) => k.startsWith(g + '.')).map((k) => k.slice(g.length + 1));
  const vals = (g) => Object.keys(sem).filter((k) => k.startsWith(g + '.')).map((k) => `${k.slice(g.length + 1)}=${show(sem[k].$value, all)}`);
  const lines = [
    START,
    `Use ${use}. Primitives (\`primitive.*\`) are for tokens/ only.`,
    '',
    '| Colour token | Light | Dark | Use |',
    '| :--- | :--- | :--- | :--- |',
    ...rows,
    '',
    `- spacing: ${vals('spacing').join(', ')}`,
    `- radius: ${vals('radius').join(', ')}`,
    `- font: ${names('font').join(', ')}`,
    `- ease: ${names('ease').join(', ')}; motion duration: ${vals('motion.duration').join(', ')}`,
    END,
  ];
  return lines.join('\n');
}

function currentBlock(text) {
  const a = text.indexOf(START);
  const b = text.indexOf(END);
  return a >= 0 && b > a ? [a, b + END.length] : null;
}

function regen() {
  const text = read(UI);
  const span = currentBlock(text);
  if (!span) throw new Error(`${UI} has no ${START} ... ${END} block`);
  writeFileSync(UI, text.slice(0, span[0]) + tokenBlock() + text.slice(span[1]));
  console.log(`docs: rewrote the tokens block in ${UI}`);
}

function check() {
  const fails = [];
  for (const [f, max] of Object.entries(BUDGET)) {
    if (!existsSync(f)) {
      fails.push(`${f}: missing`);
      continue;
    }
    const n = read(f).trimEnd().split('\n').length;
    if (n > max) fails.push(`${f}: ${n} lines, budget ${max}`);
  }
  for (const [f, max] of Object.entries(OPTIONAL_BUDGET)) {
    if (existsSync(f) && read(f).trimEnd().split('\n').length > max) fails.push(`${f}: more than ${max} lines`);
  }
  for (const f of Object.keys(BUDGET).filter(existsSync)) {
    for (const m of read(f).matchAll(/\[[^\]]*\]\(([^)\s]+)\)/g)) {
      const target = m[1].split('#')[0];
      if (!target || /^[a-z]+:/.test(target)) continue;
      if (!existsSync(join(dirname(f), target))) fails.push(`${f}: broken link ${m[1]}`);
    }
  }
  if (existsSync('AGENTS.md') && existsSync('.agents/context')) {
    const agents = read('AGENTS.md');
    for (const f of readdirSync('.agents/context').filter((x) => x.endsWith('.md') && !RECORD.includes(x))) {
      if (!agents.includes(f)) fails.push(`AGENTS.md: router does not mention .agents/context/${f}`);
    }
  }
  if (existsSync(UI)) {
    const text = read(UI);
    const span = currentBlock(text);
    if (!span) fails.push(`${UI}: tokens block markers missing`);
    else if (text.slice(span[0], span[1]) !== tokenBlock()) fails.push(`${UI}: tokens block is stale (run the docs:regen script)`);
  }
  const stackJson = '.agents/context/stack.json';
  const stackMd = '.agents/context/STACK.md';
  if (existsSync(stackJson) && existsSync(stackMd)) {
    const stamp = read(stackMd).split('\n')[0];
    if (!stamp.includes(sha(read(stackJson)))) fails.push(`${stackMd}: generated from an older stack.json (edit stack.json, then regenerate STACK.md)`);
  }
  for (const f of fails) console.log(`FAIL  ${f}`);
  console.log(fails.length ? `docs check failed: ${fails.length} problem(s)` : 'docs check passed');
  process.exit(fails.length ? 1 : 0);
}

const cmd = process.argv[2];
if (cmd === 'regen') regen();
else if (cmd === 'check') check();
else {
  console.log('usage: node docs.mjs check | regen');
  process.exit(2);
}
