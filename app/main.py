"""
TracePilot Main Application Entrypoint.
Initializes FastAPI, mounts REST API & Cockpit routers, configures CORS,
attaches OpenTelemetry correlation middleware, and serves the Visual Incident Cockpit.
"""

from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings
from app.api.v1.router import router as api_v1_router
from app.api.v1.cockpit import router as cockpit_router
from app.core.telemetry import (
    extract_correlation_headers,
)


class OpenTelemetryCorrelationMiddleware(BaseHTTPMiddleware):
    """Injects and propagates W3C TraceContext and X-Correlation-ID headers across all HTTP requests."""

    async def dispatch(self, request: Request, call_next):
        headers_dict = dict(request.headers)
        extracted = extract_correlation_headers(headers_dict)

        response = await call_next(request)

        # Inject correlation headers on response
        response.headers["X-Correlation-ID"] = extracted["correlation_id"]
        response.headers["traceparent"] = f"00-{extracted['trace_id']}-{extracted['span_id']}-01"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown routines."""
    yield


def create_app() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title="TracePilot Distributed Backend",
        description="Autonomous Distributed Systems Incident Intelligence Platform",
        version="1.0.0",
        lifespan=lifespan,
    )

    # OpenTelemetry Correlation Tracing Middleware
    app.add_middleware(OpenTelemetryCorrelationMiddleware)

    # Configure CORS for local development and dashboard integration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount REST APIs
    app.include_router(api_v1_router, prefix="/api/v1")
    app.include_router(cockpit_router, prefix="/api/v1/cockpit")

    # Serve Visual Incident Cockpit
    @app.get("/cockpit")
    def serve_cockpit():
        html_path = Path(__file__).resolve().parent / "static" / "cockpit.html"
        return FileResponse(html_path)

    @app.get("/")
    def root():
        return {
            "name": settings.app_name,
            "version": "1.0.0",
            "cockpit_url": "/cockpit",
            "docs_url": "/docs",
            "status": "operational",
        }

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=True)
