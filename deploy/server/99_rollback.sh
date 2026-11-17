#!/usr/bin/env bash
# Rolls back one deployment step of the Protocol Lab kit. The Keeper of Knowledge (and its local model runtime)
# was retired on 2026-11-17: no rollback target restarts it; its recovery material is outside the kit.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
[[ $# -le 2 ]] || die 'Usage: 99_rollback.sh [site|nginx|app [VERSION]|swap|all]'
what=${1:-all}
case $what in site|nginx|app|swap|all) ;; *) die 'Unknown rollback target' ;; esac
[[ $# -lt 2 || $what == app ]] || die 'VERSION is only valid with app'
init_changes
site() {
    local backup
    backup=$(latest_backup site)
    [[ -f $backup.tar.gz && ! -L /var/www/html/projects/protocol-lab ]] || die 'Missing archive or unexpected lab page symlink'
    local listing
    listing=$(tar -tzf "$backup.tar.gz")             # also verifies the archive; no early-exit pipe under pipefail
    if grep -Eq '^(\./)?keeper/' <<<"$listing"; then
        die "$backup predates the Keeper retirement (2026-11-17); restoring it would bring back the widget"
    fi
    rm -rf -- /var/www/html/projects/protocol-lab
    restore_site "$backup.tar.gz"
    check_web_readable
    touch "$backup/ROLLED_BACK"
    change "Removed the deployed lab page directory and restored the prior one from $backup.tar.gz"
}
nginx() {
    local backup rescue name
    backup=$(latest_backup nginx)
    if grep -q 'dkp-lab-keeper\.conf' "$backup/default"; then
        die "$backup predates the Keeper retirement (2026-11-17); restore it manually only if that is intended"
    fi
    rescue=$STATE/nginx-rollback-rescue-$(stamp)
    mkdir -m 0700 "$rescue"
    backup_file /etc/nginx/sites-enabled/default "$rescue/default"
    backup_file /etc/nginx/conf.d/dkp-limits.conf "$rescue/dkp-limits.conf"
    for name in dkp-lab.conf dkp-lab-keeper.conf; do
        backup_file "/etc/nginx/snippets/$name" "$rescue/$name"
    done
    restore_nginx "$backup"
    if sudo nginx -t && sudo systemctl reload nginx; then
        touch "$backup/ROLLED_BACK"
        change "Restored nginx from $backup; removed DKP files that were previously absent; tested and reloaded"
    else
        restore_nginx "$rescue"
        sudo nginx -t && sudo systemctl reload nginx
        die "Nginx rollback failed; restored pre-rollback files from $rescue"
    fi
}
app() {
    local target version=${1:-} current service unit
    if [[ -z $version ]]; then
        for service in "${SERVICES[@]}"; do
            if systemctl cat "$service" >/dev/null 2>&1; then
                sudo systemctl disable --now "$service"
            fi
        done
        change 'Stopped/disabled Lab services; retained releases, units, database and store'
        return
    fi
    [[ $version =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,100}$ && $version != *..* ]] || die 'Unsafe VERSION'
    target=$(sudo cat /opt/dkp-lab/PREVIOUS)
    [[ $target == "/opt/dkp-lab/releases/$version" ]] || die 'VERSION must match the release recorded in PREVIOUS'
    sudo test -f "$target/.dkp-ready" && sudo test -f "$target/lab_server/app.py" || die 'Previous release is incomplete'
    current=$(readlink -f /opt/dkp-lab/current)
    sudo systemctl stop "${SERVICES[@]}"
    # Lab code from any release runs under the kit's current Lab units: the Keeper-era units also mounted the
    # retired corpus directory read-only (which no longer exists) and are never reinstalled.
    for service in "${SERVICES[@]}"; do
        unit=$KIT_DIR/units/$service
        if sudo test -f "$target/.dkp-units/$service" && ! sudo grep -q 'dkp-corpus\|dkp-keeper' "$target/.dkp-units/$service"; then
            unit=$target/.dkp-units/$service
        fi
        sudo install -m 0644 "$unit" "/etc/systemd/system/$service"
    done
    sudo systemctl daemon-reload
    atomic_link "$target" /opt/dkp-lab/current
    printf '%s\n' "$current" | sudo tee /opt/dkp-lab/PREVIOUS.new >/dev/null
    sudo mv -f /opt/dkp-lab/PREVIOUS.new /opt/dkp-lab/PREVIOUS
    sudo systemctl enable "${SERVICES[@]}"
    sudo systemctl restart "${SERVICES[@]}"
    change "Restored Lab release $version; previous is now $current"
    health 8720 lab
    for service in "${SERVICES[@]}"; do
        sudo systemctl is-active --quiet "$service"
    done
    check_ports loopback 8720
}
swap() {
    [[ -f $STATE/swap-owned ]] || die 'No kit-owned swap; refusing to remove unrelated swap'
    if swapon --show=NAME --noheadings | grep -Fxq /swapfile; then
        sudo swapoff /swapfile
        change 'Disabled /swapfile (swapoff succeeded)'
    fi
    sudo sed -i '\|^/swapfile none swap sw 0 0 # dkp-deploy$|d' /etc/fstab
    sudo rm -f /swapfile
    restore_file "$STATE/swap-sysctl.before" /etc/sysctl.d/90-dkp-swap.conf
    sudo sysctl -w "vm.swappiness=$(cat "$STATE/swappiness.before")"
    rm -f "$STATE/swap-owned" "$STATE/swap-sysctl.before.absent"
    change 'Removed kit-owned swapfile/fstab entry and restored previous swappiness configuration'
}
case $what in
    all) site; nginx; app ;;
    app) app "${2:-}" ;;
    *) "$what" ;;
esac
