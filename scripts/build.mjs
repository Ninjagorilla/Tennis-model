import {readFile,mkdir,copyFile,writeFile,readdir,stat} from 'node:fs/promises';
import {validate,blank} from './status.mjs';
const read = async p=>JSON.parse(await readFile(p,'utf8'));
let status;
try {status=validate(await read('work/snapshot.json'));} catch(e){if(e.code==='ENOENT')status=blank();else throw e;}
await mkdir('dist/data',{recursive:true});
for (const name of ['index.html','style.css','app.js']) await copyFile(`site/${name}`,`dist/${name}`);
await writeFile('dist/data/status.json',JSON.stringify(status,null,2)+'\n');
await writeFile('dist/.nojekyll','');
const allowed = new Set(['index.html','style.css','app.js','data/status.json','.nojekyll']);
async function check(dir,prefix='') {for(const n of await readdir(dir)){const p=prefix+n;const s=await stat(`${dir}/${n}`);if(s.isDirectory())await check(`${dir}/${n}`,p+'/');else if(!allowed.has(p)||s.size>1500000)throw new Error('Unexpected publish file: '+p);}}
await check('dist');
console.log(`Site built: ${status.prediction_status}, ${status.matches.length} scheduled matches.`);
