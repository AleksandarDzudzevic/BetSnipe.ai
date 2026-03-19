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
import re
import sys
import unicodedata
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import settings, BOOKMAKERS, BET_TYPES
from core.scrapers.admiral import AdmiralScraper
from core.scrapers.soccerbet import SoccerbetScraper
from core.scrapers.maxbet import MaxbetScraper
from core.scrapers.meridian import MeridianScraper
from core.scrapers.superbet import SuperbetScraper
from core.scrapers.merkur import MerkurScraper
from core.scrapers.topbet import TopbetScraper
from core.scrapers.mozzart import MozzartScraper
from core.scrapers.balkanbet import BalkanBetScraper
from core.arbitrage import ArbitrageDetector, ArbitrageOpportunity
from telegram_utils import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce noise from aiohttp
logging.getLogger('aiohttp').setLevel(logging.WARNING)

# Fix 1: Build SCRAPERS dict with bookmaker IDs, then filter to only enabled ones.
# Meridian (id=2) has enabled=False in BOOKMAKERS config so it will be excluded.
_ALL_SCRAPERS = {
    'mozzart':   (1,  MozzartScraper),
    'admiral':   (4,  AdmiralScraper),
    'soccerbet': (5,  SoccerbetScraper),
    'maxbet':    (3,  MaxbetScraper),
    'meridian':  (2,  MeridianScraper),
    'superbet':  (6,  SuperbetScraper),
    'merkur':    (7,  MerkurScraper),
    'topbet':    (10, TopbetScraper),
    'balkanbet': (12, BalkanBetScraper),
}
SCRAPERS = {
    name: cls
    for name, (bk_id, cls) in _ALL_SCRAPERS.items()
    if BOOKMAKERS.get(bk_id, {}).get('enabled', True)
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
                        parts = [f"{odd.odd1:.2f}"] if odd.odd1 else []
                        # Fix 8: Skip zero values in addition to None
                        if odd.odd2 is not None and odd.odd2 > 0:
                            parts.append(f"{odd.odd2:.2f}")
                        if odd.odd3 is not None and odd.odd3 > 0:
                            parts.append(f"{odd.odd3:.2f}")
                        logger.info(f"          Type {odd.bet_type_id}: {' / '.join(parts)}")

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


# Fix 2: Run all scrapers concurrently with asyncio.gather instead of sequentially.
async def test_all_scrapers(sport_id: int = None):
    """Test all scrapers concurrently."""
    tasks = {name: test_scraper(name, sport_id) for name in SCRAPERS}
    results_list = await asyncio.gather(*tasks.values(), return_exceptions=True)
    results = {}
    for name, result in zip(tasks.keys(), results_list):
        if isinstance(result, Exception):
            logger.error(f"Scraper {name} failed: {result}")
            results[name] = []
        else:
            results[name] = result
    return results


MAX_ARB_PROFIT_PCT = 10.0  # Cap: anything above 10% is almost certainly a false match

# Generic club-type suffixes to strip when normalizing for cross-bookmaker matching.
# Only strip truly generic abbreviations (FC, SC, BK, CP, …) — NOT identity words like
# "United", "City", "Rovers" etc. which are part of the club's actual name.
_CLUB_SUFFIX = re.compile(
    r'\b(f\.?c\.?|s\.?c\.?|b\.?k\.?|f\.?k\.?|s\.?k\.?|c\.?f\.?|a\.?c\.?|i\.?f\.?|'
    r'a\.?f\.?c\.?|r\.?f\.?c\.?|b\.?f\.?c\.?|s\.?s\.?|c\.?d\.?|r\.?c\.?|c\.?p\.?)\b\.?',
    re.IGNORECASE
)
# Transliteration table for Scandinavian/special chars that some bookmakers expand
# (e.g. Bodø → Bodo vs Bodoe depending on bookmaker encoding choice)
_TRANSLITERATE = str.maketrans({
    'ø': 'o', 'ö': 'o', 'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o',
    'ü': 'u', 'ú': 'u', 'ù': 'u', 'û': 'u',
    'ä': 'a', 'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a',
    'ë': 'e', 'é': 'e', 'è': 'e', 'ê': 'e',
    'ï': 'i', 'í': 'i', 'ì': 'i', 'î': 'i',
    'ñ': 'n', 'ß': 'ss',
})
# Reserve/youth squad markers — captured to keep in the matching key
_SQUAD_LEVEL = re.compile(
    r'\b(u\.?21|u\.?19|u\.?18|u\.?17|u\.?16|u\.?23|under.?\d+|'
    r'\bii\b|\ 2$|\ b$|reserve|b\.?team|2nd)\b',
    re.IGNORECASE
)


def _normalize_name(name: str) -> str:
    """Normalize a team name for cross-bookmaker fuzzy grouping."""
    # Transliterate special chars (ø→o, ö→o, etc.) BEFORE NFKD so that
    # "Bodoe/Glimt" and "Bodo/Glimt" both resolve to "bodo/glimt"
    name = name.translate(_TRANSLITERATE)
    # Remove any remaining combining diacritics via NFKD
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = name.lower().strip()
    # Remove club-type suffixes (FC, SC, BK, CP, …) — they vary between bookmakers
    name = _CLUB_SUFFIX.sub('', name)
    # Collapse whitespace
    return re.sub(r'\s+', ' ', name).strip()


def _squad_level(name: str) -> str:
    """Return a squad-level tag so 'Team 2' never groups with 'Team'."""
    m = _SQUAD_LEVEL.search(name)
    if m:
        tag = m.group(0).lower().strip().replace(' ', '')
        # Normalise roman II → 2
        return '2' if tag == 'ii' else tag
    return ''


def _match_start_bucket(match) -> str:
    """Round start_time to nearest 2-hour bucket so only same-day/same-slot matches group."""
    t = match.start_time
    if t is None:
        return 'unknown'
    # Make timezone-aware if naive
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    # 2-hour buckets: floor to even hour
    bucket_hour = (t.hour // 2) * 2
    return f"{t.year}-{t.month:02d}-{t.day:02d}T{bucket_hour:02d}"


def detect_arbitrage_simple(all_matches: dict):
    """Simple arbitrage detection from scraped matches."""
    from collections import defaultdict

    # Build normalised grouping key:
    #   sport : squad_level_t1 : normalised_t1 : squad_level_t2 : normalised_t2 : time_bucket
    # This prevents:
    #   - "FC" vs no-FC mismatches (normalisation strips FC)
    #   - "Team 2" grouping with "Team" (squad level included in key)
    #   - Different-day same-fixture false groups (2-hour time bucket)
    grouped = defaultdict(list)

    for bookmaker, matches in all_matches.items():
        for match in matches:
            t1_norm = _normalize_name(match.team1)
            t2_norm = _normalize_name(match.team2)
            sq1 = _squad_level(match.team1)
            sq2 = _squad_level(match.team2)
            time_bucket = _match_start_bucket(match)
            key = f"{match.sport_id}:{sq1}:{t1_norm}:{sq2}:{t2_norm}:{time_bucket}"
            grouped[key].append((bookmaker, match))

    arbitrage_opps = []

    # Handicap conventions differ across bookmakers (European vs Asian),
    # causing systematic false arbs even at identical margin values.
    # LAST_GOAL (89) is excluded: it doesn't cover the 0-0 outcome, so the
    # implied probabilities don't sum to 1 and no true arb can exist.
    EXCLUDED_BET_TYPE_IDS = {9, 50, 56, 58, 80, 85, 95, 89}

    # Check every configured bet type, not just bt1/bt2.
    # Skip selection markets (outcomes=1) — those need per-selection logic.
    for key, bookmaker_matches in grouped.items():
        if len(bookmaker_matches) < 2:
            continue

        for bet_type_id, bt_config in BET_TYPES.items():
            bt_outcomes = bt_config.get('outcomes', 2)
            if bt_outcomes == 1:
                continue  # selection markets need different logic
            if bet_type_id in EXCLUDED_BET_TYPE_IDS:
                continue
            bt_name = bt_config.get('name', str(bet_type_id)).upper()

            # Collect all odds grouped by exact margin value.
            # CRITICAL: for O/U and handicap markets the margin (line value) must
            # match between bookmakers.  Comparing O2.5 from one book with U3.5
            # from another produces false arbs.  Group by margin so we only ever
            # compare odds that are for the identical line.
            odds_by_margin: dict = defaultdict(lambda: defaultdict(list))
            for bookmaker, match in bookmaker_matches:
                for odd in match.odds:
                    if odd.bet_type_id != bet_type_id:
                        continue
                    m = round(float(odd.margin or 0), 2)
                    if odd.odd1 and odd.odd1 > 1.0:
                        odds_by_margin[m][1].append((bookmaker, odd.odd1))
                    if odd.odd2 and odd.odd2 > 1.0:
                        odds_by_margin[m][2].append((bookmaker, odd.odd2))
                    if bt_outcomes == 3 and odd.odd3 and odd.odd3 > 1.0:
                        odds_by_margin[m][3].append((bookmaker, odd.odd3))

            for margin_val, odds_by_outcome in odds_by_margin.items():
                # Need at least 2 different bookmakers for this exact line
                all_bookmakers = set(bk for odds_list in odds_by_outcome.values() for bk, _ in odds_list)
                if len(all_bookmakers) < 2:
                    continue

                # Pick best odd per outcome
                best_odds = {}
                for outcome, odds_list in odds_by_outcome.items():
                    best = max(odds_list, key=lambda x: x[1])
                    best_odds[outcome] = best

                if bt_outcomes == 2:
                    if 1 not in best_odds or 2 not in best_odds:
                        continue
                    # Require legs from different bookmakers
                    if best_odds[1][0] == best_odds[2][0]:
                        alt = [(bk, o) for bk, o in odds_by_outcome[2] if bk != best_odds[1][0]]
                        if not alt:
                            continue
                        best_odds[2] = max(alt, key=lambda x: x[1])
                    total_prob = (1 / best_odds[1][1]) + (1 / best_odds[2][1])
                    if total_prob >= 1:
                        continue
                    profit = (1 - total_prob) * 100

                elif bt_outcomes == 3:
                    if not (1 in best_odds and 2 in best_odds and 3 in best_odds):
                        continue
                    bookmakers_used = {best_odds[o][0] for o in best_odds}
                    if len(bookmakers_used) < 2:
                        continue
                    total_prob = (1 / best_odds[1][1]) + (1 / best_odds[2][1]) + (1 / best_odds[3][1])
                    if total_prob >= 1:
                        continue
                    profit = (1 - total_prob) * 100
                else:
                    continue

                # Hard cap — anything above MAX_ARB_PROFIT_PCT is almost certainly
                # a team-name mismatch that slipped through normalisation.
                if profit > MAX_ARB_PROFIT_PCT:
                    continue

                suffix = f" (line {margin_val})" if margin_val else ""
                arbitrage_opps.append({
                    'teams': f"{bookmaker_matches[0][1].team1} vs {bookmaker_matches[0][1].team2}",
                    'bet_type': bt_name + suffix,
                    'profit': profit,
                    'odds': best_odds,
                })

    # Sort by descending profit
    arbitrage_opps.sort(key=lambda x: x['profit'], reverse=True)
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
