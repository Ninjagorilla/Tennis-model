import {validateNFL} from './nfl-status.mjs';
import {readFile,mkdir,copyFile,writeFile,readdir,stat} from 'node:fs/promises';
import {validate,blank} from './status.mjs';
const read = async p=>JSON.parse(await readFile(p,'utf8'));
let status;
try {status=validate(await read('work/snapshot.json'));} catch(e){if(e.code==='ENOENT')status=blank();else throw e;}
await mkdir('dist/data',{recursive:true});
for (const name of ['index.html','style.css','app.js','nfl.html','nfl.css','nfl.js','nfl-quality.mjs']) await copyFile(`site/${name}`,`dist/${name}`);
await writeFile('dist/data/status.json',JSON.stringify(status,null,2)+'\n');
let nfl;try{nfl=validateNFL(await read('work/nfl_snapshot.json'));}catch(e){if(e.code!=='ENOENT')throw e; const at=new Date();nfl=validateNFL({...await read('nfl/evidence/public_preview.json'),generated_at:at.toISOString(),expires_at:new Date(+at+5400000).toISOString(),execution_status:'not_run',paper_games:0,fixtures:[]});}
await writeFile('dist/data/nfl-status.json',JSON.stringify(nfl,null,2)+'\n');
await writeFile('dist/.nojekyll','');
const allowed = new Set(['index.html','style.css','app.js','data/status.json','.nojekyll','nfl.html','nfl.css','nfl.js','nfl-quality.mjs','data/nfl-status.json']);
async function check(dir,prefix='') {for(const n of await readdir(dir)){const p=prefix+n;const s=await stat(`${dir}/${n}`);if(s.isDirectory())await check(`${dir}/${n}`,p+'/');else if(!allowed.has(p)||s.size>1500000)throw new Error('Unexpected publish file: '+p);}}
await check('dist');
console.log(`Site built: ${status.prediction_status}, ${status.matches.length} scheduled matches.`);
