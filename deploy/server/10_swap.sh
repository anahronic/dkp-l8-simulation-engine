#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
init_changes
if [[ ! -f $STATE/swap-owned ]]; then
    if [[ -n $(swapon --show --noheadings) ]]; then
        change 'Existing swap found; left swap and swappiness unchanged'
        exit 0
    fi
    [[ ! -e /swapfile && ! -L /swapfile ]] || die '/swapfile already exists and is not managed by this kit'
    if grep -Eq '^[[:space:]]*/swapfile[[:space:]]' /etc/fstab; then
        die 'Existing /swapfile fstab entry is not managed by this kit'
    fi
    backup_file /etc/sysctl.d/90-dkp-swap.conf "$STATE/swap-sysctl.before"
    sysctl -n vm.swappiness >"$STATE/swappiness.before"
    touch "$STATE/swap-owned"
    change 'Claimed /swapfile for a 2 GiB swap file; recorded previous swappiness'
fi
if ! swapon --show=NAME --noheadings | grep -Fxq /swapfile; then
    [[ ! -L /swapfile ]] || die '/swapfile must not be a symlink'
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    change 'Created/enabled 2 GiB /swapfile (0600)'
fi
if ! grep -Eq '^[[:space:]]*/swapfile[[:space:]]' /etc/fstab; then
    printf '/swapfile none swap sw 0 0 # dkp-deploy\n' | sudo tee -a /etc/fstab >/dev/null
    change 'Added /swapfile to /etc/fstab once'
fi
printf 'vm.swappiness=10\n' | sudo tee /etc/sysctl.d/90-dkp-swap.conf >/dev/null
sudo sysctl -p /etc/sysctl.d/90-dkp-swap.conf
change 'Set vm.swappiness=10 in /etc/sysctl.d/90-dkp-swap.conf'
