#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
init_changes
sudo nginx -t
backup=$STATE/nginx-$(stamp)
mkdir -m 0700 "$backup"
backup_file /etc/nginx/sites-enabled/default "$backup/default"
[[ ! -f $backup/default.absent ]] || die 'Missing /etc/nginx/sites-enabled/default'
backup_file /etc/nginx/conf.d/dkp-limits.conf "$backup/dkp-limits.conf"
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
sudo install -m 0644 "$KIT_DIR/nginx/dkp-limits.conf" /etc/nginx/conf.d/dkp-limits.conf
sudo install -m 0644 "$KIT_DIR/nginx/dkp-lab-keeper.conf" /etc/nginx/snippets/dkp-lab-keeper.conf
# tee follows sites-enabled/default's symlink, retaining the Certbot file/link layout.
sudo cat "$backup/candidate" | sudo tee /etc/nginx/sites-enabled/default >/dev/null
sudo nginx -t
sudo systemctl reload nginx
change 'Installed DKP nginx zones/snippet and exactly one include; nginx test and reload passed'
