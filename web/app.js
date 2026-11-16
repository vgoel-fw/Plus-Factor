/* Plus Factor: drop files or paste details -> Jev classifies passages -> charts. */
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const lab = s => esc(String(s ?? '').replace(/_/g, ' '));
const COLORS = ['#1e3a8a', '#2563eb', '#60a5fa', '#0ea5e9', '#1d4ed8', '#93c5fd', '#0369a1'];
const S = { files: [], details: '', r: null, color: {}, mode: 'files', jev: false, rows: [{}, {}, {}], product: '' };
const api = async (path, body) => { const r = await fetch('/api' + path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}); const j = await r.json(); if (r.status === 401 && !['/login', '/me'].includes(path)) { login(); throw new Error('Your session has ended. Please sign in again.'); } if (!r.ok) throw Object.assign(new Error(j.error || r.statusText), { status: r.status }); return j; };
const toast = m => { const t = $('#toast'); t.textContent = m; t.hidden = false; setTimeout(() => t.hidden = true, 6000); };
const cite = (o, text) => `<a class="cite" data-src="${o.source_id}" data-span="${o.span_id || o.span_ids?.[0] || ''}">${text || esc((o.file || '').replace(/\.\w+$/, '')) + (o.locator ? ' · ' + esc(o.locator) : '')}</a>`;
const STATUS = { observed: ['Implemented', 'good'], partial: ['Implemented with exceptions', 'warn'], not_observed: ['Not implemented', 'bad'], unverified: ['Implementation unverified', 'warn'], no_transactions: ['No transaction data', 'mute'] };

const MENU = [['intro', 'Overview', 'About Plus Factor'], ['input', 'New Analysis', 'Records and facts'], ['summary', 'Summary of Findings', 'Key measures'], ['conduct', 'Parallel Conduct Analysis', 'Timing, pricing, deviations'],
  ['market', 'Relevant Market Analysis', 'Candidate definitions'], ['documents', 'Evidence Classification', 'Passage-level decisions'], ['cases', 'Case Law Research', 'CourtListener opinions'], ['assumptions', 'Methodology & Sources', 'Inferences and inputs']];
function side(on) { $('#side').innerHTML = `<div class="sh">Tools</div>` + MENU.map(([k, l, d]) => { const ok = k === 'input' || k === 'intro' || (S.r && document.getElementById('sec-' + k));
  return `<a data-go="${k}" class="${on === k ? 'on' : ''} ${ok ? '' : 'dis'}"><b>${l}</b><small>${d}</small></a>`; }).join('') + `<p class="foot">Runs locally. Results are observations for attorney review, not findings of agreement.</p>`; }
