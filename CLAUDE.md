# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BetSnipe.ai is a Python-based real-time arbitrage betting detection system that scrapes odds from Serbian bookmakers, identifies arbitrage opportunities, and sends Telegram notifications.

## Commands

All commands run from `PythonScraper/` directory:

```bash
# Install dependencies
pip install -r requirements.txt

# Run full application (API + scraper engine)
python main.py

# Run components separately
python main.py --api-only       # API server only (port 8000)
python main.py --scraper-only   # Scraper engine only (no API)

# Development mode with auto-reload
python main.py --reload --debug

# Test scrapers without database
python test_scrapers.py                     # All scrapers
python test_scrapers.py --scraper admiral   # Single scraper
python test_scrapers.py --sport 1           # Football only (1=Football, 2=Basketball, 3=Tennis, 4=Hockey, 5=Table Tennis)
python test_scrapers.py --arbitrage         # Include arbitrage detection
python test_scrapers.py --telegram          # Test Telegram notifications
```

## Architecture

```
ScraperEngine (core/scraper_engine.py)
    │
    ├── Registers scrapers → BaseScraper subclasses (core/scrapers/*.py)
    │
    ├── Processes matches → MatchMatcher (core/matching.py)
    │   └── Fuzzy matching with rapidfuzz, time windows, league similarity
    │
    ├── Stores to PostgreSQL → Database (core/db.py)
    │   └── asyncpg connection pool
    │
    ├── Detects arbitrage → ArbitrageDetector (core/arbitrage.py)
    │
    └── Broadcasts updates → WebSocket (api/websocket.py)
                          → Telegram (telegram_utils.py)
```

The FastAPI app (`api/main.py`) starts the scraper engine on startup and exposes REST/WebSocket endpoints.

## Creating a New Scraper

1. Create `core/scrapers/{bookmaker}.py` inheriting from `BaseScraper`
2. Implement required methods:
   - `get_base_url()` - API base URL
   - `get_supported_sports()` - List of sport IDs (1-5)
   - `scrape_sport(sport_id)` - Returns `List[ScrapedMatch]`
3. Use `fetch_json()` for HTTP requests (handles rate limiting, timeouts)
4. Use `ScrapedMatch.add_odds()` to attach odds with `bet_type_id`
5. Register in `main.py` and `test_scrapers.py`

Note: Mozzart scraper exists but is disabled in production due to Cloudflare protection.

## ID Mappings

**Sports**: Football (1), Basketball (2), Tennis (3), Hockey (4), Table Tennis (5)

**Bookmakers**: Mozzart (1), Meridian (2), Maxbet (3), Admiral (4), Soccerbet (5), Superbet (6), Merkur (7), 1xBet (8), LVBet (9), Topbet (10)

**Bet Types**: 12 (1), 1X2 (2), 1X2_H1 (3), 1X2_H2 (4), Total (5-7), BTTS (8), Handicap (9)

## Key Configuration (.env)

```bash
DATABASE_URL=postgresql://user:pass@host:5432/betsnipe
TELEGRAM_BOT_TOKEN=your-token
TELEGRAM_CHAT_ID=your-chat-id
MIN_PROFIT_PERCENTAGE=1.0      # Minimum arbitrage profit to report
MATCH_SIMILARITY_THRESHOLD=75  # Fuzzy match threshold (0-100)
SCRAPE_INTERVAL_SECONDS=2      # Time between scrape cycles
```

## API Endpoints

```
GET  /health, /stats
GET  /api/sports, /api/bookmakers
GET  /api/matches, /api/matches/{id}, /api/matches/{id}/odds-history
GET  /api/odds/best
GET  /api/arbitrage, /api/arbitrage/stats
POST /api/arbitrage/calculate

WS   /ws              # Main real-time feed
WS   /ws/odds         # Odds updates only
WS   /ws/arbitrage    # Arbitrage alerts only
```

## Database Tables

See `db/schema.sql`: bookmakers, sports, bet_types, leagues, matches, current_odds, odds_history, arbitrage_opportunities
