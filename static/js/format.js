/**
 * Number and time formatting shared by the plan view and the charts.
 */

export const number = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });

/**
 * @param {string} isoTime local ISO time such as 2026-11-25T15:00
 * @returns {string} the HH:MM part
 */
export const clock = (isoTime) => isoTime.slice(11, 16);

/**
 * A forecast hour as HH:MM, marked "tomorrow" when it falls after the observation date.
 * @param {string} time
 * @param {string} observed
 */
export const forecastTime = (time, observed) =>
  clock(time) + (time.slice(0, 10) === observed.slice(0, 10) ? '' : ' tomorrow');

/** @param {number} value PM2.5 in µg/m³ */
export const pm = (value) => `${number.format(Math.round(value))} µg/m³`;

/**
 * A mass in grams, switching to kilograms from 1,000 g.
 * @param {number|null} grams
 */
export function mass(grams) {
  const value = grams ?? 0;
  return value < 1000 ? `${number.format(value)} g` : `${number.format(value / 1000)} kg`;
}
