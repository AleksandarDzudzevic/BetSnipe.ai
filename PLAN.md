# BetSnipe.ai - Project Plan

## Current Status (Feb 2026)

### Backend - WORKING
- [x] 7 bookmaker scrapers active (Admiral, Soccerbet, Mozzart, Maxbet, Superbet, Merkur, Topbet)
- [x] Bulk database operations (~2 queries per 500 matches)
- [x] Arbitrage detection after each scrape cycle
- [x] FastAPI with REST + WebSocket endpoints
- [x] Supabase integration with RLS enabled
- [x] Timing logs for each bookmaker

### Database - OPTIMIZED
- [x] Unique constraint on matches for fast ON CONFLICT upserts
- [x] Composite indexes for bulk lookups
- [x] Foreign key indexes added
- [x] RLS enabled with public read policies
- [x] Views fixed (SECURITY INVOKER)

### Mobile App - IN PROGRESS
- [x] Expo/React Native setup
- [x] Basic screens (Home, Arbitrage, Matches, Settings)
- [x] Supabase Auth integration
- [x] API service layer
- [ ] Full testing with live backend
- [ ] Push notifications testing
- [ ] UI polish

---

## Performance Metrics

| Bookmaker | Matches | Scrape Time | DB Time | Total |
|-----------|---------|-------------|---------|-------|
| Topbet | ~700 | ~1s | ~1s | ~2s |
| Admiral | ~1200 | ~15s | ~1s | ~16s |
| Soccerbet | ~1100 | ~15s | ~1s | ~16s |
| Maxbet | ~1100 | ~17s | ~1s | ~18s |
| Merkur | ~800 | ~20s | ~1s | ~21s |
| Superbet | ~1300 | ~80s | ~1s | ~81s |
| Mozzart | ~varies | ~varies | ~1s | varies |

**Full cycle**: ~80-90s for all 7 bookmakers (limited by Superbet API speed)

---

## Next Steps

### High Priority
1. [ ] Test arbitrage detection with lower MIN_PROFIT_PERCENTAGE (0.5%)
2. [ ] Set up Telegram notifications
3. [ ] Test mobile app with live backend
4. [ ] Deploy backend to production (Railway/Render/VPS)

### Medium Priority
5. [ ] Add more bet types (Double Chance, Draw No Bet)
6. [ ] Improve Mozzart scraper reliability
7. [ ] Add odds movement tracking/alerts
8. [ ] Implement user watchlist notifications

### Low Priority
9. [ ] Re-enable Meridian scraper
10. [ ] Add 1xBet, LVBet scrapers
11. [ ] Historical arbitrage analytics
12. [ ] Profit tracking for users

---

## Known Issues

1. **Superbet slow** - Their API is slow, taking ~80s per cycle
2. **Mozzart Playwright** - Requires Chromium, adds overhead
3. **Duplicate matches** - Some scrapers return duplicates (now handled with deduplication)

---

## Environment Setup

```bash
# Required
DATABASE_URL=postgresql://...
MIN_PROFIT_PERCENTAGE=1.0

# Optional
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
SUPABASE_JWT_SECRET=...
SUPABASE_SERVICE_ROLE_KEY=...
```

---

## Quick Commands

```bash
# Start everything
cd PythonScraper && python main.py

# Start mobile app
cd MobileApp && npx expo start

# Check database
# Use Supabase MCP or dashboard
```
