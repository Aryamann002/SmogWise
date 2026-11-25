// @ts-check
/**
 * SmogWise frontend: collects the household profile, requests a plan and renders it.
 * All API text is written with textContent, never innerHTML, so it cannot inject markup.
 */

/** @typedef {{name: string, admin?: string|null, country?: string|null, country_code: string|null, latitude: number, longitude: number}} Place */
/** @typedef {{time: string, pm2_5: number}} HourlyPm */
/** @typedef {{exposure_reduction_pct: number|null, co2_kg_per_day: number|null, pm25_g_per_day: number|null}} Impact */
/** @typedef {{id: string, category: string, title: string, how: string, impact: Impact, explanation: string, method: string}} Action */
/** @typedef {{time: string, activity: string, why: string}} RoutineStep */
/** @typedef {{aqi: number, aqi_scale: string, category: string, level: number, pm2_5: number, best_hour: HourlyPm, worst_hour: HourlyPm, forecast: HourlyPm[]}} AirQuality */
/** @typedef {{households: number, co2_kg_per_day: number|null, pm25_g_per_day: number|null}} Community */
/** @typedef {{location: string, air: AirQuality, summary: string, routine: RoutineStep[], actions: Action[], community: Community, source: 'gemini'|'rules'}} Plan */

const API = Object.freeze({ geocode: '/api/geocode', plan: '/api/plan' });
const MIN_QUERY_LENGTH = 2;
const NOTES_MAX = 300;
const HOURS_PER_AXIS_LABEL = 6;
// Illustrative Delhi winter day for the landing-page card, shaped like a real hourly forecast.
const EXAMPLE_DAY = [
  104, 103, 104, 106, 107, 107, 116, 139, 160, 132, 113, 101, 84, 69, 63, 60, 70, 92, 113, 127, 134,
  137, 140, 140,
].map((pm2_5, hour) => ({ time: `2026-01-15T${String(hour).padStart(2, '0')}:00`, pm2_5 }));
const EXAMPLE_CLEANEST = EXAMPLE_DAY[15];
const EXAMPLE_SMOGGIEST = EXAMPLE_DAY[8];
// ponytail: geolocation gives no country, so infer India from the time zone for its AQI scale.
const INDIA_TIME_ZONES = new Set(['Asia/Kolkata', 'Asia/Calcutta']);
const CATEGORY_LABELS = Object.freeze({
  health: 'Health',
  indoor: 'Indoor air',
  transport: 'Transport',
  heating: 'Heating',
  cooking: 'Cooking',
  community: 'Community',
});

const number = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });

/**
 * @template {HTMLElement} T
 * @param {string} id
 * @returns {T}
 */
function byId(id) {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing element #${id}`);
  return /** @type {T} */ (element);
}

const dom = {
  form: /** @type {HTMLFormElement} */ (byId('plan-form')),
  placeQuery: /** @type {HTMLInputElement} */ (byId('place-query')),
  searchButton: /** @type {HTMLButtonElement} */ (byId('search-button')),
  locateButton: /** @type {HTMLButtonElement} */ (byId('locate-button')),
  placeSelect: /** @type {HTMLSelectElement} */ (byId('place-select')),
  placeStatus: byId('place-status'),
  language: /** @type {HTMLSelectElement} */ (byId('language')),
  notes: /** @type {HTMLTextAreaElement} */ (byId('notes')),
  notesCount: byId('notes-count'),
  formError: byId('form-error'),
  submitButton: /** @type {HTMLButtonElement} */ (byId('submit-button')),
  planStatus: byId('plan-status'),
  results: byId('results'),
  resultsTitle: byId('results-title'),
  aqiBadge: byId('aqi-badge'),
  aqiValue: byId('aqi-value'),
  aqiLabel: byId('aqi-label'),
  pmNow: byId('pm-now'),
  bestHour: byId('best-hour'),
  worstHour: byId('worst-hour'),
  previewChart: byId('preview-chart'),
  chart: byId('forecast-chart'),
  chartCaption: byId('forecast-caption'),
  forecastRows: byId('forecast-rows'),
  summary: byId('summary'),
  routine: byId('routine'),
  actions: byId('actions'),
  communityText: byId('community-text'),
  communityCo2: byId('community-co2'),
  communityPm: byId('community-pm'),
  sourceNote: byId('source-note'),
  printButton: /** @type {HTMLButtonElement} */ (byId('print-button')),
  routineTemplate: /** @type {HTMLTemplateElement} */ (byId('routine-template')),
  actionTemplate: /** @type {HTMLTemplateElement} */ (byId('action-template')),
};

