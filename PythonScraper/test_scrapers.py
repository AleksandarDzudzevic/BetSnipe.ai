#!/usr/bin/env python3
"""
BetSnipe.ai v2.0 - Scraper Test Script

Quick test to verify scrapers are working without database.
Runs all scrapers, prints matches found, and tests Telegram notifications.

Usage:
    python test_scrapers.py                    # Test all scrapers
    python test_scrapers.py --scraper admiral  # Test specific scraper
    python test_scrapers.py --sport 1          # Test specific sport (1=Football)
    python test_scrapers.py --telegram         # Also test Telegram notification
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import settings
from core.scrapers.admiral import AdmiralScraper
from core.scrapers.soccerbet import SoccerbetScraper
from core.scrapers.maxbet import MaxbetScraper
from core.scrapers.meridian import MeridianScraper
from core.scrapers.superbet import SuperbetScraper
from core.scrapers.merkur import MerkurScraper
from core.scrapers.topbet import TopbetScraper
from core.scrapers.mozzart import MozzartScraper
from core.arbitrage import ArbitrageDetector, ArbitrageOpportunity
from telegram_utils import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce noise from aiohttp
logging.getLogger('aiohttp').setLevel(logging.WARNING)

SCRAPERS = {
    'mozzart': MozzartScraper,
    'admiral': AdmiralScraper,
    'soccerbet': SoccerbetScraper,
    'maxbet': MaxbetScraper,
    'meridian': MeridianScraper,
    'superbet': SuperbetScraper,
    'merkur': MerkurScraper,
    'topbet': TopbetScraper,
}

SPORTS = {
    1: 'Football',
    2: 'Basketball',
    3: 'Tennis',
    4: 'Hockey',
    5: 'Table Tennis',
}


async def test_scraper(scraper_name: str, sport_id: int = None):
    """Test a single scraper."""
    if scraper_name not in SCRAPERS:
        logger.error(f"Unknown scraper: {scraper_name}")
        return []

    scraper_class = SCRAPERS[scraper_name]
    scraper = scraper_class()

    logger.info(f"Testing {scraper.bookmaker_name} scraper...")

    all_matches = []
    sports_to_test = [sport_id] if sport_id else scraper.get_supported_sports()

    try:
        for sid in sports_to_test:
            sport_name = SPORTS.get(sid, f"Sport {sid}")
            logger.info(f"  Scraping {sport_name}...")

            try:
                matches = await scraper.scrape_sport(sid)
                all_matches.extend(matches)

                logger.info(f"    Found {len(matches)} matches with odds")

                # Print first 3 matches as sample
                for match in matches[:3]:
                    logger.info(f"      - {match.team1} vs {match.team2}")
                    logger.info(f"        Start: {match.start_time}")
                    logger.info(f"        Odds: {len(match.odds)} bet types")
                    for odd in match.odds[:2]:
                        logger.info(f"          Type {odd.bet_type_id}: {odd.odd1:.2f} / {odd.odd2:.2f}" +
                                   (f" / {odd.odd3:.2f}" if odd.odd3 else ""))

                if len(matches) > 3:
                    logger.info(f"      ... and {len(matches) - 3} more matches")

            except Exception as e:
                logger.error(f"    Error scraping {sport_name}: {e}")
                import traceback
                traceback.print_exc()

    finally:
        # Clean up the session
        await scraper.close()

    return all_matches


async def test_all_scrapers(sport_id: int = None):
    """Test all scrapers."""
    results = {}

    for name in SCRAPERS:
        matches = await test_scraper(name, sport_id)
        results[name] = matches

    return results


def detect_arbitrage_simple(all_matches: dict):
    """Simple arbitrage detection from scraped matches."""
    from rapidfuzz import fuzz
    from collections import defaultdict

    # Group matches by team similarity
    grouped = defaultdict(list)

    for bookmaker, matches in all_matches.items():
        for match in matches:
            # Create a key based on normalized team names
            key = f"{match.sport_id}:{match.team1[:10].lower()}:{match.team2[:10].lower()}"
            grouped[key].append((bookmaker, match))

    arbitrage_opps = []

    # Check each group for arbitrage
    for key, bookmaker_matches in grouped.items():
        if len(bookmaker_matches) < 2:
            continue

        # Get all odds for bet_type_id=2 (1X2) as example
        for bet_type_id in [1, 2]:
            odds_by_outcome = defaultdict(list)  # outcome -> [(bookmaker, odd)]

            for bookmaker, match in bookmaker_matches:
                for odd in match.odds:
                    if odd.bet_type_id == bet_type_id:
                        odds_by_outcome[1].append((bookmaker, odd.odd1))
                        odds_by_outcome[2].append((bookmaker, odd.odd2))
                        if odd.odd3:
                            odds_by_outcome[3].append((bookmaker, odd.odd3))

            # Check if we have odds from at least 2 bookmakers
            if len(odds_by_outcome) >= 2:
                # Find best odds for each outcome
                best_odds = {}
                for outcome, odds_list in odds_by_outcome.items():
                    if odds_list:
                        best = max(odds_list, key=lambda x: x[1])
                        best_odds[outcome] = best

                # Calculate implied probability
                if bet_type_id == 1:  # 2-way
                    if 1 in best_odds and 2 in best_odds:
                        total_prob = (1/best_odds[1][1]) + (1/best_odds[2][1])
                        if total_prob < 1:
                            profit = (1 - total_prob) * 100
                            arbitrage_opps.append({
                                'teams': f"{bookmaker_matches[0][1].team1} vs {bookmaker_matches[0][1].team2}",
                                'bet_type': '12',
                                'profit': profit,
                                'odds': best_odds,
                            })

                elif bet_type_id == 2:  # 3-way
                    if 1 in best_odds and 2 in best_odds and 3 in best_odds:
                        total_prob = (1/best_odds[1][1]) + (1/best_odds[2][1]) + (1/best_odds[3][1])
                        if total_prob < 1:
                            profit = (1 - total_prob) * 100
                            arbitrage_opps.append({
                                'teams': f"{bookmaker_matches[0][1].team1} vs {bookmaker_matches[0][1].team2}",
                                'bet_type': '1X2',
                                'profit': profit,
                                'odds': best_odds,
                            })

    return arbitrage_opps


async def test_telegram():
    """Test Telegram notification."""
    notifier = TelegramNotifier()

    if not notifier.is_configured:
        logger.warning("Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        return False

    logger.info("Sending test Telegram message...")

    test_message = """
