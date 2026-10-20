# DKP Lab and Keeper deployment kit

This is an operator-run kit for the existing Ubuntu 24.04 x86_64 server. Creating this
kit does not deploy anything. Run the numbered server scripts **as `admin`**, using
`bash`; each calls passwordless `sudo` only where needed. Never run with `bash -x`,
which would expose credentials in diagnostic output. Keep the entire `deploy/`
directory together; scripts source `server/common.sh` and use `server/kit_helpers.py`.

**New paid resources are an author decision.** This kit provisions no paid resources,
does not change DNS or firewall rules, and does not restart the existing production
applications, PostgreSQL, pm2, fail2ban, or unattended-upgrades. It reloads nginx only
after a successful configuration test. It installs Ollama using its upstream installer;
review that retained script and its printed checksum as part of operator review.

## Prerequisites and unresolved inputs

- This checkout includes `keeper/gateway.py`, `keeper/README.md` and the API contract.
  `keeper.gateway:app` implements the documented routes and settings; dependencies are
  listed in `requirements-server.txt`. Packaging and installation reject a release
  missing the gateway. The site widget and its route manifest are supplied from the
  separate site repository. Keyed job submissions now require `X-Idempotency-Token`
  retained before POST; update the site client to the server contract before release.
- Full model-layer digest of `qwen3.5:2b` (2026-10-16, pulled from registry.ollama.ai on the author's machine,
  same layer as the registry manifest read the same day):
  `sha256:e8bf47d40c5ba68baf8f3e503ee36710da6e8641cb0a670a508cff5b3f0cfbf7`.
  Step 20 requires `sha256:` followed by 64 lowercase hex digits and checks the model layer, not the manifest
  digest. A moving model tag that no longer matches will stop Ollama and fail deployment.
- `SITE_WIDGET_DIR` means the **site repository root**, containing
  `website/keeper/{keeper-loader.js,ROUTES.json,...}`, `tools/keeper_inject.py`, and
  `website/pages/protocols`. These site sources are not in this engine checkout. The
  injector must accept `--root`, `--routes`, and `--check` as requested, and add exactly
  one `<script src="/keeper/keeper-loader.js" defer></script>` before `</body>`.
- The supplied site kit includes its actual `ROUTES.json`; the helper accepts a
  nonempty JSON list, or `{"routes": [...]}`. Entries are paths (`"/index.html"`),
  `https://dikenocracy.com/...` URLs, or objects with exactly one of `path`, `route`,
  `url`. Queries/fragments, relative paths, and other hosts are rejected. Adapt the
  helper if a later manifest changes schema; no routes are
  silently skipped. The site's injector must understand that same manifest.
- Supply the server's public IP as `PUBLIC_IP` for step 90. Server-side public-IP
  probes cannot establish accessibility from every external network. Repeat the
  port checks from a separate external machine; no server-side script can prove
  that independently. Repeat for each public IPv4/IPv6 address, if multiple exist.
- Server prerequisites: Bash, Python 3.12 with `venv`/`ensurepip`, curl, nginx,
  systemd, iproute2 (`ss`), util-linux (`flock`, swap tools), and coreutils. Step 00
  lists missing commands. If necessary, the operator installs `python3-venv` with
  apt before rerunning preflight. The kit does not run apt upgrades. Upstream Ollama
  may have additional installer prerequisites; inspect installer errors before retry.
- Local packaging uses Bash, Git, tar/gzip, sha256sum, and Python with the engine's
  existing dependencies installed. Set `PYTHON` to the desired interpreter and
  `KEEPER_SITE_PAGES` to the reviewed live-site `website` directory, and optionally
  `KEEPER_RU_SOURCES` to a local Russian source directory. Packaging has
  no network operations. Use a clean, committed engine release checkout. The kit is
  present in the supplied Git history; new local changes must be integrated into the
  release checkout before packaging. Do not build on the server.

## Installed paths

