#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .local

if [[ "${1:-}" == --restart && -f .local/server.pid ]]; then
    .venv/bin/python - <<'PY'
import os, signal, subprocess, time
from pathlib import Path
pid_text = Path('.local/server.pid').read_text().strip()
if pid_text.isdigit():
    pid = int(pid_text)
    args = subprocess.run(['ps', '-p', str(pid), '-o', 'args='], capture_output=True, text=True).stdout
    if 'uvicorn prosody_writer.app:app' in args:
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(.1)
PY
fi

# Reconnecting/restarting a Codespace should not launch another server.
if .venv/bin/python - <<'PY'
import json, sys, urllib.request
try:
    data = json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2))
    sys.exit(0 if data.get('engine') == 'prosodic' else 1)
except Exception:
    sys.exit(1)
PY
then
    echo 'Prosody Writer is already serving port 8000.'
    exit 0
fi

nohup .venv/bin/python -m uvicorn prosody_writer.app:app --host 0.0.0.0 --port 8000 > .local/server.log 2>&1 &
server_pid=$!
printf '%s\n' "$server_pid" > .local/server.pid
.venv/bin/python - <<'PY'
import json, time, urllib.request
for _ in range(30):
    try:
        data = json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=1))
        if data.get('engine') == 'prosodic':
            print('Prosody Writer is ready on port 8000. Open it from the Ports tab.')
            break
    except Exception:
        pass
    time.sleep(1)
else:
    raise SystemExit('Server did not become ready. See .local/server.log.')
PY
