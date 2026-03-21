"""FastAPI application factory for supacrawl REST API."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from supacrawl.api.models.common import ErrorResponse

logger = logging.getLogger("supacrawl.api")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Create shared services on startup, tear down on shutdown."""
    from supacrawl.mcp.api_client import create_supacrawl_services

    services = await create_supacrawl_services()
    app.state.services = services
    logger.info("Supacrawl API services initialised")

    yield

    await services.close()
    logger.info("Supacrawl API services shut down")


def create_app() -> FastAPI:
    """Build and return the FastAPI application.

    The app includes:
    - CORS middleware (all origins)
    - Global exception handler mapping errors to ``ErrorResponse``
    - 422 -> 400 remapping for validation errors
    """
    app = FastAPI(
        title="Supacrawl API",
        description="Firecrawl v2-compatible REST API for supacrawl.",
        lifespan=_lifespan,
    )

    # --- CORS ----------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Exception handlers --------------------------------------------

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Remap FastAPI's 422 validation errors to 400 Bad Request."""
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(error=str(exc)).model_dump(),
        )

    @app.exception_handler(Exception)
    async def _generic_error(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all handler; returns a consistent error envelope."""
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(error=str(exc)).model_dump(),
        )

    # --- Routers -----------------------------------------------------------
    from supacrawl.api.routers.map import router as map_router
    from supacrawl.api.routers.scrape import router as scrape_router

    app.include_router(scrape_router)
    app.include_router(map_router)

    return app
