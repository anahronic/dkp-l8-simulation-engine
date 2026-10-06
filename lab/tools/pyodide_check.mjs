// Run lab.tools.pyodide_check.identities() inside Pyodide (Node) from the web bundle.
// usage: node lab/tools/pyodide_check.mjs BUNDLE_DIR   (needs: npm install pyodide@314.0.7)
import { loadPyodide } from "pyodide";
import fs from "node:fs";

const dir = process.argv[2];
const py = await loadPyodide();
await py.loadPackage("pyyaml", { messageCallback: () => {} });
py.unpackArchive(new Uint8Array(fs.readFileSync(dir + "/lab-bundle.zip")), "zip", { extractDir: "/home/pyodide/engine" });
const out = py.runPython(`
import os, sys, json
os.chdir("/home/pyodide/engine"); sys.path.insert(0, "/home/pyodide/engine")
from lab.tools.pyodide_check import identities
json.dumps(identities(), sort_keys=True)
`);
console.log(out);
