/**
 * Keyboard and accessibility checks for the search-to-plan flow, on desktop and mobile.
 */

import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { CLEANEST, FORECAST, PLACES, SMOGGIEST, planFixture } from './fixtures.js';

/** @typedef {import('@playwright/test').Page} Page */

const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'];

/**
 * @param {Page} page
 * @param {'gemini'|'rules'} source
 */
async function mockApi(page, source) {
  await page.route('**/api/geocode?*', (route) => route.fulfill({ json: PLACES }));
  await page.route('**/api/plan', (route) => route.fulfill({ json: planFixture(source) }));
}

/**
 * Search for Delhi and submit the form using only the keyboard.
 * @param {Page} page
 * @param {string} language
 */
async function requestPlanByKeyboard(page, language) {
  await page.goto('/');
  await page.getByLabel('City or town').focus();
  await page.keyboard.type('Delhi');
  await page.keyboard.press('Enter');
  const place = page.getByLabel('Your place');
  await expect(place).toBeFocused();
  await expect(place).toHaveValue('0');
  await page.getByLabel('Language for advice').selectOption(language);
  await page.getByRole('button', { name: 'Get my plan' }).focus();
  await page.keyboard.press('Enter');
}

test('keyboard search and submit move focus to the plan heading', async ({ page }) => {
  await mockApi(page, 'gemini');
  await requestPlanByKeyboard(page, 'en');
  const heading = page.getByRole('heading', { name: 'Your plan for Delhi' });
  await expect(heading).toBeFocused();
  await expect(page.getByRole('status').filter({ hasText: 'Your plan is ready.' })).toBeVisible();
});

test('forecast hours after local midnight are labelled tomorrow', async ({ page }) => {
  await mockApi(page, 'gemini');
  await requestPlanByKeyboard(page, 'en');
  await expect(page.locator('#best-hour')).toHaveText('15:00 tomorrow, 40 µg/m³');
  await expect(page.locator('#worst-hour')).toHaveText('22:00, 180 µg/m³');
  await expect(page.locator('#forecast-caption')).toContainText('15:00 tomorrow');
  await expect(page.locator('.routine__time')).toHaveText(['21:00', '07:00 tomorrow', '15:00 tomorrow']);
});

test('rule-based fallback is tagged English when another language was asked for', async ({ page }) => {
  await mockApi(page, 'rules');
  await requestPlanByKeyboard(page, 'hi');
  await expect(page.locator('#summary')).toHaveAttribute('lang', 'en');
  await expect(page.locator('#routine')).toHaveAttribute('lang', 'en');
  await expect(page.locator('.action__card').first()).toHaveAttribute('lang', 'en');
  await expect(page.locator('#source-note')).toContainText('built-in rules');
});

test('Gemini advice is tagged with the language that was asked for', async ({ page }) => {
  await mockApi(page, 'gemini');
  await requestPlanByKeyboard(page, 'hi');
  await expect(page.locator('#summary')).toHaveAttribute('lang', 'hi');
  await expect(page.locator('.action__card').first()).toHaveAttribute('lang', 'hi');
});

test('every hour shown in the chart is in the keyboard-reachable table', async ({ page }) => {
  await mockApi(page, 'gemini');
  await requestPlanByKeyboard(page, 'en');
  const bars = page.locator('#forecast-chart .bars__bar');
  await expect(bars).toHaveCount(FORECAST.length);
  await expect(bars.nth(1)).toHaveClass(/bars__bar--smoggiest/);
  await expect(bars.nth(FORECAST.indexOf(CLEANEST))).toHaveClass(/bars__bar--cleanest/);
  await expect(bars.nth(1)).toHaveAttribute('data-tip', `22:00 · ${SMOGGIEST.pm2_5} µg/m³`);

  await page.getByText('Hourly values').focus();
  await page.keyboard.press('Enter');
  const rows = page.locator('#forecast-rows tr');
  await expect(rows).toHaveCount(FORECAST.length);
  await expect(rows).toHaveText(
    FORECAST.map((hour) => `${hour.time.replace('T', ' ')}${Math.round(hour.pm2_5)}`),
  );
});

test('the page with a plan has no axe violations', async ({ page }) => {
  await mockApi(page, 'gemini');
  await requestPlanByKeyboard(page, 'en');
  await expect(page.getByRole('heading', { name: 'Your plan for Delhi' })).toBeFocused();
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  expect(results.violations).toEqual([]);
});
