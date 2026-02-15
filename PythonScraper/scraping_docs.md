# BetSnipe.ai Scraping System Documentation

## Overview

BetSnipe.ai scrapes real-time odds from 7 Serbian bookmakers, normalizes them into a unified format, stores them in Supabase (PostgreSQL), and detects cross-bookmaker arbitrage opportunities.

All scrapers run concurrently every 2 seconds (configurable via `SCRAPE_INTERVAL_SECONDS`). Each scraper produces `ScrapedMatch` objects containing `ScrapedOdds` entries, which are bulk-upserted into the database.

---

## Architecture

```
main.py
  ├── --api-only    → uvicorn (api/main.py)
  ├── --scraper-only → ScraperEngine loop
  ├── --<bookmaker>  → Single scraper debug mode
  └── (default)      → API server (includes engine via lifespan)

ScraperEngine (core/scraper_engine.py)
  ├── Registers 7 BaseScraper subclasses
  ├── run_cycle():
  │     ├── scrape_bookmaker() × 7 (concurrent via asyncio.gather)
  │     ├── bulk_upsert_matches_and_odds() per bookmaker
  │     ├── ArbitrageDetector.detect_all()
  │     └── Notify callbacks (WebSocket, Telegram, Push)
  └── Repeats every scrape_interval_seconds
```

---

## Data Model

### ScrapedOdds (`core/scrapers/base.py`)

```python
@dataclass
class ScrapedOdds:
    bet_type_id: int          # Maps to BET_TYPES in config.py (1-124)
    odd1: float               # Primary odds value
    odd2: Optional[float]     # Secondary (e.g., under, away)
    odd3: Optional[float]     # Tertiary (e.g., draw in 1X2)
    margin: float = 0.0       # Line value (handicap, total threshold)
    selection: str = ''       # Outcome key for multi-outcome markets
```

### ScrapedMatch (`core/scrapers/base.py`)

```python
@dataclass
class ScrapedMatch:
    team1: str                # Home team (raw from bookmaker)
    team2: str                # Away team (raw from bookmaker)
    sport_id: int             # 1=Football, 2=Basketball, 3=Tennis, 4=Hockey, 5=Table Tennis
    start_time: datetime      # UTC-aware
    odds: List[ScrapedOdds]   # All odds for this match
    league_name: Optional[str]
    external_id: Optional[str]
```

### Database Primary Key

Odds are stored in `current_odds` with PK: `(match_id, bookmaker_id, bet_type_id, margin, selection)`

This means the same real-world bet **MUST** produce identical `(bet_type_id, selection, margin)` across ALL bookmakers for cross-bookmaker comparison to work.

---

## Bet Types (124 total, defined in `core/config.py`)

### Grouped Markets (fixed outcomes per bet type)

| ID | Name | Outcomes | Description |
|----|------|----------|-------------|
| 1 | winner | 2 | Two-way result (tennis, basketball) |
| 2 | 1x2 | 3 | Three-way result (football, hockey) |
| 3-4 | 1x2_h1/h2 | 3 | Half 1X2 |
| 5-7 | total_over_under, total_h1/h2 | 2 | Total goals/points O/U |
| 8 | btts | 2 | Both teams to score |
| 9 | handicap | 2 | Asian handicap (margin = line) |
| 13-14 | double_chance, draw_no_bet | 3/2 | |
| 15-21 | odd_even, double_win, win_to_nil, etc. | 2-3 | Simple markets |
| 48-55 | Basketball-specific | 2 | Team totals, half handicaps |
| 56-73 | Tennis-specific | 1-2 | Set markets, game handicaps |
| 83-98 | Corner/card markets | 1-3 | Admiral-only specialty |

### Selection Markets (outcomes=1, each row has a `selection` key)

