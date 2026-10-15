"""FastAPI application entry point."""
import logging
# Provider settings are lightweight; the SDK loads only when a model is used.
from app.llm.provider import get_chat_provider
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.api.routes import router
from app.api.streaming import router as streaming_router
from app.api.multi_city import router as multi_city_router
from app.api.auth import router as auth_router
from app.websocket.routes import router as websocket_router
from app.api.refinement import router as refinement_router
from app.api.agent import router as agent_router
from app.api.domestic import router as domestic_router
from app.api.pois import router as pois_router
from app.api.knowledge import router as knowledge_router
from app.api.system import router as system_router
from app.middleware.rate_limit import RateLimitMiddleware
from app.core.cache import cache
from app.core.logging_config import setup_logging
from app.core.monitoring import MetricsMiddleware, metrics_endpoint

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    setup_logging()
    logger.info("Starting Qingtu API...")
    provider = get_chat_provider()
    logger.info("Chat provider: %s; model: %s; configured: %s", provider.name, provider.model, bool(provider.api_key))

    await cache.connect()
    logger.info("Qingtu API started successfully")

    yield

    logger.info("Shutting down Qingtu API...")
    await cache.close()
    logger.info("Qingtu API shut down")


app = FastAPI(
    title="晴途 Qingtu API",
    description="Qingtu 晴途 · 智能旅行规划助手",
    version="2.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add metrics middleware
app.add_middleware(MetricsMiddleware)

# Add rate limiting (10 requests per minute for /plan-itinerary)
app.add_middleware(RateLimitMiddleware, requests_per_minute=10)

# Include API routes
app.include_router(auth_router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["auth"])
app.include_router(router, prefix=settings.API_V1_PREFIX)
app.include_router(knowledge_router, prefix=settings.API_V1_PREFIX)
app.include_router(system_router, prefix=settings.API_V1_PREFIX)
app.include_router(domestic_router, prefix=settings.API_V1_PREFIX, tags=["domestic"])
app.include_router(pois_router, prefix=settings.API_V1_PREFIX, tags=["POI搜索"])
app.include_router(streaming_router, prefix=settings.API_V1_PREFIX, tags=["streaming"])
app.include_router(multi_city_router, prefix=settings.API_V1_PREFIX, tags=["multi-city"])
app.include_router(websocket_router, tags=["websocket"])
app.include_router(refinement_router, prefix=settings.API_V1_PREFIX, tags=["refinement"])
app.include_router(agent_router, prefix=settings.API_V1_PREFIX, tags=["agent"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "晴途 Qingtu - Travel Planning Assistant",
        "version": "2.0.0",
        "features": [
            "AI-powered itinerary planning",
            "RAG semantic activity retrieval (pgvector)",
            "Natural language itinerary refinement",
            "Agentic planning with tool calling",
            "Explainability metadata per activity",
            "Multi-city trip support",
            "Real-time collaboration",
            "Community reviews",
            "Public sharing"
        ]
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    # Check Redis connection
    redis_status = "healthy" if cache._redis else "disconnected"

    return {
        "status": "healthy",
        "redis": redis_status,
        "environment": settings.ENVIRONMENT
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return metrics_endpoint()

