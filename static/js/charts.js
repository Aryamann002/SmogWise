/**
 * Hourly PM2.5 column chart and its table equivalent.
 */

import { clock, number, pm } from './format.js';

/** @typedef {import('./api.js').HourlyPm} HourlyPm */

const HOURS_PER_AXIS_LABEL = 6;

/**
 * Draw an hourly PM2.5 column chart; the cleanest and smoggiest hours get their own colour.
 * Heights go through a CSS custom property because the CSP forbids inline style attributes.
 * @param {HTMLElement} chart
 * @param {HourlyPm[]} hours
 * @param {HourlyPm} cleanest
 * @param {HourlyPm} smoggiest
 */
export function renderBars(chart, hours, cleanest, smoggiest) {
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

/**
 * Fill a table body with the chart's values, for screen readers and keyboard users.
 * @param {HTMLElement} rows
 * @param {HourlyPm[]} hours
 */
export function renderForecastTable(rows, hours) {
  rows.replaceChildren(
    ...hours.map((hour) => {
      const row = document.createElement('tr');
      const time = document.createElement('th');
      const value = document.createElement('td');
      time.scope = 'row';
      time.textContent = hour.time.replace('T', ' ');
      value.textContent = number.format(Math.round(hour.pm2_5));
      row.append(time, value);
      return row;
    }),
  );
}
