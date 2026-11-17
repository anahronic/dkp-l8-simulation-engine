#!/usr/bin/env bash
# Installs the Lab nginx snippet (dkp-lab.conf, which also answers the retired Keeper prefixes with 410) and the
# Lab rate-limit zone, and points the single DKP include at it. Replaces the Keeper-era dkp-lab-keeper.conf.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
init_changes
sudo nginx -t
backup=$STATE/nginx-$(stamp)
mkdir -m 0700 "$backup"
backup_file /etc/nginx/sites-enabled/default "$backup/default"
[[ ! -f $backup/default.absent ]] || die 'Missing /etc/nginx/sites-enabled/default'
backup_file /etc/nginx/conf.d/dkp-limits.conf "$backup/dkp-limits.conf"
backup_file /etc/nginx/snippets/dkp-lab.conf "$backup/dkp-lab.conf"
backup_file /etc/nginx/snippets/dkp-lab-keeper.conf "$backup/dkp-lab-keeper.conf"
sudo python3 "$KIT_DIR/kit_helpers.py" nginx-candidate "$backup/default" "$backup/candidate"
touch "$backup/READY"
change "Backed up nginx target files to $backup; validated unique HTTPS mazkira anchor"
recover() {
    local rc=$?
    if (( rc != 0 )); then
        restore_nginx "$backup"
        if sudo nginx -t && sudo systemctl reload nginx; then
            touch "$backup/ROLLED_BACK"
            change "Restored nginx backup $backup after failed install/test/reload"
        else
            change "ERROR: restored files from $backup but nginx requires manual inspection"
        fi
    fi
    exit "$rc"
}
trap recover EXIT
sudo install -m 0644 "$KIT_DIR/nginx/dkp-lab.conf" /etc/nginx/snippets/dkp-lab.conf
# tee follows sites-enabled/default's symlink, retaining the Certbot file/link layout.
sudo cat "$backup/candidate" | sudo tee /etc/nginx/sites-enabled/default >/dev/null
# The limits file drops the Keeper zones; nothing references them once the old include is gone.
sudo install -m 0644 "$KIT_DIR/nginx/dkp-limits.conf" /etc/nginx/conf.d/dkp-limits.conf
sudo rm -f /etc/nginx/snippets/dkp-lab-keeper.conf
sudo nginx -t
sudo systemctl reload nginx
change 'Installed the Lab nginx snippet/zone and exactly one include (Keeper prefixes 410); nginx test and reload passed'
