#!/usr/bin/env bash
# Installs a Protocol Lab release (API + serial worker). The Keeper of Knowledge was retired on 2026-11-17:
# this step installs no corpus, no Keeper account and no Keeper service, and needs no local model.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
[[ $# == 2 ]] || die 'Usage: 30_app.sh RELEASE_TARBALL VERSION'
tarball=$(readlink -f -- "$1")
version=$2
[[ $version =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,100}$ && $version != *..* ]] || die 'Unsafe VERSION'
[[ -f $tarball ]] || die 'Release tarball must exist'
check_archive "$tarball"
init_changes
base=/opt/dkp-lab
release=$base/releases/$version
release_hash=$(sha256sum "$tarball" | awk '{print $1}')
if ! getent passwd dkplab >/dev/null; then
    sudo useradd --system --user-group --home-dir /var/lib/dkp-lab --no-create-home --shell /usr/sbin/nologin dkplab
    change 'Created system user/group dkplab with no login shell'
fi
[[ $(getent passwd dkplab | cut -d: -f7) == /usr/sbin/nologin ]] || die 'Existing dkplab account has an unexpected shell'
# Never grant installer privileges to runtime. Reject pre-existing sudo rules too.
for group in $(id -nG dkplab); do
    [[ $group == dkplab ]] || die "Unexpected runtime group: dkplab / $group"
done
if sudo -l -U dkplab 2>/dev/null | grep -Eq '^[[:space:]]*\('; then die 'Runtime account has sudo rules: dkplab'; fi
sudo install -d -m 0755 "$base" "$base/releases"
if sudo test -e "$release/.dkp-ready"; then
    [[ $(sudo cat "$release/.dkp-ready") == "$release_hash" ]] || die 'VERSION already exists with different artifacts'
    change "Reusing verified release $version"
else
    if sudo test -e "$release"; then
        die "Incomplete release $release exists; inspect and remove it manually before retrying"
    fi
    sudo install -d -m 0755 "$release"
    change "Extracting release into $release"
    sudo tar --extract --gzip --file "$tarball" --directory "$release" --no-same-owner --no-same-permissions
    for required in requirements-server.txt requirements.txt lab_server/app.py lab_server/worker.py; do
        sudo test -f "$release/$required" || die "Release is missing $required; no service switch performed"
    done
    sudo /usr/bin/python3 -m venv "$release/venv"
    sudo "$release/venv/bin/python" -m pip install -r "$release/requirements-server.txt"
    sudo chown -R root:root "$release"
    sudo chmod -R u=rwX,go=rX "$release"
    printf '%s\n' "$release_hash" | sudo tee "$release/.dkp-ready" >/dev/null
    change "Created venv and installed requirements-server.txt in $release"
fi
sudo install -d -m 0755 -o root -g root /var/lib/dkp-lab
sudo install -d -m 0700 -o dkplab -g dkplab /var/lib/dkp-lab/lab
old=''
if sudo test -L "$base/current"; then
    old=$(readlink -f "$base/current")
    [[ $old == "$base/releases/"* ]] || die 'current points outside releases'
elif sudo test -e "$base/current"; then
    die '/opt/dkp-lab/current exists and is not a symlink'
fi
# Stop old processes before changing current; never mix code generations.
for service in "${SERVICES[@]}"; do
    if systemctl cat "$service" >/dev/null 2>&1; then sudo systemctl stop "$service"; fi
done
change 'Stopped existing Lab services before switching code'
if [[ -n $old && $old != "$release" ]]; then
    printf '%s\n' "$old" | sudo tee "$base/PREVIOUS.new" >/dev/null
    sudo mv -f "$base/PREVIOUS.new" "$base/PREVIOUS"
fi
atomic_link "$release" "$base/current"
change "Switched current to $version; previous=${old:-none}"
for service in "${SERVICES[@]}"; do
    sudo install -m 0644 "$KIT_DIR/units/$service" "/etc/systemd/system/$service"
    sudo install -D -m 0644 "$KIT_DIR/units/$service" "$release/.dkp-units/$service"
done
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICES[@]}"
sudo systemctl restart "${SERVICES[@]}"
change 'Installed units and enabled/restarted the Lab services'
health 8720 lab || die 'Lab health failed; use 99_rollback.sh app VERSION to restore PREVIOUS'
for service in "${SERVICES[@]}"; do
    sudo systemctl is-active --quiet "$service"
done
check_ports loopback 8720
change "Release $version passed local health and bind checks"