/** @type {{places: Place[]}} */
const state = { places: [] };

// --- API -------------------------------------------------------------------------------

/**
 * Fetch JSON and surface the API's safe error message on failure.
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<any>}
 */
async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error?.message ?? 'Something went wrong. Please try again.');
  }
  return body;
}

// --- Place selection -------------------------------------------------------------------

/** @param {Place} place */
function placeLabel(place) {
  return [place.name, place.admin, place.country].filter(Boolean).join(', ');
}

/** @param {Place[]} places */
function showPlaces(places) {
  state.places = places;
  dom.placeSelect.replaceChildren(
    ...places.map((place, index) => new Option(placeLabel(place), String(index))),
  );
  dom.placeSelect.disabled = places.length === 0;
  if (places.length === 0) {
    dom.placeSelect.append(new Option('No matches, try another spelling', ''));
  }
}

async function searchPlaces() {
  const query = dom.placeQuery.value.trim();
  if (query.length < MIN_QUERY_LENGTH) {
    dom.placeStatus.textContent = 'Type at least two letters of your city or town.';
    dom.placeQuery.focus();
    return;
  }
  dom.placeStatus.textContent = 'Searching…';
  try {
    const places = await fetchJson(`${API.geocode}?${new URLSearchParams({ q: query })}`);
    showPlaces(places);
    dom.placeStatus.textContent = places.length
      ? `Found ${places.length} place${places.length > 1 ? 's' : ''}. Choose yours from the list.`
      : 'No places found.';
    if (places.length) dom.placeSelect.focus();
  } catch (error) {
    dom.placeStatus.textContent = /** @type {Error} */ (error).message;
  }
}

function guessCountryCode() {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return INDIA_TIME_ZONES.has(zone) ? 'IN' : null;
}

function useMyLocation() {
  if (!('geolocation' in navigator)) {
    dom.placeStatus.textContent = 'Your browser cannot share location. Please search instead.';
    return;
  }
  dom.placeStatus.textContent = 'Finding your location…';
  navigator.geolocation.getCurrentPosition(
    ({ coords }) => {
      showPlaces([
        {
          name: 'My location',
          country_code: guessCountryCode(),
          latitude: Number(coords.latitude.toFixed(4)),
          longitude: Number(coords.longitude.toFixed(4)),
        },
      ]);
      dom.placeStatus.textContent = 'Using your current location.';
    },
    () => {
      dom.placeStatus.textContent = 'Location unavailable or blocked. Please search instead.';
    },
    { timeout: 10000, maximumAge: 600000 },
  );
}

// --- Form ------------------------------------------------------------------------------

/**
 * Turn the form into the API's PlanRequest shape.
 * @returns {object}
 */
function readForm() {
  const data = new FormData(dom.form);
  const place = state.places[Number(dom.placeSelect.value)];
  return {
    location: {
      name: place.name,
      latitude: place.latitude,
      longitude: place.longitude,
      country_code: place.country_code ?? null,
    },
    household: {
      adults: Number(data.get('adults')),
      children: Number(data.get('children')),
      elderly: Number(data.get('elderly')),
      conditions: data.getAll('conditions'),
    },
    commute: { mode: data.get('commute-mode'), distance_km: Number(data.get('distance')) },
    home: {
      heating: data.get('heating'),
      cooking: data.get('cooking'),
      has_purifier: data.has('has-purifier'),
      room_area_m2: Number(data.get('room-area')),
    },
    exercises_outdoors: data.has('exercises-outdoors'),
    community_households: Number(data.get('community')),
    language: data.get('language'),
    notes: String(data.get('notes') ?? '').trim(),
  };
}

/** @param {string} message */
function showFormError(message) {
  dom.formError.textContent = message;
  dom.formError.hidden = false;
}

/** @param {boolean} busy */
function setBusy(busy) {
  dom.submitButton.disabled = busy;
  dom.submitButton.textContent = busy ? 'Building your plan…' : 'Get my plan';
  dom.results.setAttribute('aria-busy', String(busy));
  dom.planStatus.textContent = busy ? 'Fetching live air quality and building your plan…' : '';
}

