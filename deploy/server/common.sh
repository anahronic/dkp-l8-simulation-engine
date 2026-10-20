#!/usr/bin/env bash
# Shared helpers; source from a server script, never execute as a deployment step.
set -euo pipefail
export LC_ALL=C.UTF-8
export PYTHONDONTWRITEBYTECODE=1
umask 077
KIT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
STATE=/var/lib/dkp-deploy
SERVICES=(dkp-lab-api.service dkp-lab-worker.service dkp-keeper.service)

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
note() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }
change() { note "$*" | tee -a "$STATE/CHANGES.log"; }
require_admin() {
    [[ $(id -un) == admin ]] || die 'Run as admin, not root; scripts call sudo themselves.'
    sudo -n true || die 'Passwordless sudo is required.'
}
init_changes() {
    require_admin
    sudo install -d -m 0700 -o admin -g "$(id -gn)" "$STATE"
    touch "$STATE/CHANGES.log"
    chmod 0600 "$STATE/CHANGES.log"
    exec 9>"$STATE/deploy.lock"
    flock -n 9 || die 'Another DKP deployment step is running.'
    trap 'rc=$?; if (( rc != 0 )); then change "FAILED ${0##*/} (exit $rc); inspect state before retrying"; fi' EXIT
}
stamp() { date -u +%Y%m%dT%H%M%S.%NZ; }
check_archive() { python3 "$KIT_DIR/kit_helpers.py" archive "$1"; }
check_ports() {
    python3 "$KIT_DIR/kit_helpers.py" ports "$@"
}
health() {
    local port=$1 prefix=$2 i
    for ((i=0; i<60; i++)); do
        if curl --noproxy '*' -fsS --connect-timeout 2 --max-time 5 \
            "http://127.0.0.1:$port/api/$prefix/v1/health" 2>/dev/null |
            python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("ok") is True else 1)' 2>/dev/null; then
            note "$prefix health passed on $port"
            return 0
        fi
        sleep 2
    done
    return 1
}
atomic_link() {
    local target=$1 link=$2
    sudo ln -s -- "$target" "$link.new.$$"
    sudo mv -Tf -- "$link.new.$$" "$link"
}
# Back up file contents, preserving an existing destination symlink on restoration.
backup_file() {
    local source=$1 backup=$2
    if sudo test -e "$source"; then
        sudo cp -pL -- "$source" "$backup"
    elif sudo test -L "$source"; then
        die "Dangling symlink: $source"
    else
        touch "$backup.absent"
    fi
}
restore_file() {
    local backup=$1 target=$2
    if [[ -f $backup.absent ]]; then
        sudo rm -f -- "$target"
    else
        sudo cp --preserve=mode,ownership,timestamps -- "$backup" "$target"
    fi
}
restore_nginx() {
    local backup=$1
    restore_file "$backup/default" /etc/nginx/sites-enabled/default
    restore_file "$backup/dkp-limits.conf" /etc/nginx/conf.d/dkp-limits.conf
    restore_file "$backup/dkp-lab-keeper.conf" /etc/nginx/snippets/dkp-lab-keeper.conf
}
latest_backup() {
    local kind=$1 path
    while IFS= read -r path; do
        if [[ -f $path/READY && ! -e $path/ROLLED_BACK ]]; then
            printf '%s\n' "$path"
            return 0
        fi
    done < <(find "$STATE" -maxdepth 1 -type d -name "$kind-*" | sort -r)
    die "No unconsumed $kind backup exists"
}
# nginx (www-data) reads the web root as "other"; the kit's umask 077 must never leak into served files.
check_web_readable() {
    local bad
    bad=$(find /var/www/html -type f ! -perm -o=r -print -quit)
    [[ -z $bad ]] || die "Web file not readable by nginx: $bad"
}
# Restore keeps the archived modes exactly (without -p, tar applies the kit's umask 077 and pages turn 0600 / HTTP 403).
restore_site() {
    tar --extract --gzip --file "$1" --directory /var/www/html --no-same-owner --preserve-permissions
}
