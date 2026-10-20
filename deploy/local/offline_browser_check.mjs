/** Offline lab UI harness. Arguments: WEBSITE BUNDLE_DIR OUT_DIR; PW_DIR supplies
 * existing node_modules. Serves only loopback, rewrites the worker's CDN to local
 * Pyodide and runs the existing UI assertions unchanged. No package installation.
 */
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [website, bundle, out] = process.argv.slice(2).map(p=>path.resolve(p));
const modules = path.join(process.env.PW_DIR, 'node_modules');
const runtime = path.join(modules, 'pyodide');
const server = http.createServer(async(req,res)=>{
  try {
    const route = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    const root = route.startsWith('/_runtime/') ? runtime : route.startsWith('/projects/protocol-lab/dist/') ? bundle : website;
    const rel = root === runtime ? route.slice('/_runtime/'.length) : root === bundle ? route.slice('/projects/protocol-lab/dist/'.length) : route.slice(1);
    const file = path.resolve(root, rel.endsWith('/') ? rel+'index.html' : rel);
    if (!file.startsWith(root + path.sep)) throw new Error('Path outside root');
    let data = await fs.readFile(file);
    if (route.endsWith('/worker.js')) data = Buffer.from(data.toString()
      .replace('https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs', '/_runtime/pyodide.mjs')
      .replace('`https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`', '`' + origin + '/_runtime/`'));
    res.writeHead(200, {'Content-Type': ({'.html':'text/html; charset=utf-8','.js':'text/javascript',
      '.mjs':'text/javascript','.css':'text/css','.json':'application/json','.wasm':'application/wasm'})[path.extname(file)] || 'application/octet-stream'});
    res.end(data);
  } catch {res.writeHead(404);res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin = 'http://127.0.0.1:' + server.address().port;
await fs.mkdir(out,{recursive:true});
let source = await fs.readFile('lab/tools/ui_test.mjs','utf8');
source = source.replace('from "playwright"', 'from ' + JSON.stringify(pathToFileURL(path.join(modules,'playwright/index.mjs')).href))
  .replace('await chromium.launch()', "await chromium.launch({args:['--disable-background-networking','--disable-component-update','--disable-sync','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']})")
  .replace('const problems = [];', `await page.route('**/*', route => route.request().url().startsWith(${JSON.stringify(origin)} + '/') ? route.continue() : route.abort());\nconst problems = [];`);
const script = path.join(out,'ui_test.offline.mjs');
await fs.writeFile(script,source);
process.argv = [process.argv[0],script,origin,out];
// The imported suite exits explicitly; close the server even on unexpected errors.
try {await import(pathToFileURL(script).href);}
finally {server.closeAllConnections();server.close();}
