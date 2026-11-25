/**
 * Typed access to the SmogWise API. The typedefs mirror the response models in app/schemas.py.
 */

/** @typedef {{name: string, admin?: string|null, country?: string|null, country_code: string|null, latitude: number, longitude: number}} Place */
/** @typedef {{time: string, pm2_5: number}} HourlyPm */
/** @typedef {{exposure_reduction_pct: number|null, co2_kg_per_day: number|null, pm25_g_per_day: number|null}} Impact */
/** @typedef {{id: string, category: string, title: string, how: string, impact: Impact, explanation: string, method: string}} Action */
/** @typedef {{time: string, activity: string, why: string}} RoutineStep */
/** @typedef {{observed_at: string, aqi: number, aqi_scale: string, category: string, level: number, pm2_5: number, best_hour: HourlyPm, worst_hour: HourlyPm, forecast: HourlyPm[]}} AirQuality */
/** @typedef {{households: number, co2_kg_per_day: number|null, pm25_g_per_day: number|null}} Community */
/** @typedef {{location: string, air: AirQuality, summary: string, routine: RoutineStep[], actions: Action[], community: Community, source: 'gemini'|'rules'}} Plan */

const ENDPOINTS = Object.freeze({ geocode: '/api/geocode', plan: '/api/plan' });
const FALLBACK_ERROR = 'Something went wrong. Please try again.';

/**
 * Fetch JSON and surface the API's safe error message on failure.
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<unknown>}
 */
async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.error?.message ?? FALLBACK_ERROR);
  return body;
}

/**
 * Search places by name.
 * @param {string} query
 * @returns {Promise<Place[]>}
 */
export async function findPlaces(query) {
  const url = `${ENDPOINTS.geocode}?${new URLSearchParams({ q: query })}`;
  return /** @type {Place[]} */ (await fetchJson(url));
}

/**
 * Ask the server for a household plan.
 * @param {object} request a PlanRequest body
 * @returns {Promise<Plan>}
 */
export async function requestPlan(request) {
  const plan = await fetchJson(ENDPOINTS.plan, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return /** @type {Plan} */ (plan);
}
