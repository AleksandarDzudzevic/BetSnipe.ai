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
# outcomes=1 means selection-based market (each outcome is a separate row with selection key)
BET_TYPES = {
    # === Existing types ===
    1:  {"name": "winner",              "description": "Two-way result",              "outcomes": 2},
    2:  {"name": "1x2",                 "description": "Three-way result",            "outcomes": 3},
    3:  {"name": "1x2_h1",              "description": "First half 1X2",              "outcomes": 3},
    4:  {"name": "1x2_h2",              "description": "Second half 1X2",             "outcomes": 3},
    5:  {"name": "total_over_under",    "description": "Total O/U",                   "outcomes": 2},
    6:  {"name": "total_h1",            "description": "First half total O/U",        "outcomes": 2},
    7:  {"name": "total_h2",            "description": "Second half total O/U",       "outcomes": 2},
    8:  {"name": "btts",                "description": "Both teams to score",         "outcomes": 2},
    9:  {"name": "handicap",            "description": "Asian handicap",              "outcomes": 2},
    10: {"name": "total_points",        "description": "Total points",                "outcomes": 2},
    11: {"name": "spread",              "description": "Point spread",                "outcomes": 2},
    12: {"name": "moneyline",           "description": "Moneyline",                   "outcomes": 2},
    13: {"name": "double_chance",       "description": "Double chance (1X, 12, X2)",   "outcomes": 3},
    14: {"name": "draw_no_bet",         "description": "Draw no bet",                 "outcomes": 2},
    # === New simple markets (2-3 outcomes, grouped mode) ===
    15: {"name": "odd_even",            "description": "Odd/Even total goals",        "outcomes": 2},
    16: {"name": "double_win",          "description": "Both halves winner",          "outcomes": 2},
    17: {"name": "win_to_nil",          "description": "Win to nil",                  "outcomes": 2},
    18: {"name": "first_goal",          "description": "First goal scorer team",      "outcomes": 3},
    19: {"name": "half_with_more_goals","description": "Half with more goals",        "outcomes": 3},
    20: {"name": "double_chance_h1",    "description": "First half double chance",    "outcomes": 3},
    21: {"name": "draw_no_bet_h1",      "description": "First half draw no bet",     "outcomes": 2},
    22: {"name": "to_qualify",          "description": "To qualify / advance",        "outcomes": 2},
    # === New multi-outcome markets (selection mode, outcomes=1) ===
    23: {"name": "correct_score",       "description": "Correct score",               "outcomes": 1},
    24: {"name": "ht_ft",              "description": "Halftime / Fulltime",         "outcomes": 1},
    25: {"name": "total_goals_range",   "description": "Total goals range",           "outcomes": 1},
    26: {"name": "exact_goals",         "description": "Exact number of goals",       "outcomes": 1},
    27: {"name": "team1_goals",         "description": "Team 1 total goals",          "outcomes": 1},
    28: {"name": "team2_goals",         "description": "Team 2 total goals",          "outcomes": 1},
    29: {"name": "h1_total_goals_range","description": "H1 total goals range",        "outcomes": 1},
    30: {"name": "h2_total_goals_range","description": "H2 total goals range",        "outcomes": 1},
    31: {"name": "team1_goals_h1",      "description": "Team 1 goals first half",     "outcomes": 1},
    32: {"name": "team2_goals_h1",      "description": "Team 2 goals first half",     "outcomes": 1},
    33: {"name": "team1_goals_h2",      "description": "Team 1 goals second half",    "outcomes": 1},
    34: {"name": "team2_goals_h2",      "description": "Team 2 goals second half",    "outcomes": 1},
    35: {"name": "goals_h1_h2_combo",   "description": "Goals H1 & H2 combination",  "outcomes": 1},
    36: {"name": "first_goal_result",   "description": "First goal + final result",   "outcomes": 1},
    37: {"name": "ht_ft_double_chance", "description": "HT/FT double chance",         "outcomes": 1},
    38: {"name": "result_total_goals",  "description": "Result + total goals",        "outcomes": 1},
    39: {"name": "result_combo",        "description": "Result combinations",         "outcomes": 1},
    40: {"name": "result_half_goals",   "description": "Result + half with more goals","outcomes": 1},
    41: {"name": "dc_total_goals",      "description": "Double chance + total goals", "outcomes": 1},
    42: {"name": "dc_half_goals",       "description": "DC + half with more goals",   "outcomes": 1},
    43: {"name": "dc_combo",            "description": "Double chance combinations",  "outcomes": 1},
    44: {"name": "ht_ft_total_goals",   "description": "HT/FT + total goals",        "outcomes": 1},
    45: {"name": "ht_ft_combo",         "description": "HT/FT combinations",         "outcomes": 1},
    46: {"name": "btts_combo",          "description": "BTTS combinations",           "outcomes": 1},
    47: {"name": "mozzart_chance",      "description": "Mozzart chance (proprietary)","outcomes": 1},
    # === Basketball-specific markets ===
    48: {"name": "team1_total_points", "description": "Team 1 total points O/U",    "outcomes": 2},
    49: {"name": "team2_total_points", "description": "Team 2 total points O/U",    "outcomes": 2},
    50: {"name": "handicap_h1",        "description": "First half handicap",         "outcomes": 2},
    51: {"name": "team1_total_h1",     "description": "Team 1 first half total O/U", "outcomes": 2},
    52: {"name": "team2_total_h1",     "description": "Team 2 first half total O/U", "outcomes": 2},
    53: {"name": "most_efficient_quarter_total", "description": "Most efficient quarter total O/U", "outcomes": 2},
    54: {"name": "quarter_most_points","description": "Quarter with most points",    "outcomes": 1},
    55: {"name": "h1_result_total",    "description": "H1 result + H1 total",        "outcomes": 1},
    # === Tennis-specific markets ===
    56: {"name": "handicap_sets",         "description": "Set handicap",                   "outcomes": 2},
    57: {"name": "first_set_winner",      "description": "First set winner",               "outcomes": 2},
    58: {"name": "handicap_games_s1",     "description": "First set game handicap",        "outcomes": 2},
    59: {"name": "odd_even_s1",           "description": "First set odd/even",             "outcomes": 2},
    60: {"name": "tiebreak_s1",           "description": "First set tiebreak yes/no",      "outcomes": 2},
    61: {"name": "odd_even_s2",           "description": "Second set odd/even",            "outcomes": 2},
    62: {"name": "tiebreak_s2",           "description": "Second set tiebreak yes/no",     "outcomes": 2},
    63: {"name": "set_with_more_games",   "description": "Set with more games",            "outcomes": 3},
    64: {"name": "first_set_match_combo", "description": "First set + match result",       "outcomes": 1},
    65: {"name": "exact_sets",            "description": "Exact number of sets",           "outcomes": 1},
    66: {"name": "games_range_s1",        "description": "First set games range",          "outcomes": 1},
    67: {"name": "games_range_s2",        "description": "Second set games range",         "outcomes": 1},
    68: {"name": "winner_total_games",    "description": "Winner + total games combo",     "outcomes": 1},
    69: {"name": "p1_win_games_s1",       "description": "Player 1 wins + S1 games",      "outcomes": 1},
    70: {"name": "p1_win_odd_even_s1",    "description": "Player 1 wins + S1 odd/even",   "outcomes": 2},
    71: {"name": "p2_win_games_s1",       "description": "Player 2 wins + S1 games",      "outcomes": 1},
    72: {"name": "p2_win_odd_even_s1",    "description": "Player 2 wins + S1 odd/even",   "outcomes": 2},
    73: {"name": "winner_set_more_games", "description": "Winner + set with more games",   "outcomes": 1},
    # === Hockey-specific markets ===
    74: {"name": "h1_result_total_goals", "description": "H1/P1 result + total goals",   "outcomes": 1},
}


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