function login(msg) {
  S.r = null; $('#nav').innerHTML = ''; $('#side').innerHTML = '';
  $('#app').innerHTML = `<section class="intro login"><div class="eyebrow">Plus Factor</div><h1>Sign in</h1>
    <p class="lede">Access is limited to authorised users. Documents you provide are held in a private workspace, are not written to disk, and are discarded when you sign out or after a period of inactivity.</p>
    <form id="lf"><label>Email<input name="email" type="email" autocomplete="username" required></label><label>Password<input name="password" type="password" autocomplete="current-password" required></label>
    ${msg ? `<p class="err">${esc(msg)}</p>` : ''}<button class="primary">Sign in</button></form></section>`;
  $('#lf').onsubmit = async e => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target));
    try { const me = await api('/login', f); S.me = me.email; intro(); } catch (x) { login(x.message); } };
}
const userNav = () => S.me ? `<span class="who">${esc(S.me)}</span><button id="logout">Sign out</button>` : '';
function intro() {
  $('#nav').innerHTML = userNav();
  $('#app').innerHTML = `<section class="intro"><div class="eyebrow">Antitrust analytics</div><h1>Parallel conduct and market definition, grounded in the record.</h1>
    <p class="lede">Plus Factor reconstructs supplier pricing conduct from purchaser records and price notices, tests the conduct against competing market definitions, and classifies each piece of evidence with a transparent decision model. Every finding is traceable to its source.</p>
    <ol class="steps"><li><b>Provide the record.</b><span>Upload invoices, price notices, contracts and interview notes, or enter the known facts directly.</span></li>
      <li><b>Review the analysis.</b><span>Announcement and implementation timing by supplier, deviations, and candidate market definitions.</span></li>
      <li><b>Assess the evidence.</b><span>Passage-level classifications with confidence, and related federal case law from CourtListener.</span></li></ol>
    <div class="row"><button id="begin" class="primary">Begin analysis</button><button id="sample" class="ghost">Open sample matter</button></div>
    <p class="fine">Processing occurs locally. Outputs are analytical observations for attorney review; they are not findings of agreement or assessments of pleading sufficiency.</p></section>`;
  side('intro');
}
function home() {
  $('#nav').innerHTML = userNav();
  const row = (r, i) => `<tr>${['name', 'announced', 'effective', 'pct', 'before', 'after'].map(k => `<td><input data-row="${i}" data-k="${k}" value="${esc(r[k] || '')}" type="${['announced', 'effective'].includes(k) ? 'date' : k === 'name' ? 'text' : 'number'}" step="any" placeholder="${{ name: 'Supplier', pct: '%', before: '$', after: '$' }[k] || ''}"></td>`).join('')}</tr>`;
  $('#app').innerHTML = `<section class="intake"><h1>New Analysis</h1><p class="sub">Provide purchaser records, supplier price notices and supporting notes, or enter the known facts. Each output cites its source.</p>
    <div class="tabs"><button data-mode="files" class="${S.mode === 'files' ? 'on' : ''}">Upload records</button><button data-mode="form" class="${S.mode === 'form' ? 'on' : ''}">Enter facts</button></div>
    ${S.mode === 'files' ? `<div id="drop" class="drop"><div class="big">Drag records here</div><div>or <label class="link">browse<input id="pick" type="file" multiple hidden></label> · CSV and plain text</div><div id="chips" class="chips"></div></div>`
    : `<div class="form"><label>Product<input id="product" value="${esc(S.product)}" placeholder="e.g. food-grade citric acid"></label>
      <table class="entry"><thead><tr><th>Supplier</th><th>Announced</th><th>Effective</th><th>Increase</th><th>Price before</th><th>Price after</th></tr></thead><tbody>${S.rows.map(row).join('')}</tbody></table>
      <button id="addrow" class="ghost">+ Add supplier</button><p class="hint">Leave unknown fields blank. Without pricing data, announcements are shown but implementation cannot be assessed.</p></div>`}
    <textarea id="details" placeholder="Additional facts (optional): customer communications, meeting attendance, substitutes considered and rejected">${esc(S.details)}</textarea>
    <div class="row"><button id="go" class="primary">Run analysis</button><button id="sample" class="ghost">Load sample record</button></div>
    <p class="fine">Evidence is classified by Plus Factor’s built-in decision model on this machine. No document content is transmitted.</p></section>`;
  chips(); side('input');
}
const chips = () => { const c = $('#chips'); if (c) c.innerHTML = S.files.map((f, i) => `<span class="chip">${esc(f.filename)}<b data-rm="${i}">×</b></span>`).join(''); };
const addFiles = async list => { for (const f of list) S.files.push({ filename: f.name, content: await f.text() }); chips(); };
const busy = () => { $('#app').innerHTML = '<section class="intake"><div class="spin"></div><p class="sub">Processing records and classifying evidence…</p></section>'; };
const form = () => ({ product: S.product, suppliers: S.mode === 'form' ? S.rows : [] });
const analyze = async sample => { S.details = $('#details')?.value || '';
  busy(); try { S.r = await api(sample ? '/sample' : '/analyze', sample ? {} : { files: S.mode === 'files' ? S.files : [], form: form(), details: S.details }); results(); } catch (e) { home(); toast(e.message); } };

