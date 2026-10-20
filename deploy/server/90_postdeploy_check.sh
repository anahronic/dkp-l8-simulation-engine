#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
[[ $# -le 1 ]] || die 'Usage: PUBLIC_IP=<server IP> 90_postdeploy_check.sh [BASE_URL]'
base=${1:-https://dikenocracy.com}
base=${base%/}
[[ $base =~ ^https://[a-zA-Z0-9.-]+(:[0-9]+)?$ ]] || die 'BASE_URL must be an HTTPS origin without a path'
[[ -n ${PUBLIC_IP:-} ]] || die 'Set PUBLIC_IP to the server public IP literal (no address discovery service is used)'
public_host=$(python3 "$KIT_DIR/kit_helpers.py" public-ip "$PUBLIC_IP")
init_changes
log=$STATE/postdeploy-$(stamp).log
touch "$log"
chmod 0600 "$log"
exec > >(tee -a "$log") 2>&1
work=$(mktemp -d "$STATE/postdeploy-private.XXXXXXXX")
finish() {
    local rc=$?
    rm -rf -- "$work"
    change "Post-deploy check exit=$rc; log=$log"
}
trap finish EXIT
note "Checking $base"
for path in /PRIVATE_DO_NOT_PUBLISH/ /PRIVATE_DO_NOT_PUBLISH/corpus.jsonl \
    /search_ru /ru-sources/ /keeper/corpus.jsonl /corpus.jsonl \
    /keeper/search_ru /keeper/PRIVATE_DO_NOT_PUBLISH/ /keeper/ru-sources/ \
    /audit%20rt/ /keeper/corpus.json /var/lib/dkp-corpus/corpus.jsonl; do
    status=$(curl --noproxy '*' -sS --connect-timeout 10 --max-time 30 \
        "$base$path" -o "$work/private-probe" -w '%{http_code}')
    case $status in 403|404) ;; *) die "Private path reachable or inconclusive: $path ($status)" ;; esac
done
sudo -u dkpkeeper test -r /var/lib/dkp-corpus/corpus.jsonl || die 'Keeper cannot read corpus'
for path in /var/lib/dkp-corpus /var/lib/dkp-corpus/corpus.jsonl /opt/dkp-lab /opt/dkp-lab/current; do
    if sudo -u dkpkeeper test -w "$path"; then die "Keeper can modify $path"; fi
done
for path in /var/lib/dkp-lab/lab /var/lib/dkp-lab/lab/jobs.sqlite3 /var/lib/dkp-lab/lab/store/.secret; do
    if sudo -u dkpkeeper test -r "$path"; then die 'Keeper can read Lab private state'; fi
done
sudo -u dkpkeeper test -w /var/lib/dkp-keeper/log || die 'Keeper log directory is not writable'
get() { curl --noproxy '*' -fsS --connect-timeout 10 --max-time 65 "$@"; }
for component in lab keeper; do
    get "$base/api/$component/v1/health" -o "$work/health.json"
    python3 -c 'import json,sys; x=json.load(open(sys.argv[1])); assert x.get("ok") is True, "health ok is not true"' "$work/health.json"
    note "$component health passed"
done
get "$base/api/lab/v1/scenarios/work_cycle" -o "$work/scenario.json"
python3 -c 'import json,sys; x=json.load(open(sys.argv[1])); assert x["module"]=="work_cycle" and x["variants"]; x["variants"]=x["variants"][:1]; json.dump(x,sys.stdout)' \
    "$work/scenario.json" >"$work/request.json"
get -H 'Content-Type: application/json' --data-binary "@$work/request.json" \
    "$base/api/lab/v1/jobs" -o "$work/job.json"
# Credentials stay in private files, never stdout, logs, URLs, or command arguments.
python3 -c 'import json,re,sys; x=json.load(open(sys.argv[1])); assert re.fullmatch(r"[a-f0-9]{32}",x["job_id"]); assert re.fullmatch(r"[A-Za-z0-9_-]+",x["token"]); open(sys.argv[2],"w").write("Authorization: Bearer "+x["token"]+"\n"); print(x["job_id"])' \
    "$work/job.json" "$work/auth.header" >"$work/job.id"
job=$(cat "$work/job.id")
completed=0
# >=3 seconds per poll stays below nginx's 2r/s all-methods Lab limit.
for ((i=0; i<100; i++)); do
    sleep 3
    get -H "@$work/auth.header" "$base/api/lab/v1/jobs/$job" -o "$work/status.json"
    state=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["state"])' "$work/status.json")
    case $state in
        completed) completed=1; break ;;
        failed|cancelled) die "Lab job entered $state" ;;
        queued|running) ;;
        *) die 'Unknown job state' ;;
    esac
