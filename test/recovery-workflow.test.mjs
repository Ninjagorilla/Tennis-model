import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const workflow=readFileSync(new URL('../.github/workflows/dashboard.yml',import.meta.url),'utf8');
test('main pipeline invokes bounded controller, not ad-hoc scan',()=>{
  assert.match(workflow,/run: python scripts\/recovery_controller\.py/);
  assert.match(workflow,/work\/recovery-report\.json/);
  assert.match(workflow,/name: Retain sanitized tennis diagnostic report\n        if: always\(\)/);
});
test('alerts after failed main build, degraded evidence or failed settlement, with scoped issue permission',()=>{
  assert.match(workflow,/alert:\n    if: always\(\) && github\.event_name != 'pull_request' && github\.ref == 'refs\/heads\/main' && \(needs\.build\.result == 'failure' \|\| needs\.build\.outputs\.evidence_alert == 'true' \|\| needs\.build\.outputs\.settlement_alert == 'true'\)/);
  assert.match(workflow,/id: evidence_status/);
  assert.match(workflow,/id: settlement_status/);
  assert.match(workflow,/id: evidence_repair/);
  assert.match(workflow,/id: evidence_artifact/);
  assert.match(workflow,/permissions:\n      issues: write\n      contents: read/);
  assert.match(workflow,/gh issue create/);
  assert.match(workflow,/gh issue comment/);
});
test('preserves immutable model rollback check',()=>{
  assert.match(workflow,/python scripts\/verify_rollback\.py --target 69d997c4c6a1f8765f05014fdb6a898d8701bd91/);
  assert.doesNotMatch(workflow,/git reset --hard|git push --force/);
});
