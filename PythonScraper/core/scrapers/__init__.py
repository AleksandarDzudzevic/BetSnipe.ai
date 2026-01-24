"""
BetSnipe.ai v2.0 Scrapers Module

Contains all bookmaker-specific scraper implementations.
"""

from .base import BaseScraper, ScrapedOdds, ScrapedMatch
from .admiral import AdmiralScraper
from .soccerbet import SoccerbetScraper
from .mozzart import MozzartScraper
from .meridian import MeridianScraper
from .maxbet import MaxbetScraper
from .superbet import SuperbetScraper
from .merkur import MerkurScraper
from .topbet import TopbetScraper

__all__ = [
    'BaseScraper',
    'ScrapedOdds',
    'ScrapedMatch',
    'AdmiralScraper',
    'SoccerbetScraper',
    'MozzartScraper',
    'MeridianScraper',
    'MaxbetScraper',
    'SuperbetScraper',
    'MerkurScraper',
    'TopbetScraper',
]
