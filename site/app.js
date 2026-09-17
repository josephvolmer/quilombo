'use strict';

/* ────────────────────────────────────────────────────────────
   Hero particle field — tsParticles (slim build), vendored at
   build time into vendor/ so there is no runtime CDN dependency.

   The library handles retina scaling, pointer interaction,
   pause-when-hidden and density-per-area, which is the fiddly
   part of doing this well. If it fails to load for any reason
   the hero still renders: the CSS grid, glow and type animation
   are independent of it.
   ──────────────────────────────────────────────────────────── */
function heroFX() {
  const host = document.getElementById('fx');
  if (!host || typeof tsParticles === 'undefined') return;

  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  tsParticles.load({
    id: 'fx',
    options: {
      fullScreen: { enable: false },
      detectRetina: true,
      fpsLimit: 60,
      pauseOnBlur: true,
      pauseOnOutsideViewport: true,   // stops once the hero scrolls away
      background: { color: 'transparent' },
      particles: {
        number: {
          value: 90,
          density: { enable: true, width: 1600, height: 900 },
        },
        color: { value: '#a3e635' },
        opacity: { value: { min: 0.25, max: 0.6 } },
        size: { value: { min: 0.7, max: 2.1 } },
        links: {
          enable: true,
          distance: 130,
          color: '#a3e635',
          opacity: 0.18,
          width: 1,
        },
        move: {
          enable: !reduce,
          speed: 0.5,
          direction: 'none',
          outModes: { default: 'out' },
        },
      },
      interactivity: {
        detectsOn: 'window',
        events: {
          onHover: { enable: !reduce, mode: 'grab' },
          resize: { enable: true },
        },
        modes: {
          grab: { distance: 170, links: { opacity: 0.45 } },
        },
      },
    },
  });
}

/* ────────────────────────── data ────────────────────────── */
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
  'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const DIAS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];

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
  if (reduce || to < 2) { el.textContent = to.toLocaleString('es-AR'); return; }
  const dur = 900, t0 = performance.now();
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur);
    const eased = 1 - Math.pow(1 - k, 3);
    el.textContent = Math.round(to * eased).toLocaleString('es-AR');
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

async function boot() {
  heroFX();

  try {
    const res = await fetch('data.json', { cache: 'no-cache' });
    if (!res.ok) throw new Error(res.status);
    DB = await res.json();
  } catch {
    out.innerHTML = '<p class="empty">No se pudieron cargar los datos.</p>';
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
  $('sources').textContent =
    `Actualizado ${DB.generated}. ${days.size} días con actividad.`;
}

function fillSelects() {
  [...new Set(DB.events.map((e) => e.d.slice(0, 7)))].sort().forEach((m) => {
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
  $('count').textContent = `${rows.length} shows · ${artists.size} artistas`;

  out.innerHTML = rows.length
    ? (mode === 'date' ? byDate(rows) : byArtist(rows))
    : '<p class="empty">Nada coincide con esa búsqueda.</p>';
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
  const map = new Map();
  rows.forEach((e) => (e.a || []).forEach((a) => {
    const k = norm(a);
    if (!k) return;
    if (!map.has(k)) map.set(k, { name: a, gigs: [] });
    map.get(k).gigs.push(e);
  }));

  const list = [...map.values()]
    .sort((a, b) => a.name.localeCompare(b.name, 'es', { sensitivity: 'base' }));

  return `<div class="artists">${list.map((a) => {
    const gigs = a.gigs.slice().sort((x, y) => x.d.localeCompare(y.d)).map((e) => {
      const dt = parseDay(e.d);
      return `<div class="gig"><a href="${esc(e.k || e.u)}" target="_blank" rel="noopener">`
        + `<b>${dt.getDate()} ${MESES[dt.getMonth()].slice(0, 3)}</b> · ${esc(e._v)}</a></div>`;
    }).join('');
    return `<div class="artist"><h3>${esc(a.name)}</h3>${gigs}</div>`;
  }).join('')}</div>`;
}

boot();
