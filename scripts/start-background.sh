#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .local

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
