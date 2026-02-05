"""
Database connection and operations for BetSnipe.ai v2.0

Uses asyncpg for async PostgreSQL operations with connection pooling.
"""

import asyncio
import json
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware (UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Assume naive datetime is UTC
        return dt.replace(tzinfo=timezone.utc)
    return dt

import asyncpg
from asyncpg import Pool, Connection

from .config import settings


async def _init_connection(conn: Connection) -> None:
    """Initialize connection with JSON codec for JSONB columns."""
    await conn.set_type_codec(
        'jsonb',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog'
    )
    await conn.set_type_codec(
        'json',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog'
    )

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
                min_size=5,
                max_size=50,
                command_timeout=60,
                statement_cache_size=100,
                init=_init_connection,
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
    # BULK OPERATIONS (for fast scraper processing)
    # ==========================================

    async def bulk_upsert_matches_and_odds(
        self,
        matches_data: List[Dict],
        bookmaker_id: int
    ) -> int:
        """
        Bulk upsert matches and odds using efficient batch operations.
        Uses ON CONFLICT with unique constraint for maximum speed.

        Args:
            matches_data: List of dicts with match and odds data
            bookmaker_id: The bookmaker ID

        Returns:
            Number of matches processed
        """
        if not matches_data:
            return 0

        # Deduplicate matches - some scrapers return duplicates
        seen = {}
        unique_matches = []
        for m in matches_data:
            key = (m['team1_normalized'], m['team2_normalized'], m['sport_id'],
                   ensure_utc(m['start_time']).isoformat())
            if key not in seen:
                seen[key] = len(unique_matches)
                unique_matches.append(m)
            else:
                # Merge odds from duplicate into existing match
                existing_idx = seen[key]
                unique_matches[existing_idx]['odds'].extend(m.get('odds', []))

        async with self.acquire() as conn:
            processed = 0

            # Process in chunks
            chunk_size = 500
            for i in range(0, len(unique_matches), chunk_size):
                chunk = unique_matches[i:i + chunk_size]

                # Step 1: Bulk upsert all matches using ON CONFLICT
                # Build arrays for unnest
                t1 = [m['team1'] for m in chunk]
                t2 = [m['team2'] for m in chunk]
                t1n = [m['team1_normalized'] for m in chunk]
                t2n = [m['team2_normalized'] for m in chunk]
                sids = [m['sport_id'] for m in chunk]
                times = [ensure_utc(m['start_time']) for m in chunk]
                ext_ids = [
                    {str(bookmaker_id): m['external_id']} if m.get('external_id') else {}
                    for m in chunk
                ]

                # Bulk insert/update matches and get all IDs back
                match_rows = await conn.fetch("""
                    INSERT INTO matches (team1, team2, team1_normalized, team2_normalized,
                                        sport_id, start_time, external_ids, metadata)
                    SELECT
                        unnest($1::text[]), unnest($2::text[]),
                        unnest($3::text[]), unnest($4::text[]),
                        unnest($5::int[]), unnest($6::timestamptz[]),
                        unnest($7::jsonb[]), '{}'::jsonb
                    ON CONFLICT (team1_normalized, team2_normalized, sport_id, start_time)
                    DO UPDATE SET
                        updated_at = NOW(),
                        external_ids = matches.external_ids || EXCLUDED.external_ids
                    RETURNING id, team1_normalized, team2_normalized, sport_id, start_time
                """, t1, t2, t1n, t2n, sids, times, ext_ids)

                # Build lookup from returned rows
                match_id_lookup = {}
                for row in match_rows:
                    key = (row['team1_normalized'], row['team2_normalized'],
                           row['sport_id'], row['start_time'])
                    match_id_lookup[key] = row['id']

                # Step 2: Collect all odds with their match IDs (deduplicated)
                odds_data = []
                odds_seen = set()
                for m in chunk:
                    key = (m['team1_normalized'], m['team2_normalized'],
                           m['sport_id'], ensure_utc(m['start_time']))
                    match_id = match_id_lookup.get(key)

                    if not match_id:
                        continue

                    processed += 1
                    for odds in m.get('odds', []):
                        margin = round(odds.get('margin', 0.0), 2)
                        odds_key = (match_id, odds['bet_type_id'], margin)
                        if odds_key in odds_seen:
                            continue  # Skip duplicate odds
                        odds_seen.add(odds_key)
                        odds_data.append((
                            match_id, odds['bet_type_id'],
                            odds['odd1'], odds['odd2'], odds.get('odd3'),
                            margin
                        ))

                # Step 3: Bulk upsert all odds
                if odds_data:
                    await conn.execute("""
                        INSERT INTO current_odds (match_id, bookmaker_id, bet_type_id, odd1, odd2, odd3, margin)
                        SELECT
                            unnest($1::int[]), $2,
                            unnest($3::int[]),
                            unnest($4::numeric[]), unnest($5::numeric[]), unnest($6::numeric[]),
                            unnest($7::numeric[])
                        ON CONFLICT (match_id, bookmaker_id, bet_type_id, margin)
                        DO UPDATE SET
                            odd1 = EXCLUDED.odd1,
                            odd2 = EXCLUDED.odd2,
                            odd3 = EXCLUDED.odd3,
                            updated_at = NOW()
                    """,
                        [o[0] for o in odds_data], bookmaker_id,
                        [o[1] for o in odds_data],
                        [o[2] for o in odds_data], [o[3] for o in odds_data], [o[4] for o in odds_data],
                        [o[5] for o in odds_data]
                    )

            return processed

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
            # Ensure timezone-aware datetime
            start_time_utc = ensure_utc(start_time)
            # Search within time window
            time_start = start_time_utc - timedelta(minutes=time_window_minutes)
            time_end = start_time_utc + timedelta(minutes=time_window_minutes)

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
            # Ensure timezone-aware datetime
            start_time_utc = ensure_utc(start_time)
            time_start = start_time_utc - timedelta(minutes=time_window_minutes)
            time_end = start_time_utc + timedelta(minutes=time_window_minutes)

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
        # Ensure timezone-aware datetime
        start_time = ensure_utc(start_time)
        time_window_minutes = 120
        time_start = start_time - timedelta(minutes=time_window_minutes)
        time_end = start_time + timedelta(minutes=time_window_minutes)

        async with self.acquire() as conn:
            # Check for existing match first (inline query to avoid nested connection)
            existing = await conn.fetchrow(
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

            if existing:
                match_id = existing['id']
                # Update external_ids if provided
                if external_id:
                    bookmaker_id, ext_id = external_id
                    current_ids = existing['external_ids'] or {}
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
            now = datetime.now(timezone.utc)
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
            since = datetime.now(timezone.utc) - timedelta(hours=hours)

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
            since = datetime.now(timezone.utc) - timedelta(hours=settings.arbitrage_dedup_hours)
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
            cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

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

    async def get_match(self, match_id: int) -> Optional[Dict[str, Any]]:
        """Get a match by ID with sport name."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT m.*, s.name as sport_name
                FROM matches m
                JOIN sports s ON m.sport_id = s.id
                WHERE m.id = $1
                """,
                match_id
            )
            return dict(row) if row else None

    async def get_arbitrage(self, arbitrage_id: int) -> Optional[Dict[str, Any]]:
        """Get an arbitrage opportunity by ID."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT ao.*, m.team1, m.team2, m.start_time,
                       s.name as sport_name, bt.name as bet_type_name
                FROM arbitrage_opportunities ao
                JOIN matches m ON ao.match_id = m.id
                JOIN sports s ON m.sport_id = s.id
                JOIN bet_types bt ON ao.bet_type_id = bt.id
                WHERE ao.id = $1
                """,
                arbitrage_id
            )
            return dict(row) if row else None

    # ==========================================
    # USER PREFERENCES OPERATIONS
    # ==========================================

    async def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user preferences by user ID (UUID string)."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM user_preferences WHERE user_id = $1::uuid
                """,
                user_id
            )
            return dict(row) if row else None

    async def create_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Create default user preferences."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO user_preferences (user_id)
                VALUES ($1::uuid)
                ON CONFLICT (user_id) DO NOTHING
                RETURNING *
                """,
                user_id
            )
            if row:
                return dict(row)
            # If already exists, fetch it
            return await self.get_user_preferences(user_id)

    async def update_user_preferences(
        self,
        user_id: str,
        min_profit_percentage: Optional[float] = None,
        sports: Optional[List[int]] = None,
        bookmakers: Optional[List[int]] = None,
        notification_settings: Optional[Dict] = None,
        display_settings: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """Update user preferences."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE user_preferences
                SET
                    min_profit_percentage = COALESCE($2, min_profit_percentage),
                    sports = COALESCE($3, sports),
                    bookmakers = COALESCE($4, bookmakers),
                    notification_settings = COALESCE($5, notification_settings),
                    display_settings = COALESCE($6, display_settings),
                    updated_at = NOW()
                WHERE user_id = $1::uuid
                RETURNING *
                """,
                user_id, min_profit_percentage, sports, bookmakers,
                notification_settings, display_settings
            )
            return dict(row) if row else None

    # ==========================================
    # USER DEVICE OPERATIONS
    # ==========================================

    async def register_user_device(
        self,
        user_id: str,
        expo_push_token: str,
        platform: str,
        device_id: Optional[str] = None,
        device_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Register or update a user device for push notifications."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO user_devices (user_id, expo_push_token, platform, device_id, device_name)
                VALUES ($1::uuid, $2, $3, $4, $5)
                ON CONFLICT (user_id, expo_push_token)
                DO UPDATE SET
                    platform = EXCLUDED.platform,
                    device_id = COALESCE(EXCLUDED.device_id, user_devices.device_id),
                    device_name = COALESCE(EXCLUDED.device_name, user_devices.device_name),
                    is_active = true,
                    last_used_at = NOW()
                RETURNING *
                """,
                user_id, expo_push_token, platform, device_id, device_name
            )
            return dict(row) if row else None

    async def get_user_devices(self, user_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all devices for a user."""
        async with self.acquire() as conn:
            if active_only:
                rows = await conn.fetch(
                    """
                    SELECT * FROM user_devices
                    WHERE user_id = $1::uuid AND is_active = true
                    ORDER BY last_used_at DESC
                    """,
                    user_id
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM user_devices
                    WHERE user_id = $1::uuid
                    ORDER BY last_used_at DESC
                    """,
                    user_id
                )
            return [dict(row) for row in rows]

    async def get_user_device(self, user_id: str, device_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific device for a user."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM user_devices
                WHERE user_id = $1::uuid AND id = $2
                """,
                user_id, device_id
            )
            return dict(row) if row else None

    async def deactivate_user_device(self, user_id: str, device_id: int) -> bool:
        """Deactivate a user device."""
        async with self.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE user_devices
                SET is_active = false
                WHERE user_id = $1::uuid AND id = $2 AND is_active = true
                """,
                user_id, device_id
            )
            return "UPDATE 1" in result

    async def get_user_device_count(self, user_id: str) -> int:
        """Get count of active devices for a user."""
        async with self.acquire() as conn:
            return await conn.fetchval(
                """
                SELECT COUNT(*) FROM user_devices
                WHERE user_id = $1::uuid AND is_active = true
                """,
                user_id
            ) or 0

    # ==========================================
    # USER WATCHLIST OPERATIONS
    # ==========================================

    async def get_user_watchlist(
        self,
        user_id: str,
        sport_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get user's watchlist with match details."""
        async with self.acquire() as conn:
            query = """
                SELECT
                    uw.id, uw.user_id, uw.match_id, uw.notify_on_odds_change,
                    uw.odds_change_threshold, uw.notes, uw.created_at,
                    m.team1, m.team2, m.start_time, m.status as match_status,
                    s.name as sport_name, s.id as sport_id,
                    l.name as league_name
                FROM user_watchlist uw
                JOIN matches m ON uw.match_id = m.id
                JOIN sports s ON m.sport_id = s.id
                LEFT JOIN leagues l ON m.league_id = l.id
                WHERE uw.user_id = $1::uuid
            """
            params = [user_id]

            if sport_id:
                params.append(sport_id)
                query += f" AND m.sport_id = ${len(params)}"

            if status:
                params.append(status)
                query += f" AND m.status = ${len(params)}"

            query += " ORDER BY m.start_time"

            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def get_user_watchlist_count(self, user_id: str) -> int:
        """Get count of items in user's watchlist."""
        async with self.acquire() as conn:
            return await conn.fetchval(
                """
                SELECT COUNT(*) FROM user_watchlist
                WHERE user_id = $1::uuid
                """,
                user_id
            ) or 0

    async def add_to_watchlist(
        self,
        user_id: str,
        match_id: int,
        notify_on_odds_change: bool = True,
        odds_change_threshold: float = 0.05,
        notes: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Add a match to user's watchlist."""
        async with self.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO user_watchlist (
                        user_id, match_id, notify_on_odds_change,
                        odds_change_threshold, notes
                    ) VALUES ($1::uuid, $2, $3, $4, $5)
                    RETURNING *
                    """,
                    user_id, match_id, notify_on_odds_change,
                    odds_change_threshold, notes
                )
                if row:
                    # Fetch with match details
                    return await self._get_watchlist_item_with_details(
                        conn, user_id, match_id
                    )
                return None
            except asyncpg.UniqueViolationError:
                return None  # Already in watchlist

    async def _get_watchlist_item_with_details(
        self,
        conn: Connection,
        user_id: str,
        match_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get watchlist item with match details."""
        row = await conn.fetchrow(
            """
            SELECT
                uw.id, uw.user_id, uw.match_id, uw.notify_on_odds_change,
                uw.odds_change_threshold, uw.notes, uw.created_at,
                m.team1, m.team2, m.start_time, m.status as match_status,
                s.name as sport_name, s.id as sport_id,
                l.name as league_name
            FROM user_watchlist uw
            JOIN matches m ON uw.match_id = m.id
            JOIN sports s ON m.sport_id = s.id
            LEFT JOIN leagues l ON m.league_id = l.id
            WHERE uw.user_id = $1::uuid AND uw.match_id = $2
            """,
            user_id, match_id
        )
        return dict(row) if row else None

    async def remove_from_watchlist(self, user_id: str, match_id: int) -> bool:
        """Remove a match from user's watchlist."""
        async with self.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM user_watchlist
                WHERE user_id = $1::uuid AND match_id = $2
                """,
                user_id, match_id
            )
            return "DELETE 1" in result

    async def update_watchlist_item(
        self,
        user_id: str,
        match_id: int,
        notify_on_odds_change: Optional[bool] = None,
        odds_change_threshold: Optional[float] = None,
        notes: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Update watchlist item settings."""
        async with self.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE user_watchlist
                SET
                    notify_on_odds_change = COALESCE($3, notify_on_odds_change),
                    odds_change_threshold = COALESCE($4, odds_change_threshold),
                    notes = COALESCE($5, notes)
                WHERE user_id = $1::uuid AND match_id = $2
                """,
                user_id, match_id, notify_on_odds_change, odds_change_threshold, notes
            )
            if "UPDATE 1" in result:
                return await self._get_watchlist_item_with_details(
                    conn, user_id, match_id
                )
            return None

    # ==========================================
    # USER ARBITRAGE HISTORY OPERATIONS
    # ==========================================

    async def get_user_arbitrage_history(
        self,
        user_id: str,
        action: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get user's arbitrage interaction history."""
        async with self.acquire() as conn:
            query = """
                SELECT
                    uah.id, uah.arbitrage_id, uah.match_id, uah.action,
                    uah.profit_percentage, uah.best_odds, uah.notes, uah.created_at,
                    m.team1, m.team2, s.name as sport_name
                FROM user_arbitrage_history uah
                LEFT JOIN matches m ON uah.match_id = m.id
                LEFT JOIN sports s ON m.sport_id = s.id
                WHERE uah.user_id = $1::uuid
            """
            params = [user_id]

            if action:
                params.append(action)
                query += f" AND uah.action = ${len(params)}"

            query += " ORDER BY uah.created_at DESC"
            params.extend([limit, offset])
            query += f" LIMIT ${len(params)-1} OFFSET ${len(params)}"

            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def record_arbitrage_action(
        self,
        user_id: str,
        arbitrage_id: int,
        match_id: int,
        action: str,
        profit_percentage: Optional[float] = None,
        best_odds: Optional[Dict] = None,
        notes: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Record user's interaction with an arbitrage opportunity."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO user_arbitrage_history (
                    user_id, arbitrage_id, match_id, action,
                    profit_percentage, best_odds, notes
                ) VALUES ($1::uuid, $2, $3, $4, $5, $6, $7)
                RETURNING *
                """,
                user_id, arbitrage_id, match_id, action,
                profit_percentage, best_odds, notes
            )
            return dict(row) if row else None

    async def get_user_arbitrage_stats(self, user_id: str) -> Dict[str, Any]:
        """Get statistics about user's arbitrage interactions."""
        async with self.acquire() as conn:
            stats = {}

            # Counts by action
            rows = await conn.fetch(
                """
                SELECT action, COUNT(*) as count
                FROM user_arbitrage_history
                WHERE user_id = $1::uuid
                GROUP BY action
                """,
                user_id
            )
            stats['by_action'] = {row['action']: row['count'] for row in rows}

            # Total count
            stats['total'] = await conn.fetchval(
                """
                SELECT COUNT(*) FROM user_arbitrage_history
                WHERE user_id = $1::uuid
                """,
                user_id
            ) or 0

            # Average profit of viewed opportunities
            stats['avg_profit_viewed'] = await conn.fetchval(
                """
                SELECT AVG(profit_percentage)
                FROM user_arbitrage_history
                WHERE user_id = $1::uuid AND profit_percentage IS NOT NULL
                """,
                user_id
            ) or 0

            # Count from last 7 days
            stats['last_7_days'] = await conn.fetchval(
                """
                SELECT COUNT(*) FROM user_arbitrage_history
                WHERE user_id = $1::uuid
                AND created_at >= NOW() - INTERVAL '7 days'
                """,
                user_id
            ) or 0

            return stats

    # ==========================================
    # SEARCH OPERATIONS
    # ==========================================

    async def search_matches(
        self,
        query: str,
        sport_id: Optional[int] = None,
        status: str = 'upcoming',
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Full-text search for matches."""
        async with self.acquire() as conn:
            # Use plainto_tsquery for simpler search
            sql = """
                SELECT m.*, s.name as sport_name,
                       ts_rank(m.search_vector, plainto_tsquery('simple', $1)) as rank
                FROM matches m
                JOIN sports s ON m.sport_id = s.id
                WHERE m.search_vector @@ plainto_tsquery('simple', $1)
                  AND m.status = $2
            """
            params = [query, status]

            if sport_id:
                params.append(sport_id)
                sql += f" AND m.sport_id = ${len(params)}"

            sql += " ORDER BY rank DESC, m.start_time"
            params.append(limit)
            sql += f" LIMIT ${len(params)}"

            rows = await conn.fetch(sql, *params)
            return [dict(row) for row in rows]

    async def get_odds_trends(
        self,
        match_id: int,
        bet_type_id: int = 2,  # Default to 1X2
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get odds movement analysis for a match."""
        async with self.acquire() as conn:
            since = datetime.now(timezone.utc) - timedelta(hours=hours)

            # Get history grouped by bookmaker
            rows = await conn.fetch(
                """
                SELECT
                    b.name as bookmaker_name,
                    oh.odd1, oh.odd2, oh.odd3,
                    oh.recorded_at
                FROM odds_history oh
                JOIN bookmakers b ON oh.bookmaker_id = b.id
                WHERE oh.match_id = $1
                  AND oh.bet_type_id = $2
                  AND oh.recorded_at >= $3
                ORDER BY oh.recorded_at
                """,
                match_id, bet_type_id, since
            )

            # Group by bookmaker
            by_bookmaker = {}
            for row in rows:
                bm = row['bookmaker_name']
                if bm not in by_bookmaker:
                    by_bookmaker[bm] = []
                by_bookmaker[bm].append({
                    'odd1': float(row['odd1']) if row['odd1'] else None,
                    'odd2': float(row['odd2']) if row['odd2'] else None,
                    'odd3': float(row['odd3']) if row['odd3'] else None,
                    'timestamp': row['recorded_at'].isoformat()
                })

            # Calculate movement stats
            movement = {}
            for bm, history in by_bookmaker.items():
                if len(history) >= 2:
                    first = history[0]
                    last = history[-1]
                    movement[bm] = {
                        'odd1_change': (last['odd1'] - first['odd1']) if first['odd1'] and last['odd1'] else None,
                        'odd2_change': (last['odd2'] - first['odd2']) if first['odd2'] and last['odd2'] else None,
                        'odd3_change': (last['odd3'] - first['odd3']) if first['odd3'] and last['odd3'] else None,
                        'data_points': len(history)
                    }

            return {
                'match_id': match_id,
                'bet_type_id': bet_type_id,
                'hours': hours,
                'history': by_bookmaker,
                'movement': movement
            }

    # ==========================================
    # PUSH NOTIFICATION HELPERS
    # ==========================================

    async def get_arbitrage_notification_recipients(
        self,
        profit_percentage: float,
        sport_id: int
    ) -> List[Dict[str, Any]]:
        """Get users who should receive arbitrage notifications."""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT
                    up.user_id,
                    ud.expo_push_token,
                    up.min_profit_percentage
                FROM user_preferences up
                JOIN user_devices ud ON ud.user_id = up.user_id
                WHERE ud.is_active = true
                AND up.min_profit_percentage <= $1
                AND $2 = ANY(up.sports)
                AND (up.notification_settings->>'arbitrage_alerts')::boolean = true
                """,
                profit_percentage, sport_id
            )
            return [dict(row) for row in rows]

    async def get_watchlist_notification_recipients(
        self,
        match_id: int,
        odds_change: float = 0
    ) -> List[Dict[str, Any]]:
        """Get users watching a match who should be notified."""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT
                    uw.user_id,
                    ud.expo_push_token,
                    uw.notify_on_odds_change,
                    uw.odds_change_threshold
                FROM user_watchlist uw
                JOIN user_devices ud ON ud.user_id = uw.user_id
                JOIN user_preferences up ON up.user_id = uw.user_id
                WHERE uw.match_id = $1
                AND ud.is_active = true
                AND uw.notify_on_odds_change = true
                AND ABS($2) >= uw.odds_change_threshold
                AND (up.notification_settings->>'watchlist_odds_change')::boolean = true
                """,
                match_id, odds_change
            )
            return [dict(row) for row in rows]

    async def log_push_notification(
        self,
        user_id: str,
        device_id: Optional[int],
        notification_type: str,
        title: str,
        body: str,
        data: Optional[Dict] = None,
        status: str = 'pending',
        expo_receipt_id: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> int:
        """Log a push notification."""
        async with self.acquire() as conn:
            return await conn.fetchval(
                """
                INSERT INTO push_notifications (
                    user_id, device_id, notification_type, title, body,
                    data, status, expo_receipt_id, error_message,
                    sent_at
                ) VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                RETURNING id
                """,
                user_id, device_id, notification_type, title, body,
                data, status, expo_receipt_id, error_message
            )


# Global database instance
db = Database()
