'use strict';
const $=id=>document.getElementById(id);let current;
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
function render(s){
 current=s;const stale=Date.now()>=Date.parse(s.expires_at);const ok=s.execution_status==='verified'&&!stale;
 $('nfl-headline').textContent=stale?'NFL scan expired':ok?'Full NFL engine executed. Publication remains gated.':'NFL execution is not currently verified.';
 $('nfl-detail').textContent=stale?'Live execution claims and fixtures are withheld until a fresh scan is published.':s.publication_gate;
 $('nfl-execution').textContent=ok?'Verified':stale?'Expired':s.execution_status.replaceAll('_',' ');
 $('nfl-paper').textContent=ok?String(s.paper_games):'Not current';$('nfl-date').textContent=s.state_date||'Unavailable';
 $('nfl-gate').textContent=s.publication_gate;
 const markets=$('nfl-markets');markets.replaceChildren();for(const m of s.markets){const card=el('article',undefined,'market-card');card.append(el('small','IMPLEMENTED / VALIDATION-GATED'),el('h3',m));markets.append(card);}
 const body=$('nfl-scores');body.replaceChildren();for(const [key,label]of [['game','Game-first TD'],['team','Team-first TD']]){const d=s.validation.results[key],r=el('tr');for(const value of [label,d.contracts,d.scores.baseline.log_loss.toFixed(4),d.scores.challenger.log_loss.toFixed(4),d.scores.baseline.brier.toFixed(4),d.scores.challenger.brier.toFixed(4)])r.append(el('td',String(value)));body.append(r);}
 const u=$('nfl-uncertainty');u.replaceChildren(el('h3','The release gate is still closed.'));
 for(const [key,label]of [['game','Game-first'],['team','Team-first']]){const d=s.validation.results[key];for(const metric of ['log_loss','brier']){const z=d.paired_differences[metric],ci=z.paired_game_bootstrap_95pct;u.append(el('p',`${label} ${metric.replaceAll('_',' ')}: Challenger minus baseline ${z.challenger_minus_baseline.toFixed(4)}. Paired 95% interval: ${ci[0].toFixed(4)} to ${ci[1].toFixed(4)}.`));}}
 u.append(el('p',`${s.prospective?.unique_games_graded??s.validation.prospective_games_graded} prospectively graded games. A confidence interval crossing zero leaves the direction of improvement uncertain. No profit or betting-edge claim is made.`));
 u.append(el('p','2026-only caution: game-first log loss was 3.2054 versus 3.1879 for the baseline, and Brier was 0.9385 versus 0.9348. That subgroup worsened. Historical averages do not justify releasing the model yet.'));
 if(s.paper_history_restore?.status==='unavailable')u.append(el('p','Prior paper-history retrieval failed on this run. The displayed prospective coverage may be incomplete.'));
 const limits=$('nfl-limits');limits.replaceChildren(...s.limits.map(x=>el('li',x)));renderFixtures();
}
function renderFixtures(){if(!current)return;const list=$('nfl-fixture-list');list.replaceChildren();if(current.execution_status!=='verified'||Date.now()>=Date.parse(current.expires_at)){list.append(el('p','A fresh, verified execution is required to display upcoming NFL fixtures.'));return;}
 const games=current.fixtures.filter(g=>Date.parse(g.starts_at)>Date.now());for(const g of games){const n=el('article',undefined,'fixture');n.append(el('strong',`${g.away} at ${g.home}`),el('span',new Date(g.starts_at).toLocaleString(undefined,{weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})));list.append(n);}if(!games.length)list.append(el('p','No supported future fixtures are verified in this scan.'));
}
async function load(){try{const r=await fetch('data/nfl-status.json',{cache:'no-store'});if(!r.ok)throw Error('Unavailable');const s=await r.json();if(s.schema_version!==1||s.publication_approved!==false||s.games.length!==0||!Array.isArray(s.fixtures)||!s.validation?.results?.game||!Number.isFinite(Date.parse(s.expires_at)))throw Error('Invalid record');render(s);}catch(e){current=null;$('nfl-headline').textContent='NFL execution record unavailable';$('nfl-detail').textContent='No live probabilities are being substituted or invented.';$('nfl-fixture-list').replaceChildren(el('p','No verified fixtures available.'));}}
$('nfl-refresh').addEventListener('click',load);setInterval(()=>{if(current&&Date.now()>=Date.parse(current.expires_at))render(current);else renderFixtures();},30000);load();
