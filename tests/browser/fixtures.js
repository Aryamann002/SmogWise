/**
 * Mocked API responses: a Delhi evening whose 24-hour forecast runs past local midnight, so
 * the page has to label some hours "tomorrow".
 */

/** @typedef {import('../../static/js/api.js').HourlyPm} HourlyPm */
/** @typedef {import('../../static/js/api.js').Place} Place */
/** @typedef {import('../../static/js/api.js').Plan} Plan */

export const OBSERVED_AT = '2026-01-15T20:00';
const FIRST_FORECAST_HOUR = 21;
const PM25 = [
  150, 180, 170, 160, 150, 140, 135, 130, 145, 160, 140, 120, 100, 85, 70, 60, 50, 45, 40, 55, 80,
  110, 130, 145,
];

/** @type {HourlyPm[]} */
export const FORECAST = PM25.map((pm2_5, index) => {
  const hour = FIRST_FORECAST_HOUR + index;
  const day = hour < 24 ? '15' : '16';
  return { time: `2026-01-${day}T${String(hour % 24).padStart(2, '0')}:00`, pm2_5 };
});

/** 22:00 on the observation day. */
export const SMOGGIEST = FORECAST[1];
/** 15:00 on the following day. */
export const CLEANEST = FORECAST[18];

/** @type {Place[]} */
export const PLACES = [
  {
    name: 'Delhi',
    admin: 'National Capital Territory of Delhi',
    country: 'India',
    country_code: 'IN',
    latitude: 28.65,
    longitude: 77.23,
  },
];

/**
 * A plan as the API returns it.
 * @param {Plan['source']} source
 * @returns {Plan}
 */
export function planFixture(source) {
  return {
    location: 'Delhi',
    air: {
      observed_at: OBSERVED_AT,
      aqi: 350,
      aqi_scale: 'India CPCB',
      category: 'Very Poor',
      level: 4,
      pm2_5: 150,
      best_hour: CLEANEST,
      worst_hour: SMOGGIEST,
      forecast: FORECAST,
    },
    summary: 'Air in Delhi is Very Poor tonight. Keep windows shut until tomorrow afternoon.',
    routine: [
      { time: '21:00', activity: 'Run the air filter in the bedroom.', why: 'Smog peaks at 22:00.' },
      { time: '07:00', activity: 'Exercise indoors.', why: 'Mornings stay smoggy.' },
      { time: '15:00', activity: 'Keep windows shut and run the air filter.', why: 'Cleanest hour, but still not clean.' },
    ],
    actions: [
      {
        id: 'n95-mask',
        category: 'health',
        title: 'Wear a well-fitted N95 outdoors',
        how: 'Press the nose clip so there are no gaps.',
        impact: { exposure_reduction_pct: 75, co2_kg_per_day: null, pm25_g_per_day: null },
        explanation: 'A snug N95 blocks most of the fine particles you would breathe outdoors.',
        method: 'Real-world fit efficiency of 75%.',
      },
    ],
    community: { households: 50, co2_kg_per_day: 165, pm25_g_per_day: 4000 },
    source,
  };
}
