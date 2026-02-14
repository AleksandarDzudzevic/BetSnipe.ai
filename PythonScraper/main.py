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

    # Debug a single bookmaker scraper (full engine with DB)
    python main.py --mozzart
    python main.py --admiral
    python main.py --soccerbet
    python main.py --maxbet
    python main.py --superbet
    python main.py --merkur
    python main.py --topbet

    # Single scraper with options
    python main.py --mozzart --cycles 3      # Run 3 cycles then stop
    python main.py --admiral --sport 1        # Football only
    python main.py --maxbet --no-db           # Scrape without database (dry run)

    # Specify host and port
    python main.py --host 0.0.0.0 --port 8080
"""

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core.config import settings, SPORTS, BET_TYPES
from core.db import db


# All available bookmaker scrapers
SCRAPER_REGISTRY = {
    'admiral':   {'module': 'core.scrapers.admiral',   'class': 'AdmiralScraper',   'id': 4},
    'soccerbet': {'module': 'core.scrapers.soccerbet', 'class': 'SoccerbetScraper', 'id': 5},
    'maxbet':    {'module': 'core.scrapers.maxbet',    'class': 'MaxbetScraper',     'id': 3},
    'mozzart':   {'module': 'core.scrapers.mozzart',   'class': 'MozzartScraper',    'id': 1},
    'meridian':  {'module': 'core.scrapers.meridian',  'class': 'MeridianScraper',   'id': 2},
    'superbet':  {'module': 'core.scrapers.superbet',  'class': 'SuperbetScraper',   'id': 6},
    'merkur':    {'module': 'core.scrapers.merkur',    'class': 'MerkurScraper',     'id': 7},
    'topbet':    {'module': 'core.scrapers.topbet',    'class': 'TopbetScraper',     'id': 10},
}


def setup_logging(debug: bool = False):
    """Configure logging for the application."""
    level = logging.DEBUG if debug else getattr(logging, settings.log_level.upper())
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
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
        description='BetSnipe.ai v2.0 - Real-time odds platform',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Single bookmaker debug examples:
  python main.py --mozzart                 Debug Mozzart scraper
  python main.py --admiral --cycles 5      Run Admiral for 5 cycles
  python main.py --maxbet --sport 1        Maxbet football only
  python main.py --superbet --no-db        Superbet dry run (no database)
        """
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

    # Individual bookmaker flags
    bookmaker_group = parser.add_argument_group('single bookmaker debug')
    for name in SCRAPER_REGISTRY:
        bookmaker_group.add_argument(
            f'--{name}',
            action='store_true',
            help=f'Debug {name.capitalize()} scraper only'
        )

    # Single-scraper options
    single_group = parser.add_argument_group('single scraper options')
    single_group.add_argument(
        '--cycles',
        type=int,
        default=0,
        help='Number of cycles to run (0 = infinite, default: 0)'
    )
    single_group.add_argument(
        '--sport',
        type=int,
        default=None,
        help='Scrape only this sport ID (1=Football, 2=Basketball, 3=Tennis, 4=Hockey, 5=Table Tennis)'
    )
    single_group.add_argument(
        '--no-db',
        action='store_true',
        help='Dry run: scrape and display results without database'
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


def get_selected_scraper(args) -> str | None:
    """Return the name of the selected single bookmaker, or None."""
    for name in SCRAPER_REGISTRY:
        if getattr(args, name, False):
            return name
    return None


def create_scraper_instance(name: str):
    """Dynamically import and create a scraper instance."""
    import importlib
    info = SCRAPER_REGISTRY[name]
    module = importlib.import_module(info['module'])
    cls = getattr(module, info['class'])
    return cls()


async def run_single_scraper_debug(scraper_name: str, args):
    """
    Run a single bookmaker scraper with detailed debug logging.
    Full engine with DB, arbitrage detection, and verbose output.
    """
    logger = logging.getLogger(__name__)
    scraper = create_scraper_instance(scraper_name)
    use_db = not args.no_db
    max_cycles = args.cycles
    sport_filter = args.sport

    info = SCRAPER_REGISTRY[scraper_name]

    print()
    print("=" * 60)
    print(f"  DEBUG MODE: {scraper.bookmaker_name}")
    print(f"  Bookmaker ID: {info['id']}")
    print(f"  Supported sports: {scraper.get_supported_sports()}")
    print(f"  Database: {'ON' if use_db else 'OFF (dry run)'}")
    print(f"  Sport filter: {SPORTS[sport_filter]['name'] if sport_filter else 'ALL'}")
    print(f"  Max cycles: {max_cycles if max_cycles > 0 else 'infinite'}")
    print(f"  Scrape interval: {settings.scrape_interval_seconds}s")
    print("=" * 60)
    print()

    if use_db:
        logger.info("Connecting to database...")
        await db.connect()
        logger.info("Database connected")

    cycle = 0
    try:
        while True:
            cycle += 1
            cycle_start = time.time()

            print()
            print("-" * 60)
            print(f"  CYCLE {cycle} | {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
            print("-" * 60)

            # Determine which sports to scrape
            if sport_filter:
                sports_to_scrape = [sport_filter]
            else:
                sports_to_scrape = scraper.get_supported_sports()

            all_matches = []
            total_odds = 0

            # Scrape each sport individually for detailed logging
            for sport_id in sports_to_scrape:
                sport_name = SPORTS.get(sport_id, {}).get('name', f'sport_{sport_id}')
                sport_start = time.time()

                try:
                    logger.info(f"[{scraper.bookmaker_name}] Scraping {sport_name} (id={sport_id})...")
                    matches = await scraper.scrape_sport(sport_id)
                    sport_time = time.time() - sport_start

                    sport_odds = sum(len(m.odds) for m in matches)
                    total_odds += sport_odds
                    all_matches.extend(matches)

                    print(f"  {sport_name.upper():15s} | {len(matches):4d} matches | {sport_odds:5d} odds | {sport_time:.2f}s")

                except Exception as e:
                    sport_time = time.time() - sport_start
                    print(f"  {sport_name.upper():15s} | ERROR: {e} | {sport_time:.2f}s")
                    logger.error(f"Error scraping {sport_name}: {e}", exc_info=True)

            scrape_time = time.time() - cycle_start

            print(f"  {'':15s} |---------|-------|")
            print(f"  {'TOTAL':15s} | {len(all_matches):4d} matches | {total_odds:5d} odds | {scrape_time:.2f}s")

            # Process into database
            if use_db and all_matches:
                from core.matching import normalize_team_name

                db_start = time.time()

                matches_data = []
                skipped = 0
                for match in all_matches:
                    team1_normalized = normalize_team_name(match.team1)
                    team2_normalized = normalize_team_name(match.team2)

                    if not team1_normalized or not team2_normalized:
                        skipped += 1
                        logger.debug(f"  Skipped (normalize failed): {match.team1} vs {match.team2}")
                        continue

                    odds_list = []
                    for odds in match.odds:
                        odds_list.append({
                            'bet_type_id': odds.bet_type_id,
                            'odd1': odds.odd1,
                            'odd2': odds.odd2,
                            'odd3': odds.odd3,
                            'margin': odds.margin,
                            'selection': odds.selection,
                        })

                    matches_data.append({
                        'team1': match.team1,
                        'team2': match.team2,
                        'team1_normalized': team1_normalized,
                        'team2_normalized': team2_normalized,
                        'sport_id': match.sport_id,
                        'start_time': match.start_time,
                        'external_id': match.external_id,
                        'league_name': match.league_name,
                        'odds': odds_list,
                    })

                processed = await db.bulk_upsert_matches_and_odds(
                    matches_data, info['id']
                )

                db_time = time.time() - db_start

                print()
                print(f"  DB INSERT: {processed} processed | {skipped} skipped | {db_time:.2f}s")

                # Run arbitrage detection
                arb_start = time.time()
                from core.arbitrage import ArbitrageDetector
                detector = ArbitrageDetector()
                opportunities = await detector.detect_all()
                arb_time = time.time() - arb_start

                if opportunities:
                    print(f"  ARBITRAGE: {len(opportunities)} opportunities found | {arb_time:.2f}s")
                    for opp in opportunities:
                        opp_dict = opp.to_dict()
                        print(f"    -> {opp_dict.get('profit_percentage', 0):.2f}% profit | "
                              f"{opp_dict.get('team1', '?')} vs {opp_dict.get('team2', '?')}")
                else:
                    print(f"  ARBITRAGE: none found | {arb_time:.2f}s")

            elif not use_db:
                print()
                print(f"  DRY RUN: {len(all_matches)} matches scraped, {total_odds} odds (no DB write)")

            total_time = time.time() - cycle_start
            print()
            print(f"  Cycle {cycle} completed in {total_time:.2f}s "
                  f"(scrape: {scrape_time:.2f}s"
                  f"{f', db: {total_time - scrape_time:.2f}s' if use_db else ''})")

            # Check if we should stop
            if max_cycles > 0 and cycle >= max_cycles:
                print()
                print(f"  Reached max cycles ({max_cycles}). Stopping.")
                break

            # Wait before next cycle
            print(f"  Waiting {settings.scrape_interval_seconds}s before next cycle... (Ctrl+C to stop)")
            await asyncio.sleep(settings.scrape_interval_seconds)

    except KeyboardInterrupt:
        print()
        print("  Interrupted by user.")
    finally:
        print()
        print("=" * 60)
        print(f"  FINAL STATS: {scraper.bookmaker_name}")
        print(f"  Cycles run: {cycle}")
        stats = scraper.get_stats()
        print(f"  HTTP requests: {stats['request_count']}")
        print(f"  Errors: {stats['error_count']}")
        print(f"  Last scrape: {stats['last_scrape'] or 'N/A'}")
        print("=" * 60)

        await scraper.close()
        if use_db:
            await db.disconnect()
            logger.info("Database disconnected")


async def run_scraper_only():
    """Run only the scraper engine without the API server."""
    from core.scraper_engine import engine
    from core.scrapers.admiral import AdmiralScraper
    from core.scrapers.soccerbet import SoccerbetScraper
    from core.scrapers.maxbet import MaxbetScraper
    from core.scrapers.mozzart import MozzartScraper
    from core.scrapers.meridian import MeridianScraper
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
    engine.register_scraper(MeridianScraper())
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

    # Check for single bookmaker mode
    selected_scraper = get_selected_scraper(args)

    # Force debug logging for single bookmaker mode
    if selected_scraper:
        args.debug = True

    if args.debug:
        settings.log_level = 'DEBUG'

    setup_logging(debug=args.debug)

    logger = logging.getLogger(__name__)

    if selected_scraper:
        # Single bookmaker debug mode
        asyncio.run(run_single_scraper_debug(selected_scraper, args))
        return

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