| ID | Name | Selection Format | Example |
|----|------|-----------------|---------|
| 23 | correct_score | `X:Y` | `1:0`, `2:1` |
| 24 | ht_ft | `R1/R2` | `1/1`, `X/2` |
| 25 | total_goals_range | `A-B` or `N+` | `0-2`, `3+` |
| 26 | exact_goals | `TN` | `T0`, `T1`, `T5` |
| 27-28 | team_goals | `A-B` or `N+` | `0-1`, `2+` |
| 35 | goals_h1_h2_combo | `H1:A-B&H2:C-D` | `H1:0-1&H2:2+` |
| 37 | ht_ft_double_chance | `DC/DC` | `1X/1X`, `12/X2` |
| 38 | result_total_goals | `R&A-B` | `1&2-3`, `X&4+` |
| 41 | dc_total_goals | `DC&A-B` | `1X&2-3`, `12&4+` |
| 44 | ht_ft_total_goals | `R/R&A-B` | `1/1&2-3` |
| 46 | btts_combo | `YN&...` | `GG&3+`, `NG&0-2` |
| 114 | or_combinations | `A\|B` | `1\|3+`, `X\|0-2` |
| 124 | ht_ft_or_combo | `R/R\|R/R` | `1/1\|1/2` |

---

## Selection Format Conventions

These rules ensure cross-bookmaker consistency. **All scrapers must produce identical keys for the same bet.**

| Convention | Format | Example |
|-----------|--------|---------|
| Half prefix | `H1:`, `H2:` | `H1:0-1` (first half 0-1 goals) |
| Team prefix | `H`, `A` | `H` (home), `A` (away) |
| Full-time in combos | `FT:` | `FT:2+` (full-time 2+ goals) |
| Combo separator | `&` | `1&2-3` (result=1 AND total 2-3) |
| OR separator | `\|` | `1\|3+` (result=1 OR total 3+) |
| HT/FT separator | `/` | `1/2` (HT=1, FT=2) — **NEVER** dash |
| Goal exact count | `T` prefix | `T0`, `T1`, `T5` |
| Goal range | `A-B` or `N+` | `0-2`, `3+`, `4-6` |
| BTTS | `GG`, `NG` | `GG` (yes), `NG` (no) |
| Handicap margin | positive = home advantage | `margin=1.5` means home +1.5 |

---

## Scraper Inventory

### 1. Mozzart (ID=1) — Playwright

| Property | Value |
|----------|-------|
| Base URL | `https://www.mozzartbet.com` |
| HTTP Method | POST via Playwright (Cloudflare bypass) |
| Fetch Pattern | Sport → competitions → match IDs → per-match odds |
| API Format | Group-based: `oddsGroup[]` with game/subgame names |
| Dispatch | ~47 handlers per sport, key off `gameName` + `subGameName` |
| Special | Persistent browser session, `specialOddValueType` detection (MARGIN/HANDICAP/NONE) |
| Sports | Football, Basketball, Tennis, Hockey, Table Tennis |

Mozzart is the only scraper requiring Playwright due to Cloudflare protection. It maintains a headless browser session and intercepts API responses.

### 2. MaxBet (ID=3) — aiohttp

| Property | Value |
|----------|-------|
| Base URL | `https://www.maxbet.rs/restapi/offer/sr` |
| HTTP Method | GET |
| Fetch Pattern | Sport → leagues → league matches → per-match details |
| API Format | Dual: flat code dict `{code: value}` + params dict `{param_key: {margin: odds}}` |
| Mapping Source | `ttg_lang` config endpoint (~600 code mappings, shared with Merkur/Soccerbet) |
| Special | Handicap sign **negated** for both 2-way and 3-way (raw API uses opposite convention) |
| Sports | Football, Basketball, Tennis, Hockey, Table Tennis |

MaxBet, Merkur, and Soccerbet share the same backend platform with identical market code mappings (verified via `ttg_lang` endpoint). However, MaxBet's raw handicap params use the **opposite sign** from others — both `_parse_param_handicaps_3way` and `_parse_param_handicaps_2way` negate the margin.

### 3. Admiral (ID=4) — aiohttp

