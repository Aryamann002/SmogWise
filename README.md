# SmogWise

An AI assistant that helps families and communities get through severe winter smog. You tell it where you live and how you live. It reads the live air-quality forecast and builds a plan with three parts:

- **A low-exposure daily routine** timed around today's cleanest and smoggiest hours.
- **Indoor air fixes** such as purifier sizing, a DIY box-fan filter, sealing gaps and when to open windows.
- **Cleaner alternatives** for commuting, heating and cooking.

Each recommendation shows **its direct impact** (less PM2.5 breathed, CO₂ avoided, PM2.5 no longer emitted), a plain-language explanation and the formula behind the number. Google Gemini writes the advice in the family's own language. The numbers always come from tested code.

## How it meets the brief

| The brief asks for | SmogWise does |
|---|---|
| Families and communities | Household profile: children, people over 65, asthma, COPD, heart disease, pregnancy. A "your neighbours" panel scales the savings to your street. Community actions include reporting open burning. |
| Severe winter smog | Advice built around winter inversions (dirty mornings, cleaner afternoons), smoky heating, bonfires, firecrackers and open burning. Carbon monoxide warnings for indoor braziers. |
| Low-emission daily routines | A timeline (07:00 … 21:00) built from the 24-hour PM2.5 forecast for your location. |
| Indoor air quality hacks | Clean room with a purifier or a DIY Corsi-Rosenthal filter, sized to your room, plus sealing gaps, timed ventilation and cutting indoor smoke sources. |
| Sustainable alternatives | Commute switches (metro, train, bus, cycling, walking) and heating and cooking fuel switches (electric, LPG, induction). |
| Tailored to location and lifestyle | Live Open-Meteo data for the chosen place. India gets the CPCB AQI scale, and help such as PMUY LPG subsidies and the CPCB Sameer app. Advice in 8 languages. |
| Clearly explain the direct impact | Every card shows a number, why it matters for this family and a "How we calculated this" section with the formula and source. |

## Architecture

```
Browser (static/: HTML + CSS + plain JS, no build step)
   │  GET /api/geocode   POST /api/plan
   ▼
FastAPI (app/main.py) ─ security.py: CSP, security headers, per-IP rate limit
   │
   ├── air_quality.py  Open-Meteo geocoding and air-quality client (validated, TTL-cached)
   │       └── aqi.py  US EPA and India CPCB AQI from PM2.5/PM10 breakpoints
   │
   └── planner.py      Orchestrates one plan, caches Gemini results
           ├── actions.py  Rules engine: profile + air → ranked, quantified actions and routine
           │      └── impact.py  Pure impact formulas with cited constants
           └── advisor.py  Gemini structured output: ranks, explains, translates
```

### Design decision: code owns the numbers, the LLM owns the words

The rules engine (`actions.py` and `impact.py`) chooses the candidate actions and computes every figure. Gemini gets those actions and returns JSON, validated against a schema, that only reorders known action IDs and rewrites their text. `planner.merge_advice` drops unknown IDs, keeps every number from the rules engine and falls back to rule-based text for anything missing. As a result:

- **Trust:** a hallucinated or prompt-injected response cannot change any impact figure.
- **Testability:** all the maths is pure functions with unit tests.
- **Resilience:** with no API key, a timeout or bad output, the app still returns a complete plan (`source: "rules"`).

## Impact methodology

| Impact | Formula | Source of constants |
|---|---|---|
| Commute CO₂ avoided | (factor for current mode − factor for new mode) × km × 2 | UK DESNZ GHG Conversion Factors 2024; India GHG Program 2015 (auto-rickshaw) |
| Indoor PM2.5 with purifier or DIY filter | C_in/C_out = ACH / (ACH + k + CADR/V) | Riley et al. 2002 (deposition k); AHAM 2/3 rule (target CADR) |
| Sealing gaps | Same mass balance with infiltration cut from 0.5 to 0.3 air changes per hour | Typical residential infiltration ranges |
| Exercise or ventilation timing | 1 − PM2.5 at best hour ÷ PM2.5 at baseline hour | Open-Meteo / CAMS hourly forecast |
| N95 mask | 75% dose reduction (real-world fit, not the 95% lab figure) | Real-world fit studies |
| Heating and cooking fuel switch | Emission factor × kg of fuel per day | EMEP/EEA Guidebook 2023, 1.A.4 |
| No open burning | 19 g PM2.5 per kg of leaves | US EPA AP-42 §2.5 |

