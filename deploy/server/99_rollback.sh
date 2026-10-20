#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
[[ $# -le 2 ]] || die 'Usage: 99_rollback.sh [site|nginx|app [VERSION]|ollama|swap|all]'
what=${1:-all}
case $what in site|nginx|app|ollama|swap|all) ;; *) die 'Unknown rollback target' ;; esac
[[ $# -lt 2 || $what == app ]] || die 'VERSION is only valid with app'
init_changes
site() {
    local backup
    backup=$(latest_backup site)
    [[ -f $backup.tar.gz && ! -L /var/www/html/keeper ]] || die 'Missing archive or unexpected keeper symlink'
    tar -tzf "$backup.tar.gz" >/dev/null
    rm -rf -- /var/www/html/keeper /var/www/html/projects/protocol-lab
    restore_site "$backup.tar.gz"
    check_web_readable
    touch "$backup/ROLLED_BACK"
    change "Removed deployed keeper and lab-page directories and restored HTML/prior keeper from $backup.tar.gz"
}
nginx() {
    local backup rescue
    backup=$(latest_backup nginx)
    rescue=$STATE/nginx-rollback-rescue-$(stamp)
    mkdir -m 0700 "$rescue"
    backup_file /etc/nginx/sites-enabled/default "$rescue/default"
    backup_file /etc/nginx/conf.d/dkp-limits.conf "$rescue/dkp-limits.conf"
    backup_file /etc/nginx/snippets/dkp-lab-keeper.conf "$rescue/dkp-lab-keeper.conf"
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
    local target version=${1:-} current service
    if [[ -z $version ]]; then
        for service in "${SERVICES[@]}"; do
            if systemctl cat "$service" >/dev/null 2>&1; then
                sudo systemctl disable --now "$service"
            fi
        done
        change 'Stopped/disabled DKP services; retained releases, units, corpus, database and store'
        return
    fi
    [[ $version =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,100}$ && $version != *..* ]] || die 'Unsafe VERSION'
    target=$(sudo cat /opt/dkp-lab/PREVIOUS)
    [[ $target == "/opt/dkp-lab/releases/$version" ]] || die 'VERSION must match the release recorded in PREVIOUS'
    sudo test -f "$target/.dkp-ready" && sudo test -f "$target/.dkp-corpus.jsonl" || die 'Previous release is incomplete'
    # Old shared-user units are not an acceptable rollback target after isolation.
    for service in "${SERVICES[@]}"; do
        sudo test -f "$target/.dkp-units/$service" || die 'Previous release lacks isolated units; stop services instead'
    done
    sudo grep -q '^User=dkpkeeper$' "$target/.dkp-units/dkp-keeper.service" || die 'Unsafe legacy Keeper unit'
    current=$(readlink -f /opt/dkp-lab/current)
    sudo systemctl stop "${SERVICES[@]}"
    sudo install -d -o root -g dkplab -m 0750 /var/lib/dkp-corpus
    sudo install -o root -g dkplab -m 0640 "$target/.dkp-corpus.jsonl" /var/lib/dkp-corpus/corpus.jsonl.new
    sudo mv -f /var/lib/dkp-corpus/corpus.jsonl.new /var/lib/dkp-corpus/corpus.jsonl
    for service in "${SERVICES[@]}"; do
        sudo install -m 0644 "$target/.dkp-units/$service" "/etc/systemd/system/$service"
    done
    sudo systemctl daemon-reload
    atomic_link "$target" /opt/dkp-lab/current
    printf '%s\n' "$current" | sudo tee /opt/dkp-lab/PREVIOUS.new >/dev/null
    sudo mv -f /opt/dkp-lab/PREVIOUS.new /opt/dkp-lab/PREVIOUS
    sudo systemctl enable "${SERVICES[@]}"
    sudo systemctl restart "${SERVICES[@]}"
    change "Restored release $version and matching corpus; previous is now $current"
    health 8720 lab && health 8721 keeper
    for service in "${SERVICES[@]}"; do
        sudo systemctl is-active --quiet "$service"
    done
    check_ports loopback 8720 8721
}
ollama() {
    if systemctl cat ollama.service >/dev/null 2>&1; then sudo systemctl disable --now ollama.service; fi
    change 'Stopped/disabled Ollama; kept binaries, unit, user, and model files'
    cat <<'EOF'
Optional full removal after reviewing paths (NOT executed):
  sudo rm -f /etc/systemd/system/ollama.service
  sudo rm -rf /etc/systemd/system/ollama.service.d
  sudo systemctl daemon-reload
  command -v ollama  # inspect the installed binary path, then remove that exact file
  sudo rm -rf /usr/local/lib/ollama /usr/lib/ollama
  sudo rm -rf /usr/share/ollama  # destroys model files
  sudo userdel ollama
  sudo groupdel ollama  # only if still present and unused
EOF
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
    all) site; nginx; app; ollama ;;
    app) app "${2:-}" ;;
    *) "$what" ;;
esac
