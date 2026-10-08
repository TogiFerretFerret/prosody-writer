#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python_bin="${PYTHON_BIN:-python3}"
"$python_bin" scripts/build_preview.py
"$python_bin" -m venv .venv
.venv/bin/python -m pip install --no-cache-dir -r requirements.lock
.venv/bin/python -m pip install --no-cache-dir --no-deps -e .
mkdir -p .local/nltk_data
# The cloud's managed egress proxy is trusted. Keep TLS verification enabled.
NLTK_ALLOW_PROXIED_URLOPEN=1 .venv/bin/python - <<'PY'
import nltk
for package in ('punkt', 'punkt_tab'):
    if not nltk.download(package, download_dir='.local/nltk_data', quiet=True, raise_on_error=True):
        raise SystemExit(f'Could not install {package}')
PY

# Rootless native setup for Debian amd64/arm64 images. Apt verifies signed
# archive metadata and package hashes; do not substitute unverified downloads.
if [[ -f /etc/debian_version && -f /usr/share/keyrings/debian-archive-keyring.gpg ]] && ! .venv/bin/python - <<'PY'
import ctypes.util, sys
sys.exit(0 if ctypes.util.find_library('espeak-ng') or ctypes.util.find_library('espeak') else 1)
PY
then
    mkdir -p .local/apt/lists/partial .local/apt/cache/archives/partial .local/downloads
    debian_suite=$(.venv/bin/python -c 'import platform; print(platform.freedesktop_os_release()["VERSION_CODENAME"])')
    printf '%s\n' "deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian $debian_suite main" > .local/apt/sources.list
    apt_opts=(-o "Dir::Etc::sourcelist=$PWD/.local/apt/sources.list" -o Dir::Etc::sourceparts=-
              -o "Dir::State::lists=$PWD/.local/apt/lists" -o "Dir::Cache=$PWD/.local/apt/cache")
    apt-get "${apt_opts[@]}" update
    project_root="$PWD"
    cd .local/downloads
    apt-get "${apt_opts[@]}" download libespeak-ng1 espeak-ng-data libpcaudio0 libsonic0
    for package in ./*.deb; do dpkg-deb -x "$package" ../native; done
    cd "$project_root"
fi
.venv/bin/python - <<'PY'
from prosody_writer.engine import Scanner
scanner = Scanner()
assert scanner.update("Shall I compare thee to a summer's day?")['lines'][0]['status'] == 'ok'
assert scanner.frame('florple moon').num_forms.min() > 0
print('Full Prosodic and eSpeak fallback verified.')
PY
