#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
[[ $# == 1 ]] || die 'Usage: 50_site.sh WIDGET_TARBALL'
tarball=$(readlink -f -- "$1")
check_archive "$tarball"
init_changes
[[ -O /var/www/html && -w /var/www/html && ! -L /var/www/html/keeper ]] || die 'Web root must belong to admin; keeper must not be a symlink'
backup=$STATE/site-$(stamp)
mkdir -m 0700 "$backup"
stage=$(mktemp -d "$STATE/widget.XXXXXXXX")
cleanup() { rm -rf -- "$stage"; }
trap 'rc=$?; cleanup; if (( rc != 0 )); then change "Site staging failed (exit $rc); web root unchanged"; fi' EXIT
tar --extract --gzip --file "$tarball" --directory "$stage" --no-same-owner --no-same-permissions
for required in keeper_inject.py ROUTES.json keeper-loader.js; do
    [[ -f $stage/$required ]] || die "Widget archive missing $required at archive root"
done
python3 "$KIT_DIR/kit_helpers.py" routes "$stage/ROUTES.json" >"$backup/routes.txt"
# HTML outside keeper plus the complete old keeper directory, without duplicates.
(
    cd /var/www/html
    find . -path ./keeper -prune -o -type f -name '*.html' -print0
    if [[ -d keeper ]]; then printf 'keeper\0'; fi
) >"$backup/files.list"
tar --create --gzip --file "$backup.tar.gz" --directory /var/www/html --null --files-from "$backup/files.list"
touch "$backup/READY"
change "Backed up every site HTML file and existing keeper directory to $backup.tar.gz"
recover() {
    local rc=$?
    if (( rc != 0 )); then
        rm -rf -- /var/www/html/keeper
        if tar --extract --gzip --file "$backup.tar.gz" --directory /var/www/html --no-same-owner; then
            touch "$backup/ROLLED_BACK"
            change "Restored site backup $backup.tar.gz after failure"
        else
            change "ERROR: site restore failed; recover from $backup.tar.gz"
        fi
    fi
    cleanup
    exit "$rc"
}
trap recover EXIT
rm -rf -- /var/www/html/keeper
mkdir -m 0755 /var/www/html/keeper
cp -R -- "$stage/." /var/www/html/keeper/
chmod -R u=rwX,go=rX /var/www/html/keeper
change 'Installed widget in /var/www/html/keeper as admin'
python3 /var/www/html/keeper/keeper_inject.py --root /var/www/html --routes /var/www/html/keeper/ROUTES.json
python3 /var/www/html/keeper/keeper_inject.py --root /var/www/html --routes /var/www/html/keeper/ROUTES.json --check
change 'Injected loader and passed injector --check (web-root operations used no sudo)'