🧪 *BetSnipe.ai v2.0 Test*

This is a test message from the scraper test script.

If you see this, Telegram notifications are working!

Timestamp: {}
""".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    success = await notifier.send_message(test_message)

    if success:
        logger.info("Telegram test message sent successfully!")
    else:
        logger.error("Failed to send Telegram test message")

    return success


async def main():
    parser = argparse.ArgumentParser(description='Test BetSnipe.ai scrapers')
    parser.add_argument('--scraper', type=str, help='Test specific scraper (admiral, soccerbet, etc.)')
    parser.add_argument('--sport', type=int, help='Test specific sport (1=Football, 2=Basketball, etc.)')
    parser.add_argument('--telegram', action='store_true', help='Test Telegram notification')
    parser.add_argument('--arbitrage', action='store_true', help='Run arbitrage detection on results')
    args = parser.parse_args()

    print("=" * 60)
    print("  BetSnipe.ai v2.0 - Scraper Test")
    print("=" * 60)
    print()

    # Test Telegram if requested
    if args.telegram:
        await test_telegram()
        print()

    # Test scrapers
    if args.scraper:
        results = {args.scraper: await test_scraper(args.scraper, args.sport)}
    else:
        results = await test_all_scrapers(args.sport)

    # Print summary
    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)

    total_matches = 0
    for name, matches in results.items():
        print(f"  {name.capitalize()}: {len(matches)} matches")
        total_matches += len(matches)

    print(f"  ---------------------")
    print(f"  Total: {total_matches} matches")
    print()

    # Run arbitrage detection if requested
    if args.arbitrage and total_matches > 0:
        print("=" * 60)
        print("  ARBITRAGE DETECTION")
        print("=" * 60)

        arb_opps = detect_arbitrage_simple(results)

        if arb_opps:
            print(f"  Found {len(arb_opps)} potential arbitrage opportunities:")
            for opp in arb_opps:
                print(f"    {opp['teams']}")
                print(f"      Type: {opp['bet_type']}, Profit: {opp['profit']:.2f}%")
                for outcome, (bookmaker, odd) in opp['odds'].items():
                    print(f"        Outcome {outcome}: {odd:.2f} @ {bookmaker}")
        else:
            print("  No arbitrage opportunities found (this is normal)")
        print()


if __name__ == "__main__":
    asyncio.run(main())
