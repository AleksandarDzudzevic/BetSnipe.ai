# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BetSnipe.ai is a Python-based real-time arbitrage betting detection system that scrapes odds from Serbian bookmakers, identifies arbitrage opportunities, and provides a mobile app + API for users.

## Tech Stack

- **Backend**: Python FastAPI + asyncpg (PostgreSQL) + WebSocket
- **Database**: Supabase (PostgreSQL with Row Level Security)
- **Mobile**: Expo/React Native with TypeScript
- **Auth**: Supabase Auth with JWT tokens
- **Scraping**: aiohttp + Playwright (for Cloudflare-protected sites)

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
python test_scrapers.py --sport 1           # Football only
python test_scrapers.py --arbitrage         # Include arbitrage detection
```

## Architecture

```
ScraperEngine (core/scraper_engine.py)
    │
    ├── Registers scrapers → BaseScraper subclasses (core/scrapers/*.py)
    │
    ├── Bulk processes matches → bulk_upsert_matches_and_odds (core/db.py)
    │   └── Uses ON CONFLICT for fast upserts, deduplicates before insert
    │
    ├── Stores to Supabase → Database (core/db.py)
    │   └── asyncpg connection pool (50 connections)
    │
    ├── Detects arbitrage → ArbitrageDetector (core/arbitrage.py)
    │   └── Runs after each scrape cycle, checks all 124 bet types
    │
    └── Broadcasts updates → WebSocket (api/websocket.py)
                          → Telegram (telegram_utils.py)
                          → Push notifications (core/push_notifications.py)
```

## Active Scrapers

| Bookmaker | ID | Method | Status |
|-----------|-----|--------|--------|
| Admiral | 4 | aiohttp | ✅ Active |
| Soccerbet | 5 | aiohttp | ✅ Active |
| Mozzart | 1 | Playwright | ✅ Active (Cloudflare bypass) |
| Maxbet | 3 | aiohttp | ✅ Active |
| Superbet | 6 | aiohttp | ✅ Active |
| Merkur | 7 | aiohttp | ✅ Active |
| Topbet | 10 | aiohttp | ✅ Active |
| Meridian | 2 | - | ❌ Disabled |

## ID Mappings

**Sports**: Football (1), Basketball (2), Tennis (3), Hockey (4), Table Tennis (5)

**Bet Types** (124 total, IDs 1-124):
- 2-way (outcomes=2): O/U, BTTS, yes/no markets — odd1 vs odd2
- 3-way (outcomes=3): 1X2 markets — odd1 vs oddX vs odd2
- Selection-based (outcomes=1): correct score, HT/FT, combos — each row has a selection key, odd1 only
- See `core/config.py` BET_TYPES for full list

## Key Configuration (.env)

```bash
DATABASE_URL=postgresql://user:pass@host:5432/betsnipe
TELEGRAM_BOT_TOKEN=your-token
TELEGRAM_CHAT_ID=your-chat-id
MIN_PROFIT_PERCENTAGE=1.0      # Minimum arbitrage profit to report
MATCH_SIMILARITY_THRESHOLD=75  # Fuzzy match threshold (0-100)
SCRAPE_INTERVAL_SECONDS=2      # Time between scrape cycles

# Supabase (for auth)
SUPABASE_JWT_SECRET=your-jwt-secret
SUPABASE_SERVICE_ROLE_KEY=your-service-key
```

## Database Schema

Key tables in Supabase:
- `matches` - Deduplicated matches with unique constraint on (team1_normalized, team2_normalized, sport_id, start_time)
- `current_odds` - Latest odds with PK (match_id, bookmaker_id, bet_type_id, margin, selection)
- `arbitrage_opportunities` - Detected arbitrage with profit %, stakes
- `odds_history` - Historical odds for trend analysis

User tables (v3):
- `user_preferences` - Min profit, sports, bookmaker filters
- `user_devices` - Expo push tokens
- `user_watchlist` - Watched matches
- `user_arbitrage_history` - User interactions

RLS is enabled on all tables with public read policies.

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

## Temporary Test Scripts

Use `PythonScraper/claude_test/` for any temporary test, diagnostic, or dump scripts. This folder is gitignored — create and delete files freely without cluttering the repo.

## Slash Commands

- `/audit <sport_id>` — Run cross-bookmaker audit (1=Football, 2=Basketball, etc.)
- `/test-scraper <name> [sport_id]` — Test a single scraper without database
- `/expand <bookmaker>` — Guided expansion of a bookmaker's market coverage

## Performance Optimizations

1. **Bulk inserts** - Uses `unnest()` arrays with ON CONFLICT for ~100x faster DB operations
2. **Deduplication** - Matches and odds deduplicated before insert to avoid conflicts
3. **Connection pool** - 50 connections for concurrent operations
4. **Composite indexes** - `idx_matches_bulk_lookup` for fast lookups
5. **Concurrent scraping** - All 7 bookmakers scraped in parallel

## Mobile App (MobileApp/)

Expo/React Native app with:
- `src/app/` - Expo Router screens
- `src/services/` - API, WebSocket, Auth, Notifications
- `src/stores/` - Zustand state management
- `src/types/` - TypeScript types
