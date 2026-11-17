# DKP Protocol Lab deployment kit

Operator-run kit for the existing Ubuntu 24.04 x86_64 server (dikenocracy.com). Creating a release does not deploy
anything. Run the numbered server scripts **as `admin`** with `bash`; each calls passwordless `sudo` only where
needed. Never run with `bash -x`. Keep the whole `deploy/` directory together: scripts source `server/common.sh`
and use `server/kit_helpers.py`.

**Keeper of Knowledge retired (owner decision, 2026-11-17).** The AI reference assistant, its corpus, widget, local
model runtime (Ollama) and service account were removed from production and from this branch. Its last release is
tag `release-c9909c6-1d40ec7b8562`; source and restoration notes stay in Git history (`git show
release-c9909c6-1d40ec7b8562:keeper/README.md`, `…:deploy/README.md`). Encrypted non-public recovery material
(corpus, units, nginx snippets) is kept outside Git (`KEEPER_RETIREMENT_2026-11-17.md` in the project folder). This
kit installs **only the Protocol Lab**; it never installs, starts or health-checks the Keeper, and the former public
prefixes `/api/keeper/` and `/keeper/` answer **410 Gone**.

The kit provisions no paid resources, does not change DNS, firewall or SSH, and does not restart unrelated
applications (PostgreSQL, pm2, fail2ban, the feedback service). It reloads nginx only after `nginx -t` passes.

## What a release contains

`deploy/local/make_release.sh ENGINE_DIR SITE_DIR OUT_DIR` (clean trees; `SITE_DIR` = the site repository
`anahronic/Dikenocracy`) writes, with `VERSION = <engine short sha>-lab`:

| File | Content |
|---|---|
| `engine-<V>.tar.gz` | `git archive` of the engine commit (Lab API `lab_server/`, worker, `lab/`, `core/`, `simulation/`) |
| `labpage-<V>.tar.gz` | `website/projects/protocol-lab/` with `dist/` rebuilt from the same engine commit (`lab.tools.build_web_bundle`); rejected if it still references the Keeper loader or contains private markers (`check_public.py`) |
| `VERSION`, `REVISIONS` (engine + site commits), `CHANGES.log`, `SHA256SUMS` | provenance |

Set `PYTHONUTF8=1` on Windows and `PYTHON=<venv python>` if `python3` is not the build interpreter.

## Installed paths

| Path | Owner / mode | Purpose |
|---|---|---|
| `/opt/dkp-lab/releases/<V>/` (+ `venv/`, `.dkp-ready` = release SHA-256, `.dkp-units/`) | root, read-only | code |
| `/opt/dkp-lab/current` → release; `/opt/dkp-lab/PREVIOUS` | root | atomic switch and rollback target |
| `/var/lib/dkp-lab/lab/` (`jobs.sqlite3`, `store/`, `.secret`) | `dkplab` 0700 | job queue and results |
| `/etc/systemd/system/dkp-lab-api.service`, `dkp-lab-worker.service` | root | API on 127.0.0.1:8720 (300 MB, 50 % CPU), serial worker (600 MB, 60 % CPU) |
| `/etc/nginx/snippets/dkp-lab.conf`, `/etc/nginx/conf.d/dkp-limits.conf` | root | `/api/lab/v1/` proxy (2 r/s per visitor), private-path deny, Keeper 410 |
| `/var/www/html/projects/protocol-lab/` | admin, world-readable | Lab page + browser bundle |
| `/var/lib/dkp-deploy/` | admin 0700 | lock, `CHANGES.log`, backups of nginx/site before each change |

## Execution order

```bash
# workstation
PYTHONUTF8=1 bash deploy/local/make_release.sh <engine repo> <site repo> <empty out dir>
# copy the out dir and `git archive HEAD deploy` to /home/admin/releases/<V>/ ; sha256sum -c SHA256SUMS
# server, as admin
bash deploy/server/00_preflight.sh                       # read-only: commands, RAM >= 1 GB, disk >= 3 GB, port 8720 free (fails after install: expected)
bash deploy/server/10_swap.sh                            # optional: 2 GiB kit-owned swap if the host has none
bash deploy/server/30_app.sh $PWD/engine-<V>.tar.gz <V>  # venv, atomic switch, units, local health
bash deploy/server/40_nginx.sh                           # snippet + zone + exactly one include after the mazkira anchor
bash deploy/server/50_site.sh $PWD/labpage-<V>.tar.gz    # Lab page only; no page outside it is modified
PUBLIC_IP=<server IP> bash deploy/server/90_postdeploy_check.sh
```

- **30_app.sh** creates the no-login system user `dkplab` (refuses extra groups or sudo rules), extracts the release
  once (`.dkp-ready` must match the tarball hash on reuse), stops the Lab services, records `PREVIOUS`, switches
  `current`, installs the units from `server/units/`, restarts, and requires `/api/lab/v1/health` and loopback-only
  binding on 8720.
- **40_nginx.sh** backs up `sites-enabled/default`, `dkp-limits.conf`, `dkp-lab.conf` and the Keeper-era
  `dkp-lab-keeper.conf`; `kit_helpers.py nginx-candidate` requires exactly one `include …/mazkira.conf;` in the
  dikenocracy.com HTTPS server block and replaces any previous DKP include (`dkp-lab-keeper.conf` or `dkp-lab.conf`)
  with one `include /etc/nginx/snippets/dkp-lab.conf;`. The old snippet is removed; on any failure the backup is
  restored and nginx re-tested.
- **50_site.sh** backs up the current Lab page directory and installs the new one as `admin`; it refuses an archive
  that references the Keeper loader.
- **90_postdeploy_check.sh** probes private paths (403/404/410), Lab health, the retired Keeper paths (must be 410),
  the Lab page (no Keeper loader), a complete Lab job through the public API (submit → poll → report → export ZIP,
  ids cross-checked), loopback binding of 8720, that the retired ports 8721/11434 do not listen, and public-IP probes
  from the server itself (repeat from an external host before claiming isolation).

## Rollback (`99_rollback.sh`)

| Target | Effect |
|---|---|
| `app` | stop and disable the Lab services (releases, data and units stay) |
| `app <VERSION>` | `VERSION` must be the release in `PREVIOUS`; switch `current` back and restart the Lab services. Keeper-era releases run their Lab code under the kit's current units (their recorded units mounted the retired corpus directory). The Keeper is never restarted. |
| `nginx` | restore the newest unconsumed nginx backup; refuses a backup that still includes `dkp-lab-keeper.conf` (pre-retirement) |
| `site` | restore the newest unconsumed Lab page backup; refuses a pre-retirement backup that contains the Keeper widget |
| `swap` | remove only the kit-owned swap file |
| `all` | `site`, `nginx`, `app` |

## Resource budget

Lab only: API ≤ 300 MB, worker ≤ 600 MB, CPU quotas 50 % / 60 %, one job at a time. The 2 vCPU / 3.7 GB server
previously also carried the Keeper gateway and a 2.7 GB local model; both are gone (see the retirement report for the
measured RAM/disk recovered).

## Local validation

```bash
python deploy/local/run_checks.py <out dir>     # tests/server + full pytest + registry/coverage/trace/calibration checks
PW_DIR=<dir with node_modules/playwright, pyodide> node deploy/local/offline_browser_check.mjs <website> <bundle dir> <out dir>
bash -n deploy/server/*.sh                      # syntax
```

## History

Keeper-era sections of this README (model identity, KT9/KT10 isolation, Ollama installation, widget routes) are in
Git history: `git show release-c9909c6-1d40ec7b8562:deploy/README.md`.