done
(( completed == 1 )) || die 'Lab job did not complete in the polling window'
get -H "@$work/auth.header" "$base/api/lab/v1/jobs/$job/report" -o "$work/report.json"
get -H "@$work/auth.header" "$base/api/lab/v1/jobs/$job/export" -o "$work/export.zip"
python3 -c '
import json,sys,zipfile
from pathlib import Path
p=Path(sys.argv[1]); status=json.loads((p/"status.json").read_text()); report=json.loads((p/"report.json").read_text())
assert report["schema"]=="dkp-lab-result/1"
assert report["result_id"]==status["result_id"]
assert report["input_id"]==status["input_ids"]["request"]
assert {k:v["input_id"] for k,v in report["variants"].items()}==status["input_ids"]["variants"]
with zipfile.ZipFile(p/"export.zip") as z:
    assert z.testzip() is None
    assert {"request.json","result.json","report.en.md","report.ru.md","report.html","provenance.json","REPLAY.md","SHA256SUMS"} <= set(z.namelist())
    assert json.loads(z.read("result.json"))["result_id"]==status["result_id"]
print("result_id:",status["result_id"])
print("input_ids:",json.dumps(status["input_ids"],sort_keys=True))
' "$work"
python3 -c 'import json; print(json.dumps({"question":"Почему восстановление обязательно в рабочем цикле?", "lang":"ru", "stream":False},ensure_ascii=False))' >"$work/ask.json"
curl --noproxy '*' -fsS --connect-timeout 10 --max-time 180 -H 'Content-Type: application/json' \
    --data-binary "@$work/ask.json" -o "$work/answer.json" -w 'Keeper ask: HTTP %{http_code}, total %{time_total}s\n' \
    "$base/api/keeper/v1/ask"
python3 -c 'import json,sys; x=json.load(open(sys.argv[1])); assert x.get("state")=="answer", "Expected a grounded answer"; assert x.get("answer") and x.get("citations"); p=x["provenance"]; assert p.get("model_digest") and p.get("corpus_version"); print("Keeper Russian ask passed; state="+x["state"])' "$work/answer.json"
python3 "$KIT_DIR/kit_helpers.py" routes /var/www/html/keeper/ROUTES.json >"$work/routes"
while IFS= read -r route; do
    get "$base$route" -o "$work/page.html"
    python3 "$KIT_DIR/kit_helpers.py" loader "$work/page.html"
    note "Loader present once: $route"
done <"$work/routes"
check_ports loopback 11434 8720 8721
for port in 11434 8720 8721; do
    # Do not use -f: any HTTP response, including a 404/500, proves exposure.
    rc=0
    connections=$(curl --noproxy '*' -sS --connect-timeout 5 --max-time 8 \
        "http://$public_host:$port/" -o /dev/null -w '%{num_connects}' 2>/dev/null) || rc=$?
    [[ $connections == 0 ]] || die "Port $port accepted a TCP connection"
    case $rc in
        7|28) note "Public-IP probe $port rejected/timed out" ;;
        *) die "Port $port reachable or inconclusive (curl exit $rc); expected refused/timed out" ;;
    esac
done
note 'These public-IP probes originate on the server; repeat from an independent external host before claiming outside isolation.'
free -h
OLLAMA_HOST=127.0.0.1:11434 ollama ps
change 'All scripted post-deploy checks passed; independent external-port verification is still an operator step'