| Path | Purpose and ownership |
| --- | --- |
| `/opt/dkp-lab/releases/VERSION/` | Root-owned code, venv, artifact hashes and matching corpus; no runtime writes |
| `/opt/dkp-lab/current` | Atomically replaced symlink to the active release |
| `/opt/dkp-lab/PREVIOUS` | Absolute previous release path, preserved when reinstalling the same version |
| `/var/lib/dkp-lab` | `root:root`, 0755; runtime cannot replace its children |
| `/var/lib/dkp-lab/lab` | `dkplab:dkplab`, 0700; API/worker database/store/secret |
| `/var/lib/dkp-corpus` | `root:dkplab`, 0750; no runtime directory writes |
| `/var/lib/dkp-corpus/corpus.jsonl` | `root:dkplab`, 0640; Keeper reads via supplementary group |
| `/var/lib/dkp-keeper` | `dkpkeeper:dkpkeeper`, 0700; Keeper logs/temporary state only |
| `/etc/systemd/system/dkp-*.service` | API, serial worker and Keeper units |
| `/etc/systemd/system/ollama.service.d/dkp.conf` | Local bind, cloud disable, concurrency/context and resource limits |
| `/usr/share/ollama/.ollama/models/` | `root:ollama`; group read-only after administrator installation |
| `/etc/nginx/conf.d/dkp-limits.conf` | HTTP-context rate/connection zones |
| `/etc/nginx/snippets/dkp-lab-keeper.conf` | HTTPS server locations for Lab, Keeper and widget |
| `/var/www/html/keeper/` | Admin-owned widget assets, routes and injector; files readable by nginx |
| `/swapfile`, `/etc/sysctl.d/90-dkp-swap.conf` | Kit-owned 2 GiB swap and swappiness=10, only if swap was absent |
| `/var/lib/dkp-deploy/` | Admin-owned 0700 operational state, backups, installer, lock and logs |

The corpus and code are versioned together. Runtime state is retained independently.
Keep the Lab SQLite database and store (including `.secret`) together during recovery;
the kit never deletes them. Server changes are printed and appended to
`/var/lib/dkp-deploy/CHANGES.log`. Read-only preflight deliberately creates no log.
Local packaging writes `OUT_DIR/CHANGES.log`, since it does not access the server.
Step 90 also creates a private timestamped log. Job tokens and authorization headers
are held in temporary mode-0600 files and deleted on exit, never printed or put in URLs.
Backups are retained until an operator removes them; there is no automated pruning.

## Execution order and effects

1. **Build locally**, using the matching engine and site sources:

   ```bash
   KEEPER_SITE_PAGES=/path/to/live-site/website \
     bash deploy/local/make_release.sh /path/to/engine /path/to/widget /path/to/empty-output
   # Optional: PYTHON=/path/to/venv/bin/python KEEPER_RU_SOURCES=/path/to/ru ...
   ```

   Refuses dirty/untracked engine, widget and live-site files. Creates a `git archive` of HEAD, the corpus
   plus manifest (with site-anchor comparison), a widget tarball with the injector
   at its root, a freshly rebuilt browser bundle, `VERSION` (`<engine short sha>-<corpus version>`),
   full engine/widget/site-page HEADs in `REVISIONS`, and `SHA256SUMS`.
   Corpus comparison uses the actual live-site revision, not the older widget branch.
   Nested public tar/ZIP content is checked for private markers and translation passages;
   failure removes the widget tarball. The private corpus is a separate server artifact,
   never a static download. `KEEPER_RU_SOURCES` enables the full translation scan.
   Output must be empty and outside both source trees. Do not change sources during
   the build; review the corpus manifest's missing-page/anchor results. Archives with
   symlinks, hardlinks, devices, traversal, or duplicate paths are rejected. This is
   a deliberate packaging constraint. Pip requirements are not a complete dependency
   lock and the installer URL is mutable; retain the release artifacts and installer
   checksum for audit, rather than assuming future rebuilds are byte-identical.

2. Transfer the artifacts and this `deploy/` directory using the operator's existing
   transfer process. Verify artifacts with `sha256sum -c SHA256SUMS` in their directory.
   No transfer or connection is performed by this kit's authoring workflow.

3. **`bash deploy/server/00_preflight.sh`**: read-only command, Python, RAM/swap/disk,
   load, free-port and `sudo nginx -t` checks. Requires at least 2.5 GB available RAM
   and 12 GB free disk. Load is printed for operator judgment. The free-port check is
   intentionally a first-install check; it will fail after DKP is running.

4. **`bash deploy/server/10_swap.sh`**: if swap is absent, claims and creates a 2 GiB
   `/swapfile`, enables it, adds its tagged fstab line once, and sets swappiness=10.
   Existing unrelated swap is left alone. Existing unowned `/swapfile` or its fstab
   entry is a blocker. Saves prior sysctl configuration for rollback. Reruns complete
   an interrupted kit-owned setup or reuse its active swap.

