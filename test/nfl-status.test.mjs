import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {validateNFL} from '../scripts/nfl-status.mjs';
const good=()=>{const s=JSON.parse(readFileSync('nfl/evidence/public_preview.json'));s.generated_at=new Date().toISOString();s.expires_at=new Date(Date.parse(s.generated_at)+5400000).toISOString();return s;};
test('NFL gated record is valid',()=>assert.equal(validateNFL(good()).publication_approved,false));
test('NFL probabilities cannot leak through a gated record',()=>{const s=good();s.games=[{p:.9}];assert.throws(()=>validateNFL(s));});
test('NFL gate cannot be turned off implicitly',()=>{const s=good();s.publication_approved=true;assert.throws(()=>validateNFL(s));});
test('NFL future clock rejected',()=>{const s=good();s.generated_at='2099-01-01T00:00:00Z';assert.throws(()=>validateNFL(s));});
test('NFL duplicate fixtures rejected',()=>{const s=good();const g={event_id:'2026_06_NYJ_BUF',home:'BUF',away:'NYJ',starts_at:'2026-10-18T17:00:00Z'};s.fixtures=[g,g];assert.throws(()=>validateNFL(s));});
test('NFL unknown model cannot replace original',()=>{const s=good();s.engine_version='invented';assert.throws(()=>validateNFL(s));});
test('NFL unreviewed promotion fails closed',()=>{const s=good();s.validation.promotion_approved=true;assert.throws(()=>validateNFL(s));});
