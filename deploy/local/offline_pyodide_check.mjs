/** Uses only the preinstalled runtime named by PW_DIR. No downloads. */
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const runtime = path.join(process.env.PW_DIR, 'node_modules/pyodide');
const {loadPyodide} = await import(pathToFileURL(path.join(runtime, 'pyodide.mjs')).href);
globalThis.fetch = async () => {throw new Error('Network disabled for offline identity check');};
const py = await loadPyodide({indexURL: runtime + path.sep});
await py.loadPackage('pyyaml', {messageCallback:()=>{}});
py.unpackArchive(new Uint8Array(fs.readFileSync(process.argv[2] + '/lab-bundle.zip')), 'zip', {extractDir:'/home/pyodide/engine'});
const result = py.runPython(`
import os, sys, json
os.chdir('/home/pyodide/engine'); sys.path.insert(0, '/home/pyodide/engine')
from lab.tools.pyodide_check import identities
json.dumps(identities(), sort_keys=True)
`);
fs.writeFileSync(process.argv[3], result + '\n');
console.log('Pyodide identities:', Object.keys(JSON.parse(result)).length);