| Property | Value |
|----------|-------|
| Base URL | `https://srboffer.admiralbet.rs/api/offer` |
| HTTP Method | GET |
| Fetch Pattern | Hierarchy: competitions → matches → per-match `bets[]` array |
| API Format | Structured JSON with `betTypeId`, `betTypeName`, `betOutcomes[]` |
| Mapping | ~90 bet types mapped (highest diversity of any scraper) |
| Special | `_normalize_selection()` for combo markets, bt25→bt26 exact goals remapping |
| Sports | Football (91 BTs), Basketball (15), Tennis (8), Hockey (12), Table Tennis (2) |

Admiral has the most diverse bet type coverage, including corners, cards, and penalty markets that no other bookmaker offers. It uses a comprehensive `_normalize_selection()` function to convert raw Serbian names (I/II half, Tim1/Tim2 teams, GG/NG) into the standard format.

### 4. Soccerbet (ID=5) — aiohttp

| Property | Value |
|----------|-------|
| Base URL | `https://www.soccerbet.rs/restapi/offer/sr` |
| HTTP Method | GET |
| Fetch Pattern | Sport → leagues → league matches → per-match details |
| API Format | Flat code-based map `{code: {"NULL": {"ov": value}}}` (fixed margins only) |
| Mapping Source | Shared `ttg_lang` codes with MaxBet/Merkur (~600 codes) |
| Special | No param-based markets (handicap, team totals come from codes, not params) |
| Sports | Football (51 BTs), Basketball (7), Tennis (6), Hockey (7), Table Tennis (5) |

Soccerbet has the highest avg odds per match for football (664.4) due to deep combo market coverage. It shares the same code structure as MaxBet but lacks param-based handicap/total markets.

### 5. SuperBet (ID=6) — aiohttp

| Property | Value |
|----------|-------|
| Base URL | `https://production-superbet-offer-rs.freetls.fastly.net/sb-rs/api/v2/sr-Latn-RS` |
| HTTP Method | GET |
| Fetch Pattern | Sport → event IDs → per-event details |
| API Format | Market-name-based dispatch with `odds[]` containing `code`, `name`, `price`, `specialBetValue` |
| Mapping | ~80 named markets + ~30 combo handlers |
| Special | Extensive combo parsing, the most matches (1,400+), Fastly CDN |
| Sports | Football (43 BTs), Basketball (14), Tennis (17), Hockey (17), Table Tennis (5) |

SuperBet has the largest match inventory but uses Serbian market names for dispatch. Simple markets map via `FOOTBALL_MARKETS` dict; combo markets are parsed by `_try_football_combo()` which pattern-matches market names and dispatches to dedicated parser methods.

### 6. Merkur (ID=7) — aiohttp

| Property | Value |
|----------|-------|
| Base URL | `https://www.merkurxtip.rs/restapi/offer/sr` |
| HTTP Method | GET |
| Fetch Pattern | Identical to MaxBet (shared platform) |
| API Format | Identical to MaxBet: flat code dict + params dict |
| Mapping | Shares MaxBet's ~600 code mappings |
| Special | Same code as MaxBet but raw 3-way handicap params use **standard** sign (no negation needed) |
| Sports | Football (55 BTs), Basketball (4), Tennis (10), Hockey (12), Table Tennis (5) |

Merkur is nearly identical to MaxBet in API structure and code mappings. The key difference is that Merkur's raw 3-way handicap params already use the standard sign convention (positive = home advantage), while MaxBet's are inverted.

### 7. TopBet (ID=10) — aiohttp

| Property | Value |
|----------|-------|
| Base URL | `https://sports-sm-distribution-api.de-2.nsoftcdn.com/api/v1` |
| HTTP Method | GET |
| Fetch Pattern | Single overview API call per sport (compressed format) |
| API Format | Compressed fields: `b=marketId`, `d=variant`, `n=margin`, `h=outcomes`, `e=code`, `g=price` |
| Mapping | ~16 bet types in overview mode (compressed), ~93 in full format |
| Special | NSoft platform, binary-like compression, HT/FT dash→slash normalization |
| Sports | Football only (16 BTs) |

