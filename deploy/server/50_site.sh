#!/usr/bin/env bash
# Installs the Protocol Lab page (/projects/protocol-lab/) with the browser bundle built from the same engine
# revision. Since the Keeper's retirement (2026-11-17) no widget is installed and no page is modified.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
[[ $# == 1 ]] || die 'Usage: 50_site.sh LABPAGE_TARBALL'
tarball=$(readlink -f -- "$1")
check_archive "$tarball"
init_changes
[[ -O /var/www/html && -w /var/www/html && ! -L /var/www/html/projects/protocol-lab ]] || die 'Web root must belong to admin; the lab page must not be a symlink'
check_web_readable                                   # never back up (and later restore) a broken web root
backup=$STATE/site-$(stamp)
mkdir -m 0700 "$backup"
stage=$(mktemp -d "$STATE/labpage.XXXXXXXX")
cleanup() { rm -rf -- "$stage"; }
trap 'rc=$?; cleanup; if (( rc != 0 )); then change "Lab page staging failed (exit $rc); web root unchanged"; fi' EXIT
tar --extract --gzip --file "$tarball" --directory "$stage" --no-same-owner --no-same-permissions
for required in index.html dist/lab-bundle.zip; do
    [[ -f $stage/$required ]] || die "Lab page archive missing $required at archive root"
done
if grep -rlq 'keeper-loader' "$stage"; then die 'Lab page archive still references the retired Keeper loader'; fi
(
    cd /var/www/html
    if [[ -d projects/protocol-lab ]]; then printf 'projects/protocol-lab\0'; fi
) >"$backup/files.list"
tar --create --gzip --file "$backup.tar.gz" --directory /var/www/html --null --files-from "$backup/files.list"
touch "$backup/READY"
change "Backed up the existing lab page directory to $backup.tar.gz"
recover() {
    local rc=$?
    if (( rc != 0 )); then
        rm -rf -- /var/www/html/projects/protocol-lab
        if restore_site "$backup.tar.gz"; then
            touch "$backup/ROLLED_BACK"
            change "Restored lab page backup $backup.tar.gz after failure"
        else
            change "ERROR: lab page restore failed; recover from $backup.tar.gz"
        fi
    fi
    cleanup
    exit "$rc"
}
trap recover EXIT
rm -rf -- /var/www/html/projects/protocol-lab
mkdir -p -m 0755 /var/www/html/projects
cp -R -- "$stage" /var/www/html/projects/protocol-lab
chmod -R u=rwX,go=rX /var/www/html/projects/protocol-lab
check_web_readable
change 'Installed the lab page in /var/www/html/projects/protocol-lab as admin (web-root operations used no sudo)'
