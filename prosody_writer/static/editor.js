const poem = document.querySelector('#poem');
const results = document.querySelector('#results');
const status = document.querySelector('#status');
// randomUUID is unavailable in some embedded/non-secure preview contexts.
const session = typeof crypto.randomUUID === 'function' ? crypto.randomUUID() :
  '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, c =>
    (Number(c) ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> Number(c) / 4).toString(16));
const apiURL = new URL('api/scan', document.baseURI);
let revision = 0, timer, running = false, dirty = false;
try { const saved = localStorage.getItem('prosody-draft'); if (saved !== null) poem.value = saved; } catch {}
function element(tag, className, text) {
  const node = document.createElement(tag); node.className = className; node.textContent = text; return node;
}
function render(data) {
  results.replaceChildren();
  for (const line of data.lines) {
    if (line.status === 'empty') continue;
    const row = element('div', 'scan-line', '');
    row.append(element('p', 'line-text', line.text));
    if (line.status !== 'ok') row.append(element('p', 'note', line.message));
    else {
      const syllables = element('div', 'syllables', '');
      for (const syl of line.syllables) {
        const violations = Object.entries(syl.violations).filter(([, n]) => n > 0);
        const node = element('span', 'syllable' + (violations.length ? ' violation' : ''), '');
        node.title = `${syl.ipa} · lexical stress: ${syl.stress ? 'stressed' : 'unstressed'}${violations.length ? ' · ' + violations.map(([key]) => key).join(', ') : ''}`;
        node.append(element('span', 'mark', syl.meter === 's' ? '´' : '˘'), element('span', '', syl.text));
        syllables.append(node);
      }
      row.append(syllables);
    }
    results.append(row);
  }
  status.textContent = `${data.elapsed_ms} ms · ${data.work.parsed_lines} lines scanned`;
}
async function scan() {
  if (running) { dirty = true; return; }
  running = true; dirty = false;
  const sentRevision = revision;
  status.textContent = 'Scanning…';
  try {
    const response = await fetch(apiURL, {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({session, revision:sentRevision, text:poem.value})});
    if (response.status === 429) { dirty = true; return; }
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      throw new Error('This preview is serving the HTML file without the Python scanning API. Open the running app preview on port 8000.');
    }
    if (!response.ok) throw new Error((await response.json()).detail || 'Scanning failed');
    const data = await response.json();
    if (data.revision === revision) render(data);
  } catch (error) { status.textContent = String(error.message); }
  finally { running = false; if (dirty || sentRevision !== revision) { clearTimeout(timer); timer = setTimeout(scan, 180); } }
}
poem.addEventListener('input', () => {
  revision++;
  try { localStorage.setItem('prosody-draft', poem.value); } catch {}
  clearTimeout(timer); status.textContent = 'Waiting for your line…'; timer = setTimeout(scan, 180);
});
scan();