/** @param {SubmitEvent} event */
async function submitPlan(event) {
  event.preventDefault();
  dom.formError.hidden = true;
  if (!state.places[Number(dom.placeSelect.value)]) {
    showFormError('Please search for and choose your city first.');
    dom.placeQuery.focus();
    return;
  }
  if (!dom.form.reportValidity()) return;
  setBusy(true);
  try {
    /** @type {Plan} */
    const plan = await fetchJson(API.plan, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(readForm()),
    });
    setBusy(false);
    renderPlan(plan, dom.language.value);
    dom.planStatus.textContent = 'Your plan is ready.';
    dom.resultsTitle.focus();
  } catch (error) {
    setBusy(false);
    showFormError(/** @type {Error} */ (error).message);
  }
}

// --- Rendering -------------------------------------------------------------------------

/** @param {string} isoTime local ISO time such as 2026-11-25T15:00 */
const clock = (isoTime) => isoTime.slice(11, 16);

/** @param {number} value */
const pm = (value) => `${number.format(Math.round(value))} µg/m³`;

/** @param {AirQuality} air */
function renderAir(air) {
  dom.aqiBadge.dataset.level = String(air.level);
  dom.aqiValue.textContent = `AQI ${air.aqi}`;
  dom.aqiLabel.textContent = `${air.category} (${air.aqi_scale})`;
  dom.pmNow.textContent = pm(air.pm2_5);
  dom.bestHour.textContent = `${clock(air.best_hour.time)}, ${pm(air.best_hour.pm2_5)}`;
  dom.worstHour.textContent = `${clock(air.worst_hour.time)}, ${pm(air.worst_hour.pm2_5)}`;
  renderBars(dom.chart, air.forecast, air.best_hour, air.worst_hour);
  renderForecastTable(air.forecast);
  dom.chartCaption.textContent =
    `PM2.5 for the next 24 hours: cleanest at ${clock(air.best_hour.time)}, ` +
    `smoggiest at ${clock(air.worst_hour.time)}.`;
}

/**
 * Draw an hourly PM2.5 column chart; the cleanest and smoggiest hours get their own colour.
 * Heights go through a CSS custom property because the CSP forbids inline style attributes.
 * @param {HTMLElement} chart
 * @param {HourlyPm[]} hours
 * @param {HourlyPm} cleanest
 * @param {HourlyPm} smoggiest
 */
function renderBars(chart, hours, cleanest, smoggiest) {
  const max = Math.max(...hours.map((hour) => hour.pm2_5), 1);
  const plot = document.createElement('div');
  const axis = document.createElement('div');
  plot.className = 'bars__plot';
  axis.className = 'bars__axis';
  hours.forEach((hour, index) => {
    const bar = document.createElement('span');
    bar.className = 'bars__bar';
    bar.classList.toggle('bars__bar--cleanest', hour.time === cleanest.time);
    bar.classList.toggle('bars__bar--smoggiest', hour.time === smoggiest.time);
    bar.dataset.tip = `${clock(hour.time)} · ${pm(hour.pm2_5)}`;
    bar.style.setProperty('--value', String(hour.pm2_5 / max));
    bar.style.setProperty('--index', String(index));
    plot.append(bar);
    if (index % HOURS_PER_AXIS_LABEL === 0) {
      const label = document.createElement('span');
      label.textContent = clock(hour.time);
      label.style.gridColumn = `${index + 1} / span ${HOURS_PER_AXIS_LABEL}`;
      axis.append(label);
    }
  });
  chart.replaceChildren(plot, axis);
}

/** @param {HourlyPm[]} hours the same values as the chart, for screen readers and keyboard users */
function renderForecastTable(hours) {
  dom.forecastRows.replaceChildren(
    ...hours.map((hour) => {
      const row = document.createElement('tr');
      const time = document.createElement('th');
      const value = document.createElement('td');
      time.scope = 'row';
      time.textContent = clock(hour.time);
      value.textContent = number.format(Math.round(hour.pm2_5));
      row.append(time, value);
      return row;
    }),
  );
}

/** @param {RoutineStep[]} routine */
function renderRoutine(routine) {
  dom.routine.replaceChildren(
    ...routine.map((step) => {
      const item = /** @type {DocumentFragment} */ (dom.routineTemplate.content.cloneNode(true));
      fill(item, '.routine__time', step.time);
      fill(item, '.routine__activity', step.activity);
      fill(item, '.routine__why', step.why);
      return item;
    }),
  );
}

