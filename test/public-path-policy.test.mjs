import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {isSafeSourcePath} from '../scripts/public-path-policy.mjs';

test('new source and regression tests are approved without allowlist edits', () => {
  for (const p of ['scripts/identity.py','scripts/fixture-check.mjs','test/test_identity.py','test/new-fixture.test.mjs'])
    assert.equal(isSafeSourcePath(p), true, p);
});
test('workflow, data, binary, secret, traversal and nested files are never auto-approved', () => {
  for (const p of [
    '.github/workflows/rogue.yml','engine/champion.py','nfl/engine/new.py',
    'scripts/.env','scripts/.env.py','scripts/x.pyc','scripts/archive.zip',
    'scripts/../engine/manifest.json','scripts/nested/new.py',
    'site/attack.js','test/../scripts/secrets.py','test/test_data.csv',
    'scripts/PLAYER_HISTORY.json','README.md','scripts/secret.json'
  ]) assert.equal(isSafeSourcePath(p), false, p);
});
test('PR validation is deterministic; production inference is main-only', () => {
  const y=readFileSync(new URL('../.github/workflows/dashboard.yml',import.meta.url),'utf8');
  assert.doesNotMatch(y,/github\.head_ref/);
  assert.match(y,/name: Verify tennis models and score current matches\n        if: github.event_name != 'pull_request' && github.ref == 'refs\/heads\/main'/);
  assert.match(y,/name: Publish independent tennis results channel\n        continue-on-error: true/);
  assert.match(y,/name: Audit sanitized public files\n        run: npm run audit/);
});
