'use strict';

function heroFX() {
  // hero.js owns the WebGL backdrop; it reports false if unsupported,
  // in which case the CSS gradient + grid carry the hero on their own.
  if (typeof window.initHero === 'function') window.initHero();
}

/* ────────────────────────── data ────────────────────────── */
const T = (k, ...a) => window.I18N.t(k, ...a);
const MESES = () => window.I18N.months;
const DIAS = () => window.I18N.days;

const $ = (id) => document.getElementById(id);
const out = $('out');

let DB = null;
let mode = 'date';

const norm = (s) => (s || '').toLowerCase()
  .normalize('NFD').replace(/[̀-ͯ]/g, '');

function parseDay(iso) {            // local-time parse; avoids UTC day shift
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function esc(s) {
  return (s || '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function countUp(el, to) {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce || to < 2) { el.textContent = to.toLocaleString(window.I18N.locale); return; }
  const dur = 900, t0 = performance.now();
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur);
    const eased = 1 - Math.pow(1 - k, 3);
    el.textContent = Math.round(to * eased).toLocaleString(window.I18N.locale);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

async function boot() {
  window.I18N.apply();
  heroFX();

  try {
    const res = await fetch('data.json', { cache: 'no-cache' });
    if (!res.ok) throw new Error(res.status);
    DB = await res.json();
  } catch {
    out.innerHTML = `<p class="empty">${T('list.failed')}</p>`;
    return;
  }

  DB.events.forEach((e) => {
    e._v = DB.venues[e.v];
    e._s = norm([e.t, e._v, (e.a || []).join(' '), (e.g || []).join(' ')].join(' '));
  });

  fillSelects();
  bind();
  render();

  const months = new Set(DB.events.map((e) => e.d.slice(0, 7)));
  const artists = new Set();
  DB.events.forEach((e) => (e.a || []).forEach((a) => artists.add(norm(a))));

  $('gen').textContent = DB.generated;
  const vals = [DB.events.length, artists.size, DB.venues.length, months.size];
  $('stats').querySelectorAll('.stat b').forEach((el, i) => countUp(el, vals[i]));

  const days = new Set(DB.events.map((e) => e.d));
  $('sources').textContent = T('foot.updated', DB.generated, days.size);
}

function fillSelects() {
  // Remember the active filters so switching language doesn't reset them.
  const keep = { month: $('month').value, venue: $('venue').value, genre: $('genre').value };
  ['month', 'venue', 'genre'].forEach((id) => { $(id).innerHTML = ''; });

  $('month').add(new Option(T('ctl.allMonths'), ''));
  [...new Set(DB.events.map((e) => e.d.slice(0, 7)))].sort().forEach((m) => {
    const [y, mm] = m.split('-');
    $('month').add(new Option(`${MESES()[+mm - 1]} ${y}`, m));
  });

  $('venue').add(new Option(T('ctl.allVenues'), ''));
  const counts = new Map();
  DB.events.forEach((e) => counts.set(e._v, (counts.get(e._v) || 0) + 1));
  [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .forEach(([v, n]) => $('venue').add(new Option(`${v} (${n})`, v)));

  // Genres come from the scraped data (RA's own taxonomy) and stay as-is.
  $('genre').add(new Option(T('ctl.allGenres'), ''));
  (DB.genres || []).forEach((g) => $('genre').add(new Option(g, g)));

  $('month').value = keep.month;
  $('venue').value = keep.venue;
  $('genre').value = keep.genre;
}

function bind() {
  document.querySelectorAll('[data-lang-btn]').forEach((b) =>
    b.addEventListener('click', () => window.I18N.set(b.dataset.langBtn)));

  // Static strings are swapped by I18N.apply(); anything rendered from
  // data has to be rebuilt here.
  document.addEventListener('langchange', () => {
    fillSelects();
    render();
    const days = new Set(DB.events.map((e) => e.d));
    $('sources').textContent = T('foot.updated', DB.generated, days.size);
  });

  let t;
  $('q').addEventListener('input', () => { clearTimeout(t); t = setTimeout(render, 110); });
  ['month', 'venue', 'genre'].forEach((id) => $(id).addEventListener('change', render));
  $('mode-date').addEventListener('click', () => setMode('date'));
  $('mode-artist').addEventListener('click', () => setMode('artist'));
}

function setMode(m) {
  mode = m;
  const d = m === 'date';
  $('mode-date').classList.toggle('on', d);
  $('mode-artist').classList.toggle('on', !d);
  $('mode-date').setAttribute('aria-selected', String(d));
  $('mode-artist').setAttribute('aria-selected', String(!d));
  render();
}

function current() {
  const q = norm($('q').value.trim());
  const mo = $('month').value, ve = $('venue').value, ge = $('genre').value;
  return DB.events.filter((e) => {
    if (mo && !e.d.startsWith(mo)) return false;
    if (ve && e._v !== ve) return false;
    if (ge && !(e.g || []).includes(ge)) return false;
    if (q && !e._s.includes(q)) return false;
    return true;
  });
}

function render() {
  const rows = current();
  const artists = new Set();
  rows.forEach((e) => (e.a || []).forEach((a) => artists.add(norm(a))));
  $('count').textContent = T('count', rows.length, artists.size);

  out.innerHTML = rows.length
    ? (mode === 'date' ? byDate(rows) : byArtist(rows))
    : `<p class="empty">${T('list.empty')}</p>`;
}

function eventHTML(e) {
  const bits = [];
  if (e.h) bits.push(esc(e.h));
  bits.push(`<span class="venue">${esc(e._v)}</span>`);
  if (e.p) bits.push(esc(e.p));

  const chips = (e.g || []).map((g) => `<span class="chip">${esc(g)}</span>`);
  chips.push(`<span class="chip src">${esc((e.s || []).join(' · '))}</span>`);

  return `<div class="ev">
    <a class="name" href="${esc(e.k || e.u)}" target="_blank" rel="noopener">${esc(e.t)}</a>
    <div class="meta">${bits.join(' · ')}</div>
    <div class="chips">${chips.join('')}</div>
  </div>`;
}

function byDate(rows) {
  const days = new Map();
  rows.forEach((e) => {
    if (!days.has(e.d)) days.set(e.d, []);
    days.get(e.d).push(e);
  });

  let html = '', lastMonth = '';
  [...days.keys()].sort().forEach((iso) => {
    const dt = parseDay(iso), mk = iso.slice(0, 7);
    if (mk !== lastMonth) {
      lastMonth = mk;
      html += `<h2 class="month">${MESES()[dt.getMonth()]} ${dt.getFullYear()}</h2>`;
    }
    html += `<section class="day">
      <div class="dnum">${DIAS()[dt.getDay()]}<b>${dt.getDate()}</b></div>
      <div>${days.get(iso).map(eventHTML).join('')}</div>
    </section>`;
  });
  return html;
}

function byArtist(rows) {
  const map = new Map();
  rows.forEach((e) => (e.a || []).forEach((a) => {
    const k = norm(a);
    if (!k) return;
    if (!map.has(k)) map.set(k, { name: a, gigs: [] });
    map.get(k).gigs.push(e);
  }));

  const list = [...map.values()]
    .sort((a, b) => a.name.localeCompare(b.name, window.I18N.locale, { sensitivity: 'base' }));

  return `<div class="artists">${list.map((a) => {
    const gigs = a.gigs.slice().sort((x, y) => x.d.localeCompare(y.d)).map((e) => {
      const dt = parseDay(e.d);
      return `<div class="gig"><a href="${esc(e.k || e.u)}" target="_blank" rel="noopener">`
        + `<b>${dt.getDate()} ${MESES()[dt.getMonth()].slice(0, 3)}</b> · ${esc(e._v)}</a></div>`;
    }).join('');
    return `<div class="artist"><h3>${esc(a.name)}</h3>${gigs}</div>`;
  }).join('')}</div>`;
}

boot();
