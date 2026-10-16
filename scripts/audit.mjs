import {execFileSync} from 'node:child_process';
import {readFile,lstat} from 'node:fs/promises';
const allowed = new Set(['.gitignore','.github/workflows/dashboard.yml','README.md','SECURITY.md','package.json','config/models.json','config/recovery.json','scripts/audit.mjs','scripts/build.mjs','scripts/status.mjs','test/status.test.mjs','site/index.html','site/style.css','site/app.js']);
const files=execFileSync('git',['ls-files','-z'],{encoding:'utf8'}).split('\0').filter(Boolean);
let total=0;
for(const path of files){
  if(!allowed.has(path))throw new Error('Unreviewed public file: '+path);
  const s=await lstat(path);if(!s.isFile()||s.isSymbolicLink()||s.size>100000)throw new Error('Unsupported public file: '+path);total+=s.size;
  const text=await readFile(path,'utf8');
  const patterns=[/gh[pousr]_[A-Za-z0-9]{30,}/,/github_pat_[A-Za-z0-9_]{30,}/,/-----BEGIN [A-Z ]*PRIVATE KEY-----/,/C:\\\\Users\\\\/i,/chatgpt\.com\/c\/[a-f0-9-]+/i];
  if(patterns.some(p=>p.test(text)))throw new Error('Potential private content: '+path);
}
if(total>500000)throw new Error('Public source exceeds size budget');
console.log(`Public file audit passed: ${files.length} files, ${total} bytes. Review content before every push; this is not a universal secret detector.`);
