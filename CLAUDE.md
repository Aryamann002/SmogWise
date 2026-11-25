# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

SmogWise is a competition entry for the brief in `challange.txt`: a GenAI assistant for families facing winter smog. It is judged on the rubric in `Parameters.txt`: code quality (where most points are lost), security, efficiency, testing, accessibility and alignment with the problem statement. Keep every change consistent with that rubric.

SmogWise runs FastAPI on Python 3.12 or later and serves plain HTML, CSS and JavaScript from `static/`. It uses Gemini through `google-genai` and reads forecasts from Open-Meteo. Vercel and Cloud Run use the same Dockerfile.

## Commands

```bash
. .venv/bin/activate                         # PowerShell on Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload                # http://localhost:8000
ruff check . && ruff format --check .        # lint and format (strict rule set in pyproject.toml)
mypy app                                     # strict mode
pytest --cov                                 # coverage must stay >= 90%
pytest tests/test_actions.py::test_long_car_commute_switches_to_rail   # single test
npm ci                                       # install locked frontend dev dependencies (CI uses Node 24)
npx playwright install chromium               # on fresh Linux: add --with-deps
npm run typecheck                            # strict JSDoc check of static/js and tests/browser
npm run test:browser                         # starts FastAPI using the active environment's python
```

## Architecture

- **Code owns the numbers, the LLM owns the words.**
  - `actions.py` (rules engine) and `impact.py` (pure formulas with cited `Final` constants) produce every action and figure.
  - `advisor.py` sends the existing rule plan to Gemini for action ranking, wording, a summary and routine translation.
  - `planner.merge_advice` drops unknown IDs and never takes numbers from the model.
  - Keep this boundary: never let model output set impact values.
- **Graceful fallback.** With no Gemini key, the planner builds the rule plan directly. It also returns that plan on adviser failure, empty output or an incomplete translation. Only plans with a model contribution enter the Gemini cache.
- **Request flow.**
  - `main.py` routes call `OpenMeteoClient.air_quality` in `air_quality.py`, which validates the upstream payload, computes AQI through `aqi.py` and caches results by rounded coordinates.
  - The routes then call `Planner.create_plan`.
- **AQI scales.** `aqi.Severity` (0–5) is shared by the US EPA and India CPCB scales, so rules compare severity and never raw AQI. India is detected by `country_code == "IN"`.
- **Adding a recommendation.**
  - Write a `*_rule(request, air) -> RankedAction | None` in `actions.py` and add it to `RULES`.
  - Put any new constants, with their source, in `impact.py`.
  - Every action needs an impact number and a `method` string.
- **Errors.**
  - Domain errors in `errors.py` are mapped to `{"error": {code, message}}` responses in `main.py`.
  - Validation errors never echo user input.
  - `security.py` adds the CSP and other headers, plus the `/api/*` rate limit.
- **Testing boundaries.** Python tests use FastAPI dependency overrides, `httpx.MockTransport` and fake Gemini clients. Playwright serves the real static files and CSP over localhost and mocks both API routes in the browser. Test rule and planner behavior in Python and rendered interactions in `tests/browser/`.

## Conventions

- **Frontend:**
  - ES modules in `static/js/`, one concern each: `main.js` wires the page, `plan-view.js` renders a plan, `api.js` holds the typed API calls and response typedefs, `charts.js` the PM2.5 chart. Add every new module to the `modulepreload` links in `index.html`.
  - Types are JSDoc checked by `tsc` in strict mode through `jsconfig.json`; keep it passing.
  - The CSP forbids inline scripts and styles, so put no inline handlers or `style=` attributes in HTML. Set dynamic values through CSSOM, such as `element.style.setProperty`.
  - Render API text with `textContent` and `<template>` clones only.
  - Keep pages free of axe-core violations.
- **Python:**
  - Google-style docstrings on public functions.
  - Private helpers are prefixed `_`.
  - Async tests use `@pytest.mark.anyio`.
  - Deliberate simplifications carry a `ponytail:` comment naming their limit.
