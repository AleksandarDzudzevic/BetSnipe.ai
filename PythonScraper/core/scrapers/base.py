"""
Base scraper class for BetSnipe.ai v2.0

All bookmaker scrapers inherit from this base class.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
import aiohttp
from aiohttp import ClientTimeout, ClientSession

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class ScrapedOdds:
    """Represents odds scraped from a bookmaker."""
    bet_type_id: int
    odd1: float
    odd2: Optional[float] = None
    odd3: Optional[float] = None
    margin: float = 0.0
    selection: str = ''  # outcome identifier for multi-outcome markets

    def to_tuple(self) -> Tuple:
        return (self.bet_type_id, self.margin, self.odd1, self.odd2, self.odd3, self.selection)


@dataclass
class ScrapedMatch:
    """Represents a match with odds scraped from a bookmaker."""
    team1: str
    team2: str
    sport_id: int
    start_time: datetime
    odds: List[ScrapedOdds] = field(default_factory=list)
    league_name: Optional[str] = None
    external_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_odds(self, bet_type_id: int, odd1: float, odd2: Optional[float] = None,
                 odd3: Optional[float] = None, margin: float = 0.0,
                 selection: str = '') -> None:
        """Add odds to this match."""
        self.odds.append(ScrapedOdds(
            bet_type_id=bet_type_id,
            odd1=odd1,
            odd2=odd2,
            odd3=odd3,
            margin=margin,
            selection=selection
        ))


class BaseScraper(ABC):
    """
    Abstract base class for all bookmaker scrapers.

    Subclasses must implement:
    - scrape_sport(sport_id) - Scrape all matches for a sport
    - get_supported_sports() - Return list of supported sport IDs

    Optional overrides:
    - get_headers() - Custom HTTP headers
    - get_base_url() - API base URL
    """

    def __init__(self, bookmaker_id: int, bookmaker_name: str):
        self.bookmaker_id = bookmaker_id
        self.bookmaker_name = bookmaker_name
        self._session: Optional[ClientSession] = None
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
        self._request_count = 0
        self._error_count = 0
        self._last_scrape: Optional[datetime] = None

    @property
    def session(self) -> ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=settings.request_timeout_seconds)
            self._session = ClientSession(
                timeout=timeout,
                headers=self.get_headers()
            )
        return self._session

    async def reset_session(self) -> None:
        """Reset the session for error recovery (close and null so it's lazily recreated)."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for requests. Override for custom headers."""
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9,sr;q=0.8',
        }

    @abstractmethod
    def get_base_url(self) -> str:
        """Return the API base URL for this bookmaker."""
        pass

    @abstractmethod
    def get_supported_sports(self) -> List[int]:
        """Return list of sport IDs this scraper supports."""
        pass

    @abstractmethod
    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]:
        """
        Scrape all matches for a given sport.

        Args:
            sport_id: The sport ID to scrape

        Returns:
            List of ScrapedMatch objects with odds
        """
        pass

    async def scrape_all(self) -> List[ScrapedMatch]:
        """Scrape all supported sports concurrently."""
        all_matches = []
        sports = self.get_supported_sports()

        logger.info(f"[{self.bookmaker_name}] Scraping {len(sports)} sports")

        tasks = [self.scrape_sport(sport_id) for sport_id in sports]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sport_id, result in zip(sports, results):
            if isinstance(result, Exception):
                logger.error(f"[{self.bookmaker_name}] Error scraping sport {sport_id}: {result}")
                self._error_count += 1
            else:
                all_matches.extend(result)
                logger.debug(f"[{self.bookmaker_name}] Sport {sport_id}: {len(result)} matches")

        self._last_scrape = datetime.now(timezone.utc)
        logger.info(f"[{self.bookmaker_name}] Total: {len(all_matches)} matches")

        return all_matches

    async def fetch_json(
        self,
        url: str,
        method: str = 'GET',
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        headers: Optional[Dict] = None
    ) -> Optional[Any]:
        """
        Fetch JSON from URL with rate limiting and error handling.

        Args:
            url: The URL to fetch
            method: HTTP method (GET, POST)
            params: Query parameters
            json_data: JSON body for POST requests
            headers: Additional headers

        Returns:
            Parsed JSON or None on error
        """
        async with self._semaphore:
            self._request_count += 1

            try:
                request_headers = self.get_headers()
                if headers:
                    request_headers.update(headers)

                if method.upper() == 'GET':
                    async with self.session.get(
                        url, params=params, headers=request_headers
                    ) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            logger.warning(
                                f"[{self.bookmaker_name}] HTTP {response.status} for {url}"
                            )
                            return None
                else:  # POST
                    async with self.session.post(
                        url, params=params, json=json_data, headers=request_headers
                    ) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            logger.warning(
                                f"[{self.bookmaker_name}] HTTP {response.status} for {url}"
                            )
                            return None

            except asyncio.TimeoutError:
                logger.warning(f"[{self.bookmaker_name}] Timeout for {url}")
                self._error_count += 1
                return None
            except aiohttp.ClientError as e:
                logger.warning(f"[{self.bookmaker_name}] Client error for {url}: {e}")
                self._error_count += 1
                return None
            except Exception as e:
                logger.error(f"[{self.bookmaker_name}] Unexpected error for {url}: {e}")
                self._error_count += 1
                return None

    def parse_teams(self, match_name: str, separator: str = ' - ') -> Tuple[str, str]:
        """Parse team names from match name string."""
        parts = match_name.split(separator, 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        # Fallback: try other separators
        for sep in [' vs ', ' v ', ' @ ', '-']:
            if sep in match_name:
                parts = match_name.split(sep, 1)
                if len(parts) == 2:
                    return parts[0].strip(), parts[1].strip()
        # Last resort: return as-is
        return match_name.strip(), ""

    def parse_timestamp(self, timestamp: Any) -> Optional[datetime]:
        """Parse various timestamp formats to datetime (returns UTC-aware datetime)."""
        result = None
        if isinstance(timestamp, datetime):
            result = timestamp
        elif isinstance(timestamp, (int, float)):
            # Unix timestamp (seconds or milliseconds)
            if timestamp > 1e12:  # Milliseconds
                result = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
            else:
                result = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        elif isinstance(timestamp, str):
            # Remove trailing 'Z' for UTC
            timestamp = timestamp.rstrip('Z')
            # Try common formats
            for fmt in [
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%S.%f',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M',
            ]:
                try:
                    result = datetime.strptime(timestamp, fmt)
                    break
                except ValueError:
                    continue

        # Ensure result is timezone-aware (UTC)
        if result and result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result

    def get_stats(self) -> Dict[str, Any]:
        """Get scraper statistics."""
        return {
            'bookmaker_id': self.bookmaker_id,
            'bookmaker_name': self.bookmaker_name,
            'request_count': self._request_count,
            'error_count': self._error_count,
            'last_scrape': self._last_scrape.isoformat() if self._last_scrape else None,
            'supported_sports': self.get_supported_sports(),
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(bookmaker={self.bookmaker_name})>"
