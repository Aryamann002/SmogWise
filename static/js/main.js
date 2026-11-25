/**
 * SmogWise page entry: the landing-page example chart, place search, the household form and
 * plan submission.
 */

import { findPlaces, requestPlan } from './api.js';
import { renderBars } from './charts.js';
import { byId } from './dom.js';
import { setPlanBusy, showPlan } from './plan-view.js';

/** @typedef {import('./api.js').Place} Place */

const MIN_QUERY_LENGTH = 2;
const NOTES_MAX = 300;
const GEOLOCATION_OPTIONS = Object.freeze({ timeout: 10_000, maximumAge: 600_000 });
// Illustrative Delhi winter day for the landing-page card, shaped like a real hourly forecast.
const EXAMPLE_DAY = [
  104, 103, 104, 106, 107, 107, 116, 139, 160, 132, 113, 101, 84, 69, 63, 60, 70, 92, 113, 127, 134,
  137, 140, 140,
].map((pm2_5, hour) => ({ time: `2026-01-15T${String(hour).padStart(2, '0')}:00`, pm2_5 }));
const EXAMPLE_CLEANEST = EXAMPLE_DAY[15];
const EXAMPLE_SMOGGIEST = EXAMPLE_DAY[8];
// ponytail: geolocation gives no country, so infer India from the time zone for its AQI scale.
const INDIA_TIME_ZONES = new Set(['Asia/Kolkata', 'Asia/Calcutta']);

const dom = {
  previewChart: byId('preview-chart'),
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
  printButton: /** @type {HTMLButtonElement} */ (byId('print-button')),
};

/**
 * `locationRequest` increases with every new search or geolocation attempt, so a slow reply
 * to an earlier one cannot overwrite the current choice.
 * @type {{places: Place[], locationRequest: number}}
 */
const state = { places: [], locationRequest: 0 };

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

/** Forget the chosen place and return the id of the location request that replaces it. */
function clearLocation() {
  state.locationRequest++;
  state.places = [];
  dom.placeSelect.replaceChildren(new Option('Choose a location', ''));
  dom.placeSelect.disabled = true;
  dom.placeStatus.textContent = '';
  return state.locationRequest;
}

async function searchPlaces() {
  const request = clearLocation();
  const query = dom.placeQuery.value.trim();
  if (query.length < MIN_QUERY_LENGTH) {
    dom.placeStatus.textContent = 'Type at least two letters of your city or town.';
    dom.placeQuery.focus();
    return;
  }
  dom.placeStatus.textContent = 'Searching…';
  try {
    const places = await findPlaces(query);
    if (request !== state.locationRequest) return;
    showPlaces(places);
    dom.placeStatus.textContent = places.length
      ? `Found ${places.length} place${places.length > 1 ? 's' : ''}. Choose yours from the list.`
      : 'No places found.';
    if (places.length) dom.placeSelect.focus();
  } catch (error) {
    if (request !== state.locationRequest) return;
    dom.placeStatus.textContent = /** @type {Error} */ (error).message;
  }
}

function guessCountryCode() {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return INDIA_TIME_ZONES.has(zone) ? 'IN' : null;
}

function useMyLocation() {
  const request = clearLocation();
  if (!('geolocation' in navigator)) {
    dom.placeStatus.textContent = 'Your browser cannot share location. Please search instead.';
    return;
  }
  dom.placeStatus.textContent = 'Finding your location…';
  navigator.geolocation.getCurrentPosition(
    ({ coords }) => {
      if (request !== state.locationRequest) return;
      dom.placeQuery.value = '';
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
      if (request !== state.locationRequest) return;
      dom.placeStatus.textContent = 'Location unavailable or blocked. Please search instead.';
    },
    GEOLOCATION_OPTIONS,
  );
}

// --- Form ------------------------------------------------------------------------------

/**
 * Turn the form into the API's PlanRequest shape.
 * @param {Place} place
 */
function readForm(place) {
  const data = new FormData(dom.form);
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
  dom.planStatus.textContent = busy ? 'Fetching live air quality and building your plan…' : '';
  setPlanBusy(busy);
}

/** @param {SubmitEvent} event */
async function submitPlan(event) {
  event.preventDefault();
  dom.formError.hidden = true;
  const place = state.places[Number(dom.placeSelect.value)];
  if (!place) {
    showFormError('Please search for and choose your city first.');
    dom.placeQuery.focus();
    return;
  }
  if (!dom.form.reportValidity()) return;
  setBusy(true);
  const language = dom.language.value;
  try {
    const plan = await requestPlan(readForm(place));
    setBusy(false);
    dom.planStatus.textContent = 'Your plan is ready.';
    showPlan(plan, language);
  } catch (error) {
    setBusy(false);
    showFormError(/** @type {Error} */ (error).message);
  }
}

// --- Wiring ----------------------------------------------------------------------------

function updateNotesCount() {
  dom.notesCount.textContent = `${dom.notes.value.length} of ${NOTES_MAX} characters`;
}

renderBars(dom.previewChart, EXAMPLE_DAY, EXAMPLE_CLEANEST, EXAMPLE_SMOGGIEST);
dom.searchButton.addEventListener('click', searchPlaces);
dom.placeQuery.addEventListener('input', clearLocation);
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
