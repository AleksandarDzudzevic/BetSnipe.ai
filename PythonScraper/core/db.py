"""
Database connection and operations for BetSnipe.ai v2.0

Uses asyncpg for async PostgreSQL operations with connection pooling.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import asyncpg
from asyncpg import Pool, Connection

from .config import settings

logger = logging.getLogger(__name__)


class Database:
    """Async database manager with connection pooling."""

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or settings.database_url
        self._pool: Optional[Pool] = None
        self._connected = False

    async def connect(self) -> None:
        """Initialize connection pool."""
        if self._pool is not None:
            return

        try:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60,
                statement_cache_size=100,
            )
            self._connected = True
            logger.info("Database connection pool established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            self._connected = False
            logger.info("Database connection pool closed")

    @property
    def is_connected(self) -> bool:
        return self._connected and self._pool is not None

    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool."""
        if not self._pool:
            await self.connect()
        async with self._pool.acquire() as conn:
            yield conn

    # ==========================================
    # MATCH OPERATIONS
    # ==========================================

    async def find_matching_match(
        self,
        team1_normalized: str,
        team2_normalized: str,
        sport_id: int,
        start_time: datetime,
        time_window_minutes: int = 120
    ) -> Optional[Dict[str, Any]]:
        """Find an existing match that matches the given criteria."""
        async with self.acquire() as conn:
            # Search within time window
            time_start = start_time - timedelta(minutes=time_window_minutes)
            time_end = start_time + timedelta(minutes=time_window_minutes)

            row = await conn.fetchrow(
                """
                SELECT id, team1, team2, team1_normalized, team2_normalized,
                       sport_id, league_id, start_time, external_ids, status
                FROM matches
                WHERE sport_id = $1
                  AND start_time BETWEEN $2 AND $3
                  AND status = 'upcoming'
                  AND (
                      (team1_normalized = $4 AND team2_normalized = $5)
                      OR (team1_normalized = $5 AND team2_normalized = $4)
                  )
                LIMIT 1
                """,
                sport_id, time_start, time_end, team1_normalized, team2_normalized
            )

            return dict(row) if row else None

    async def find_potential_matches(
        self,
        sport_id: int,
        start_time: datetime,
        time_window_minutes: int = 120
    ) -> List[Dict[str, Any]]:
        """Find all potential matches within time window for fuzzy matching."""
        async with self.acquire() as conn:
            time_start = start_time - timedelta(minutes=time_window_minutes)
            time_end = start_time + timedelta(minutes=time_window_minutes)

            rows = await conn.fetch(
                """
                SELECT id, team1, team2, team1_normalized, team2_normalized,
                       sport_id, league_id, start_time, external_ids, status
                FROM matches
                WHERE sport_id = $1
                  AND start_time BETWEEN $2 AND $3
                  AND status = 'upcoming'
                """,
                sport_id, time_start, time_end
            )

            return [dict(row) for row in rows]

    async def upsert_match(
        self,
        team1: str,
        team2: str,
        team1_normalized: str,
        team2_normalized: str,
        sport_id: int,
        start_time: datetime,
        league_id: Optional[int] = None,
        external_id: Optional[Tuple[int, str]] = None,  # (bookmaker_id, external_id)
        metadata: Optional[Dict] = None
    ) -> int:
        """Insert or update a match, returning the match ID."""
        async with self.acquire() as conn:
            # Check for existing match first
            existing = await self.find_matching_match(
                team1_normalized, team2_normalized, sport_id, start_time
            )

            if existing:
                match_id = existing['id']
                # Update external_ids if provided
                if external_id:
                    bookmaker_id, ext_id = external_id
                    current_ids = existing.get('external_ids') or {}
                    current_ids[str(bookmaker_id)] = ext_id
                    await conn.execute(
                        """
                        UPDATE matches
                        SET external_ids = $1, updated_at = NOW()
                        WHERE id = $2
                        """,
                        current_ids, match_id
                    )
                return match_id
            else:
                # Insert new match
                external_ids = {}
                if external_id:
                    bookmaker_id, ext_id = external_id
                    external_ids[str(bookmaker_id)] = ext_id

                match_id = await conn.fetchval(
                    """
                    INSERT INTO matches (
                        team1, team2, team1_normalized, team2_normalized,
                        sport_id, league_id, start_time, external_ids, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING id
                    """,
                    team1, team2, team1_normalized, team2_normalized,
                    sport_id, league_id, start_time, external_ids, metadata or {}
                )
                return match_id

    async def get_match_by_id(self, match_id: int) -> Optional[Dict[str, Any]]:
        """Get a match by ID."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM matches WHERE id = $1",
                match_id
            )
            return dict(row) if row else None

    async def get_upcoming_matches(
        self,
        sport_id: Optional[int] = None,
        hours_ahead: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get upcoming matches."""
        async with self.acquire() as conn:
            now = datetime.utcnow()
            end_time = now + timedelta(hours=hours_ahead)

            if sport_id:
                rows = await conn.fetch(
                    """
                    SELECT m.*, s.name as sport_name
                    FROM matches m
                    JOIN sports s ON m.sport_id = s.id
                    WHERE m.sport_id = $1
                      AND m.start_time BETWEEN $2 AND $3
                      AND m.status = 'upcoming'
                    ORDER BY m.start_time
                    LIMIT $4
                    """,
                    sport_id, now, end_time, limit
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT m.*, s.name as sport_name
                    FROM matches m
                    JOIN sports s ON m.sport_id = s.id
                    WHERE m.start_time BETWEEN $1 AND $2
                      AND m.status = 'upcoming'
                    ORDER BY m.start_time
                    LIMIT $3
                    """,
                    now, end_time, limit
                )

            return [dict(row) for row in rows]

    # ==========================================
    # ODDS OPERATIONS
    # ==========================================

    async def upsert_current_odds(
        self,
        match_id: int,
        bookmaker_id: int,
        bet_type_id: int,
        odd1: float,
        odd2: float,
        odd3: Optional[float] = None,
        margin: float = 0
    ) -> bool:
        """Update or insert current odds. Returns True if odds changed."""
        async with self.acquire() as conn:
            # Check if odds already exist
            existing = await conn.fetchrow(
                """
                SELECT odd1, odd2, odd3 FROM current_odds
                WHERE match_id = $1 AND bookmaker_id = $2
                  AND bet_type_id = $3 AND margin = $4
                """,
                match_id, bookmaker_id, bet_type_id, margin
            )

            if existing:
                # Check if odds changed
                if (existing['odd1'] == odd1 and
                    existing['odd2'] == odd2 and
                    existing['odd3'] == odd3):
                    return False  # No change

                # Update existing odds
                await conn.execute(
                    """
                    UPDATE current_odds
                    SET odd1 = $5, odd2 = $6, odd3 = $7, updated_at = NOW()
                    WHERE match_id = $1 AND bookmaker_id = $2
                      AND bet_type_id = $3 AND margin = $4
                    """,
                    match_id, bookmaker_id, bet_type_id, margin,
                    odd1, odd2, odd3
                )
            else:
                # Insert new odds
                await conn.execute(
                    """
                    INSERT INTO current_odds (
                        match_id, bookmaker_id, bet_type_id, margin,
                        odd1, odd2, odd3
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    match_id, bookmaker_id, bet_type_id, margin,
                    odd1, odd2, odd3
                )

            return True  # Odds changed or new

    async def record_odds_history(
        self,
        match_id: int,
        bookmaker_id: int,
        bet_type_id: int,
        odd1: float,
        odd2: float,
        odd3: Optional[float] = None,
        margin: float = 0
    ) -> None:
        """Record odds snapshot for historical tracking."""
        if not settings.enable_odds_history:
            return

        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO odds_history (
                    match_id, bookmaker_id, bet_type_id, margin,
                    odd1, odd2, odd3
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                match_id, bookmaker_id, bet_type_id, margin,
                odd1, odd2, odd3
            )

    async def get_current_odds_for_match(
        self,
        match_id: int
    ) -> List[Dict[str, Any]]:
        """Get all current odds for a match."""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT co.*, b.name as bookmaker_name, b.display_name,
                       bt.name as bet_type_name
                FROM current_odds co
                JOIN bookmakers b ON co.bookmaker_id = b.id
                JOIN bet_types bt ON co.bet_type_id = bt.id
                WHERE co.match_id = $1
                ORDER BY bt.id, co.margin, b.name
                """,
                match_id
            )
            return [dict(row) for row in rows]

    async def get_odds_history(
        self,
        match_id: int,
        bookmaker_id: Optional[int] = None,
        bet_type_id: Optional[int] = None,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get historical odds for a match."""
        async with self.acquire() as conn:
            since = datetime.utcnow() - timedelta(hours=hours)

            query = """
                SELECT oh.*, b.name as bookmaker_name, bt.name as bet_type_name
                FROM odds_history oh
                JOIN bookmakers b ON oh.bookmaker_id = b.id
                JOIN bet_types bt ON oh.bet_type_id = bt.id
                WHERE oh.match_id = $1 AND oh.recorded_at >= $2
            """
            params = [match_id, since]

            if bookmaker_id:
                query += " AND oh.bookmaker_id = $3"
                params.append(bookmaker_id)

            if bet_type_id:
                query += f" AND oh.bet_type_id = ${len(params) + 1}"
                params.append(bet_type_id)

            query += " ORDER BY oh.recorded_at DESC"

            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    # ==========================================
    # ARBITRAGE OPERATIONS
    # ==========================================

    async def check_arbitrage_exists(self, arb_hash: str) -> bool:
        """Check if arbitrage opportunity was already detected."""
        async with self.acquire() as conn:
            since = datetime.utcnow() - timedelta(hours=settings.arbitrage_dedup_hours)
            exists = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM arbitrage_opportunities
                    WHERE arb_hash = $1 AND detected_at >= $2
                )
                """,
                arb_hash, since
            )
            return exists

    async def insert_arbitrage(
        self,
        match_id: int,
        bet_type_id: int,
        margin: float,
        profit_percentage: float,
        best_odds: List[Dict],
        stakes: List[float],
        arb_hash: str,
        expires_at: Optional[datetime] = None
    ) -> Optional[int]:
        """Insert new arbitrage opportunity. Returns ID or None if duplicate."""
        # Check for duplicate first
        if await self.check_arbitrage_exists(arb_hash):
            return None

        async with self.acquire() as conn:
            try:
                arb_id = await conn.fetchval(
                    """
                    INSERT INTO arbitrage_opportunities (
                        match_id, bet_type_id, margin, profit_percentage,
                        best_odds, stakes, arb_hash, expires_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id
                    """,
                    match_id, bet_type_id, margin, profit_percentage,
                    best_odds, stakes, arb_hash, expires_at
                )
                return arb_id
            except asyncpg.UniqueViolationError:
                # Race condition - duplicate
                return None

    async def get_active_arbitrage(
        self,
        min_profit: Optional[float] = None,
        sport_id: Optional[int] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get active arbitrage opportunities."""
        async with self.acquire() as conn:
            query = """
                SELECT ao.*, m.team1, m.team2, m.start_time,
                       s.name as sport_name, bt.name as bet_type_name
                FROM arbitrage_opportunities ao
                JOIN matches m ON ao.match_id = m.id
                JOIN sports s ON m.sport_id = s.id
                JOIN bet_types bt ON ao.bet_type_id = bt.id
                WHERE ao.is_active = true
            """
            params = []

            if min_profit:
                params.append(min_profit)
                query += f" AND ao.profit_percentage >= ${len(params)}"

            if sport_id:
                params.append(sport_id)
                query += f" AND m.sport_id = ${len(params)}"

            query += " ORDER BY ao.profit_percentage DESC"
            params.append(limit)
            query += f" LIMIT ${len(params)}"

            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def mark_arbitrage_notified(self, arb_id: int) -> None:
        """Mark arbitrage as notified."""
        async with self.acquire() as conn:
            await conn.execute(
                """
                UPDATE arbitrage_opportunities
                SET notified_at = NOW()
                WHERE id = $1
                """,
                arb_id
            )

    async def deactivate_expired_arbitrage(self) -> int:
        """Deactivate arbitrage opportunities where match has started."""
        async with self.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE arbitrage_opportunities ao
                SET is_active = false
                FROM matches m
                WHERE ao.match_id = m.id
                  AND ao.is_active = true
                  AND m.start_time < NOW()
                """
            )
            # Parse affected rows from result
            count = int(result.split()[-1]) if result else 0
            return count

    # ==========================================
    # LEAGUE OPERATIONS
    # ==========================================

    async def upsert_league(
        self,
        name: str,
        sport_id: int,
        country: Optional[str] = None,
        external_id: Optional[Tuple[int, str]] = None
    ) -> int:
        """Insert or update a league, returning the league ID."""
        async with self.acquire() as conn:
            # Normalize league name
            name_normalized = name.lower().strip()

            existing = await conn.fetchrow(
                """
                SELECT id, external_ids FROM leagues
                WHERE name_normalized = $1 AND sport_id = $2
                """,
                name_normalized, sport_id
            )

            if existing:
                league_id = existing['id']
                if external_id:
                    bookmaker_id, ext_id = external_id
                    current_ids = existing.get('external_ids') or {}
                    current_ids[str(bookmaker_id)] = ext_id
                    await conn.execute(
                        """
                        UPDATE leagues SET external_ids = $1 WHERE id = $2
                        """,
                        current_ids, league_id
                    )
                return league_id
            else:
                external_ids = {}
                if external_id:
                    bookmaker_id, ext_id = external_id
                    external_ids[str(bookmaker_id)] = ext_id

                league_id = await conn.fetchval(
                    """
                    INSERT INTO leagues (name, name_normalized, sport_id, country, external_ids)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                    """,
                    name, name_normalized, sport_id, country, external_ids
                )
                return league_id

    # ==========================================
    # UTILITY OPERATIONS
    # ==========================================

    async def cleanup_old_data(self, days_to_keep: int = 7) -> Dict[str, int]:
        """Clean up old data from database."""
        async with self.acquire() as conn:
            cutoff = datetime.utcnow() - timedelta(days=days_to_keep)

            # Delete old odds history
            result1 = await conn.execute(
                "DELETE FROM odds_history WHERE recorded_at < $1",
                cutoff
            )
            odds_deleted = int(result1.split()[-1]) if result1 else 0

            # Deactivate old arbitrage
            result2 = await conn.execute(
                """
                UPDATE arbitrage_opportunities
                SET is_active = false
                WHERE detected_at < $1 AND is_active = true
                """,
                cutoff
            )
            arb_deactivated = int(result2.split()[-1]) if result2 else 0

            # Mark old matches as finished
            result3 = await conn.execute(
                """
                UPDATE matches
                SET status = 'finished'
                WHERE start_time < NOW() - INTERVAL '4 hours'
                AND status = 'upcoming'
                """
            )
            matches_updated = int(result3.split()[-1]) if result3 else 0

            return {
                "odds_deleted": odds_deleted,
                "arbitrage_deactivated": arb_deactivated,
                "matches_updated": matches_updated
            }

    async def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        async with self.acquire() as conn:
            stats = {}

            stats['total_matches'] = await conn.fetchval(
                "SELECT COUNT(*) FROM matches WHERE status = 'upcoming'"
            )
            stats['total_odds'] = await conn.fetchval(
                "SELECT COUNT(*) FROM current_odds"
            )
            stats['active_arbitrage'] = await conn.fetchval(
                "SELECT COUNT(*) FROM arbitrage_opportunities WHERE is_active = true"
            )
            stats['bookmakers_with_odds'] = await conn.fetchval(
                "SELECT COUNT(DISTINCT bookmaker_id) FROM current_odds"
            )

            return stats


# Global database instance
db = Database()
