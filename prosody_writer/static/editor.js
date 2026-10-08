const poem = document.querySelector('#poem');
const results = document.querySelector('#results');
const summary = document.querySelector('#summary');
const status = document.querySelector('#status');
const copyButton = document.querySelector('#copy');
// randomUUID is unavailable in some embedded/non-secure preview contexts.
const session = typeof crypto.randomUUID === 'function' ? crypto.randomUUID() :
  '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, c =>
    (Number(c) ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> Number(c) / 4).toString(16));
const apiURL = new URL('api/scan', document.baseURI);
let revision = 0, timer, running = false, dirty = false, latest = null;
const toggles = {rhyme: '#show-rhyme', meter: '#show-meter', sound: '#show-sound'};
try { const saved = localStorage.getItem('prosody-draft'); if (saved !== null) poem.value = saved; } catch {}
for (const [name, selector] of Object.entries(toggles)) {
  const box = document.querySelector(selector);
  try { const saved = localStorage.getItem('prosody-show-' + name); if (saved !== null) box.checked = saved === '1'; } catch {}
  box.addEventListener('change', () => {
    try { localStorage.setItem('prosody-show-' + name, box.checked ? '1' : '0'); } catch {}
    if (latest) render(latest);
  });
}
const shown = name => document.querySelector(toggles[name]).checked;
function element(tag, className, text) {
  const node = document.createElement(tag); node.className = className; if (text !== undefined) node.textContent = text; return node;
}
// A stable hue per rhyme letter, so a letter keeps its colour as the poem grows.
function letterColor(letter) {
  let n = 0; for (const c of letter) n = n * 26 + c.charCodeAt(0) - 64;
  return `hsl(${(n * 47) % 360} 48% 38%)`;
}
function chip(text, title) { const node = element('span', 'chip', text); if (title) node.title = title; return node; }
const KIND = {perfect: 'perfect rhyme', identical: 'identical rhyme', assonant: 'shared vowel', consonant: 'shared ending sound'};

function renderSummary(data) {
  const a = data.analysis;
  summary.replaceChildren();
  if (!a || !a.lines) { summary.hidden = true; return; }
  summary.hidden = false;
  const grid = element('div', 'summary-grid');
  const stat = (label, value, title) => {
    const box = element('div', 'stat'); if (title) box.title = title;
    box.append(element('span', 'stat-label', label), element('span', 'stat-value', value)); grid.append(box);
  };
  if (a.form) stat('Form', a.form);
  if (a.meter) stat('Meter', a.meter.label, `${a.meter.lines} of ${a.meter.of} lines`);
  if (a.meter) stat('Regularity', `${a.meter.lines}/${a.meter.of} lines`);
  if (a.scheme) stat('Rhyme scheme', a.scheme);
  stat('Lines', `${a.lines}${a.stanzas > 1 ? ' · ' + a.stanzas + ' stanzas' : ''}`);
  stat('Syllables', `${a.syllables} · avg ${a.average_syllables}${a.shortest !== a.longest ? ` · ${a.shortest}–${a.longest}` : ''}`);
  summary.append(grid);
  if (shown('rhyme') && a.rhyme_groups.length) {
    const row = element('div', 'chips'); row.append(element('span', 'chips-label', 'Rhyme sounds'));
    for (const g of a.rhyme_groups) {
      const node = chip(`${g.letter}  /${g.sound}/  ${g.words.join(', ')}`);
      node.style.borderColor = letterColor(g.letter); node.style.color = letterColor(g.letter); row.append(node);
    }
    summary.append(row);
  }
  if (a.repeats.length) {
    const row = element('div', 'chips'); row.append(element('span', 'chips-label', 'Echoes'));
    for (const r of a.repeats) row.append(chip(`${r.word} ×${r.count}`, 'Repeated word'));
    summary.append(row);
  }
}

