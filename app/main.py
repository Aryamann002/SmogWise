"""FastAPI entry point: wires dependencies, API routes and the static frontend."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Final, cast

import httpx
from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google import genai

from app.advisor import GeminiAdvisor
from app.air_quality import OpenMeteoClient
from app.config import get_settings
from app.errors import SmogWiseError
from app.planner import Planner
from app.schemas import ErrorResponse, Place, PlanRequest, PlanResponse
from app.security import SlidingWindowRateLimiter, error_response, install_security

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATIC_DIR: Final = Path(__file__).resolve().parent.parent / "static"
HTTP_TIMEOUT: Final = httpx.Timeout(10.0, connect=5.0)
USER_AGENT: Final = "SmogWise/1.0"
GZIP_MIN_BYTES: Final = 1024
HTTP_UNPROCESSABLE: Final = 422
ERROR_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    HTTP_UNPROCESSABLE: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create shared clients once per process and close them on shutdown."""
    settings = get_settings()
    gemini = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as http:
        app.state.open_meteo = OpenMeteoClient(http)
        app.state.planner = Planner(
            GeminiAdvisor(gemini, settings.gemini_model, settings.gemini_timeout_s)
            if gemini
            else None
        )
        try:
            yield
        finally:
            if gemini:
                await gemini.aio.aclose()


def get_open_meteo(request: Request) -> OpenMeteoClient:
    """Dependency: the shared Open-Meteo client."""
    return cast("OpenMeteoClient", request.app.state.open_meteo)


def get_planner(request: Request) -> Planner:
    """Dependency: the shared planner."""
    return cast("Planner", request.app.state.planner)


OpenMeteo = Annotated[OpenMeteoClient, Depends(get_open_meteo)]
PlannerDep = Annotated[Planner, Depends(get_planner)]

router = APIRouter(prefix="/api", responses=ERROR_RESPONSES)


@router.get("/geocode")
async def geocode(
    q: Annotated[str, Query(min_length=2, max_length=80)], open_meteo: OpenMeteo
) -> tuple[Place, ...]:
    """Search for a city or town by name."""
    return await open_meteo.search_places(q)


@router.post("/plan")
async def plan(body: PlanRequest, open_meteo: OpenMeteo, planner: PlannerDep) -> PlanResponse:
    """Build a personalised smog plan for one household at one location."""
    loc = body.location
    air = await open_meteo.air_quality(loc.latitude, loc.longitude, loc.country_code)
    return await planner.create_plan(body, air)


async def _handle_domain_error(_: Request, exc: Exception) -> JSONResponse:
    error = exc if isinstance(exc, SmogWiseError) else SmogWiseError()
    return error_response(error.status_code, error.code, error.public_message)


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    # Field names only: user input is never echoed back in error responses.
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    fields = sorted({".".join(str(part) for part in err["loc"][1:]) for err in errors})
    message = "Please check these fields: " + ", ".join(fields) if fields else "Invalid request."
    return error_response(HTTP_UNPROCESSABLE, "invalid_request", message)


def create_app() -> FastAPI:
    """Assemble the application; tests call this to get an isolated instance."""
    app = FastAPI(
        title="SmogWise",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    install_security(app, SlidingWindowRateLimiter(get_settings().rate_limit_per_minute))
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MIN_BYTES)
    app.add_exception_handler(SmogWiseError, _handle_domain_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.include_router(router)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()
