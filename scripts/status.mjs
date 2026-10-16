export const identities = Object.freeze({champion:'SR-Elo 1.0',challenger:'SR-GLM 0.2',experimental:'v3.4-A'});
export function createStatus(registry, receipt, now = new Date(), env = {}) {
  if (!Array.isArray(registry) || registry.length !== 3 || new Set(registry.map(m=>m.id)).size !== 3) throw new Error('Invalid registry');
  for (const m of registry) {
    if (identities[m.id] !== m.name || m.cloud_enabled !== false) throw new Error('Unverified model enablement rejected');
  }
  if (!receipt || receipt.kind !== 'local_diagnostic_preflight' || !Array.isArray(receipt.models)) throw new Error('Invalid receipt');
  const checked = Date.parse(receipt.checked_at);
  if (!Number.isFinite(checked) || checked > now.getTime()) throw new Error('Invalid verification timestamp');
  const sha = /^[a-f0-9]{64}$/;
  if (!sha.test(receipt.archive_sha256) || !sha.test(receipt.report_sha256)) throw new Error('Missing evidence hashes');
  if (receipt.models.length !== 3 || new Set(receipt.models.map(m=>m.id)).size !== 3) throw new Error('Incomplete receipt');
  const models = registry.map(m => {
    const r = receipt.models.find(r=>r.id===m.id);
    if (!r || !Number.isInteger(r.successful_checks) || r.successful_checks < 0 || r.successful_checks > 4 || r.total_checks !== 4) throw new Error('Invalid check count');
    if (!Array.isArray(r.state_dates) || r.state_dates.some(d=>!/^\d{4}-\d{2}-\d{2}$/.test(d) || !Number.isFinite(Date.parse(d)) || Date.parse(d)>checked)) throw new Error('Invalid state date');
    return {id:m.id,name:m.name,role:m.role,cloud_status:'unavailable',reason:'Runtime artifacts are local; no approved cloud artifact source is configured.',local_verification:{checked_at:receipt.checked_at,successful_checks:r.successful_checks,total_checks:4,state_dates:r.state_dates},research_only:m.id==='experimental'};
  });
  const commit = /^[a-f0-9]{40}$/.test(env.GITHUB_SHA || '') ? env.GITHUB_SHA : null;
  const runId = /^\d+$/.test(env.GITHUB_RUN_ID || '') ? env.GITHUB_RUN_ID : null;
  return {schema_version:1,generated_at:now.toISOString(),stale_after_hours:48,build:{status:'generated',commit,run_id:runId},prediction_status:'blocked',models,fixtures:{status:'not_collected',count:null,scopes:['ATP','WTA','ATP Challenger','WTA 125']},predictions:[],recovery:{archive_sha256:receipt.archive_sha256,report_sha256:receipt.report_sha256,checked_at:receipt.checked_at},limitations:['Local diagnostic checks are not a live scan or cloud execution.','Current fixture collection and verified cloud model delivery are not configured.','Experimental v3.4-A is uncalibrated. Agreement is not a calibrated consensus probability.']};
}
