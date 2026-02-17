# Continue: Fix P2 (Coverage Gaps) and P3 (Cosmetic) from Scraper Audit

## Context

We completed a full live coverage & cross-bookmaker consistency audit of all 7 bookmaker scrapers. Three critical/major bugs were found and fixed:

- **BUG #1 FIXED**: TopBet HT/FT dash→slash (`topbet.py`)
- **BUG #2 FIXED**: Admiral combo selection normalization (`admiral.py` — `_normalize_selection()`)
- **BUG #3 FIXED**: MaxBet handicap sign convention (`maxbet.py` — negated `_parse_param_handicaps_3way`)

Full audit results are in `COVERAGE_AUDIT.md`. The audit script is at `PythonScraper/audit_scrapers.py`.

## What to fix now

### P2 — Coverage Gaps

#### Fix 4: SuperBet missing markets
SuperBet has 1,407 football matches but only 240 avg odds/match (vs 664 for Soccerbet). Many combo markets exist in the API but aren't mapped.

**Approach**:
1. Run SuperBet scraper with DEBUG logging to see unmapped market names: `python test_scrapers.py --scraper superbet --sport 1 2>&1 | grep "Unmapped"`
2. Map missing markets to existing bet_type_ids (75-124 range for combos, corners, cards)
3. Missing markets likely include: bt16 (Double Win), bt17 (Win to Nil), bt37 (HT/FT DC), bt113 (HT/FT NOT), bt114 (OR Combos), bt119-124 (H1&H2 combos, win margin, etc.)
4. SuperBet file: `PythonScraper/core/scrapers/superbet.py`
5. After mapping, verify cross-bookmaker consistency against Admiral/Soccerbet/MaxBet

#### Fix 5: Soccerbet missing markets (LOW PRIORITY)
Soccerbet is missing bt9 (Handicap), bt18 (First Goal), bt48/49 (Team Total). These likely DON'T EXIST on Soccerbet's API — it has no param-based markets. Skip unless investigation reveals otherwise.

#### Fix 6: TopBet coverage expansion (LOW PRIORITY)
TopBet only has 16 bet types via overview mode. Full format (WEB_SINGLE_MATCH) gets 30 types but requires individual event fetches (slow). Consider adding more market mappings to overview dispatch maps if the API offers them.

### P3 — Cosmetic

#### Fix 7: Admiral exact goals remapping
Admiral's bt25 (Goal Range) includes exact count selections (`0`, `1`, `2`, `3`, `4`, `5`) that should map to bt26 (exact_goals) instead. Only the range selections (`0-1`, `1-2`, `2-3`, `3+`, etc.) belong in bt25.

**File**: `PythonScraper/core/scrapers/admiral.py` — look at the `_parse_selection` output for bt25 and split exact values to bt26.

## Key conventions (MUST follow)

- **Standard: positive margin = home advantage** (home receives that many goals/points)
- **Selection format**: `H1:` / `H2:` prefixes for half-specific, `H` / `A` for home/away team, `FT:` prefix for full-time values in combos, `&` separator for combos, `|` for OR, `/` for HT/FT (never `-`)
- **Cross-bookmaker verification**: After any mapping change, verify the same real-world bet produces identical `(bet_type_id, selection, margin)` keys across all bookmakers
- Config with all 124 bet type IDs: `PythonScraper/core/config.py`

## How to verify

```bash
cd PythonScraper

# Test single scraper
python test_scrapers.py --scraper superbet --sport 1

# Run cross-bookmaker audit
python audit_scrapers.py --sport 1 --match-detail --match-limit 5

# Quick coverage check
python audit_scrapers.py --sport 1
```