/* ---- charts ---- */
const day = s => Date.parse(s.length === 7 ? s + '-15T00:00:00Z' : s + 'T00:00:00Z') / 864e5;
function conductChart(c) {
  const lanes = Object.entries(c.lanes), [a, b] = c.window.map(day), L = 64, R = 190, W = 1040, PH = 250, LH = 34, top = 28, lt = top + PH + 70;
  const X = d => L + (day(d) - a) / (b - a || 1) * (W - L - R), all = c.series.flatMap(s => s.points.map(p => p[1]));
  const lo = Math.min(...all) * 0.97, hi = Math.max(...all) * 1.03, Y = v => top + PH - (v - lo) / (hi - lo || 1) * PH;
  let g = '';
  for (let i = 0; i <= 4; i++) { const v = lo + (hi - lo) * i / 4; g += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" class="grid"/><text x="${L - 8}" y="${Y(v) + 4}" class="ax" text-anchor="end">$${v.toFixed(2)}</text>`; }
  const d0 = new Date(c.window[0] + 'T00:00:00Z');
  for (let d = new Date(Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth(), 1)); d.getTime() / 864e5 <= b; d.setUTCMonth(d.getUTCMonth() + 1)) { const iso = d.toISOString().slice(0, 10); if (day(iso) < a) continue;
    g += `<text x="${X(iso)}" y="${top + PH + 18}" class="ax">${d.toLocaleString('en', { month: 'short', timeZone: 'UTC' })}${d.getUTCMonth() === 0 ? ' ’' + String(d.getUTCFullYear()).slice(2) : ''}</text>`; }
  const effs = [...new Set(lanes.flatMap(([, l]) => l.events.filter(e => e.type === 'effective').map(e => e.date_start)))];
  effs.forEach(e => g += `<line x1="${X(e)}" x2="${X(e)}" y1="${top - 8}" y2="${lt + lanes.length * LH - 10}" class="eff"/><text x="${X(e) + 5}" y="${top - 12}" class="effl">stated effective date · ${e}</text>`);
  c.series.forEach(s => { const col = S.color[s.key], pts = s.points.map(p => [X(p[0]), Y(p[1])]), last = pts[pts.length - 1];
    g += `<polyline points="${pts.map(p => p.join(',')).join(' ')}" fill="none" stroke="${col}" stroke-width="2.5" stroke-linejoin="round"/>` + pts.map(p => `<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="${col}"/>`).join('')
      + `<text x="${last[0] + 8}" y="${last[1] + 4}" class="sl" fill="${col}">${esc(s.name)}</text>`; });
  g += `<text x="${L}" y="${lt - 26}" class="hd">WHAT EACH SUPPLIER SAID, AND WHEN</text>`;
  lanes.forEach(([k, l], i) => { const y = lt + i * LH, col = S.color[k] || '#94a3b8';
    g += `<line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" class="lane"/><text x="${W - R + 8}" y="${y + 4}" class="sl" fill="${col}">${esc(l.name)}</text>`;
    if (!l.events.length) g += `<text x="${L + 6}" y="${y - 5}" class="empty">no announcement in the files supplied</text>`;
    l.events.forEach(e => { const x1 = X(e.date_start), x2 = X(e.date_end), x = (x1 + x2) / 2;
      const shape = e.type === 'announcement' ? `<path d="M${x} ${y - 8}l8 14h-16z" fill="${col}"/>` : e.type === 'effective' ? `<circle cx="${x}" cy="${y}" r="6.5" fill="#fff" stroke="${col}" stroke-width="2.5"/>`
        : e.type === 'decision' ? `<path d="M${x} ${y - 8}l8 8-8 8-8-8z" fill="#fff" stroke="${col}" stroke-width="2.5"/>` : `<path d="M${x - 6} ${y - 6}l12 12m0-12l-12 12" stroke="#dc2626" stroke-width="2.5"/>`;
      g += `<a data-src="${e.source_id}" data-span="${e.span_ids[0]}"><title>${lab(e.type)} · ${e.date_start}${e.precision !== 'day' ? ' to ' + e.date_end : ''}${e.value ? ' · ' + e.value + '%' : ''}</title>${x2 - x1 > 3 ? `<line x1="${x1}" x2="${x2}" y1="${y}" y2="${y}" stroke="${col}" stroke-width="7" opacity=".25" stroke-linecap="round"/>` : ''}${shape}</a>`; }); });
  return `<svg viewBox="0 0 ${W} ${lt + lanes.length * LH + 4}" class="chart"><text x="${L}" y="12" class="hd">MEDIAN UNIT PRICE PER LB, BY MONTH</text>${g}</svg>
    <div class="legend"><span>▲ announcement</span><span>○ stated effective date</span><span>◇ decision (as described)</span><span class="x">✕ exception</span><span>shaded bar = uncertain date</span><span>click a marker to open the source</span></div>`;
}
function marketChart(ms) {
  return ms.map(m => `<div class="mk"><div class="mkh"><div><b>${esc(m.name.split(': ')[0])}</b><span>${esc(m.name.split(': ')[1] || '')}</span></div><span class="pill ${m.baseline ? 'mute' : m.pattern_holds ? 'good' : 'bad'}">${m.baseline ? 'Baseline definition' : m.pattern_holds ? 'Parallelism sustained' : 'Parallelism not sustained'}</span></div>
    <div class="bar">${m.suppliers.map(s => `<i style="width:${(s.share * 100).toFixed(2)}%;background:${S.color[s.key]}${s.status === 'not_observed' ? ';opacity:.45' : ''}" title="${esc(s.name)} · ${(s.share * 100).toFixed(1)}% of purchases · ${STATUS[s.status]?.[0] || s.status}"></i>`).join('')}</div>
    <div class="mkf">${m.suppliers.map(s => `<span><em style="background:${S.color[s.key]}"></em>${esc(s.name)} ${(s.share * 100).toFixed(0)}%${s.status === 'not_observed' ? ' · flat' : ''}</span>`).join('')}</div>
    <p>${m.transactions} invoice lines · ${m.announcers} of ${m.with_records} suppliers announced · ${esc(m.reading)}</p></div>`).join('');
}