function renderLine(line, number) {
  const row = element('div', 'scan-line');
  const head = element('div', 'line-head');
  if (shown('rhyme') && line.rhyme) {
    const r = line.rhyme;
    const badge = element('span', 'rhyme-badge' + (r.unrhymed ? ' unrhymed' : ''), r.letter + (r.near ? '~' : ''));
    badge.style.setProperty('--rhyme', letterColor(r.letter));
    badge.title = r.unrhymed ? 'No other line rhymes with this one' :
      `Rhymes with “${r.word}” — ${KIND[r.kind] || 'rhyme'} (/${r.sound}/)${r.near ? ' · near rhyme' : ''}`;
    head.append(badge);
  }
  head.append(element('p', 'line-text', line.text));
  row.append(head);
  if (line.status !== 'ok') { row.append(element('p', 'note', line.message)); return row; }
  const meta = element('div', 'chips');
  meta.append(chip(`${line.syllable_count} syllables`, 'Syllables in the best-scoring scansion'));
  if (shown('meter')) {
    const m = line.meter;
    if (m) {
      meta.append(chip(m.label, `${m.feet} feet · ${m.distance} off the ideal pattern`));
      for (const v of m.variants) meta.append(chip(v, 'A common variation, not an error'));
      for (const d of m.deviations) meta.append(chip(`foot ${d.foot}: ${d.name}`, `Foot ${d.foot} reads ${d.pattern}`));
    } else meta.append(chip('irregular', 'No regular meter fits this line'));
  }
  row.append(meta);
  const syllables = element('div', 'syllables');
  const spans = line.words && line.words.length ? line.words : [{start: 0, end: line.syllables.length}];
  const tailFrom = shown('rhyme') && line.rhyme ? spans[spans.length - 1].start + line.rhyme.from : Infinity;
  for (const word of spans) {
    const group = element('span', 'word' + (word.alt ? ' varies' : ''));
    if (word.alt) group.title = `“${word.text}” can be read with ${word.alt.join(' or ')} syllables`;
    for (let i = word.start; i < word.end; i++) {
      const syl = line.syllables[i];
      const violations = Object.entries(syl.violations).filter(([, n]) => n > 0);
      const inTail = i >= tailFrom;
      const node = element('span', 'syllable' + (violations.length ? ' violation' : '') + (inTail ? ' tail' : ''), '');
      if (inTail) node.style.setProperty('--rhyme', letterColor(line.rhyme.letter));
      node.title = `${syl.ipa} · lexical stress: ${syl.stress ? 'stressed' : 'unstressed'}${violations.length ? ' · ' + violations.map(([key]) => key).join(', ') : ''}`;
      node.append(element('span', 'mark', syl.meter === 's' ? '´' : '˘'), element('span', '', syl.text));
      group.append(node);
    }
    syllables.append(group);
  }
  row.append(syllables);
  if (shown('sound') && (line.alliteration.length || line.assonance.length)) {
    const devices = element('div', 'chips devices');
    for (const g of line.alliteration) devices.append(chip(`alliteration /${g.sound}/ ${g.words.join(' · ')}`, 'Repeated opening sound'));
    for (const g of line.assonance) devices.append(chip(`assonance /${g.sound}/ ${g.words.join(' · ')}`, 'Repeated stressed vowel'));
    row.append(devices);
  }
  return row;
}

function render(data) {
  latest = data;
  results.replaceChildren();
  renderSummary(data);
  let number = 0, gap = false;
  for (const line of data.lines) {
    if (line.status === 'empty') { gap = number > 0; continue; }
    number++;
    const row = renderLine(line, number);
    if (gap) { row.classList.add('stanza-break'); gap = false; }
    results.append(row);
  }
  status.textContent = `${data.elapsed_ms} ms · ${data.work.parsed_lines} lines scanned`;
}

function analysisText(data) {
  const a = data.analysis, out = [];
  if (a.form) out.push(`Form: ${a.form}`);
  if (a.meter) out.push(`Meter: ${a.meter.label} (${a.meter.lines} of ${a.meter.of} lines)`);
  if (a.scheme) out.push(`Rhyme scheme: ${a.scheme}`);
  out.push(`${a.lines} lines · ${a.syllables} syllables`, '');
  let n = 0;
  for (const line of data.lines) {
    if (line.status === 'empty') { out.push(''); continue; }
    n++;
    const rhyme = line.rhyme ? line.rhyme.letter + (line.rhyme.near ? '~' : '') : '-';
    const meter = line.meter ? line.meter.label + (line.meter.variants.length ? ` (${line.meter.variants.join(', ')})` : '') : '';
    out.push(`${String(n).padStart(2)}  ${rhyme.padEnd(3)} ${String(line.syllable_count ?? '').padStart(2)}  ${line.scansion || ''}  ${meter}  | ${line.text}`);
  }
  return out.join('\n');
}
copyButton.addEventListener('click', async () => {
  if (!latest) return;
  try { await navigator.clipboard.writeText(analysisText(latest)); copyButton.textContent = 'Copied!'; }
  catch { copyButton.textContent = 'Copy failed'; }
  setTimeout(() => { copyButton.textContent = 'Copy analysis'; }, 1500);
});

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
