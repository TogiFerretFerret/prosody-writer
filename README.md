# Prosody Writer

A first realtime poetry editor powered by the **full Python Prosodic 3.10.0 library**, including its pronunciation alternatives, syllabification, constraint scoring, and harmonic bounding. English lexical stress is enabled. Optional sentence-level syntax models are not installed in this first prototype.

## Run in GitHub Codespaces

Push these files to the repository, then choose **Code → Codespaces → Create codespace** on GitHub. The included `.devcontainer` installs Python 3.12 and eSpeak, installs the pinned Python dependencies, and starts the app automatically. Open **Prosody Writer / port 8000** from the Codespace's **Ports** tab. Keep the forwarded port private; Codespaces handles authenticated access. Reopening a stopped Codespace restarts the server.

If the preview does not open automatically, run `bash scripts/start-background.sh` and open port 8000 from the Ports tab. Server logs are in `.local/server.log`.

## Develop

In this Debian amd64 cloud environment, with Python 3.12:

```sh
cd /workspace/prosody-writer
bash scripts/setup.sh
.venv/bin/python -m pytest -q
.venv/bin/python -m uvicorn prosody_writer.app:app --host 0.0.0.0 --port 8000
```

The editor scans automatically after 180 ms without input, shows weak/strong syllables and constraint violations, and saves the draft in browser local storage. Text is sent to the running server to scan. The server retains bounded in-memory session caches; it does not persist drafts. Run this prototype on a trusted development machine; authentication and production deployment are not implemented.

`python scripts/build_preview.py` embeds the CSS and JavaScript into both HTML entry points. Regenerate after changing `static/template.html`, `style.css`, or `editor.js`. This supports single-file HTML previews and server proxies mounted under a path prefix. An HTML-only file preview still needs the Python API to scan; it displays an explicit connection message if the API is absent.

Setup installs signed Debian eSpeak packages without root and NLTK tokenizer data into ignored `.local/`. Prosodic's hardcoded home-data expansion is redirected only during initial import to `.local/prosodic_data`; `HOME` and the installed library are unchanged. Set `PROSODY_DATA_DIR` to choose another writable directory. On other platforms, install eSpeak normally and set `PHONEMIZER_ESPEAK_LIBRARY` if needed. The dependency lock was validated on Python 3.12 in this cloud image.

## What is incremental

- `graph.py` implements an append-only DAG keyed by syllable offset and previous metrical position. A new syllable layer adds a bounded number of nodes/edges for fixed strong/weak position limits. Shortening a line retains layers for later reuse.
- `IncrementalMeter` replaces Prosodic's candidate enumeration through its meter extension point. The graph produces the same candidates **in the same order**, preserving tie breaking. No reduced dictionary or simplified scoring engine is substituted.
- Each session caches pronunciation blocks by token and results by line. Editing a line reuses other lines, including after insertion or deletion. A changed final word gets a fresh pronunciation; existing words remain cached.
- The browser coalesces updates, keeps at most one request in flight, and discards results for older revisions. The server serializes parsing, bounds sessions and caches, and refuses overload.

**Graph extension is constant work per new syllable, but a full scan is not constant time.** Materializing candidate paths and evaluating/pooling pronunciations still runs again for the changed line. Prosodic 3's parser is vectorized; graph construction is not assumed to be its sole bottleneck. Document splitting and response assembly also scale with document size. This prototype establishes a tested integration seam for further optimization rather than claiming an exact constant-time parser.

The interactive budget is at most 18 syllables across every pronunciation, 256 pronunciation combinations, 300 characters per line, and 200 lines / 12,000 characters per request. Over-budget lines display a limit message rather than silently approximating. A single syllable displays a provisional message until a foot can be scanned.

## Verify and measure

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/benchmark.py
```

Tests compare graph candidates, best scansions, scores, violation counts, and chosen pronunciations with fresh full Prosodic parses. They also cover edit sequences, empty input, limits, API behavior, and an invented word that requires eSpeak.

Next optimization: profile the edited-line pronunciation pooling and constraint evaluation, retain sufficient boundary state and violation vectors, and compare every incremental update against a cold parse. Pruning only the current winning parse is unsafe: an appended syllable can change the winner, position boundaries, and harmonic bounding. A true scoring frontier needs an equivalence proof or explicit fallback for nonlocal constraints and pronunciation changes.
