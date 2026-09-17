'use strict';

/* ────────────────────────────────────────────────────────────
   Two-language support (es / en).

   Spanish is the default: the audience is in Buenos Aires, and
   venue/event names stay in Spanish regardless. Only the chrome
   translates — event titles are scraped data and are left alone.

   Language resolution order:
     1. ?lang= in the URL (shareable links)
     2. localStorage (a returning visitor's choice)
     3. navigator.language
     4. es
   ──────────────────────────────────────────────────────────── */

const STRINGS = {
  es: {
    'html.lang': 'es',
    'meta.title': 'QUILOMBO — recitales y fiestas en Buenos Aires',
    'meta.desc': 'Todos los recitales, fiestas y shows de Buenos Aires. Meses por delante, en una sola página.',

    'hero.eyebrow': 'Buenos Aires · actualizado',
    'hero.sub': 'Todo lo que se viene en la ciudad: recitales, fiestas y clubes.',
    'hero.subStrong': 'Meses por delante, en una sola página.',
    'hero.shows': 'shows',
    'hero.artists': 'artistas',
    'hero.venues': 'salas',
    'hero.months': 'meses',
    'hero.cue': 'ver la agenda',

    'ctl.search': 'Buscar artista, sala o género…',
    'ctl.allMonths': 'Todos los meses',
    'ctl.allVenues': 'Todas las salas',
    'ctl.allGenres': 'Todos los géneros',
    'ctl.byDate': 'Por fecha',
    'ctl.byArtist': 'Por artista',
    'ctl.month': 'Mes',
    'ctl.venue': 'Sala',
    'ctl.genre': 'Género',
    'ctl.view': 'Vista',

    'list.empty': 'Nada coincide con esa búsqueda.',
    'list.failed': 'No se pudieron cargar los datos.',
    'count': (n, a) => `${n} shows · ${a} artistas`,
    'foot.updated': (d, days) => `Actualizado ${d}. ${days} días con actividad.`,
    'foot.note': 'Datos recolectados de fuentes públicas. Horarios y precios pueden cambiar — confirmá siempre en el link de la entrada.',

    months: ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
      'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'],
    days: ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'],
    locale: 'es-AR',
  },

  en: {
    'html.lang': 'en',
    'meta.title': 'QUILOMBO — gigs and parties in Buenos Aires',
    'meta.desc': 'Every gig, party and show in Buenos Aires. Months ahead, on a single page.',

    'hero.eyebrow': 'Buenos Aires · updated',
    'hero.sub': "Everything coming up in the city: gigs, parties and clubs.",
    'hero.subStrong': 'Months ahead, on a single page.',
    'hero.shows': 'shows',
    'hero.artists': 'artists',
    'hero.venues': 'venues',
    'hero.months': 'months',
    'hero.cue': 'see the listings',

    'ctl.search': 'Search artist, venue or genre…',
    'ctl.allMonths': 'All months',
    'ctl.allVenues': 'All venues',
    'ctl.allGenres': 'All genres',
    'ctl.byDate': 'By date',
    'ctl.byArtist': 'By artist',
    'ctl.month': 'Month',
    'ctl.venue': 'Venue',
    'ctl.genre': 'Genre',
    'ctl.view': 'View',

    'list.empty': 'Nothing matches that search.',
    'list.failed': 'Could not load the data.',
    'count': (n, a) => `${n} shows · ${a} artists`,
    'foot.updated': (d, days) => `Updated ${d}. ${days} days with events.`,
    'foot.note': 'Data collected from public sources. Times and prices can change — always confirm on the ticket link.',

    months: ['January', 'February', 'March', 'April', 'May', 'June', 'July',
      'August', 'September', 'October', 'November', 'December'],
    days: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
    locale: 'en-GB',
  },
};

const SUPPORTED = Object.keys(STRINGS);

function pickLang() {
  const q = new URLSearchParams(location.search).get('lang');
  if (q && SUPPORTED.includes(q)) return q;
  try {
    const saved = localStorage.getItem('quilombo.lang');
    if (saved && SUPPORTED.includes(saved)) return saved;
  } catch { /* private mode: fall through */ }
  const nav = (navigator.language || 'es').slice(0, 2).toLowerCase();
  return SUPPORTED.includes(nav) ? nav : 'es';
}

const I18N = {
  lang: pickLang(),

  t(key, ...args) {
    const dict = STRINGS[this.lang] || STRINGS.es;
    const val = dict[key];
    if (typeof val === 'function') return val(...args);
    return val !== undefined ? val : (STRINGS.es[key] ?? key);
  },

  get months() { return (STRINGS[this.lang] || STRINGS.es).months; },
  get days() { return (STRINGS[this.lang] || STRINGS.es).days; },
  get locale() { return (STRINGS[this.lang] || STRINGS.es).locale; },

  set(lang) {
    if (!SUPPORTED.includes(lang) || lang === this.lang) return;
    this.lang = lang;
    try { localStorage.setItem('quilombo.lang', lang); } catch { /* ignore */ }
    // Keep the URL shareable without adding a history entry per toggle.
    const url = new URL(location.href);
    url.searchParams.set('lang', lang);
    history.replaceState(null, '', url);
    this.apply();
    document.dispatchEvent(new CustomEvent('langchange', { detail: lang }));
  },

  /** Swap every static string marked up in the HTML. */
  apply() {
    document.documentElement.lang = this.t('html.lang');
    document.title = this.t('meta.title');

    const desc = document.querySelector('meta[name="description"]');
    if (desc) desc.setAttribute('content', this.t('meta.desc'));

    document.querySelectorAll('[data-i18n]').forEach((el) => {
      el.textContent = this.t(el.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-ph]').forEach((el) => {
      el.setAttribute('placeholder', this.t(el.dataset.i18nPh));
    });
    document.querySelectorAll('[data-i18n-aria]').forEach((el) => {
      el.setAttribute('aria-label', this.t(el.dataset.i18nAria));
    });

    document.querySelectorAll('[data-lang-btn]').forEach((b) => {
      const on = b.dataset.langBtn === this.lang;
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', String(on));
    });
  },
};

window.I18N = I18N;
