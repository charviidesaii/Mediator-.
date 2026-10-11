"""FastAPI application entrypoint for AI Team Alignment Platform Backend.

Provides:
- REST API endpoints for projects, responses, multi-agent analysis, and decisions.
- OpenAPI interactive documentation at /docs and /redoc.
- Configurable CORS support for decoupled frontend and Slack bots.
- Modular separation between routes, agents, workflows, and persistence.
- Built-in test UI harness served at /test-ui for API verification before Figma Make integration.
"""

from contextlib import asynccontextmanager
import logging
import os
import sys

# Ensure backend root is on sys.path so 'import app' resolves when run as backend.app.main:app
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models.schemas import APIErrorResponse
from app.routes import (
    analysis_router,
    decisions_router,
    projects_router,
    responses_router,
)
from app.services.supabase import storage_service

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.debug else logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("alignment_backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info(f"Starting {settings.project_name} v{settings.version}")
    logger.info(f"Using Gemini Model: {settings.gemini_model}")
    logger.info(f"Storage Backend: {settings.storage_backend} ({storage_service.db_path})")

    # Initialize persistent storage tables
    await storage_service.initialize()

    if settings.active_api_key:
        logger.info("Gemini API key is configured. Live agent execution available.")
    else:
        logger.info("No Gemini API key configured. Agent services running in deterministic mock mode.")
    yield
    logger.info(f"Shutting down {settings.project_name}")


app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    description=(
        "Backend and Multi-Agent AI system for team alignment, hidden disagreement detection, "
        "and collaborative consensus synthesis using Google ADK and Gemini."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Configure CORS with credential compliance (avoid credentials with wildcard *)
allow_all_origins = "*" in settings.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all_origins else settings.cors_origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Optional API Key Authentication Middleware
@app.middleware("http")
async def authentication_middleware(request: Request, call_next):
    """Enforces API key authentication when AUTH_ENABLED is enabled."""
    if settings.auth_enabled and request.url.path.startswith(settings.api_prefix):
        # Permit CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)

        api_key = request.headers.get("x-api-key")
        auth_header = request.headers.get("authorization", "")
        if not api_key and auth_header.startswith("Bearer "):
            api_key = auth_header[7:].strip()

        if api_key != settings.api_secret_key:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Unauthorized: Invalid or missing API key."},
            )

    return await call_next(request)


# Global unhandled exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    error_payload = APIErrorResponse(
        error=type(exc).__name__,
        detail=str(exc) or "Internal server error occurred.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_payload.model_dump(mode="json"),
    )


# Mount API routers
app.include_router(projects_router, prefix=settings.api_prefix)
app.include_router(responses_router, prefix=settings.api_prefix)
app.include_router(analysis_router, prefix=settings.api_prefix)
app.include_router(decisions_router, prefix=settings.api_prefix)


# Path helpers for frontend
_workspace_root = os.path.dirname(_backend_dir)
_frontend_dist = os.path.join(_workspace_root, "frontend", "dist")
_frontend_assets = os.path.join(_frontend_dist, "assets")

# Mount React static assets if built
if os.path.exists(_frontend_assets):
    app.mount("/assets", StaticFiles(directory=_frontend_assets), name="assets")


@app.get("/", tags=["UI / Health"])
async def root(request: Request):
    """Serves the Mediator web dashboard for browsers, or API metadata for JSON clients."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return await serve_dashboard()
    return {
        "name": settings.project_name,
        "version": settings.version,
        "status": "online",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "dashboard_url": "/dashboard",
        "test_ui_url": "/test-ui",
        "api_prefix": settings.api_prefix,
        "storage_backend": settings.storage_backend,
        "slack_configured": settings.is_slack_configured,
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for container orchestrators and monitoring."""
    return {
        "status": "healthy",
        "model": settings.gemini_model,
        "api_key_configured": bool(settings.active_api_key),
        "storage_backend": settings.storage_backend,
        "auth_enabled": settings.auth_enabled,
        "slack_configured": settings.is_slack_configured,
    }


@app.get("/dashboard", tags=["UI"], response_class=FileResponse)
async def serve_dashboard():
    """Serves the full Mediator interactive Web Dashboard (React or fallback)."""
    react_index = os.path.join(_frontend_dist, "index.html")
    if os.path.exists(react_index):
        return FileResponse(react_index, media_type="text/html")
    dummy_ui_path = os.path.join(os.path.dirname(__file__), "..", "dummy_frontend", "index.html")
    if os.path.exists(dummy_ui_path):
        return FileResponse(dummy_ui_path, media_type="text/html")
    return JSONResponse(
        status_code=404,
        content={"detail": "Dashboard frontend file not found."},
    )


@app.get("/test-ui", tags=["Test Harness"], response_class=FileResponse)
async def serve_test_ui():
    """Serves the legacy test console (backward-compatible test UI route)."""
    dummy_ui_path = os.path.join(os.path.dirname(__file__), "..", "dummy_frontend", "index.html")
    if os.path.exists(dummy_ui_path):
        return FileResponse(dummy_ui_path, media_type="text/html")
    return await serve_dashboard()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
