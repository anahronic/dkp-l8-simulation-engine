#!/usr/bin/env bash
set -euo pipefail
# Deliberately does not call init_changes: this step is read-only.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
require_admin
failed=0
for command in bash sudo python3 curl tar gzip sha256sum systemctl nginx ss free df \
    uptime awk sed grep find sort tee install cp mv ln readlink mktemp flock \
    fallocate chmod mkswap swapon swapoff sysctl getent useradd id date sleep \
    touch rm cat chown stat cut; do
    if ! command -v "$command" >/dev/null; then
        note "BLOCKER: missing command $command"
        failed=1
    fi
done
(( failed == 0 )) || exit 1
note 'Read-only capacity and existing service checks'
free -h
swapon --show
df -h /
uptime
ss -ltn
available=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
disk=$(df -Pk / | awk 'NR==2 {print $4}')
if (( available < 2500000 )); then note 'BLOCKER: less than 2.5 GB available RAM'; failed=1; fi
if (( disk < 12000000 )); then note 'BLOCKER: less than 12 GB free disk'; failed=1; fi
if ! python3 -c 'import sys,venv,ensurepip; assert sys.version_info >= (3,12)'; then
    note 'BLOCKER: Python >=3.12 with venv/ensurepip required; install python3-venv manually'
    failed=1
fi
if ! check_ports free 8720 8721 11434; then failed=1; fi
if ! sudo nginx -t; then failed=1; fi
note "Summary: available RAM=${available} KiB; disk=${disk} KiB; blockers=$failed"
note 'No swap is expected initially; step 10 adds it. Port checks intentionally fail after installation.'
note 'No application, nginx, package, or filesystem configuration was changed.'
exit "$failed"
