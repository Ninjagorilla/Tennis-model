// Auto-approve only ordinary source/test files in these two reviewed directories.
// CI workflows, assets, manifests, data, and model artifacts stay explicitly approved.
const SCRIPT = /^scripts\/[a-z][a-z0-9_-]*\.(?:py|mjs)$/;
const TEST = /^test\/(?:test_[a-z0-9_-]+\.py|[a-z][a-z0-9_-]*\.test\.mjs)$/;
export function isSafeSourcePath(path) {
  return typeof path === 'string' && (SCRIPT.test(path) || TEST.test(path));
}
