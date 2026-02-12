"""
Configuration management for BetSnipe.ai v2.0

Uses pydantic-settings for environment variable loading and validation.
"""

import os
from typing import Optional
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database (PostgreSQL/Supabase)
    database_url: str = Field(
        default="postgresql://localhost:5432/betsnipe",
        alias="DATABASE_URL",
        description="PostgreSQL connection string"
    )

    # Supabase specific (optional)
    supabase_url: Optional[str] = Field(default=None, alias="SUPABASE_URL")
    supabase_key: Optional[str] = Field(default=None, alias="SUPABASE_KEY")
    supabase_jwt_secret: Optional[str] = Field(
        default=None,
        alias="SUPABASE_JWT_SECRET",
        description="JWT secret for validating Supabase tokens"
    )
    supabase_service_role_key: Optional[str] = Field(
        default=None,
        alias="SUPABASE_SERVICE_ROLE_KEY",
        description="Service role key for admin operations"
    )

    # Telegram notifications
    telegram_bot_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, alias="TELEGRAM_CHAT_ID")

    # Scraper settings
    scrape_interval_seconds: float = Field(
        default=2.0,
        description="Seconds between scrape cycles"
    )
    request_timeout_seconds: float = Field(
        default=30.0,
        description="HTTP request timeout"
    )
    max_concurrent_requests: int = Field(
        default=10,
        description="Max concurrent HTTP requests per bookmaker"
    )

    # Match matching settings
    match_time_window_minutes: int = Field(
        default=120,
        description="Time window for matching games (in minutes)"
    )
    match_similarity_threshold: float = Field(
        default=75.0,
        description="Minimum similarity score for auto-matching (0-100)"
    )

    # Arbitrage settings
    min_profit_percentage: float = Field(
        default=1.0,
        description="Minimum profit percentage to report arbitrage"
    )
    arbitrage_dedup_hours: int = Field(
        default=24,
        description="Hours to deduplicate arbitrage opportunities"
    )

    # API settings
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_reload: bool = Field(default=False)
    cors_origins: str = Field(
        default="*",
        description="Comma-separated CORS origins"
    )

    # Logging
    log_level: str = Field(default="INFO")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Feature flags
    enable_telegram: bool = Field(default=True)
    enable_websocket: bool = Field(default=True)
    enable_odds_history: bool = Field(default=True)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields in .env

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


# Bookmaker configuration
BOOKMAKERS = {
    1: {"name": "mozzart", "display": "Mozzart Bet", "enabled": False},  # Cloudflare blocked
    2: {"name": "meridian", "display": "Meridian Bet", "enabled": True},  # Re-enabled
    3: {"name": "maxbet", "display": "MaxBet", "enabled": True},
    4: {"name": "admiral", "display": "Admiral Bet", "enabled": True},
    5: {"name": "soccerbet", "display": "Soccer Bet", "enabled": True},
    6: {"name": "superbet", "display": "SuperBet", "enabled": True},
    7: {"name": "merkur", "display": "Merkur", "enabled": True},
    8: {"name": "1xbet", "display": "1xBet", "enabled": False},  # Often blocked
    9: {"name": "lvbet", "display": "LVBet", "enabled": False},
    10: {"name": "topbet", "display": "TopBet", "enabled": True},
    11: {"name": "pinnacle", "display": "Pinnacle", "enabled": False},
}

# Sport configuration
SPORTS = {
    1: {"name": "football", "name_sr": "Fudbal", "time_window_minutes": 30},
    2: {"name": "basketball", "name_sr": "Kosarka", "time_window_minutes": 20},
    3: {"name": "tennis", "name_sr": "Tenis", "time_window_minutes": 10},
    4: {"name": "hockey", "name_sr": "Hokej", "time_window_minutes": 20},
    5: {"name": "table_tennis", "name_sr": "Stoni Tenis", "time_window_minutes": 5},
    6: {"name": "volleyball", "name_sr": "Odbojka", "time_window_minutes": 15},
    7: {"name": "handball", "name_sr": "Rukomet", "time_window_minutes": 20},
    8: {"name": "esports", "name_sr": "Esport", "time_window_minutes": 15},
}

# Bet type configuration
BET_TYPES = {
    1: {"name": "12", "description": "Two-way result", "outcomes": 2},
    2: {"name": "1X2", "description": "Three-way result", "outcomes": 3},
    3: {"name": "1X2_H1", "description": "First half 1X2", "outcomes": 3},
    4: {"name": "1X2_H2", "description": "Second half 1X2", "outcomes": 3},
    5: {"name": "total_over_under", "description": "Total O/U", "outcomes": 2},
    6: {"name": "total_h1", "description": "First half total", "outcomes": 2},
    7: {"name": "total_h2", "description": "Second half total", "outcomes": 2},
    8: {"name": "btts", "description": "Both teams to score", "outcomes": 2},
    9: {"name": "handicap", "description": "Asian handicap", "outcomes": 2},
    10: {"name": "total_points", "description": "Total points", "outcomes": 2},
    11: {"name": "spread", "description": "Point spread", "outcomes": 2},
    12: {"name": "moneyline", "description": "Moneyline", "outcomes": 2},
}


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