function results() {
  const r = S.r, c = r.conduct;
  $('#nav').innerHTML = '<button id="dl">Download data</button><button id="print">Print</button><button id="new" class="primary">New analysis</button>' + userNav();
  const keys = [...new Set([...(c ? Object.keys(c.lanes) : []), ...r.markets.flatMap(m => m.suppliers.map(s => s.key))])];
  keys.forEach((k, i) => S.color[k] = COLORS[i % COLORS.length]);
  const lanes = c ? Object.values(c.lanes) : [], ann = lanes.filter(l => l.has_conduct_event), moved = lanes.filter(l => ['observed', 'partial'].includes(l.implementation.status));
  const spread = c?.lags_days.announcement, wider = r.markets.filter(m => !m.baseline), broke = wider.filter(m => !m.pattern_holds), unv = ann.filter(l => ['unverified', 'no_transactions'].includes(l.implementation.status)).length, flatN = ann.filter(l => l.implementation.status === 'not_observed').length;
  const tile = (n, l, s) => `<div class="tile"><b>${n}</b><span>${l}</span><small>${s || ''}</small></div>`;
  $('#app').innerHTML = `<section class="res">
  ${c ? `<div class="tiles" id="sec-summary">${tile(`${ann.length}<i>/${lanes.length}</i>`, 'Suppliers Announcing Increases', spread ? `announcements within ${spread[1]} days` : 'of suppliers in the record')}
    ${tile(`${moved.length}<i>/${ann.length}</i>`, 'Implementation Verified', [unv && `${unv} unverified for lack of post-effective invoices`, flatN && `${flatN} with no price change in invoices`].filter(Boolean).join(' · ') || 'matched invoices, before vs after')}
    ${tile(c.exceptions.length, 'Deviations Identified', c.exceptions[0] ? esc(c.exceptions[0].kind) : 'none in the record')}
    ${tile(wider.length ? `${wider.length - broke.length}<i>/${wider.length}</i>` : '—', 'Parallelism Across Markets', !wider.length ? 'no broader definition testable on this record' : 'broader definitions in which parallelism is sustained')}</div>
  <div class="card" id="sec-conduct"><h2>Parallel Conduct Analysis</h2><p class="sub">${esc(c.denominator.text)} Clustered timing is reported as an observation and does not constitute a finding of agreement.</p>${conductChart(c)}
    <div class="notes">${c.flags.map(f => `<div class="call warn"><b>Common effective date, distinct decision dates.</b> ${esc(f.text)}</div>`).join('')}
    ${c.exceptions.map((x, i) => `<div class="call bad"><b>${i ? 'Additional deviation' : 'Principal deviation'}.</b> ${esc(x.text)}</div>`).join('')}</div>
    <table><thead><tr><th>Supplier</th><th>Announced</th><th>Effective</th><th class="n">Before</th><th class="n">After</th><th class="n">Change</th><th>Reading</th></tr></thead><tbody>
    ${Object.entries(c.lanes).flatMap(([k, l]) => { const im = l.implementation, an = l.events.find(e => e.type === 'announcement'), ef = l.events.find(e => e.type === 'effective'), gs = im.groups.length ? im.groups : [null];
      return gs.map((x, i) => `<tr><td>${i ? '' : `<em class="dot" style="background:${S.color[k]}"></em>${esc(l.name)}`}</td><td>${i ? '' : an ? cite(an, `${an.date_start}${an.value ? ' · +' + an.value + '%' : ''}`) : '—'}</td><td>${i ? '' : ef ? cite(ef, ef.date_start) : '—'}</td>
        <td class="n">${x ? '$' + x.pre_median.toFixed(3) : '—'}</td><td class="n">${x ? '$' + x.post_median.toFixed(3) : '—'}</td><td class="n ${x && !x.followed ? 'badt' : ''}">${x ? (x.change_pct > 0 ? '+' : '') + x.change_pct.toFixed(1) + '%' : '—'}${x && gs.length > 1 ? `<small> ${esc(x.ship_to)}</small>` : ''}</td>
        <td>${i ? '' : `<span class="pill ${STATUS[im.status]?.[1]}">${STATUS[im.status]?.[0] || lab(im.status)}</span>`}</td></tr>`); }).join('')}</tbody></table></div>
  <div class="card" id="sec-market"><h2>Relevant Market Analysis</h2><p class="sub">Candidate definitions derived from the purchaser’s transactions and expanded one boundary at a time. Shares reflect the purchaser’s purchases, not market share.</p>${marketChart(r.markets)}</div>`
  : `<div class="card" id="sec-conduct"><h2>Parallel Conduct Analysis</h2><p class="sub">Transaction data is required to assess implementation and market definition. Provide a purchase export (CSV).${r.events?.length ? ' Announcements found:' : ''}</p>${(r.events || []).map(e => `<div class="call">${esc(e.actor)} · ${lab(e.type)} · ${cite(e, e.date)}${e.value ? ' · +' + e.value + '%' : ''}</div>`).join('')}</div>`}
  <div class="card" id="sec-documents"><h2>Evidence Classification</h2><p class="sub">Each passage is evaluated against narrow, typed questions by ${esc(r.adapter)}. The model returns a probability for every permitted answer; answers below the 0.80 confidence threshold are withheld for attorney review. The model is never asked whether an agreement existed.</p>
    ${evidence(r)}</div>
  <div class="card" id="sec-cases"><h2>Case Law Research</h2><p class="sub">${r.cases.agreement.live ? 'Published opinions retrieved from CourtListener (Free Law Project). Holdings have not been reviewed and should be confirmed before reliance.' : 'CourtListener could not be reached; reference notes on published opinions are shown. Confirm each against the opinion.'}</p>
    <div class="cases">${[['Parallel Conduct and Plus Factors', r.cases.agreement.results], ['Defendant-Specific Participation', r.cases.attribution.results]].map(([t, rows]) => `<div><h3>${t}</h3>${rows.map(k => `<a class="case" href="${esc(k.url)}" target="_blank" rel="noopener"><b>${esc(k.name)}</b><span>${esc([k.citation, k.court, k.date].filter(Boolean).join(' · '))}</span><p>${esc(k.snippet)}</p></a>`).join('') || '<p class="hint">No results.</p>'}</div>`).join('')}</div>
    <h3>Adverse Authority</h3>${r.unfavorable.map(k => `<a class="case bad" href="${esc(k.url)}" target="_blank" rel="noopener"><b>${esc(k.name)}</b><span>${esc(k.citation)} · ${esc(k.disposition)} as to ${esc(k.scope)}</span><p>${esc(k.snippet)}</p></a>`).join('')}</div>
  <div class="card slim" id="sec-assumptions"><h2>Methodology &amp; Sources</h2><ul>${r.assumptions.map(a => `<li>${esc(a)}</li>`).join('')}</ul>
    ${r.skipped.length ? `<h3>Excluded inputs</h3><ul>${r.skipped.map(s => `<li><b>${esc(s.file)}</b>: ${esc(s.reason)}</li>`).join('')}</ul>` : ''}
    <p class="files">${r.files.map(f => `<a class="cite" data-src="${f.id}">${esc(f.name)}</a>`).join(' ')}</p></div></section>`;
  scrollTo(0, 0); side('summary');
}

