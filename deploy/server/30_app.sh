#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
[[ $# == 3 ]] || die 'Usage: 30_app.sh RELEASE_TARBALL CORPUS_JSONL VERSION'
tarball=$(readlink -f -- "$1")
corpus=$(readlink -f -- "$2")
version=$3
[[ $version =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,100}$ && $version != *..* ]] || die 'Unsafe VERSION'
[[ -f $tarball && -s $corpus ]] || die 'Release and nonempty corpus must exist'
check_archive "$tarball"
init_changes
base=/opt/dkp-lab
release=$base/releases/$version
release_hash=$(sha256sum "$tarball" | awk '{print $1}')
corpus_hash=$(sha256sum "$corpus" | awk '{print $1}')
if ! getent passwd dkplab >/dev/null; then
    sudo useradd --system --user-group --home-dir /var/lib/dkp-lab --no-create-home --shell /usr/sbin/nologin dkplab
    change 'Created system user/group dkplab with no login shell'
fi
[[ $(getent passwd dkplab | cut -d: -f7) == /usr/sbin/nologin ]] || die 'Existing dkplab account has an unexpected shell'
sudo install -d -m 0755 "$base" "$base/releases"
if sudo test -e "$release/.dkp-ready"; then
    [[ $(sudo cat "$release/.dkp-ready") == "$release_hash $corpus_hash" ]] || die 'VERSION already exists with different artifacts'
    change "Reusing verified release $version"
else
    if sudo test -e "$release"; then
        die "Incomplete release $release exists; inspect and remove it manually before retrying"
    fi
    sudo install -d -m 0755 "$release"
    change "Extracting release into $release"
    sudo tar --extract --gzip --file "$tarball" --directory "$release" --no-same-owner --no-same-permissions
    for required in requirements-server.txt requirements.txt lab_server/app.py lab_server/worker.py keeper/gateway.py; do
        sudo test -f "$release/$required" || die "Release is missing $required; no service switch performed"
    done
    sudo /usr/bin/python3 -m venv "$release/venv"
    sudo "$release/venv/bin/python" -m pip install -r "$release/requirements-server.txt"
    sudo chown -R root:root "$release"
    sudo chmod -R u=rwX,go=rX "$release"
    printf '%s %s\n' "$release_hash" "$corpus_hash" | sudo tee "$release/.dkp-ready" >/dev/null
    change "Created venv and installed requirements-server.txt in $release"
fi
# Save the corpus with its release so app rollback restores the matching corpus too.
sudo install -o root -g root -m 0640 "$corpus" "$release/.dkp-corpus.jsonl"
sudo install -d -m 0700 -o dkplab -g dkplab /var/lib/dkp-lab /var/lib/dkp-lab/lab /var/lib/dkp-lab/keeper
old=''
if sudo test -L "$base/current"; then
    old=$(readlink -f "$base/current")
    [[ $old == "$base/releases/"* ]] || die 'current points outside releases'
elif sudo test -e "$base/current"; then
    die '/opt/dkp-lab/current exists and is not a symlink'
fi
# Stop old processes before changing corpus/current; never mix code generations.
for service in "${SERVICES[@]}"; do
    if systemctl cat "$service" >/dev/null 2>&1; then sudo systemctl stop "$service"; fi
done
change 'Stopped existing DKP services before switching corpus and code'
sudo install -o dkplab -g dkplab -m 0640 "$corpus" /var/lib/dkp-lab/keeper/corpus.jsonl.new
sudo mv -f /var/lib/dkp-lab/keeper/corpus.jsonl.new /var/lib/dkp-lab/keeper/corpus.jsonl
if [[ -n $old && $old != "$release" ]]; then
    printf '%s\n' "$old" | sudo tee "$base/PREVIOUS.new" >/dev/null
    sudo mv -f "$base/PREVIOUS.new" "$base/PREVIOUS"
fi
atomic_link "$release" "$base/current"
change "Switched current to $version; previous=${old:-none}; installed private data directories and corpus"
for service in "${SERVICES[@]}"; do
    sudo install -m 0644 "$KIT_DIR/units/$service" "/etc/systemd/system/$service"
done
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICES[@]}"
sudo systemctl restart "${SERVICES[@]}"
change 'Installed units and enabled/restarted the three DKP services'
health 8720 lab || die 'Lab health failed; use 99_rollback.sh app VERSION to restore PREVIOUS'
health 8721 keeper || die 'Keeper health failed; use 99_rollback.sh app VERSION to restore PREVIOUS'
for service in "${SERVICES[@]}"; do
    sudo systemctl is-active --quiet "$service"
done
check_ports loopback 8720 8721
change "Release $version passed local health and bind checks"
