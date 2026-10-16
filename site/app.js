const $=id=>document.getElementById(id);
const repo='Ninjagorilla/Tennis-model';
const date=s=>new Date(s).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'});
function element(tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e;}
function validate(d){
  const ids={champion:'SR-Elo 1.0',challenger:'SR-GLM 0.2',experimental:'v3.4-A'};
  if(d.schema_version!==1||d.prediction_status!=='blocked'||!Array.isArray(d.predictions)||d.predictions.length||!Array.isArray(d.models)||d.models.length!==3||new Set(d.models.map(m=>m.id)).size!==3||!Number.isFinite(Date.parse(d.generated_at))||Date.parse(d.generated_at)>Date.now()+300000||d.models.some(m=>ids[m.id]!==m.name||m.cloud_status!=='unavailable'))throw new Error('Invalid snapshot');
}
function render(d){validate(d);const stale=Date.now()-Date.parse(d.generated_at)>48*3600000;
  $('headline').textContent=stale?'Snapshot stale · predictions withheld':'Predictions withheld · cloud runtime unavailable';
  $('notice-detail').textContent=stale?'No recent dashboard build is available. Check the workflow before relying on this snapshot.':'Recovered local checks are separate from cloud readiness. No current probabilities have been generated.';
  $('ready').textContent='0 / 3';$('updated').textContent=date(d.generated_at);$('freshness').textContent=stale?'Older than 48 hours':'Snapshot age checked in your browser';
  $('model-cards').replaceChildren();
  for(const m of d.models){const card=element('article','', 'model');card.append(element('div',m.role,'role'),element('h3',m.name),element('span','Cloud unavailable','pill'));const dl=element('dl','');const r=m.local_verification;
    for(const [k,v]of [['Last local diagnostic',`${r.successful_checks} / ${r.total_checks} checks passed`],['Checked',date(r.checked_at)],['Saved model state',r.state_dates.join(' · ')||'Not established']])dl.append(element('dt',k),element('dd',v));
    card.append(dl,element('p',m.research_only?'Research only · uncalibrated. No live forecast is implied by these checks.':m.reason));$('model-cards').append(card);
  }
  const passed=d.models.every(m=>m.local_verification.successful_checks===4);$('local-icon').textContent=passed?'✓':'○';$('local-detail').textContent=passed?'12 / 12 diagnostic checks passed across four tour categories. This is a dated local verification, not a live scan.':'Some local diagnostic checks did not pass. Review the recovery evidence.';
  $('evidence-time').textContent=`Local verification recorded ${date(d.recovery.checked_at)}. The receipt is historical and is not refreshed by a dashboard rebuild.`;
  $('archive-hash').textContent=d.recovery.archive_sha256;$('report-hash').textContent=d.recovery.report_sha256;
}
async function load(){const b=$('refresh');b.disabled=true;
  try{const r=await fetch('data/status.json',{cache:'no-store',signal:AbortSignal.timeout(10000)});if(!r.ok)throw new Error();render(await r.json());}
  catch{$('headline').textContent='Status unavailable · predictions withheld';$('notice-detail').textContent='The dashboard could not load a valid status file. Open the workflow for details.';$('model-cards').replaceChildren(element('p','Verification status is unknown.'));$('ready').textContent='Unknown';$('updated').textContent='Unknown';$('freshness').textContent='Snapshot unavailable';$('local-icon').textContent='○';$('local-detail').textContent='Local evidence could not be loaded.';for(const id of ['evidence-time','archive-hash','report-hash'])$(id).textContent='Unknown';}
  try{const r=await fetch(`https://api.github.com/repos/${repo}/actions/workflows/dashboard.yml/runs?branch=main&per_page=1`,{headers:{Accept:'application/vnd.github+json'},cache:'no-store',signal:AbortSignal.timeout(10000)});if(!r.ok)throw new Error();const run=(await r.json()).workflow_runs?.[0];if(!run)throw new Error();$('workflow').textContent=run.status==='completed'?run.conclusion:run.status.replaceAll('_',' ');$('workflow-detail').textContent=`${date(run.created_at)} · build/deploy, not inference`;}
  catch{$('workflow').textContent='Unknown';$('workflow-detail').textContent='GitHub unavailable or rate limited; use Open workflow.';}
  b.disabled=false;
}
$('refresh').addEventListener('click',load);load();
