# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

SmogWise is a competition entry for the brief in `challange.txt`: a GenAI assistant for families facing winter smog. It is judged on the rubric in `Parameters.txt`: code quality (where most points are lost), security, efficiency, testing, accessibility and alignment with the problem statement. Keep every change consistent with that rubric.

Stack: FastAPI on Python 3.12 or later, with a plain HTML/CSS/JS frontend in `static/` (no build step). It uses Gemini through `google-genai` and Open-Meteo, which needs no key. Deployment target is Cloud Run.

## Commands

```bash
.venv/Scripts/activate                       # Windows venv (bin/activate elsewhere)
pip install -r requirements-dev.txt
uvicorn app.main:app --reload                # http://localhost:8000
ruff check . && ruff format --check .        # lint and format (strict rule set in pyproject.toml)
mypy app                                     # strict mode
pytest --cov                                 # coverage must stay >= 90%
pytest tests/test_actions.py::test_long_car_commute_switches_to_rail   # single test
npx --package typescript@6.0.3 tsc -p jsconfig.json   # strict JSDoc type check of static/js
```

## Architecture

- **Code owns the numbers, the LLM owns the words.**
  - `actions.py` (rules engine) and `impact.py` (pure formulas with cited `Final` constants) produce every action and figure.
  - `advisor.py` asks Gemini only to rank action IDs and rewrite title, how and explanation text in the user's language.
  - `planner.merge_advice` drops unknown IDs and never takes numbers from the model.
  - Keep this boundary: never let model output set impact values.
- **Graceful fallback.** If there is no `GEMINI_API_KEY`, or on timeout, API error or invalid JSON, `AdvisorError` is raised and `Planner` returns the full rule-based plan with `source="rules"`.
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
- **Dependency injection.** Shared clients live on `app.state`, created in the startup/shutdown setup. Tests swap them through `app.dependency_overrides[get_open_meteo / get_planner]` and the fakes in `tests/factories.py`. Tests never hit the network: they use `httpx.MockTransport` and fake Gemini clients.

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
