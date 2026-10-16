#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
export LC_ALL=C.UTF-8
umask 077
[[ $# == 3 ]] || { echo 'Usage: make_release.sh ENGINE_DIR SITE_WIDGET_DIR OUT_DIR' >&2; exit 1; }
engine=$(cd -- "$1" && pwd)
site=$(cd -- "$2" && pwd)
kit=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../server" && pwd)
python=${PYTHON:-python3}
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
for command in git "$python" tar gzip sha256sum mktemp; do
    command -v "$command" >/dev/null || die "Missing command: $command"
done
[[ $(git -C "$engine" rev-parse --show-toplevel) == "$engine" ]] || die 'ENGINE_DIR must be the repository root'
[[ -z $(git -C "$engine" status --porcelain --untracked-files=all) ]] || die 'Engine tree is dirty (including untracked files)'
[[ -f $engine/keeper/gateway.py ]] || die 'keeper/gateway.py is missing; this engine cannot ship the Keeper service'
[[ -d $site/website/keeper && -d $site/website/pages/protocols && -f $site/tools/keeper_inject.py ]] || die 'SITE_WIDGET_DIR must contain website/keeper, website/pages/protocols and tools/keeper_inject.py'
[[ -f $site/website/keeper/keeper-loader.js && -f $site/website/keeper/ROUTES.json ]] || die 'Widget lacks keeper-loader.js or ROUTES.json'
"$python" "$kit/kit_helpers.py" routes "$site/website/keeper/ROUTES.json" >/dev/null
mkdir -p -- "$3"
out=$(cd -- "$3" && pwd)
case $out/ in "$engine/"*|"$site/"*) die 'OUT_DIR must be outside both source trees' ;; esac
[[ -z $(find "$out" -mindepth 1 -maxdepth 1 -print -quit) ]] || die 'OUT_DIR must be empty (prevents mixing release artifacts)'
log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$out/CHANGES.log"; }
stage=$(mktemp -d "$out/.stage.XXXXXXXX")
trap 'rc=$?; rm -rf -- "$stage"; if (( rc != 0 )); then log "Release build failed (exit $rc); inspect output and use a fresh OUT_DIR"; fi' EXIT
head=$(git -C "$engine" rev-parse HEAD)
short=$(git -C "$engine" rev-parse --short HEAD)
log "Building engine HEAD $head; no network or package installation is performed"
git -C "$engine" archive --format=tar.gz --output="$stage/engine.tar.gz" "$head"
"$python" "$kit/kit_helpers.py" archive "$stage/engine.tar.gz"
args=(build "$stage/corpus" --site "$site/website")
if [[ -n ${KEEPER_RU_SOURCES:-} ]]; then
    ru=$(cd -- "$KEEPER_RU_SOURCES" && pwd)
    args+=(--ru "$ru")
fi
# Corpus builder uses git HEAD for engine provenance; build in the clean source tree.
(cd "$engine" && "$python" -m keeper.corpus "${args[@]}")
shopt -s nullglob
manifests=("$stage"/corpus/corpus-*.json)
[[ ${#manifests[@]} == 1 ]] || die 'Expected exactly one corpus manifest'
corpus_version=$("$python" -c 'import json,re,sys; x=json.load(open(sys.argv[1])); assert re.fullmatch(r"[0-9a-f]{12}",x["version"]); assert x["engine_commit"]==sys.argv[2]; print(x["version"])' "${manifests[0]}" "$head")
version=$short-$corpus_version
[[ $(git -C "$engine" rev-parse HEAD) == "$head" && -z $(git -C "$engine" status --porcelain --untracked-files=all) ]] || die 'Engine changed during build'
mkdir "$stage/widget"
cp -R -- "$site/website/keeper/." "$stage/widget/"
cp -- "$site/tools/keeper_inject.py" "$stage/widget/keeper_inject.py"
# The lab page (research alpha) ships with the widget: the panel links to it and its route is in ROUTES.json.
[[ -f $site/website/projects/protocol-lab/index.html && -f $site/website/projects/protocol-lab/dist/lab-bundle.zip ]] || die 'Lab page or its bundle missing'
cp -R -- "$site/website/projects/protocol-lab" "$stage/widget/protocol-lab"
tar --create --gzip --file "$out/widget-$version.tar.gz" --directory "$stage/widget" .
"$python" "$kit/kit_helpers.py" archive "$out/widget-$version.tar.gz"
mv -- "$stage/engine.tar.gz" "$out/engine-$version.tar.gz"
cp -- "$stage/corpus/corpus-$corpus_version.json" "$stage/corpus/corpus-$corpus_version.jsonl" "$out/"
printf '%s\n' "$version" >"$out/VERSION"
log "Created engine-$version.tar.gz, corpus-$corpus_version.json[l], widget-$version.tar.gz, VERSION"
(
    cd "$out"
    sha256sum "engine-$version.tar.gz" "corpus-$corpus_version.json" \
        "corpus-$corpus_version.jsonl" "widget-$version.tar.gz" VERSION CHANGES.log >SHA256SUMS
)
printf 'Release: %s\nArtifacts: %s\n' "$version" "$out"