const Q = { passage_kind: 'Subject of passage', knowledge_basis: 'Basis of knowledge', date_role: 'Role of date', assertion_support: 'Support for assertion' };
const ROUTE = { proposed: ['Proposed · pending review', 'good'], abstain: ['Withheld · below threshold', 'warn'], review_required: ['Referred for review', 'warn'], blocked: ['Blocked', 'bad'] };
function evidence(r) {
  const by = {}; r.checks.forEach(k => (by[k.span_id] ||= { ...k, qs: [] }).qs.push(k));
  const order = [...r.statements.map(s => s.span_id), ...Object.keys(by)].filter((v, i, a) => by[v] && a.indexOf(v) === i);
  const card = id => { const p = by[id];
    return `<div class="ev"><div class="evp"><div class="evsrc">${cite(p)}</div><p>${esc(p.passage)}</p></div><div class="evq">${p.qs.map(q => { const pr = Object.entries(q.probabilities || {}).sort((a, b) => b[1] - a[1]), rt = ROUTE[q.route] || [lab(q.route), 'mute'];
      return `<div class="qq"><div class="qh"><b>${Q[q.task] || esc(q.question)}</b><span class="pill ${rt[1]}">${rt[0]}</span></div>${pr.map(([l, v]) => `<div class="pb ${l === q.label ? 'top' : ''}"><span>${lab(l)}</span><i><em style="width:${(v * 100).toFixed(1)}%"></em><u></u></i><b>${(v * 100).toFixed(0)}%</b></div>`).join('')}</div>`; }).join('')}</div></div>`; };
  return order.slice(0, 6).map(card).join('') + (order.length > 6 ? `<details><summary>${order.length - 6} additional passages</summary>${order.slice(6).map(card).join('')}</details>` : '');
}
async function openSrc(id, span) {
  const s = await api('/sources/' + id), sp = s.spans.find(x => x.id === span), d = $('#drawer');
  const body = sp ? esc(s.text.slice(0, sp.start)) + `<mark id="hit">${esc(s.text.slice(sp.start, sp.end))}</mark>` + esc(s.text.slice(sp.end)) : esc(s.text);
  d.hidden = false;
  d.innerHTML = `<div class="dh"><div><b>${esc(s.filename)}</b><span>${lab(s.kind)}${sp ? ' · ' + esc(sp.locator) : ''} · ${s.integrity ? 'unaltered since upload' : 'HASH MISMATCH'}</span></div><button id="close">×</button></div><pre>${body}</pre>`;
  $('#hit')?.scrollIntoView({ block: 'center' });
}
const download = () => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(S.r, null, 1)], { type: 'application/json' })); a.download = 'plus-factor-analysis.json'; a.click(); };

