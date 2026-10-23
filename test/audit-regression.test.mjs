import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, writeFileSync, copyFileSync, rmSync, readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFileSync, spawnSync} from 'node:child_process';

function fixture(t) {
  const dir = mkdtempSync(join(tmpdir(), 'tennis-audit-'));
  t.after(() => rmSync(dir, {recursive: true, force: true}));
  for (const p of ['scripts', 'engine', 'nfl', '.github/workflows']) mkdirSync(join(dir, p), {recursive: true});
  for (const p of ['audit.mjs', 'public-path-policy.mjs']) copyFileSync(new URL('../scripts/' + p, import.meta.url), join(dir, 'scripts', p));
  for (const p of ['engine', 'nfl']) writeFileSync(join(dir, p, 'manifest.json'), '{"files":{}}');
  execFileSync('git', ['init', '-q', dir]);
  return {
    put(path, content) { writeFileSync(join(dir, path), content); },
    audit() {
      execFileSync('git', ['add', '.'], {cwd: dir});
      return spawnSync(process.execPath, ['scripts/audit.mjs'], {cwd: dir, encoding: 'utf8'});
    }
  };
}

test('reviewed independent workflow passes the actual public audit', t => {
  const f = fixture(t);
  f.put('.github/workflows/tennis-independent.yml', 'name: Reviewed recovery\n');
  const r = f.audit();
  assert.equal(r.status, 0, r.stderr);
});

test('unreviewed workflows still fail closed', t => {
  const f = fixture(t);
  f.put('.github/workflows/unreviewed.yml', 'name: Unreviewed\n');
  const r = f.audit();
  assert.equal(r.status, 1);
  assert.match(r.stderr, /Unreviewed public files/);
});

test('allowlisted workflows still receive content inspection', t => {
  const f = fixture(t);
  f.put('.github/workflows/tennis-independent.yml', ['ghp', '_', 'x'.repeat(36)].join(''));
  const r = f.audit();
  assert.equal(r.status, 1);
  assert.match(r.stderr, /Potential private content/);
});

test('npm tests and direct builds retain independent audit gates', () => {
  const pkg = JSON.parse(readFileSync(new URL('../package.json', import.meta.url)));
  assert.equal(pkg.scripts.pretest, 'node scripts/audit.mjs');
  const build = readFileSync(new URL('../scripts/build.mjs', import.meta.url), 'utf8');
  assert.match(build, /import '\.\/audit\.mjs';/);
});
