"""
Unified Scraper Engine for BetSnipe.ai v2.0

Orchestrates all bookmaker scrapers, processes matches, detects arbitrage,
and broadcasts updates via WebSocket.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable

from .config import settings, SPORTS
from .db import db, Database
from .matching import MatchMatcher, normalize_team_name
from .arbitrage import ArbitrageDetector, ArbitrageOpportunity, format_arbitrage_message
from .scrapers.base import BaseScraper, ScrapedMatch

# Import telegram notifier (lazy to avoid circular imports)
_telegram_notifier = None

def get_telegram_notifier():
    global _telegram_notifier
    if _telegram_notifier is None:
        from telegram_utils import notifier
        _telegram_notifier = notifier
    return _telegram_notifier

logger = logging.getLogger(__name__)


class ScraperEngine:
    """
    Main orchestrator for the scraping system.

    Responsibilities:
    - Manage scraper lifecycle
    - Process scraped matches and store them
    - Detect arbitrage opportunities
    - Broadcast updates to connected clients
    """

    def __init__(self):
        self._scrapers: List[BaseScraper] = []
        self._running = False
        self._matcher = MatchMatcher()
        self._detector = ArbitrageDetector()
        self._update_callbacks: List[Callable] = []
        self._stats = {
            'cycles': 0,
            'matches_processed': 0,
            'odds_updated': 0,
            'arbitrage_found': 0,
            'errors': 0,
            'last_cycle': None,
        }

    def register_scraper(self, scraper: BaseScraper) -> None:
        """Register a scraper to be run by the engine."""
        self._scrapers.append(scraper)
        logger.info(f"Registered scraper: {scraper.bookmaker_name}")

    def register_update_callback(self, callback: Callable) -> None:
        """Register a callback to be called when updates occur."""
        self._update_callbacks.append(callback)

    async def _notify_update(self, update_type: str, data: Any) -> None:
        """Notify all registered callbacks of an update."""
        for callback in self._update_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(update_type, data)
                else:
                    callback(update_type, data)
            except Exception as e:
                logger.error(f"Error in update callback: {e}")

    async def process_scraped_match(
        self,
        match: ScrapedMatch,
        bookmaker_id: int
    ) -> Optional[int]:
        """
        Process a scraped match: match it to existing or create new, update odds.

        Args:
            match: The scraped match data
            bookmaker_id: The bookmaker ID

        Returns:
            The match ID in the database
        """
        try:
            # Normalize team names
            team1_normalized = normalize_team_name(match.team1)
            team2_normalized = normalize_team_name(match.team2)

            if not team1_normalized or not team2_normalized:
                logger.warning(f"Could not normalize teams: {match.team1} vs {match.team2}")
                return None

            # Get sport-specific time window
            sport_config = SPORTS.get(match.sport_id, {})
            time_window = sport_config.get('time_window_minutes', 30)

            # Try to find existing match
            existing = await db.find_matching_match(
                team1_normalized, team2_normalized,
                match.sport_id, match.start_time,
                time_window_minutes=time_window
            )

            if existing:
                match_id = existing['id']
            else:
                # Try fuzzy matching against potential candidates
                candidates = await db.find_potential_matches(
                    match.sport_id, match.start_time,
                    time_window_minutes=time_window * 2
                )

                best_match, score = self._matcher.find_best_match(
                    match.team1, match.team2,
                    match.sport_id, match.start_time,
                    candidates,
                    league_name=match.league_name
                )

                if best_match and score and score.is_match:
                    match_id = best_match['id']
                    logger.debug(
                        f"Fuzzy matched: {match.team1} vs {match.team2} -> "
                        f"{best_match['team1']} vs {best_match['team2']} "
                        f"(confidence: {score.confidence:.1f})"
                    )
                else:
                    # Create new match
                    match_id = await db.upsert_match(
                        team1=match.team1,
                        team2=match.team2,
                        team1_normalized=team1_normalized,
                        team2_normalized=team2_normalized,
                        sport_id=match.sport_id,
                        start_time=match.start_time,
                        external_id=(bookmaker_id, match.external_id) if match.external_id else None,
                        metadata=match.metadata
                    )

            # Update odds
            odds_changed = False
            for odds in match.odds:
                try:
                    changed = await db.upsert_current_odds(
                        match_id=match_id,
                        bookmaker_id=bookmaker_id,
                        bet_type_id=odds.bet_type_id,
                        odd1=odds.odd1,
                        odd2=odds.odd2,
                        odd3=odds.odd3,
                        margin=odds.margin
                    )

                    if changed:
                        odds_changed = True
                        self._stats['odds_updated'] += 1

                        # Record history if enabled
                        await db.record_odds_history(
                            match_id=match_id,
                            bookmaker_id=bookmaker_id,
                            bet_type_id=odds.bet_type_id,
                            odd1=odds.odd1,
                            odd2=odds.odd2,
                            odd3=odds.odd3,
                            margin=odds.margin
                        )
                except Exception as e:
                    logger.debug(f"Error upserting odds for match {match_id}: {e}")

            self._stats['matches_processed'] += 1

            # Notify if odds changed
            if odds_changed:
                await self._notify_update('odds_update', {
                    'match_id': match_id,
                    'bookmaker_id': bookmaker_id,
                    'team1': match.team1,
                    'team2': match.team2,
                })

            return match_id

        except Exception as e:
            logger.debug(f"Error processing match {match.team1} vs {match.team2}: {e}")
            raise

    async def scrape_bookmaker(self, scraper: BaseScraper) -> int:
        """
        Run a single bookmaker scraper and process results.

        Args:
            scraper: The scraper to run

        Returns:
            Number of matches processed
        """
        start_time = time.time()

        try:
            matches = await scraper.scrape_all()
            scrape_time = time.time() - start_time
            logger.info(f"[{scraper.bookmaker_name}] Scraped {len(matches)} matches in {scrape_time:.2f}s, processing...")

            # Convert ScrapedMatch objects to dicts for bulk processing
            matches_data = []
            for match in matches:
                team1_normalized = normalize_team_name(match.team1)
                team2_normalized = normalize_team_name(match.team2)

                if not team1_normalized or not team2_normalized:
                    continue

                odds_list = []
                for odds in match.odds:
                    odds_list.append({
                        'bet_type_id': odds.bet_type_id,
                        'odd1': odds.odd1,
                        'odd2': odds.odd2,
                        'odd3': odds.odd3,
                        'margin': odds.margin,
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

            # Use bulk processing for much faster inserts
            processed = await db.bulk_upsert_matches_and_odds(
                matches_data, scraper.bookmaker_id
            )

            total_time = time.time() - start_time
            self._stats['matches_processed'] += processed
            logger.info(f"[{scraper.bookmaker_name}] Processed {processed} matches in {total_time:.2f}s (scrape: {scrape_time:.2f}s, db: {total_time - scrape_time:.2f}s)")
            return len(matches)

        except Exception as e:
            logger.error(f"Error scraping {scraper.bookmaker_name}: {e}", exc_info=True)
            self._stats['errors'] += 1
            # Reset session on error to avoid poisoned connections next cycle
            await scraper.reset_session()
            return 0

    async def run_cycle(self) -> Dict[str, Any]:
        """
        Run a single scraping cycle.

        Returns:
            Cycle statistics
        """
        cycle_start = datetime.utcnow()

        # Scrape all bookmakers concurrently
        tasks = [
            self.scrape_bookmaker(scraper)
            for scraper in self._scrapers
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_matches = sum(r for r in results if isinstance(r, int))

        # Detect arbitrage
        arbitrage_opportunities = await self._detector.detect_all()

        # Notify about new arbitrage
        for opp in arbitrage_opportunities:
            self._stats['arbitrage_found'] += 1
            await self._notify_update('arbitrage', opp.to_dict())

            # Send Telegram notification
            try:
                telegram = get_telegram_notifier()
                if telegram.is_configured:
                    await telegram.send_arbitrage_alert(opp)
            except Exception as e:
                logger.error(f"Error sending Telegram notification: {e}")

        # Deactivate expired arbitrage
        await db.deactivate_expired_arbitrage()

        cycle_end = datetime.utcnow()
        cycle_duration = (cycle_end - cycle_start).total_seconds()

        self._stats['cycles'] += 1
        self._stats['last_cycle'] = cycle_end.isoformat()

        cycle_stats = {
            'cycle': self._stats['cycles'],
            'duration_seconds': cycle_duration,
            'matches_scraped': total_matches,
            'arbitrage_found': len(arbitrage_opportunities),
            'timestamp': cycle_end.isoformat(),
        }

        logger.info(
            f"Cycle {self._stats['cycles']}: "
            f"{total_matches} matches, "
            f"{len(arbitrage_opportunities)} arbitrage, "
            f"{cycle_duration:.1f}s"
        )

        return cycle_stats

    async def start(self) -> None:
        """Start the continuous scraping loop."""
        if self._running:
            logger.warning("Engine already running")
            return

        if not self._scrapers:
            logger.warning("No scrapers registered")
            return

        self._running = True
        logger.info(f"Starting scraper engine with {len(self._scrapers)} scrapers")

        # Connect to database
        await db.connect()

        try:
            while self._running:
                try:
                    await self.run_cycle()
                except Exception as e:
                    logger.error(f"Error in scrape cycle: {e}")
                    self._stats['errors'] += 1

                # Wait before next cycle
                await asyncio.sleep(settings.scrape_interval_seconds)

        finally:
            # Cleanup
            await self.stop()

    async def stop(self) -> None:
        """Stop the scraping loop."""
        logger.info("Stopping scraper engine")
        self._running = False

        # Close all scraper sessions
        for scraper in self._scrapers:
            await scraper.close()

        # Disconnect from database
        await db.disconnect()

    @property
    def is_running(self) -> bool:
        return self._running

    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        stats = {
            **self._stats,
            'scrapers': [s.get_stats() for s in self._scrapers],
        }
        return stats


# Global engine instance
engine = ScraperEngine()
