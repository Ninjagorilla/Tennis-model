import test from 'node:test';
import assert from 'node:assert/strict';
import {createDashboard} from '../site/app.js';
import {blank,validate} from '../site/forecast-state.mjs';

const now=Date.parse('2026-10-17T23:00:00Z');
export function scan(at='2026-10-17T20:44:00Z'){
  const s=blank();s.generated_at=at;s.expires_at=new Date(Date.parse(at)+5400000).toISOString();s.prediction_status='available';
  for(const m of s.models){m.preflight.passed=4;m.cloud_status='verified';m.predictions=1;}
  s.matches=[{tour:'ATP',regime:'challenger',surface:'Hard',tournament:'Test Open',round:'Final',name_a:'Player Alpha',name_b:'Player Beta',starts_at:'2026-10-17T22:00:00Z',results:Object.fromEntries(s.models.map((m,i)=>[m.id,{status:'ok',p_a:i===1?.3:.6,p_b:i===1?.7:.4,artifact_sha256:'a'.repeat(64),state_date:'2026-10-05',research_only:true,explanation:{}}]))}];
  return validate(s,now);
}
class Element{
  constructor(){this.children=[];this.textContent='';this.value='';this.dataset={};this.attrs={};this.listeners={};}
  append(...c){this.children.push(...c);}replaceChildren(...c){this.children=c;}
  setAttribute(k,v){this.attrs[k]=v;}addEventListener(k,fn){this.listeners[k]=fn;}
  text(){return this.textContent+' '+this.children.map(c=>c.text()).join(' ');}
}
function harness(storage=new Map()){
  const ids=new Map(),views=['all','upcoming'].map(view=>Object.assign(new Element(),{dataset:{view}}));
  const document={getElementById:id=>{if(!ids.has(id))ids.set(id,new Element());return ids.get(id);},createElement:()=>new Element(),querySelectorAll:q=>q==='[data-view]'?views:[]};
  let current=scan(),backup=null,fail=false,delay;
  const app=createDashboard({document,now:()=>now,storage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},fetch:async path=>{if(delay)await delay;if(fail)throw Error('offline');return {ok:true,text:async()=>JSON.stringify(path.includes('last-success')?backup:current)};}});
  return {app,ids,views,storage,set current(v){current=v;},set backup(v){backup=v;},set fail(v){fail=v;},set delay(v){delay=v;},text:id=>ids.get(id)?.text()||''};
}
test('stale and started matches remain visible with named picks and age labels',async()=>{
  const h=harness();await h.app.load();assert.match(h.text('headline'),/Saved scan/);assert.match(h.text('match-list'),/Pick: Player Alpha/);assert.match(h.text('match-list'),/Pick: Player Beta/);assert.match(h.text('match-list'),/Scheduled start passed/);assert.equal(h.ids.get('match-count').textContent,1);
  await h.views[1].listeners.click();assert.match(h.text('match-list'),/No matches match these filters/);
  await h.views[0].listeners.click();assert.match(h.text('match-list'),/60.0%/);
});
test('refresh unchanged, updated, offline, malformed and regressed scans keep appropriate results',async()=>{
  const h=harness();await h.app.load();await h.app.load();assert.match(h.text('refresh-status'),/no newer scan/);
  h.current=scan('2026-10-17T22:50:00Z');await h.app.load();assert.match(h.text('refresh-status'),/latest published scan loaded/);
  h.current=scan();await h.app.load();assert.match(h.text('refresh-status'),/older scan/);
  h.fail=true;await h.app.load();assert.match(h.text('refresh-status'),/Refresh failed/);assert.match(h.text('match-list'),/Pick: Player Alpha/);
  h.fail=false;h.current={schema_version:99};await h.app.load();assert.match(h.text('refresh-status'),/Refresh failed/);assert.equal(h.ids.get('refresh').disabled,false);
});
test('failed latest scan retains last successful public results on a fresh device',async()=>{
  const h=harness();const failed=blank();failed.generated_at='2026-10-17T22:55:00Z';failed.expires_at='2026-10-18T00:25:00Z';h.current=failed;h.backup=scan();await h.app.load();assert.match(h.text('headline'),/Latest scan has no picks/);assert.match(h.text('notice-detail'),/blocked/);assert.match(h.text('match-list'),/Pick: Player Alpha/);
});
test('validated device cache survives page restart and network failure',async()=>{
  const h=harness();await h.app.load();const restart=harness(h.storage);restart.fail=true;await restart.app.load();assert.match(restart.text('match-list'),/Pick: Player Alpha/);assert.match(restart.text('refresh-status'),/keeping saved results/);
});
test('backup endpoint alone recovers results when latest endpoint is broken',async()=>{
  const h=harness();h.current={};h.backup=scan();await h.app.load();assert.match(h.text('match-list'),/Pick: Player Alpha/);
});
test('empty scan and initial network failure explain what happened',async()=>{
  const h=harness();h.current={...scan(),prediction_status:'unavailable',matches:[]};await h.app.load();assert.match(h.text('match-list'),/No verified fixtures/);
  const offline=harness();offline.fail=true;await offline.app.load();assert.match(offline.text('refresh-status'),/could not be loaded/);assert.equal(offline.ids.get('refresh').disabled,false);
});
test('rapid refresh clicks share one active load and expose loading state',async()=>{
  const h=harness();let resolve;h.delay=new Promise(r=>resolve=r);const pending=h.app.load();assert.equal(h.ids.get('refresh').disabled,true);assert.equal(h.ids.get('refresh').textContent,'Checking…');await h.app.load();resolve();await pending;assert.equal(h.ids.get('refresh').disabled,false);
});
test('corrupt cache and denied storage do not prevent online results',async()=>{
  const storage=new Map([['courtside-tennis-scans-v1','broken']]);const h=harness(storage);await h.app.load();assert.match(h.text('match-list'),/Pick: Player Alpha/);
  const denied=harness({get(){throw Error('denied');},set(){throw Error('quota');}});await denied.app.load();assert.match(denied.text('match-list'),/Pick: Player Alpha/);
});
test('successful backup cached without a latest record survives reopening offline',async()=>{
  const h=harness();h.current={};h.backup=scan();await h.app.load();const restart=harness(h.storage);restart.fail=true;await restart.app.load();assert.match(restart.text('match-list'),/Pick: Player Alpha/);
});
