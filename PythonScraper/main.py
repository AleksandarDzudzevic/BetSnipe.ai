#!/usr/bin/env python3
"""
BetSnipe.ai v2.0 - Main Entry Point

Real-time odds comparison and arbitrage detection for Serbian bookmakers.

Usage:
    # Run the full application (API + scraper engine)
    python main.py

    # Run only the API server
    python main.py --api-only

    # Run only the scraper engine (no API)
    python main.py --scraper-only

    # Specify host and port
    python main.py --host 0.0.0.0 --port 8080
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core.config import settings
from core.db import db


def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format=settings.log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )

    # Reduce noise from third-party libraries
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('websockets').setLevel(logging.WARNING)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='BetSnipe.ai v2.0 - Real-time odds platform'
    )

    parser.add_argument(
        '--api-only',
        action='store_true',
        help='Run only the API server without scraper engine'
    )

    parser.add_argument(
        '--scraper-only',
        action='store_true',
        help='Run only the scraper engine without API server'
    )

    parser.add_argument(
        '--host',
        type=str,
        default=settings.api_host,
        help=f'API server host (default: {settings.api_host})'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=settings.api_port,
        help=f'API server port (default: {settings.api_port})'
    )

    parser.add_argument(
        '--reload',
        action='store_true',
        help='Enable auto-reload for development'
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )

    return parser.parse_args()


async def run_scraper_only():
    """Run only the scraper engine without the API server."""
    from core.scraper_engine import engine
    from core.scrapers.admiral import AdmiralScraper
    from core.scrapers.soccerbet import SoccerbetScraper
    from core.scrapers.maxbet import MaxbetScraper
    from core.scrapers.mozzart import MozzartScraper
    # from core.scrapers.meridian import MeridianScraper  # Disabled temporarily
    from core.scrapers.superbet import SuperbetScraper
    from core.scrapers.merkur import MerkurScraper
    from core.scrapers.topbet import TopbetScraper

    logger = logging.getLogger(__name__)

    logger.info("Starting BetSnipe.ai v2.0 (scraper only mode)")

    # Connect to database
    await db.connect()

    # Register all scrapers
    engine.register_scraper(AdmiralScraper())
    engine.register_scraper(SoccerbetScraper())
    engine.register_scraper(MaxbetScraper())
    engine.register_scraper(MozzartScraper())
    # engine.register_scraper(MeridianScraper())  # Disabled temporarily
    engine.register_scraper(SuperbetScraper())
    engine.register_scraper(MerkurScraper())
    engine.register_scraper(TopbetScraper())

    # Optional Telegram notifications
    if settings.enable_telegram and settings.telegram_bot_token:
        from telegram_utils import send_telegram_message
        from core.arbitrage import format_arbitrage_message

        async def on_arbitrage(update_type: str, data):
            if update_type == 'arbitrage':
                from core.arbitrage import ArbitrageOpportunity
                # Convert data back to ArbitrageOpportunity if needed
                # and send notification
                message = f"New arbitrage detected: {data.get('profit_percentage', 0):.2f}% profit"
                logger.info(message)
                # await send_telegram_message(message)

        engine.register_update_callback(on_arbitrage)

    try:
        await engine.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await engine.stop()
        await db.disconnect()


def run_api_server(host: str, port: int, reload: bool = False):
    """Run the FastAPI server with uvicorn."""
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=settings.log_level.lower(),
    )


def main():
    """Main entry point."""
    args = parse_args()

    if args.debug:
        settings.log_level = 'DEBUG'

    setup_logging()

    logger = logging.getLogger(__name__)

    logger.info("=" * 50)
    logger.info("  BetSnipe.ai v2.0")
    logger.info("  Real-time Odds Platform for Serbian Bookmakers")
    logger.info("=" * 50)

    if args.api_only and args.scraper_only:
        logger.error("Cannot specify both --api-only and --scraper-only")
        sys.exit(1)

    if args.scraper_only:
        # Run scraper only (no API server)
        asyncio.run(run_scraper_only())
    else:
        # Run API server (which includes scraper engine by default)
        run_api_server(
            host=args.host,
            port=args.port,
            reload=args.reload
        )


if __name__ == "__main__":
    main()