TopBet uses the NSoft platform with a compressed overview format. It has the lowest coverage (116.5 avg odds/match, football only) because only the overview endpoint is used for most matches. A full-format parser exists for per-match detail but is not used in bulk mode.

---

## BaseScraper Interface (`core/scrapers/base.py`)

All scrapers inherit from `BaseScraper` and implement:

```python
class BaseScraper(ABC):
    def __init__(self, bookmaker_id: int, bookmaker_name: str):
        # Lazy aiohttp session, semaphore for rate limiting,
        # request/error counters

    @abstractmethod
    def get_base_url(self) -> str: ...

    @abstractmethod
    def get_supported_sports(self) -> List[int]: ...

    @abstractmethod
    async def scrape_sport(self, sport_id: int) -> List[ScrapedMatch]: ...

    # Provided by base:
    async def scrape_all(self) -> List[ScrapedMatch]:
        """Scrape all sports concurrently via asyncio.gather"""

    async def fetch_json(self, url, method='GET', params=None, json_data=None) -> Any:
        """Rate-limited HTTP with error handling"""

    def parse_teams(self, match_name: str) -> Tuple[str, str]: ...
    def parse_timestamp(self, timestamp: Any) -> datetime: ...
```

Key features:
- **Lazy session**: `self.session` property creates `aiohttp.ClientSession` on first access
- **Rate limiting**: `asyncio.Semaphore(max_concurrent_requests)` (default 10)
- **Error recovery**: `reset_session()` closes and nulls session for lazy recreation
- **Stats tracking**: Request count, error count, last scrape timestamp

---

## ScraperEngine (`core/scraper_engine.py`)

The engine orchestrates all scrapers in a continuous loop:

1. **Register scrapers**: `engine.register_scraper(AdmiralScraper())`
2. **Run cycle**: All scrapers execute concurrently via `asyncio.gather`
3. **Bulk upsert**: Each bookmaker's results are bulk-upserted using `unnest()` arrays with `ON CONFLICT`
4. **Arbitrage detection**: After all scrapers complete, `ArbitrageDetector.detect_all()` runs
5. **Notifications**: New arbitrage → WebSocket broadcast + Telegram alert
6. **Sleep**: Wait `scrape_interval_seconds` before next cycle

### Bulk Processing Flow

```
scrape_bookmaker(scraper):
  matches = await scraper.scrape_all()          # List[ScrapedMatch]
  for match in matches:
    normalize team names (rapidfuzz)
    convert odds to dicts
  await db.bulk_upsert_matches_and_odds(data, bookmaker_id)
```

The bulk upsert uses PostgreSQL `unnest()` arrays for ~100x faster inserts compared to individual row upserts. Matches and odds are deduplicated before insert to avoid PK conflicts.

---

## Running Scrapers

### Full Application (API + Engine)
```bash
cd PythonScraper
python main.py                    # Default: API on port 8000 + engine
python main.py --host 0.0.0.0 --port 8080
python main.py --reload --debug   # Development mode
```

### Engine Only (No API)
```bash
python main.py --scraper-only
```

### Single Bookmaker Debug
```bash
python main.py --admiral                     # Admiral, all sports, infinite cycles
python main.py --mozzart --cycles 3          # 3 cycles then stop
python main.py --superbet --sport 1          # Football only
python main.py --maxbet --no-db              # Dry run (no database writes)
python main.py --topbet --debug              # Enable DEBUG logging (shows unmapped markets)
```

Single bookmaker mode uses INFO logging by default. Add `--debug` to see unmapped market debug messages.

### Testing Without Database
```bash
python test_scrapers.py                      # All scrapers
python test_scrapers.py --scraper admiral    # Single scraper
python test_scrapers.py --sport 1            # Football only
python test_scrapers.py --arbitrage          # Include arbitrage detection
```

