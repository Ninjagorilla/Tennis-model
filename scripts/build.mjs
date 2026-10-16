import {readFile,mkdir,copyFile,writeFile,readdir,stat} from 'node:fs/promises';
import {createStatus} from './status.mjs';
const read = async p=>JSON.parse(await readFile(p,'utf8'));
const status = createStatus(await read('config/models.json'), await read('config/recovery.json'), new Date(), process.env);
await mkdir('dist/data',{recursive:true});
for (const name of ['index.html','style.css','app.js']) await copyFile(`site/${name}`,`dist/${name}`);
await writeFile('dist/data/status.json',JSON.stringify(status,null,2)+'\n');
await writeFile('dist/.nojekyll','');
const allowed = new Set(['index.html','style.css','app.js','data/status.json','.nojekyll']);
async function check(dir,prefix='') {for(const n of await readdir(dir)){const p=prefix+n;const s=await stat(`${dir}/${n}`);if(s.isDirectory())await check(`${dir}/${n}`,p+'/');else if(!allowed.has(p)||s.size>100000)throw new Error('Unexpected publish file: '+p);}}
await check('dist');
console.log('Dashboard built. Cloud inference: BLOCKED. Predictions: none.');
