"""
FastAPI Application for BetSnipe.ai v3.0

Main entry point for the REST API and WebSocket server.
Includes user authentication and push notifications.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.db import db
from core.scraper_engine import engine
from core.scrapers import (
    AdmiralScraper,
    SoccerbetScraper,
    MozzartScraper,
    # MeridianScraper,  # Disabled temporarily
    MaxbetScraper,
    SuperbetScraper,
    MerkurScraper,
    TopbetScraper,
)

from .routes import odds, arbitrage, auth, user
from .websocket import router as websocket_router, manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Starts up the database connection and scraper engine,
    and cleans up on shutdown.
    """
    # Startup
    logger.info("Starting BetSnipe.ai API server")

    # Connect to database
    await db.connect()
    logger.info("Database connected")

    # Register all scrapers
    engine.register_scraper(AdmiralScraper())
    engine.register_scraper(SoccerbetScraper())
    engine.register_scraper(MozzartScraper())
    # engine.register_scraper(MeridianScraper())  # Disabled temporarily
    engine.register_scraper(MaxbetScraper())
    engine.register_scraper(SuperbetScraper())
    engine.register_scraper(MerkurScraper())
    engine.register_scraper(TopbetScraper())
    logger.info(f"Registered {len(engine._scrapers)} scrapers")

    # Register WebSocket update callback
    async def on_update(update_type: str, data):
        await manager.broadcast({
            'type': update_type,
            'data': data
        })

    engine.register_update_callback(on_update)

    # Start scraper engine in background
    scraper_task = asyncio.create_task(engine.start())

    yield

    # Shutdown
    logger.info("Shutting down BetSnipe.ai API server")

    # Stop scraper engine
    await engine.stop()
    scraper_task.cancel()

    # Disconnect from database
    await db.disconnect()

    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="BetSnipe.ai API",
        description="Real-time odds comparison and arbitrage detection for Serbian bookmakers",
        version="3.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(odds.router, prefix="/api", tags=["odds"])
    app.include_router(arbitrage.router, prefix="/api", tags=["arbitrage"])
    app.include_router(auth.router, prefix="/api", tags=["auth"])
    app.include_router(user.router, prefix="/api", tags=["user"])
    app.include_router(websocket_router, tags=["websocket"])

    # Error handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)}
        )

    # Health check endpoint
    @app.get("/health", tags=["health"])
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "database": db.is_connected,
            "scraper_running": engine.is_running,
        }

    # Stats endpoint
    @app.get("/stats", tags=["health"])
    async def get_stats():
        """Get system statistics."""
        db_stats = await db.get_stats() if db.is_connected else {}
        engine_stats = engine.get_stats()

        return {
            "database": db_stats,
            "engine": engine_stats,
        }

    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )
