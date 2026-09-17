'use strict';

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
  'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const DIAS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];

const $ = (id) => document.getElementById(id);
const out = $('out');

let DB = null;
let mode = 'date';

const norm = (s) => (s || '').toLowerCase()
  .normalize('NFD').replace(/[̀-ͯ]/g, '');

// Dates are plain YYYY-MM-DD; parse as local so nothing shifts a day.
function parseDay(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function esc(s) {
  return (s || '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

async function boot() {
  let res;
  try {
    res = await fetch('data.json', { cache: 'no-cache' });
    if (!res.ok) throw new Error(res.status);
    DB = await res.json();
  } catch (err) {
    out.innerHTML = '<p class="empty">No se pudieron cargar los datos.</p>';
    return;
  }

  // Precompute a search blob per event so filtering stays instant.
  DB.events.forEach((e) => {
    e._v = DB.venues[e.v];
    e._s = norm([e.t, e._v, (e.a || []).join(' '), (e.g || []).join(' ')].join(' '));
  });

  fillSelects();
  bind();
  render();

  const days = new Set(DB.events.map((e) => e.d));
  const months = new Set(DB.events.map((e) => e.d.slice(0, 7)));
  const artists = new Set();
  DB.events.forEach((e) => (e.a || []).forEach((a) => artists.add(norm(a))));
  $('tagline').textContent =
    `${DB.events.length} shows · ${artists.size} artistas · ${DB.venues.length} salas · `
    + `${months.size} meses por delante`;
  $('sources').textContent =
    `Actualizado ${DB.generated}. ${days.size} días con actividad.`;
}

function fillSelects() {
  const months = [...new Set(DB.events.map((e) => e.d.slice(0, 7)))].sort();
  months.forEach((m) => {
    const [y, mm] = m.split('-');
    $('month').add(new Option(`${MESES[+mm - 1]} ${y}`, m));
  });

  const counts = new Map();
  DB.events.forEach((e) => counts.set(e._v, (counts.get(e._v) || 0) + 1));
  [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .forEach(([v, n]) => $('venue').add(new Option(`${v} (${n})`, v)));

  (DB.genres || []).forEach((g) => $('genre').add(new Option(g, g)));
}

function bind() {
  let t;
  $('q').addEventListener('input', () => {
    clearTimeout(t);
    t = setTimeout(render, 120);
  });
  ['month', 'venue', 'genre'].forEach((id) =>
    $(id).addEventListener('change', render));

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
  const mo = $('month').value;
  const ve = $('venue').value;
  const ge = $('genre').value;
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
  $('count').textContent =
    `${rows.length} shows · ${artists.size} artistas`;

  if (!rows.length) {
    out.innerHTML = '<p class="empty">Nada coincide con esa búsqueda.</p>';
    return;
  }
  out.innerHTML = mode === 'date' ? byDate(rows) : byArtist(rows);
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

  let html = '';
  let lastMonth = '';
  [...days.keys()].sort().forEach((iso) => {
    const dt = parseDay(iso);
    const mk = iso.slice(0, 7);
    if (mk !== lastMonth) {
      lastMonth = mk;
      html += `<h2 class="month">${MESES[dt.getMonth()]} ${dt.getFullYear()}</h2>`;
    }
    html += `<section class="day">
      <div class="dnum">${DIAS[dt.getDay()]}<b>${dt.getDate()}</b></div>
      <div>${days.get(iso).map(eventHTML).join('')}</div>
    </section>`;
  });
  return html;
}

function byArtist(rows) {
  // One entry per artist, listing every date they play.
  const map = new Map();
  rows.forEach((e) => {
    (e.a || []).forEach((a) => {
      const k = norm(a);
      if (!k) return;
      if (!map.has(k)) map.set(k, { name: a, gigs: [] });
      map.get(k).gigs.push(e);
    });
  });

  const list = [...map.values()].sort((a, b) =>
    a.name.localeCompare(b.name, 'es', { sensitivity: 'base' }));

  const html = list.map((a) => {
    const gigs = a.gigs
      .slice()
      .sort((x, y) => x.d.localeCompare(y.d))
      .map((e) => {
        const dt = parseDay(e.d);
        return `<div class="gig"><a href="${esc(e.k || e.u)}" target="_blank" rel="noopener">`
          + `<b>${dt.getDate()} ${MESES[dt.getMonth()].slice(0, 3)}</b> · ${esc(e._v)}</a></div>`;
      }).join('');
    return `<div class="artist"><h3>${esc(a.name)}</h3>${gigs}</div>`;
  }).join('');

  return `<div class="artists">${html}</div>`;
}

boot();