/**
 * Human-readable impact figures; only the ones that apply.
 * @param {Impact} impact
 * @returns {[string, string][]}
 */
function impactEntries(impact) {
  /** @type {[string, string][]} */
  const entries = [];
  if (impact.exposure_reduction_pct != null) {
    entries.push(['Less PM2.5 breathed', `${number.format(Math.round(impact.exposure_reduction_pct))}%`]);
  }
  if (impact.co2_kg_per_day != null) {
    entries.push(['CO₂ avoided', `${number.format(impact.co2_kg_per_day)} kg/day`]);
  }
  if (impact.pm25_g_per_day != null) {
    entries.push(['PM2.5 kept out of the air', `${number.format(impact.pm25_g_per_day)} g/day`]);
  }
  return entries;
}

/**
 * @param {ParentNode} root
 * @param {string} selector
 * @param {string} text
 */
function fill(root, selector, text) {
  const element = root.querySelector(selector);
  if (element) element.textContent = text;
}

/**
 * @param {Action} action
 * @param {string} lang
 */
function renderAction(action, lang) {
  const item = /** @type {DocumentFragment} */ (dom.actionTemplate.content.cloneNode(true));
  const card = /** @type {HTMLElement} */ (item.querySelector('.action__card'));
  card.lang = lang;
  card.dataset.category = action.category;
  fill(item, '.action__category', CATEGORY_LABELS[/** @type {keyof CATEGORY_LABELS} */ (action.category)] ?? action.category);
  fill(item, '.action__title', action.title);
  fill(item, '.action__explanation', action.explanation);
  fill(item, '.action__how-text', action.how);
  fill(item, '.action__method-text', action.method);
  const impactList = /** @type {HTMLElement} */ (item.querySelector('.action__impact'));
  for (const [label, value] of impactEntries(action.impact)) {
    const wrapper = document.createElement('div');
    const term = document.createElement('dt');
    const detail = document.createElement('dd');
    term.textContent = label;
    detail.textContent = value;
    wrapper.append(term, detail);
    impactList.append(wrapper);
  }
  return item;
}

/** @param {number|null} grams */
function mass(grams) {
  const value = grams ?? 0;
  return value < 1000 ? `${number.format(value)} g` : `${number.format(value / 1000)} kg`;
}

/** @param {Community} community */
function renderCommunity(community) {
  dom.communityText.textContent =
    `If ${number.format(community.households)} households near you made the same changes, ` +
    'this is what your shared air would be spared every day.';
  dom.communityCo2.textContent = `${number.format(community.co2_kg_per_day ?? 0)} kg`;
  dom.communityPm.textContent = mass(community.pm25_g_per_day);
}

/**
 * @param {Plan} plan
 * @param {string} language
 */
function renderPlan(plan, language) {
  const lang = plan.source === 'gemini' ? language : 'en';
  dom.resultsTitle.textContent = `Your plan for ${plan.location}`;
  renderAir(plan.air);
  dom.summary.textContent = plan.summary;
  dom.summary.lang = lang;
  dom.routine.lang = lang;
  renderRoutine(plan.routine);
  dom.actions.replaceChildren(...plan.actions.map((action) => renderAction(action, lang)));
  renderCommunity(plan.community);
  dom.sourceNote.textContent =
    plan.source === 'gemini'
      ? 'Explanations written by Google Gemini. Every number comes from the formulas shown under each card.'
      : 'Explanations from built-in rules (the AI writer is unavailable right now). Numbers are unaffected.';
  dom.results.hidden = false;
}

// --- Wiring ----------------------------------------------------------------------------

function updateNotesCount() {
  dom.notesCount.textContent = `${dom.notes.value.length} of ${NOTES_MAX} characters`;
}

renderBars(dom.previewChart, EXAMPLE_DAY, EXAMPLE_CLEANEST, EXAMPLE_SMOGGIEST);
dom.searchButton.addEventListener('click', searchPlaces);
dom.placeQuery.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    searchPlaces();
  }
});
dom.locateButton.addEventListener('click', useMyLocation);
dom.notes.addEventListener('input', updateNotesCount);
dom.form.addEventListener('submit', submitPlan);
dom.printButton.addEventListener('click', () => window.print());
window.addEventListener('beforeprint', () => {
  for (const details of document.querySelectorAll('details')) details.open = true;
});