AQI uses the US EPA 2024 PM2.5 breakpoints, or the India CPCB 2014 breakpoints for Indian locations. Both scales are defined on 24-hour averages; SmogWise applies them to the current hourly value so the index reacts to the smog you are breathing now.

## Security

- **Input validation:** Pydantic validates every input field. Numbers are bounded, choices are enums, strings have a maximum length and unknown fields are rejected.
- **Safe errors:** validation errors list field names only and never echo user input back.
- **Secrets:** `GEMINI_API_KEY` is read only from the environment (Secret Manager on Cloud Run). Open-Meteo needs no key.
- **HTTP headers:** a strict CSP (`default-src 'self'`, no inline scripts or styles), `frame-ancestors 'none'`, HSTS, `nosniff`, `no-referrer` and a Permissions-Policy that allows only geolocation.
- **Rate limit:** a sliding-window limit of 20 requests per minute per client on `/api/*`.
- **Prompt injection:** user notes are wrapped in delimiters as data only, angle brackets are stripped and the model output is schema-validated. Coordinates are never sent to the LLM.
- **Rendering:** the frontend writes all text with `textContent` and never uses `innerHTML`.
- **Upstream data:** responses from Open-Meteo are validated before use, with timeouts on every outbound call.
- **Container:** runs as a non-root user, with pinned dependencies.

## Efficiency

- **One shared HTTP client:** a single `httpx.AsyncClient` serves all outbound requests.
- **Caching:** TTL plus LRU caches hold air quality (30 minutes, coordinates rounded to about 1 km), geocoding (24 hours) and Gemini plans (15 minutes).
- **Gemini cost:** one Gemini call per plan, at low thinking level, with a hard 25-second timeout.
- **Small, compressed frontend:** GZip responses, and three static files with no framework, no images and no build step.

## Accessibility

- **Automated audit:** no axe-core violations against WCAG 2.1 AA and best-practice rules, checked in light and dark mode at desktop and mobile widths.
- **Page structure:** semantic landmarks, a skip link, a label for every input and fieldsets with legends.
- **Screen readers and keyboard:** status messages are announced politely, focus moves to the results heading and focus rings are visible.
- **Not colour alone:** AQI is shown as text, number and colour together, with text colours chosen per band to meet contrast requirements.
- **Display settings:** supports `prefers-color-scheme` and `prefers-reduced-motion`, uses a mobile-first layout sized in rem units, and has 44 px touch targets.
- **Language:** advice in English, Hindi, Bengali, Marathi, Tamil, Telugu, Spanish and Chinese, with the correct `lang` attributes for screen readers.
- **Print:** a print stylesheet lets the plan go on the fridge.

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export GEMINI_API_KEY=...       # optional; without it the app uses rule-based text
uvicorn app.main:app --reload   # http://localhost:8000
```

## Test and lint

```bash
ruff check . && ruff format --check .
mypy app                        # strict mode, configured in pyproject.toml
pytest --cov                    # fails under 90% coverage
pytest tests/test_impact.py::test_commute_switch_saving   # a single test
```

The tests never touch the network. Open-Meteo is mocked with `httpx.MockTransport`, and Gemini and the data client are replaced through FastAPI dependency overrides and injected fakes.

## Deploy

The same `Dockerfile` runs on Vercel and on Cloud Run.

**Vercel.** `vercel.json` runs the Dockerfile as a container service, and `.vercelignore` uploads only the files the build needs.

```bash
vercel link --project smogwise
vercel env add GEMINI_API_KEY production --sensitive
printf 8080 | vercel env add PORT production
vercel deploy --prod
```

**Cloud Run.**

```bash
echo -n "$GEMINI_API_KEY" | gcloud secrets create gemini-key --data-file=-
gcloud run deploy smogwise --source . --region asia-south1 \
  --set-secrets GEMINI_API_KEY=gemini-key:latest --allow-unauthenticated
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | unset | Enables Gemini explanations; without it, rule-based text is used |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Gemini model ID |
| `GEMINI_TIMEOUT_S` | `25` | Hard timeout for the model call |
| `RATE_LIMIT_PER_MINUTE` | `20` | Per-client API limit |
