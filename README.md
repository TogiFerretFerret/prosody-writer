# Prosody Writer

A realtime poetry editor using the **full Python Prosodic 3.10.0 library** for pronunciations, syllabification, and lexical features, with an incremental DP for its default English grammar. It selects the best weighted scan with Prosodic's tie breakers, without enumerating all scansions or pronunciation combinations. Optional syntax models, configurable grammars, and enumeration of every unbounded alternative are not implemented.

## Run locally on Asahi Linux (aarch64)

For Fedora Asahi Remix, install Python 3.12 and the native pronunciation library:

```sh
sudo dnf install python3.12 espeak-ng
git clone https://github.com/TogiFerretFerret/prosody-writer.git
cd prosody-writer
PYTHON_BIN=python3.12 bash scripts/setup.sh
.venv/bin/python -m uvicorn prosody_writer.app:app --port 8000
```

Open **http://localhost:8000** in your browser. Stop the server with Ctrl-C. For subsequent runs, only the final command is needed. To update an existing checkout, run `git pull` and rerun setup before starting the server. Debian/Ubuntu users should install Python 3.12 with venv support and `espeak-ng` through apt instead of dnf. The pinned native Python dependencies publish Linux aarch64 wheels for Python 3.12; execution on Asahi hardware has not been tested here.

## Run in GitHub Codespaces

Choose **Code → Codespaces → Create codespace** on GitHub. The included `.devcontainer` installs Python 3.12 and eSpeak, installs the pinned Python dependencies, and starts the app automatically. Open **Prosody Writer / port 8000** from the Codespace's **Ports** tab. Keep the forwarded port private; Codespaces handles authenticated access. Reopening a stopped Codespace restarts the server.

If the preview does not open automatically, run `bash scripts/start-background.sh` and open port 8000 from the Ports tab. Server logs are in `.local/server.log`.

After pulling an update in an existing Codespace, run `bash scripts/setup.sh` followed by `bash scripts/start-background.sh --restart` to reload the running server.

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

## What it analyses

Beyond the scansion itself, every scan reports, per line and for the whole poem:

- **Syllables.** The count in the best-scoring reading, and for the poem the total, the average and the shortest and longest line. Words with more than one pronunciation (`temperate`, `heaven`, `every`) are marked, because a different reading changes the count.
- **Meter.** The scansion is named: iambic, trochaic, anapestic or dactylic, with a foot count (`iambic pentameter`). Common variations are reported rather than counted against the line: a feminine ending, a catalectic last foot, and substituted feet (`foot 1: trochee`, `foot 5: pyrrhic`). Lines too short or too irregular to name say `irregular`. The poem summary shows the dominant meter and how many lines follow it.
- **Rhyme.** Each line is tagged with a rhyme letter, computed from the end word's last stressed vowel onward, using the pronunciation the scansion chose. Perfect and identical rhymes share a letter. A line left alone is attached to the nearest half rhyme it has (`B~`), either a shared vowel or a shared closing sound, and a line with no echo at all is greyed out. The rhyming syllables are underlined in the line's colour. The summary lists each rhyme sound with its words.
- **Sound devices.** Alliteration (shared opening consonant on stressed content words) and assonance (a shared stressed vowel), per line. The same word twice counts as repetition, not as a device.
- **Form.** The scheme and syllable counts are matched against haiku, tanka, limerick, Shakespearean and Petrarchan sonnets, villanelle, terza rima, rhyming couplets and quatrain shapes. A blank line starts a new stanza.
- **Echoes.** Repeated content words across the poem.

The editor has toggles for rhyme, meter and sound devices, and a button that copies the analysis as plain text. The analysis lives in `prosody_writer/analysis.py` as pure functions over the pronunciation the scanner already chose, so it adds no second parse and is cached per line like the scan.

Rhyme and meter naming are heuristics over the dictionary pronunciation. A word the dictionary stresses differently from how a poet reads it (`temperate` as a rhyme for `date`) can only be caught as a near rhyme.

## What is incremental

- `dp.py` consumes every pronunciation alternative word by word. Equivalent states merge with backpointers; the Cartesian product of pronunciations is never constructed.
- Word-boundary checkpoints retain the preceding frontier. Append resumes there; deletion or a mid-line edit rolls back to the first changed word. Insertions/deletions of lines preserve other lines' frontiers.
- Scoring matches Prosodic's six default constraints with unit weights and strong/weak position sizes capped at two. The state also retains the last three metrical values, period-2/3 match counts, a pseudo-foot type bitset, open-position context, and syllable count, preserving Prosodic's nonlocal tie breakers.
- All weights are strictly positive, so a global minimum score cannot be harmonically bounded. Selecting the best scan therefore does not require computing the entire Pareto frontier. Paths with worse `(score, strong-resolution count)` in an equivalent scoring state cannot recover after append; tied paths merge only when their remaining ranking state is equivalent.
- Each session caches pronunciation blocks by token and results by line. Editing a line reuses other lines, including after insertion or deletion. A changed final word gets a fresh pronunciation; existing words remain cached.
- The browser coalesces updates, keeps at most one request in flight, and discards results for older revisions. The server serializes parsing, bounds sessions and caches, and refuses overload.

**No exponential path materialization remains in the editor's parsing path.** For this fixed grammar, the state space is polynomial: three bounded-by-line-length counters (syllable count and two regularity counts), a constant-size foot bitset, and finite boundary context. It is not constant time in the worst case: the frontier can grow, changed suffixes need recomputation, and reconstructing the displayed scan costs linear time. Lexical lookup and tokenization also contribute to end-to-end latency. `graph.py` remains as a reference enumerator for tests, outside the editor's hot path.

The interactive budget is 128 syllables across every pronunciation, 300 characters per line, and 200 lines / 12,000 characters per request. There is no pronunciation-combination cap. Over-budget lines display a limit message rather than silently approximating. A single canonical syllable displays a provisional message until a foot can be scanned. The API reports DP transitions, reused prefix words, peak states, and zero materialized candidate paths.

## Verify and measure

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/benchmark.py
```

Tests compare best scansions, scores, violation counts, and chosen pronunciations with full Prosodic, including 150 seeded synthetic pronunciation lattices. They cover append/rollback, checkpoint identity, line movement, input limits, API behavior, an invented word requiring eSpeak, and 32 independent binary pronunciations (2**32 combinations) without path enumeration. The benchmark also measures append at 64 binary-ambiguous words. Full-parser comparisons remain within its 18-syllable/4096-combination limits; longer lines test DP invariants instead. Never infer compatibility with fitted zone weights, zero/negative weights, phrasal stress, or arbitrary extra constraints from these tests.
