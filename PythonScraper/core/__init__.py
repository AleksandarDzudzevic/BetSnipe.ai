"""
BetSnipe.ai v2.0 Core Module

Real-time odds scraping, matching, and arbitrage detection.
"""

from .config import settings
from .db import Database
from .scraper_engine import ScraperEngine
from .matching import MatchMatcher
from .arbitrage import ArbitrageDetector

__all__ = [
    'settings',
    'Database',
    'ScraperEngine',
    'MatchMatcher',
    'ArbitrageDetector',
]

__version__ = '2.0.0'
