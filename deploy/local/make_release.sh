#!/usr/bin/env bash
# Builds a Protocol Lab release: the engine source archive (Lab API + worker) and the Lab page with the browser
# bundle built from the same engine revision. The Keeper of Knowledge (corpus, widget) was retired on 2026-11-17;
# its last release is tag release-c9909c6-1d40ec7b8562 and its code stays in Git history.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
export LC_ALL=C.UTF-8
umask 077
[[ $# == 3 ]] || { echo 'Usage: make_release.sh ENGINE_DIR SITE_DIR OUT_DIR' >&2; exit 1; }
engine=$(cd -- "$1" && (pwd -W 2>/dev/null || pwd))   # pwd -W: Windows form, as git prints it
site=$(cd -- "$2" && (pwd -W 2>/dev/null || pwd))
kit=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../server" && pwd)
python=${PYTHON:-python3}
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
for command in git "$python" tar gzip sha256sum mktemp; do
    command -v "$command" >/dev/null || die "Missing command: $command"
done
[[ $(git -C "$engine" rev-parse --show-toplevel) == "$engine" ]] || die 'ENGINE_DIR must be the repository root'
[[ -z $(git -C "$engine" status --porcelain --untracked-files=all) ]] || die 'Engine tree is dirty (including untracked files)'
[[ -z $(git -C "$site" status --porcelain --untracked-files=all) ]] || die 'Site tree is dirty'
site_head=$(git -C "$site" rev-parse HEAD)
[[ -f $engine/lab_server/app.py && -f $engine/lab_server/worker.py ]] || die 'ENGINE_DIR lacks lab_server'
page=$site/website/projects/protocol-lab
[[ -f $page/index.html ]] || die 'SITE_DIR must contain website/projects/protocol-lab/index.html'
if grep -rlq 'keeper-loader' "$page"; then die 'The Lab page still references the retired Keeper loader'; fi
mkdir -p -- "$3"
out=$(cd -- "$3" && pwd)
case $out/ in "$engine/"*|"$site/"*) die 'OUT_DIR must be outside both source trees' ;; esac
[[ -z $(find "$out" -mindepth 1 -maxdepth 1 -print -quit) ]] || die 'OUT_DIR must be empty (prevents mixing release artifacts)'
log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$out/CHANGES.log"; }
stage=$(mktemp -d "$out/.stage.XXXXXXXX")
trap 'rc=$?; rm -rf -- "$stage"; if (( rc != 0 )); then log "Release build failed (exit $rc); inspect output and use a fresh OUT_DIR"; fi' EXIT
head=$(git -C "$engine" rev-parse HEAD)
short=$(git -C "$engine" rev-parse --short HEAD)
version=$short-lab
log "Building engine HEAD $head; no network or package installation is performed"
git -C "$engine" archive --format=tar.gz --output="$stage/engine.tar.gz" "$head"
"$python" "$kit/kit_helpers.py" archive "$stage/engine.tar.gz"
mkdir "$stage/labpage"
cp -R -- "$page/." "$stage/labpage/"
# Always ship the bundle built from this engine revision, not a stale site checkout copy.
rm -rf -- "$stage/labpage/dist"
(cd "$engine" && "$python" -m lab.tools.build_web_bundle "$stage/labpage/dist")
[[ -f $stage/labpage/dist/lab-bundle.zip ]] || die 'Lab bundle was not built'
tar --create --gzip --file "$out/labpage-$version.tar.gz" --directory "$stage/labpage" .
"$python" "$kit/kit_helpers.py" archive "$out/labpage-$version.tar.gz"
if ! "$python" "$engine/deploy/local/check_public.py" "$out/labpage-$version.tar.gz"; then
    rm -f -- "$out/labpage-$version.tar.gz"
    die 'Public Lab page archive contains private material'
fi
[[ $(git -C "$engine" rev-parse HEAD) == "$head" && -z $(git -C "$engine" status --porcelain --untracked-files=all) ]] || die 'Engine changed during build'
[[ $(git -C "$site" rev-parse HEAD) == "$site_head" && -z $(git -C "$site" status --porcelain --untracked-files=all) ]] || die 'Site changed during build'
printf 'engine=%s\nsite=%s\n' "$head" "$site_head" >"$out/REVISIONS"
mv -- "$stage/engine.tar.gz" "$out/engine-$version.tar.gz"
printf '%s\n' "$version" >"$out/VERSION"
log "Created engine-$version.tar.gz, labpage-$version.tar.gz, VERSION"
(
    cd "$out"
    sha256sum "engine-$version.tar.gz" "labpage-$version.tar.gz" VERSION REVISIONS CHANGES.log >SHA256SUMS
)
printf 'Release: %s\nArtifacts: %s\n' "$version" "$out"
