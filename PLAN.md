# BetSnipe.ai v2.0 - Implementation Plan

## Goal
Transform the current batch-based arbitrage detector into a real-time odds platform (OddsJam for Serbian market).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     BetSnipe.ai v2.0                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Unified    │    │   Match      │    │   FastAPI    │      │
│  │   Scraper    │───▶│   Engine     │───▶│   WebSocket  │      │
│  │   Engine     │    │   (Matching) │    │   Server     │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                   │                   │               │
│         ▼                   ▼                   ▼               │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              PostgreSQL (Supabase)                   │       │
│  │  - matches, odds_history, arbitrage_opportunities   │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Deployment (Free Tier)

| Component | Service | Cost |
|-----------|---------|------|
| Database | Supabase Free | $0 (500MB PostgreSQL) |
| Backend | Railway.app or Render.com | $0 (free tier) |
| Mobile (Phase 2) | Expo | $0 |

---

## Phase 1: Backend (What We Build Now)

### 1.1 Database Schema

**Tables:**

```sql
-- Reference tables
bookmakers (id, name, api_base_url, is_active)
sports (id, name, name_sr)
bet_types (id, name, num_outcomes)
leagues (id, name, sport_id, country, external_ids)

-- Core tables
matches (id, team1, team2, team1_normalized, team2_normalized,
         sport_id, league_id, start_time, external_ids, status)

current_odds (match_id, bookmaker_id, bet_type_id, margin,
              odd1, odd2, odd3, updated_at)

odds_history (id, match_id, bookmaker_id, bet_type_id, margin,
              odd1, odd2, odd3, recorded_at)

arbitrage_opportunities (id, match_id, bet_type_id, margin,
                         profit_percentage, best_odds, stakes,
                         arb_hash, detected_at, notified_at, is_active)
```

### 1.2 Unified Scraper Engine

**Key improvements over current system:**
- Single async process (not 20+ subprocesses)
- Persistent HTTP connection pools (faster)
- Incremental updates (UPSERT, not DELETE/INSERT)
- Real-time match deduplication

**Flow:**
```
while True:
    1. Fetch odds from all 8 bookmakers in parallel (asyncio)
    2. For each match found:
       - Normalize team names
       - Find or create unified match record
       - Update current_odds table
       - Insert into odds_history
    3. Detect arbitrage opportunities
    4. Send Telegram alerts for new opportunities
    5. Sleep 1-2 seconds
    6. Repeat
```

### 1.3 Enhanced Match Matching

**Current system:** Team name fuzzy matching only

**New system:** Multi-factor scoring
1. **Team name similarity** (RapidFuzz) - 50% weight
2. **Time proximity** (within 2 hours) - 25% weight
3. **League match** (if available) - 15% weight
4. **Odds similarity** (within 20%) - 10% weight

**Confidence tiers:**
- Score >= 85: Auto-match
- Score 70-84: Match if time within 30min
- Score < 70: Create new match record

**Tennis-specific:**
- Extract surnames from player names
- Handle name order reversal (Player A vs Player B = Player B vs Player A)

### 1.4 FastAPI Server

**REST Endpoints:**
```
GET  /health              - Health check
GET  /stats               - System statistics
GET  /api/sports          - List sports
GET  /api/bookmakers      - List bookmakers
GET  /api/matches         - List matches with odds
GET  /api/matches/{id}    - Get match details
GET  /api/matches/{id}/odds-history  - Odds history for charting
GET  /api/odds/best       - Best odds comparison
GET  /api/arbitrage       - Active arbitrage opportunities
GET  /api/arbitrage/stats - Arbitrage statistics
POST /api/arbitrage/calculate - Calculate arbitrage from given odds
```

**WebSocket Endpoints:**
```
WS /ws                - Main feed (all updates)
WS /ws/odds           - Odds updates only
WS /ws/arbitrage      - Arbitrage alerts only
```

---

## Phase 2: Mobile App (Future)

React Native with Expo:
- Real-time odds feed via WebSocket
- Push notifications for arbitrage
- Odds comparison charts
- User authentication
- Subscription management

---

## New File Structure