5. **`bash deploy/server/20_ollama.sh 'sha256:<full model-layer digest>'`**:
   downloads/prints SHA256/runs the installer only when Ollama is absent. Stages the
   drop-in before the installer can start the service (systemd does not inherit the
   shell's environment), enables/restarts the service, pulls `qwen3.5:2b`, checks its local manifest,
   effective environment, and IPv4-loopback-only listener. Existing installs are not
   upgraded. Reruns reuse downloaded model layers. `EXPECTED_MODEL_DIGEST` may replace
   the argument. A failed post-start verification stops Ollama. This step uses the
   network **when the operator runs it**, as do pip and public smoke tests below.

6. **Install the app** using the filenames produced above:

   ```bash
   VERSION=$(cat /path/to/artifacts/VERSION)
   bash deploy/server/30_app.sh /path/to/artifacts/engine-"$VERSION".tar.gz \
     /path/to/artifacts/corpus-<corpus-version>.jsonl "$VERSION"
   ```

   Creates `dkplab`, immutable release directory and venv; installs
   `requirements-server.txt` (which includes `requirements.txt`); prepares private data
   paths. Stops existing DKP processes before switching code/corpus, records PREVIOUS,
   atomically replaces current, installs units, enables/restarts them and waits for
   both local health endpoints. There is brief DKP downtime during upgrades. An
   existing version is reused only when both artifact hashes match. An incomplete
   version directory is left for inspection; remove that **specific inactive release**
   manually before retrying. Health failure leaves the failed release selected for
   diagnosis; use explicit app rollback. No database schema downgrade is attempted.

7. **`bash deploy/server/40_nginx.sh`**: backs up default and both target files under
   `nginx-<timestamp>/`, including absent-file markers. Preserves the default file's
   symlink layout. Requires exactly one mazkira include inside the dikenocracy.com
   HTTPS/443 server; otherwise fails before changing nginx. Installs zones/snippet and
   inserts exactly one DKP include immediately after that anchor. Tests and reloads
   nginx. Any install/test/reload failure restores the backup and exits nonzero.
   Repeated runs do not duplicate includes. Default configuration backups are complete
   snapshots; serialize nginx edits with other administrators.

8. **`bash deploy/server/50_site.sh /path/to/artifacts/widget-<VERSION>.tar.gz`**:
   validates/extracts widget into private staging, backs up every HTML file plus any
   existing keeper directory to `site-<timestamp>.tar.gz`, replaces the widget, runs
   injector and `--check`. All web-root changes run as admin without sudo. Failure
   restores the site backup. No website build is performed there. Serialize this
   step with other site deployments. The backup excludes other unchanged static files.

9. **`PUBLIC_IP=<public-IP> bash deploy/server/90_postdeploy_check.sh [BASE_URL]`**:
   defaults to `https://dikenocracy.com`. Verifies both health endpoints; submits the
   first work_cycle scenario variant; polls for up to roughly five minutes plus HTTP
   time; downloads and cross-checks report/export IDs and ZIP integrity; prints result
   and input IDs; asks one Russian question with elapsed time; checks every declared
   route has one deferred loader. Checks loopback listeners and probes the public IP
   on 11434/8720/8721 (any HTTP reply is a failure), then prints `free -h` and `ollama ps`.
   A grounded Russian response with citations is required. Downloads/token files are
   temporary and removed; test jobs remain subject to normal worker retention.

## Verification and traffic behavior

Run `sudo systemctl status dkp-lab-api dkp-lab-worker dkp-keeper ollama` and inspect
the corresponding journal units if a step fails. `systemctl show ollama -p Environment`
must contain all six Ollama settings from the drop-in; step 20 checks them without
printing unrelated variables. Inspect `sudo ss -ltnp` for only `127.0.0.1` on the
three new ports. From an independent outside host, `curl --noproxy '*' --connect-timeout
5 --max-time 8 http://<public-IP>:8720/` (and 8721/11434) must fail to connect, not
merely return an HTTP error. Confirm existing website, `/api/`, and
`/AA/Alienclimber/api/` behavior using their existing operational checks.

Lab routes in `lab_server/app.py` explicitly contain `/api/lab/v1`; `proxy_pass` has
**no trailing slash/URI** to preserve that prefix. Keeper uses the analogous documented
prefix in `keeper/gateway.py`. The longer `^~`
locations take precedence over `/api/` and regex locations. Lab nginx requests are
limited to 2 requests/second/IP (burst 20), with the application's separate 10 POST/min limit.
Keeper nginx requests are 12/min/IP, burst 4 nodelay, at most two active connections;
the gateway contract additionally limits asks to 6/min and one generation. Polling
is spaced by three seconds. Keeper buffering, caching and gzip are disabled for SSE;
the nginx response has `X-Accel-Buffering: no` and a 180-second read timeout. Widget
responses use `Cache-Control: no-cache`. Proxy IP headers are trusted only from
127.0.0.1 by uvicorn. The gateway's actual SSE behavior needs runtime verification.

## Resource budget

| Process / reservation | Memory ceiling or planning allowance | CPU ceiling |
| --- | --- | --- |
| Ollama, Q8_0 model layer (2,012,012,448 bytes), 8192 context | MemoryHigh 2500 MiB; MemoryMax 2700 MiB | 170% (1.7 cores) |
| Lab API, one uvicorn worker | 300 MiB | 50% |
| Lab worker plus its spawned calculation | 600 MiB | 60%; Nice=10 |
| Keeper gateway, one uvicorn worker | 400 MiB | 50% |
| Existing services + kernel | Roughly 0.7 GiB currently used; retain headroom | Existing configuration |
| Added swap | 2 GiB disk, swappiness=10 | Not extra CPU or RAM |

The four memory ceilings total **4000 MiB**, exceeding the server's 3.7 GiB RAM even
before existing services. They are independent ceilings, not reservations or a safe
simultaneous-use budget. CPU quotas total 330% on a 200% host and likewise do not
reserve capacity for production. One model/one generation, short queues, serial Lab
work, and swap reduce contention but cannot guarantee acceptable latency or prevent
system-wide memory pressure. `OOMScoreAdjust=500` makes Ollama a preferred OOM victim;
swapping may make inference slow. Context/KV overhead and CPU latency are unmeasured.
Watch existing production latency, memory pressure, swap use and journal OOM events
during the smoke test. If pressure appears, stop DKP/Ollama and have the author decide
whether to change the budget/model/context or approve new resources.

The venv/model/releases/backup growth needs disk space beyond the model
(2,683,398,370 bytes of local manifest-referenced blobs, including the projector) and
2 GiB swap; preflight's 12 GB floor is conservative initial headroom, not a retention
policy. Ollama remains warm for 30 minutes; the gateway's model timeout is documented
as 150 seconds. Successful CPU-only generation on this machine is not established.

## Rollback

Run `bash deploy/server/99_rollback.sh WHAT`. Each operation prints/logs changes.

- `site`: restore the latest successful, not-yet-consumed site backup, removing the
  deployed keeper directory first. On the initial deployment, keeper disappears; if
  there was a prior keeper, that prior directory is restored too. Existing HTML is
  overwritten with its backup, so later unrelated HTML edits must be saved separately.
- `nginx`: restore the latest successful, not-yet-consumed backup. Files originally
  absent are removed (including DKP snippet/limits on first install); previously
  present files are restored, so repeated installations can be unwound safely. Test
  and reload; if that fails, restore pre-rollback nginx files. Entire default-file
  restoration can overwrite later unrelated changes: reconcile those before rollback.
- `app`: stop/disable all three DKP services, retaining units/releases/private data.
  `app VERSION`: VERSION must match the basename of `/opt/dkp-lab/PREVIOUS`; stop
  services, atomically repoint current there, restore its saved corpus, enable/restart,
  and check health. PREVIOUS becomes the release just replaced. Units are the same
  kit configuration; a future deployment with different units or database migrations
  requires a separately reviewed rollback procedure.
- `ollama`: stop/disable Ollama but retain models; print optional full-removal commands
  for operator review. It does not run those removal commands.
- `swap`: remove only kit-owned swap after successful `swapoff`, remove its tagged
  fstab entry, and restore prior swappiness. Stop memory-heavy services first; if
  swapoff cannot succeed, it exits without deleting the active swapfile.
- `all` (also the default): `site`, `nginx`, `app`, `ollama`, in that order. Swap is
  deliberately retained. Missing backups or failed steps stop the sequence; use
  individual targets for a partial deployment. Repeated site/nginx rollback walks
  backward through backups; it is not a no-op.

## Local validation of this kit

Only syntax checks should be run during kit authoring, never the deployment scripts:

```bash
find deploy -name '*.sh' -print0 | while IFS= read -r -d '' script; do bash -n "$script"; done
if command -v shellcheck >/dev/null; then
  shellcheck -x -P deploy/server deploy/server/*.sh deploy/local/*.sh
fi
```

All files use LF endings. Syntax checks do not validate nginx on the destination,
systemd runtime behavior, remote dependencies, model performance, site injector
behavior on the deployed pages, or connectivity. Local packaging and syntax checks
do not establish installation, load tolerance or rollback on the server; B3 and release
remain incomplete until those runtime checks pass.


## Model identity and validation limits (KT9 review)

KT10 adds isolated users and read-only paths; see the implementation notes below.

Local `ollama show qwen3.5:2b` on 2026-10-17 reports **Q8_0**. The exact command output,
manifest, layer sizes and full manifest digest are retained in
[`keeper/model-metadata.json`](../keeper/model-metadata.json). Manifest SHA-256:
`ae1e257587aba65399b17e22000128fae7d5e9ae02ecc300cb9106c461eaf494`;
model layer SHA-256: `e8bf47d40c5ba68baf8f3e503ee36710da6e8641cb0a670a508cff5b3f0cfbf7`.
The local layer matches the KT9 pin. Before installation compare both actual model
metadata and the retained evaluation identity; a tag alone is insufficient. Disk size
is not inference RAM. About 20 seconds and a 1.3–1.5× Genoa speedup remain hypotheses;
limiting the local CPU to two threads does not emulate the server's two vCPUs.

The reported 29/36 and 31/36 are heuristic scores on a fixed eval set. Six 2b runs
used deterministic intake and have `model_digest: null`; these are not 36 independent
language-model quality checks. The selected 2b scored 0/3 on the definition and F-001
questions: require a correct sourced answer or an honest handoff to the source.
The current `/explain` is also deterministic and records a null model digest.

Public corpus 839086c3df09 was reproduced without Russian search keys. Its Russian
queries for the definition and DTI found no sources. The KT9 archive contained only
the manifest for private-key configuration 9af06b7a5ce9; independent reconstruction
requires that private input or reproducible keys from permitted sources. Verify Russian
retrieval against the actual deployed corpus and retain its identity and permitted inputs.

General open-author-question notices depend on retrieval. S-LAB-08/work_cycle adds
explicit provision bindings for known UNRESOLVED Q-012 and Q-013 from the pinned
corpus; this neither chooses an interpretation nor guarantees detection of every
related question. See the Keeper API contract for the exact scope. Offline fault
injection tests verify service behavior, not how often a real model makes an error.

## KT10 isolation and rollback (2026-10-20)

The installer remains `admin`; runtime accounts never receive sudo. Keeper runs as
`dkpkeeper` (nologin, private primary group, supplementary `dkplab` for corpus reads).
API/worker use `dkplab`; their state directory is mode 0700, so group membership does
not disclose SQLite/store/secret. Corpus and code parents belong to root. All units
mount code/corpus read-only and have empty capability sets and NoNewPrivileges.
Keeper cannot access Lab state, web-root, SSH configuration or deployment backups;
its network policy allows only loopback. Reports pass through the token-authorized API.

Ollama has its own user, cloud disabled and loopback bind. Step 20 temporarily permits
administrator-triggered model installation, then makes models root-owned/read-only
and restricts networking to localhost. Verify systemd controls on the actual Ubuntu
host, including IPAddressDeny enforcement; static tests are not runtime evidence.
Step 90 checks private HTTPS paths, corpus reads, protected parents and Lab-state
denial without printing secrets. Repeat inside the actual units; confirm log writes
and continued report/calculation operation before acceptance.

Each isolated release saves its units and corpus. Rollback restores both with root
ownership and 0640 corpus permissions. Legacy shared-user releases are rejected as
rollback targets; `99_rollback.sh app` stops new services while retaining data.
Exercise rollback to a known isolated release on an operator test host before claiming
deployed rollback readiness.

This task forbids commits and network/SSH: the dirty worktree is a review candidate,
not a clean release. The release builder must keep rejecting it. After owner review
and commit, use the command above and numbered steps, retaining all seven SHA256SUMS
entries. No model/server latency, systemd runtime or live 51-page result was measured.
Historical browser evidence is `KEEPER/e2e_browser/e2e.json` in the checkpoint archive,
not new evidence for this candidate. Local evidence is under `simulation/outputs/kt10-*`;
see `keeper/KT10_IMPLEMENTATION.md` for the candidate results.
