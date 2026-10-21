import {execFileSync} from 'node:child_process';
import {readFile,lstat} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {isSafeSourcePath} from './public-path-policy.mjs';
const manifest=JSON.parse(await readFile('engine/manifest.json','utf8'));
const allowed=new Set(['.gitignore','MATCHUP_V2.md','.github/workflows/dashboard.yml','README.md','RELIABILITY.md','SECURITY.md','ATTRIBUTION.md','package.json','requirements.txt','scripts/audit.mjs','scripts/build.mjs','scripts/status.mjs','scripts/runtime.py','scripts/model_worker.py','scripts/inference.py','scripts/collect.py','scripts/scan.py','test/status.test.mjs','test/test_scan.py','site/index.html','site/style.css','site/app.js','engine/manifest.json',...Object.keys(manifest.files).map(n=>'engine/'+n)]);
for(const p of ['.github/workflows/tennis-independent.yml','.gitattributes','scripts/tenniscom.py','scripts/explanations.py','scripts/quality.py','scripts/verify_scan.py','test/test_sources.py','test/test_quality.py','test/test_verify_scan.py'])allowed.add(p);
// Newly reviewed, read-only gate workflows; keep exact allowlist rather than wildcarding.
for(const p of ['.github/workflows/phoenix-promotion-gate.yml','.github/workflows/tennis-shadow-routing.yml','.github/workflows/nba-research-ci.yml','.github/workflows/nfl-verified-order.yml'])allowed.add(p);
for(const p of ['data/manual_challenger_fixtures.json','docs/manual-challenger-entry-example.json'])allowed.add(p);\nfor(const p of ['site/forecast-state.mjs','scripts/last-scan.mjs','test/dashboard.test.mjs','test/last-scan.test.mjs'])allowed.add(p);
const nfl=JSON.parse(await readFile('nfl/manifest.json','utf8'));
for(const n of ['.github/workflows/challenger-integration.yml','.github/workflows/nfl-integration.yml','nfl/manifest.json','scripts/nfl-status.mjs','test/nfl-status.test.mjs','site/nfl.html','site/nfl.css','site/nfl.js','site/nfl-quality.mjs','nfl/prop_outcomes.py','test/test_prop_outcomes.py','test/nfl-quality.test.mjs',...Object.keys(nfl.files)])allowed.add(n);
for(const n of ["nba_engine/IMPLEMENTATION_STATUS.md","nba_engine/README.md","nba_engine/RESEARCH_V2.md","nba_engine/__init__.py","nba_engine/advanced.py","nba_engine/calibration.py","nba_engine/champion_designation.json","nba_engine/cli.py","nba_engine/core.py","nba_engine/evaluation.py","nba_engine/ledger.py","nba_engine/player_sim.py","nba_engine/possession_sim.py","nba_engine/providers.py","nba_engine/recovery.py","tests/test_nba_advanced.py","tests/test_nba_engine.py","tests/test_nba_extended.py","tests/test_nba_possession.py"])allowed.add(n);
for(const p of ['nfl/verified_pbp_order.py','nfl/tests/test_verified_pbp_order.py'])allowed.add(p);
const files=execFileSync('git',['ls-files','-z'],{encoding:'utf8'}).split('\0').filter(Boolean);
const unexpected=files.filter(path=>!allowed.has(path) && !isSafeSourcePath(path));
if(unexpected.length)throw Error('Unreviewed public files ('+unexpected.length+'):\n'+unexpected.join('\n'));
let total=0;
for(const path of files){
  const s=await lstat(path);if(!s.isFile()||s.isSymbolicLink()||s.size>4000000)throw Error('Unsupported public file: '+path);total+=s.size;
  const raw=await readFile(path),text=raw.toString('utf8');
  if(raw.includes(0)||!Buffer.from(text,'utf8').equals(raw))throw Error('Non-UTF8 public file: '+path);
  const patterns=[/gh[pousr]_[A-Za-z0-9]{30,}/,/github_pat_[A-Za-z0-9_]{30,}/,/-----BEGIN [A-Z ]*PRIVATE KEY-----/,/C:\\+Users\\+/i,/chatgpt\.com\/c\/[a-f0-9-]+/i,/USER_VIDEO_/,/USER_RECORDING_/,/user_instruction/];
  // The audit's own regex literals are not private source content.
  if(path!=='scripts/audit.mjs'&&patterns.some(p=>p.test(text)))throw Error('Potential private content: '+path);
  if(nfl.files[path]&&createHash('sha256').update(raw).digest('hex')!==nfl.files[path])throw Error('Changed NFL source or parameters: '+path);
  if(path.startsWith('engine/')&&path!=='engine/manifest.json'&&createHash('sha256').update(raw).digest('hex')!==manifest.files[path.slice(7)])throw Error('Changed model artifact: '+path);
}
for(const n of Object.keys(nfl.files))if(!files.includes(n))throw Error('Missing NFL file: '+n);
for(const n of Object.keys(manifest.files))if(!files.includes('engine/'+n))throw Error('Missing runtime file: '+n);
if(total>20000000)throw Error('Public source exceeds size budget');
console.log(`Public audit passed: ${files.length} approved text files, ${total} bytes. No archives, model binaries, private history, runtime logs or historical raw datasets.`);