```
PythonScraper/
├── main.py                 # NEW: Entry point
├── requirements.txt        # UPDATED: New dependencies
├── .env.example            # NEW: Environment template
│
├── core/                   # NEW: Core business logic
│   ├── __init__.py
│   ├── config.py           # Configuration (pydantic)
│   ├── db.py               # Database operations (asyncpg)
│   ├── scraper_engine.py   # Main orchestrator
│   ├── matching.py         # Enhanced match matching
│   ├── arbitrage.py        # Arbitrage detection
│   └── scrapers/           # Bookmaker scrapers
│       ├── __init__.py
│       ├── base.py         # Base scraper class
│       ├── admiral.py
│       ├── soccerbet.py
│       ├── mozzart.py
│       ├── meridian.py
│       ├── maxbet.py
│       ├── superbet.py
│       ├── merkur.py
│       └── topbet.py
│
├── api/                    # NEW: FastAPI application
│   ├── __init__.py
│   ├── main.py             # FastAPI app
│   ├── websocket.py        # WebSocket handler
│   └── routes/
│       ├── odds.py         # Odds endpoints
│       └── arbitrage.py    # Arbitrage endpoints
│
├── db/                     # NEW: Database files
│   └── schema.sql          # PostgreSQL schema
│
└── telegram_utils.py       # KEEP: Telegram notifications
```

---

## Implementation Steps

### Step 1: Database Setup
1. Create Supabase account (free)
2. Create `db/schema.sql` with all tables
3. Run schema on Supabase
4. Create `core/config.py` for environment variables
5. Create `core/db.py` with asyncpg connection pool

### Step 2: Core Scraper Infrastructure
1. Create `core/scrapers/base.py` - base class with common HTTP logic
2. Port Admiral scraper to new format (as template)
3. Port remaining 7 scrapers
4. Create `core/scraper_engine.py` - orchestrator

### Step 3: Match Matching
1. Create `core/matching.py` with multi-factor scoring
2. Add league normalization mappings
3. Add tennis-specific name handling
4. Test matching accuracy

### Step 4: Arbitrage Detection
1. Create `core/arbitrage.py`
2. Implement 2-way and 3-way arbitrage calculation
3. Add deduplication (24-hour window)
4. Integrate Telegram notifications

### Step 5: FastAPI Server
1. Create `api/main.py` with FastAPI app
2. Create REST endpoints
3. Create WebSocket handler
4. Test locally

### Step 6: Deployment
1. Create `.env.example` template
2. Deploy to Railway/Render
3. Connect to Supabase
4. Test end-to-end

---

## Key Technical Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Database | PostgreSQL (Supabase) | Free, time-series support, real-time subscriptions |
| Async framework | asyncio + aiohttp | Native Python, no external broker needed |
| API framework | FastAPI | Async support, WebSocket, auto-docs |
| Match storage | Unified matches table | One match = one record, link odds via foreign key |
| Odds storage | current_odds + odds_history | Fast queries + full history |
| Deployment | Railway/Render | Free tier, easy Python deployment |

---

## Sports & Bookmaker IDs (Internal)

**Sports:**
- Football (1), Basketball (2), Tennis (3), Hockey (4), Table Tennis (5)

**Bookmakers:**
- Mozzart (1), Meridian (2), Maxbet (3), Admiral (4), Soccerbet (5)
- Superbet (6), Merkur (7), 1xBet (8), LVBet (9), Topbet (10)

**Bet Types:**
- 12 (1), 1X2 (2), 1X2_H1 (3), 1X2_H2 (4), Total (5-7), BTTS (8), Handicap (9)

---

## Environment Variables

```bash
# Database (Supabase)
DATABASE_URL=postgresql://postgres:[password]@db.[project].supabase.co:5432/postgres

# Telegram
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id

# API Server
API_HOST=0.0.0.0
API_PORT=8000

# Scraper Settings
SCRAPE_INTERVAL_SECONDS=2
MIN_PROFIT_PERCENTAGE=1.0
MATCH_SIMILARITY_THRESHOLD=75
```

---

## Verification Checklist

- [ ] Database tables created successfully
- [ ] All 8 scrapers fetch data correctly
- [ ] Same match from 2 bookmakers links to one record
- [ ] Odds history accumulates over time
- [ ] Arbitrage detected when profitable odds exist
- [ ] Telegram alerts sent for new arbitrage
- [ ] REST API returns correct data
- [ ] WebSocket broadcasts updates in real-time
- [ ] System runs continuously without memory leaks
