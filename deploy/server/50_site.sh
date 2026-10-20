#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
[[ $# == 1 ]] || die 'Usage: 50_site.sh WIDGET_TARBALL'
tarball=$(readlink -f -- "$1")
check_archive "$tarball"
init_changes
[[ -O /var/www/html && -w /var/www/html && ! -L /var/www/html/keeper ]] || die 'Web root must belong to admin; keeper must not be a symlink'
check_web_readable                                   # never back up (and later restore) a broken web root
backup=$STATE/site-$(stamp)
mkdir -m 0700 "$backup"
stage=$(mktemp -d "$STATE/widget.XXXXXXXX")
cleanup() { rm -rf -- "$stage"; }
trap 'rc=$?; cleanup; if (( rc != 0 )); then change "Site staging failed (exit $rc); web root unchanged"; fi' EXIT
tar --extract --gzip --file "$tarball" --directory "$stage" --no-same-owner --no-same-permissions
for required in keeper_inject.py ROUTES.json keeper-loader.js protocol-lab/index.html; do
    [[ -f $stage/$required ]] || die "Widget archive missing $required at archive root"
done
python3 "$KIT_DIR/kit_helpers.py" routes "$stage/ROUTES.json" >"$backup/routes.txt"
# HTML outside keeper and the lab page, plus the complete old keeper and lab directories, without duplicates.
(
    cd /var/www/html
    find . \( -path ./keeper -o -path ./projects/protocol-lab \) -prune -o -type f -name '*.html' -print0
    if [[ -d keeper ]]; then printf 'keeper\0'; fi
    if [[ -d projects/protocol-lab ]]; then printf 'projects/protocol-lab\0'; fi
) >"$backup/files.list"
tar --create --gzip --file "$backup.tar.gz" --directory /var/www/html --null --files-from "$backup/files.list"
touch "$backup/READY"
change "Backed up every site HTML file and existing keeper directory to $backup.tar.gz"
recover() {
    local rc=$?
    if (( rc != 0 )); then
        rm -rf -- /var/www/html/keeper /var/www/html/projects/protocol-lab
        if restore_site "$backup.tar.gz"; then
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
rm -rf -- /var/www/html/keeper /var/www/html/projects/protocol-lab
mkdir -p -m 0755 /var/www/html/keeper /var/www/html/projects
cp -R -- "$stage/protocol-lab" /var/www/html/projects/protocol-lab
rm -rf -- "$stage/protocol-lab"
cp -R -- "$stage/." /var/www/html/keeper/
chmod -R u=rwX,go=rX /var/www/html/keeper /var/www/html/projects/protocol-lab
change 'Installed widget in /var/www/html/keeper and the lab page in /var/www/html/projects/protocol-lab as admin'
# Live pages are kept as they are (they are newer than the site branch); only the loader tag is added to each route file.
mapfile -d '' routes < <(python3 -c 'import json,sys; [print(r["file"], end="\0") for r in json.load(open(sys.argv[1]))["routes"]]' /var/www/html/keeper/ROUTES.json)
python3 /var/www/html/keeper/keeper_inject.py /var/www/html "${routes[@]}"
python3 /var/www/html/keeper/keeper_inject.py --check --routes /var/www/html/keeper/ROUTES.json /var/www/html
check_web_readable
change 'Injected loader and passed injector --check (web-root operations used no sudo)'
