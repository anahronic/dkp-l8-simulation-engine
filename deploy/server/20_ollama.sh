#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
expected=${1:-${EXPECTED_MODEL_DIGEST:-}}
[[ $# -le 1 && $expected =~ ^sha256:[0-9a-f]{64}$ ]] || die 'Pass the full sha256:<64 hex> model-layer digest as argument or EXPECTED_MODEL_DIGEST'
init_changes
install_ollama=0
if ! command -v ollama >/dev/null; then
    change 'Downloading Ollama installer to /var/lib/dkp-deploy/install-ollama.sh'
    curl --proto '=https' --tlsv1.2 -fSL --connect-timeout 20 --max-time 180 \
        https://ollama.com/install.sh -o "$STATE/install-ollama.sh"
    sha256sum "$STATE/install-ollama.sh" | tee -a "$STATE/CHANGES.log"
    install_ollama=1
else
    change 'Ollama already installed; skipped installer and upgrade'
fi
sudo install -d -m 0755 /etc/systemd/system/ollama.service.d
cat <<'EOF' | sudo tee /etc/systemd/system/ollama.service.d/dkp.conf >/dev/null
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_NO_CLOUD=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_KEEP_ALIVE=30m"
Environment="OLLAMA_CONTEXT_LENGTH=8192"
MemoryMax=2700M
MemoryHigh=2500M
CPUQuota=170%
OOMScoreAdjust=500
User=ollama
Group=ollama
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
CapabilityBoundingSet=
RestrictSUIDSGID=true
InaccessiblePaths=-/var/lib/dkp-lab -/var/lib/dkp-corpus -/var/lib/dkp-keeper -/var/lib/dkp-deploy -/etc/ssh
# Model installation needs this exception temporarily; revoked after verified pull.
ReadWritePaths=/usr/share/ollama
EOF
sudo chmod 0644 /etc/systemd/system/ollama.service.d/dkp.conf
change 'Wrote Ollama drop-in before any installer-triggered service start'
trap 'rc=$?; if (( rc != 0 )); then sudo systemctl stop ollama.service || true; change "Ollama installation/verification failed; requested Ollama stop"; fi' EXIT
if (( install_ollama == 1 )); then
    # Pre-stage the drop-in: systemd does not inherit the installer shell environment.
    sudo env OLLAMA_NO_CLOUD=1 sh "$STATE/install-ollama.sh"
    change 'Ran upstream Ollama installer (installer retained with its SHA256 in log)'
fi
sudo systemctl daemon-reload
sudo systemctl enable ollama.service
sudo systemctl restart ollama.service
change 'Installed Ollama loopback/cloud-disabled/resource-limit drop-in; enabled and restarted Ollama'
ready=0
for ((i=0; i<60; i++)); do
    if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null; then ready=1; break; fi
    sleep 1
done
(( ready == 1 )) || die 'Ollama did not become ready'
check_ports loopback 11434
# Inspect Environment without printing unrelated, potentially secret variables.
sudo systemctl show ollama -p Environment |
    python3 "$KIT_DIR/kit_helpers.py" ollama-env
if sudo -l -U ollama 2>/dev/null | grep -Eq '^[[:space:]]*\('; then die 'Ollama account has sudo rules'; fi
# Installer-only update window; the previous release made these files read-only.
sudo install -d -o ollama -g ollama -m 0750 /usr/share/ollama/.ollama/models
sudo chown -R ollama:ollama /usr/share/ollama/.ollama/models
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 ollama pull qwen3.5:2b
sudo python3 "$KIT_DIR/kit_helpers.py" model-digest \
    /usr/share/ollama/.ollama/models/manifests/registry.ollama.ai/library/qwen3.5/2b "$expected"
check_ports loopback 11434
change "Pulled qwen3.5:2b and verified model layer $expected and effective environment"
sudo chown -R root:ollama /usr/share/ollama/.ollama/models
sudo chmod -R u=rwX,g=rX,o= /usr/share/ollama/.ollama/models
cat <<'EOF' | sudo tee -a /etc/systemd/system/ollama.service.d/dkp.conf >/dev/null
ReadWritePaths=
ReadOnlyPaths=/usr/share/ollama/.ollama/models
IPAddressDeny=any
IPAddressAllow=localhost
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama.service
change 'Revoked model-install write access and non-local network access from runtime Ollama'
