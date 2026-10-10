"""FastAPI application entrypoint for AI Team Alignment Platform Backend.

Provides:
- REST API endpoints for projects, responses, multi-agent analysis, and decisions.
- OpenAPI interactive documentation at /docs and /redoc.
- Configurable CORS support for decoupled frontend and Slack bots.
- Modular separation between routes, agents, workflows, and persistence.
"""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes import (
    analysis_router,
    decisions_router,
    projects_router,
    responses_router,
)

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
    if settings.active_api_key:
        logger.info("Gemini API key is configured.")
    else:
        logger.warning("No Gemini API key configured. Agent services will run in high-fidelity mock mode.")
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

# Configure CORS for decoupled frontend (Figma Make, React/Vite, Next.js) and Slack/n8n
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(projects_router, prefix=settings.api_prefix)
app.include_router(responses_router, prefix=settings.api_prefix)
app.include_router(analysis_router, prefix=settings.api_prefix)
app.include_router(decisions_router, prefix=settings.api_prefix)


@app.get("/", tags=["Health"])
async def root():
    """Root status endpoint with API links."""
    return {
        "name": settings.project_name,
        "version": settings.version,
        "status": "online",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "api_prefix": settings.api_prefix,
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for container orchestrators and monitoring."""
    return {
        "status": "healthy",
        "model": settings.gemini_model,
        "api_key_configured": bool(settings.active_api_key),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