document.addEventListener('click', e => { const t = e.target, c = t.closest('[data-src]');
  if (c) return openSrc(c.dataset.src, c.dataset.span).catch(x => toast(x.message));
  if (t.dataset.rm) { S.files.splice(+t.dataset.rm, 1); return chips(); }
  if (t.dataset.mode) { S.mode = t.dataset.mode; return home(); }
  const g = t.closest('[data-go]'); if (g) { const k = g.dataset.go; if (k === 'intro') { S.r = null; return intro(); } if (k === 'input') { S.r = null; return home(); }
    const el = document.getElementById('sec-' + k); if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'start' }); side(k); } return; }
  ({ logout: async () => { await api('/logout', {}); S.me = null; S.files = []; login(); }, begin: home, addrow: () => { S.rows.push({}); home(); }, go: () => analyze(false), sample: () => analyze(true), new: () => { S.files = []; S.details = ''; S.r = null; home(); }, close: () => $('#drawer').hidden = true, dl: download, print: () => print() })[t.id]?.();
  if (t.closest('#home')) { S.r = null; intro(); } });
document.addEventListener('change', e => { const t = e.target; if (t.id === 'pick') addFiles(t.files); if (t.id === 'usejev') S.jev = t.checked; });
document.addEventListener('input', e => { const t = e.target; if (t.dataset.row) S.rows[+t.dataset.row][t.dataset.k] = t.value; if (t.id === 'product') S.product = t.value; if (t.id === 'details') S.details = t.value; });
document.addEventListener('dragover', e => { e.preventDefault(); $('#drop')?.classList.add('over'); });
document.addEventListener('dragleave', () => $('#drop')?.classList.remove('over'));
document.addEventListener('drop', e => { e.preventDefault(); $('#drop')?.classList.remove('over'); if ($('#drop')) addFiles(e.dataTransfer.files); });
api('/me').then(m => { S.me = m.email; intro(); }).catch(() => login());