### Cross-Bookmaker Audit
```bash
python audit_scrapers.py --sport 1                         # Football coverage
python audit_scrapers.py --sport 1 --match-detail          # With key comparison
python audit_scrapers.py --sport 1 --scraper admiral maxbet  # Specific scrapers
python audit_scrapers.py --sport 1 --dump                  # Raw odds dump
```

---

## Adding a New Scraper

1. Create `core/scrapers/<name>.py` inheriting from `BaseScraper`
2. Implement `get_base_url()`, `get_supported_sports()`, `scrape_sport()`
3. Map bookmaker's market names/codes to `BET_TYPES` IDs (1-124)
4. Ensure selections match the standard format conventions (see above)
5. Register in `SCRAPER_REGISTRY` in `main.py`
6. Add imports in `run_scraper_only()` in `main.py`
7. Run `audit_scrapers.py` to verify cross-bookmaker key consistency

### Mapping Markets

The most critical step is ensuring that odds keys `(bet_type_id, selection, margin)` are **identical** to other scrapers for the same real-world bet. Common pitfalls:

- **Handicap sign**: Must follow `positive = home advantage` convention
- **HT/FT separator**: Must use `/` (never `-` or `--`)
- **Goal ranges**: Use standard format (`0-2`, `3+`, not `0,1,2` or `over 2.5`)
- **Combo markets**: Use `&` separator, half prefixes `H1:`/`H2:`, `FT:` for full-time
- **OR markets**: Use `|` separator
- **Exact goals**: Use `T` prefix (`T0`, `T1`, not `0`, `1`)

### Adding Bet Types

If a new market doesn't map to any existing bet type (1-124), add it to `BET_TYPES` in `core/config.py`. Use `outcomes=1` for selection-based markets, `outcomes=2` for two-way, `outcomes=3` for three-way.

---

## Configuration (`core/config.py`)

### Settings (from .env)

| Setting | Default | Description |
|---------|---------|-------------|
| `DATABASE_URL` | localhost:5432 | PostgreSQL connection |
| `SCRAPE_INTERVAL_SECONDS` | 2.0 | Seconds between cycles |
| `REQUEST_TIMEOUT_SECONDS` | 30.0 | HTTP request timeout |
| `MAX_CONCURRENT_REQUESTS` | 10 | Per-bookmaker semaphore |
| `MATCH_SIMILARITY_THRESHOLD` | 75.0 | Fuzzy match threshold (0-100) |
| `MIN_PROFIT_PERCENTAGE` | 1.0 | Minimum arbitrage profit to report |
| `LOG_LEVEL` | INFO | Logging level |

### Constants

- **BOOKMAKERS**: 11 entries (7 active), maps ID → name/display/enabled
- **SPORTS**: 8 entries, maps ID → name/name_sr/time_window_minutes
- **BET_TYPES**: 124 entries (IDs 1-124), maps ID → name/description/outcomes

---

## Troubleshooting

### Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Mozzart timeout | Cloudflare session expired | Restart — Playwright creates new session |
| Duplicate key violation | Race condition in bulk upsert | Handled by `ON CONFLICT` — safe to ignore |
| MaxBet handicap mismatch | Sign convention | Already fixed — `_parse_param_handicaps_3way` negates |
| Admiral combo mismatch | Raw Serbian names | Already fixed — `_normalize_selection()` handles |
| TopBet HT/FT mismatch | Dashes instead of slashes | Already fixed — `_HTFT_BET_TYPES` conversion |
| "Unmapped" debug messages | Markets with no cross-bookmaker comparison | Normal — player props, quarters, niche combos |

### Debug Logging

Each scraper logs unmapped markets at DEBUG level. To see them:
```bash
python main.py --admiral --debug --cycles 1 --no-db
```

Most unmapped markets are intentionally unmapped (player-specific, quarter-specific, niche combos that no other bookmaker offers).
