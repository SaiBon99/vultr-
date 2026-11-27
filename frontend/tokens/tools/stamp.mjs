// Token staleness guard. `node tokens/tools/stamp.mjs` records a hash of every token source and the build config;
// `--check` fails when the sources changed after the last build. Generated CSS is never hand-edited.
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, readdirSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';

const STAMP = 'src/styles/.tokens-hash';
const CONFIGS = ["terrazzo.config.mjs"];

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? walk(join(dir, e.name)) : e.name.endsWith('.json') ? [join(dir, e.name)] : []);
}
const files = [...walk('tokens'), ...CONFIGS.filter(existsSync)].sort();
const text = (f) => readFileSync(f, 'utf8').replace(/\r\n/g, '\n');
const hash = createHash('sha256').update(files.map((f) => f.replace(/\\/g, '/') + '\0' + text(f)).join('\0')).digest('hex');

if (process.argv.includes('--check')) {
  const stored = existsSync(STAMP) ? readFileSync(STAMP, 'utf8').trim() : '';
  if (stored !== hash) {
    console.error('tokens: sources changed since the last build (or the build never ran). Run the tokens:build script.');
    process.exit(1);
  }
  console.log('tokens: generated CSS matches the sources');
} else {
  mkdirSync(dirname(STAMP), { recursive: true });
  writeFileSync(STAMP, hash + '\n');
  console.log('tokens: stamped ' + hash.slice(0, 12));
}
