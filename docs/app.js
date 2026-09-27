import { $, esc, fail, int, kpis, load, pct, table } from './kit.js';

// graphrag/retrieve.py's router and graph walk, in the browser.
const VERB = /\b(depend(?:s|ed)? on|rel(?:y|ies) on|requires?|needs?|pulls? in|built on|dependenc(?:y|ies))\b/;
const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export function makeRetriever(d) {
  const entities = (question) => {
    const found = []; let text = question.toLowerCase();
    for (const [alias, node] of d.aliases) {
      if (alias.length <= 2) continue;
      const m = new RegExp(`(?<![\\w-])${escRe(alias)}(?![\\w-])`).exec(text);
      if (m && !found.some(([n]) => n === node)) { found.push([node, m.index]); text = text.slice(0, m.index) + ' '.repeat(alias.length) + text.slice(m.index + alias.length); }
    }
    return found.sort((a, b) => a[1] - b[1]);
  };
  const route = (question) => {
    const named = entities(question), q = question.toLowerCase(), verb = VERB.exec(q);
    if (!named.length) return ['vector', 'fact', named];
    if (named.length >= 2 && /\b(in common|share[sd]?|both)\b/.test(q)) return ['graph', 'shared', named];
    if (verb && /licen[cs]e/.test(q)) return ['graph', 'dep_licenses', named];
    if (verb && /\b(maintain\w*|authors?|wrote)\b/.test(q)) return ['graph', 'dep_maintainers', named];
    if (verb) return ['graph', named[0][1] > verb.index && !verb[1].startsWith('dependenc') ? 'dependents' : 'deps', named];
    return ['vector', 'fact', named];
  };
  const out = (n) => d.nodes[n]?.deps || [], into = (n) => d.nodes[n]?.dependents || [];
  const graph = (names, intent, k = 10) => {
    if (intent === 'shared' && names.length >= 2) { const b = new Set(out(names[1])); return [...names.slice(0, 2), ...out(names[0]).filter((x) => b.has(x)).sort()].slice(0, k); }
    if (intent === 'dependents') return names.flatMap(into).slice(0, k);
    const deps = names.flatMap(out);
    return (['deps', 'dep_licenses', 'dep_maintainers'].includes(intent) ? deps : names).slice(0, k);
  };
  return { entities, route, graph };
}

const name = (d, n) => d.nodes[n]?.name || n.replace(/^package:/, '');
try {
  const d = await load();
  const R = makeRetriever(d), Q = d.questions, S = d.summary;
  const mean = (xs, k) => xs.reduce((a, x) => a + x[k], 0) / xs.length;
  kpis($('#kpis'), [
    { label: 'Recall@10, vector search', value: pct(mean(Q, 'vector')), note: '360 questions, six kinds' },
    { label: 'Recall@10, routed', value: pct(mean(Q, 'routed')), note: `graph for relationships; merged with vector: ${pct(mean(Q, 'both'))}` },
    { label: 'Router picked the right path', value: pct(Q.filter((q) => q.routed_intent === q.kind).length / Q.length), note: 'on the same questions' },
    { label: 'Graph', value: `${int(S.counts.Package)} packages`, note: `${int(S.counts.DEPENDS_ON)} dependencies; ${int(S.resolution.resolved)} of ${int(S.resolution.mentions)} names resolved` },
  ]);
  const ask = (question) => {
    const [path, intent, named] = R.route(question);
    $('#route').innerHTML = `<div>Packages named<b>${named.length ? esc(named.map(([n]) => name(d, n)).join(', ')) : 'none'}</b><span class="muted small">longest alias first</span></div>` +
      `<div>Route<b>${path === 'graph' ? `graph: ${intent.replace('_', ' ')}` : 'vector search'}</b><span class="muted small">${path === 'graph' ? 'walks edges; each answer cites its source chunk' : 'no relationship the graph can follow'}</span></div>`;
    if (path !== 'graph') { $('#answer').innerHTML = '<p class="muted">Vector search runs on bge-small embeddings, which this page does not load. On fact questions it finds the right package in the top 10 almost every time.</p>'; return; }
    const nodes = R.graph(named.map(([n]) => n), intent);
    if (intent === 'dep_maintainers') { $('#answer').innerHTML = `<p class="muted">The graph would list the maintainers of ${esc(nodes.map((n) => name(d, n)).join(', ') || 'no dependencies')}; their names are left out of this page.</p>`; return; }
    const rows = intent === 'dep_licenses'
      ? nodes.flatMap((n) => (d.nodes[n]?.licences.length ? d.nodes[n].licences : ['not in the corpus']).map((l) => ({ pkg: name(d, n), licence: l, src: `${n}#0` })))
      : nodes.map((n) => ({ pkg: name(d, n), src: `${n}#0` }));
    if (!rows.length) { $('#answer').innerHTML = '<p class="muted">The graph has no such edges for that package.</p>'; return; }
    table($('#answer'), [{ key: 'pkg', label: 'Package' }, ...(intent === 'dep_licenses' ? [{ key: 'licence', label: 'Licence' }] : []), { key: 'src', label: 'Source chunk', fmt: (v) => v }], rows);
  };
  const samples = ['What does fastapi depend on?', 'What depends on urllib3?', 'What licences do the packages httpx needs use?', 'What do requests and httpx have in common?', 'What is attrs used for?'];
  $('#examples').innerHTML = 'Try: ' + samples.map((s) => `<button type="button" class="step" data-q="${esc(s)}">${esc(s)}</button>`).join(' ');
  $('#examples').onclick = (e) => { const b = e.target.closest('button[data-q]'); if (b) { $('#q').value = b.dataset.q; ask(b.dataset.q); } };
  $('#form').onsubmit = (e) => { e.preventDefault(); if ($('#q').value.trim()) ask($('#q').value); };
  $('#q').value = samples[0];
  ask(samples[0]);

  const kinds = [...new Set(Q.map((q) => q.kind))];
  table($('#kinds'), [
    { key: 'kind', label: 'Question kind' }, { key: 'n', label: 'Questions', num: true },
    { key: 'router', label: 'Router right', num: true, fmt: (v) => pct(v, 0) },
    { key: 'vector', label: 'Vector', num: true, fmt: (v) => pct(v) }, { key: 'routed', label: 'Routed', num: true, fmt: (v) => pct(v) }, { key: 'both', label: 'Merged', num: true, fmt: (v) => pct(v) },
  ], kinds.map((k) => { const xs = Q.filter((q) => q.kind === k); return { kind: k.replace('_', ' '), n: xs.length, router: xs.filter((q) => q.routed_intent === k).length / xs.length, vector: mean(xs, 'vector'), routed: mean(xs, 'routed'), both: mean(xs, 'both') }; }),
  { cls: (r) => (r.vector < 0.5 ? 'bad' : '') });
} catch (err) {
  fail(err);
}
