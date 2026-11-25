/**
 * Renders a plan from the API into the results section.
 */

import { renderBars, renderForecastTable } from './charts.js';
import { byId, fill } from './dom.js';
import { clock, forecastTime, mass, number, pm } from './format.js';

/** @typedef {import('./api.js').Action} Action */
/** @typedef {import('./api.js').AirQuality} AirQuality */
/** @typedef {import('./api.js').Community} Community */
/** @typedef {import('./api.js').Impact} Impact */
/** @typedef {import('./api.js').Plan} Plan */
/** @typedef {import('./api.js').RoutineStep} RoutineStep */

const CATEGORY_LABELS = Object.freeze({
  health: 'Health',
  indoor: 'Indoor air',
  transport: 'Transport',
  heating: 'Heating',
  cooking: 'Cooking',
  community: 'Community',
});

const view = {
  results: byId('results'),
  resultsTitle: byId('results-title'),
  aqiBadge: byId('aqi-badge'),
  aqiValue: byId('aqi-value'),
  aqiLabel: byId('aqi-label'),
  pmNow: byId('pm-now'),
  bestHour: byId('best-hour'),
  worstHour: byId('worst-hour'),
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
  routineTemplate: /** @type {HTMLTemplateElement} */ (byId('routine-template')),
  actionTemplate: /** @type {HTMLTemplateElement} */ (byId('action-template')),
};

/** @param {AirQuality} air */
function renderAir(air) {
  view.aqiBadge.dataset.level = String(air.level);
  view.aqiValue.textContent = `Estimated AQI ${air.aqi}`;
  view.aqiLabel.textContent = `${air.category} (${air.aqi_scale})`;
  view.pmNow.textContent = pm(air.pm2_5);
  const best = forecastTime(air.best_hour.time, air.observed_at);
  const worst = forecastTime(air.worst_hour.time, air.observed_at);
  view.bestHour.textContent = `${best}, ${pm(air.best_hour.pm2_5)}`;
  view.worstHour.textContent = `${worst}, ${pm(air.worst_hour.pm2_5)}`;
  renderBars(view.chart, air.forecast, air.best_hour, air.worst_hour);
  renderForecastTable(view.forecastRows, air.forecast);
  view.chartCaption.textContent =
    `PM2.5 for the next 24 hours: suggested lower-exposure hour ${best}, peak pollution at ${worst}.`;
}

/**
 * @param {RoutineStep[]} routine
 * @param {string} observed
 */
function renderRoutine(routine, observed) {
  view.routine.replaceChildren(
    ...routine.map((step) => {
      const item = /** @type {DocumentFragment} */ (view.routineTemplate.content.cloneNode(true));
      const tomorrow = step.time.slice(0, 2) < clock(observed).slice(0, 2);
      fill(item, '.routine__time', step.time + (tomorrow ? ' tomorrow' : ''));
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
 * @param {Action} action
 * @param {string} lang
 */
function renderAction(action, lang) {
  const item = /** @type {DocumentFragment} */ (view.actionTemplate.content.cloneNode(true));
  const card = /** @type {HTMLElement} */ (item.querySelector('.action__card'));
  card.lang = lang;
  card.dataset.category = action.category;
  const category = /** @type {keyof typeof CATEGORY_LABELS} */ (action.category);
  fill(item, '.action__category', CATEGORY_LABELS[category] ?? action.category);
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

/** @param {Community} community */
function renderCommunity(community) {
  view.communityText.textContent =
    `If ${number.format(community.households)} households near you made the same changes, ` +
    'this is what your shared air would be spared every day.';
  view.communityCo2.textContent = `${number.format(community.co2_kg_per_day ?? 0)} kg`;
  view.communityPm.textContent = mass(community.pm25_g_per_day);
}

/** @param {boolean} busy */
export function setPlanBusy(busy) {
  view.results.setAttribute('aria-busy', String(busy));
}

/**
 * Render the plan, reveal the results and move focus to their heading.
 * @param {Plan} plan
 * @param {string} language the language the user asked for; rule-based text is English
 */
export function showPlan(plan, language) {
  const lang = plan.source === 'gemini' ? language : 'en';
  view.resultsTitle.textContent = `Your plan for ${plan.location}`;
  renderAir(plan.air);
  view.summary.textContent = plan.summary;
  view.summary.lang = lang;
  view.routine.lang = lang;
  renderRoutine(plan.routine, plan.air.observed_at);
  view.actions.replaceChildren(...plan.actions.map((action) => renderAction(action, lang)));
  renderCommunity(plan.community);
  view.sourceNote.textContent =
    plan.source === 'gemini'
      ? 'Explanations written by Google Gemini. The impact figures on each card come from the formulas shown.'
      : 'Explanations from built-in rules (the AI writer is unavailable right now). Numbers are unaffected.';
  view.results.hidden = false;
  view.resultsTitle.focus();
}
