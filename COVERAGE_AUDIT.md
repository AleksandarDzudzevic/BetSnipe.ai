# BetSnipe.ai — Live Coverage & Cross-Bookmaker Consistency Audit

**Date**: 2026-02-15
**Method**: Live API scraping via `audit_scrapers.py`
**Scrapers tested**: Admiral, Soccerbet, MaxBet, SuperBet, Merkur, TopBet, BalkanBet (Mozzart excluded — requires Playwright)

---

## 1. Coverage Summary

### Football (Sport ID=1)

| Bookmaker | Matches | Total Odds | Avg/Match | Bet Types |
|-----------|---------|------------|-----------|-----------|
| Admiral   | 414     | 239,010    | 577.3     | 91        |
| Soccerbet | 539     | 358,136    | 664.4     | 51        |
| MaxBet    | 653     | 364,419    | 558.1     | 56        |
| SuperBet  | 1,407   | 494,157    | 351.2     | 43        |
| Merkur    | 453     | 202,259    | 446.5     | 55        |
| TopBet    | 456     | 53,145     | 116.5     | 16        |
| BalkanBet | 786     | 385,179    | 490.0     | 46        |

**Key observations:**
- **Admiral** leads in bet type diversity (91 types) — only scraper with corners, cards, penalties
- **Soccerbet** leads in avg odds per match (664.4) — deepest combo market coverage
- **SuperBet** has the most matches (1,407) and improved avg/match (351.2) after combo market expansion
- **BalkanBet** added Feb 2026: strong coverage (490 avg/match, 46 types) via NSoft distribution API
- **TopBet** is far behind (116.5 avg/match, 16 types) — overview-only mode captures basics

### Basketball (Sport ID=2)

| Bookmaker | Matches | Total Odds | Avg/Match | Bet Types |
|-----------|---------|------------|-----------|-----------|
| Admiral   | 127     | 3,383      | 26.6      | 15        |
| SuperBet  | 129     | 4,692      | 36.4      | 14        |
| Soccerbet | 122     | 1,052      | 8.6       | 7         |
| MaxBet    | 84      | 1,149      | 13.7      | 4         |
| Merkur    | 66      | 408        | 6.2       | 4         |
| TopBet    | 0       | 0          | 0.0       | 0         |

**Key observations:**
- **SuperBet** and **Admiral** lead in basketball coverage
- **MaxBet/Merkur** only have 4 bet types each (winner, handicap, total, team total)
- **Soccerbet** has 7 types but low avg odds (8.6)
- **TopBet** has zero basketball matches

### Tennis (Sport ID=3)

| Bookmaker | Matches | Total Odds | Avg/Match | Bet Types |
|-----------|---------|------------|-----------|-----------|
| SuperBet  | 151     | 7,033      | 46.6      | 17        |
| Merkur    | 70      | 463        | 6.6       | 10        |
| MaxBet    | 61      | 731        | 12.0      | 12        |
| Admiral   | 58      | 437        | 7.5       | 8         |
| Soccerbet | 53      | 444        | 8.4       | 6         |
| TopBet    | 0       | 0          | 0.0       | 0         |

### Hockey (Sport ID=4)

| Bookmaker | Matches | Total Odds | Avg/Match | Bet Types |
|-----------|---------|------------|-----------|-----------|
| SuperBet  | 104     | 3,739      | 36.0      | 17        |
| Admiral   | 99      | 2,145      | 21.7      | 12        |
| MaxBet    | 97      | 1,213      | 12.5      | 13        |
| Soccerbet | 56      | 342        | 6.1       | 7         |
| Merkur    | 27      | 481        | 17.8      | 12        |
| TopBet    | 0       | 0          | 0.0       | 0         |

---

## 2. CRITICAL Cross-Bookmaker Key Mismatches

### BUG #1: TopBet HT/FT uses dashes instead of slashes (CRITICAL) — FIXED

**Status**: FIXED. Added `_HTFT_BET_TYPES` set and dash-to-slash conversion in both `_parse_selection_compressed` and `_parse_selection_full`.

**File**: `PythonScraper/core/scrapers/topbet.py`

---

### BUG #2: Admiral combo market selection format mismatch (CRITICAL) — FIXED

**Status**: FIXED. Added comprehensive `_normalize_selection()` function to `admiral.py` with 126 test cases.

**Changes**:
- `_normalize_part()`: Converts individual tokens (I→H1:, II→H2:, Tim1→H, Tim2→A, GGI→GG_H1, etc.)
- `_normalize_selection()`: Handles all bet-type-specific logic:
  - Goal range BTs (bt25,27-34): standalone digit → T-prefix
  - HT/FT simple (bt24,37,113): dash→slash
  - HT/FT combos (bt44,45): smart dash→slash in HT/FT part only, normalize goal part
  - HT/FT OR (bt124): v→| + dash→slash
  - OR combos (bt114): v→| + normalize parts
  - First goal (bt36): swap to result-first ordering
  - Combo BTs (bt35,38,39-41,46,114-116,119-124): I/II/Tim/GG/NG normalization
  - FT: prefix (bt35,119,120): add FT: to plain goal values when paired with H1:/H2:
- Both `_parse_selection` and `_parse_selection_htft` now call `_normalize_selection()`

**Verified result**: Admiral bt35 now matches other bookmakers:
```
bt35 [H1:0-1&H2:0-1]  3.20  3.10  3.15  3.00  ---  ---   ← All match
bt35 [H1:1+&FT:2+]    1.40  1.33  1.37  1.37  ---  ---   ← FT: prefix now matches
```

**File**: `PythonScraper/core/scrapers/admiral.py`

---

### BUG #3: Handicap margin sign convention inconsistency (MAJOR) — FIXED

**Status**: FIXED. Negated sign in MaxBet's `_parse_param_handicaps_3way` to match standard convention.

**Root cause**: MaxBet's raw API params for 3-way European handicap use the **opposite sign** from all other bookmakers. MaxBet raw: negative = home advantage. Standard (Admiral/Merkur/SuperBet): positive = home advantage.

**Standard convention**: `positive margin = home advantage` (home receives that many goals).

**Diagnosis**: Live data comparison of same match across bookmakers:
```
Galatasaray vs Juventus (MaxBet vs Merkur BEFORE fix):
  MaxBet m=-2.0: odd1=1.23  =  Merkur m=+2.0: odd1=1.25  ← SAME bet, OPPOSITE signs!
  MaxBet m=-1.0: odd1=1.70  =  Merkur m=+1.0: odd1=1.72  ← SAME bet, OPPOSITE signs!
  MaxBet m=+1.0: odd1=7.10  =  Merkur m=-1.0: odd1=6.90  ← SAME bet, OPPOSITE signs!
```

**Fix**: In `maxbet.py` `_parse_param_handicaps_3way`, changed `margin=float(margin_val)` to `margin=-float(margin_val)`. This is consistent with the 2-way handler which already negated.

**Verified AFTER fix** (106 common matches):
```
AEL Limassol vs Pafos:   m=-1.0  MaxBet=9.00  Admiral=8.90  ← MATCH
                          m=+1.0  MaxBet=1.83  Admiral=1.90  ← MATCH
AD Fafe vs Braga B:       m=-1.0  MaxBet=2.85  Admiral=2.91  ← MATCH
                          m=+1.0  MaxBet=1.14  Admiral=1.13  ← MATCH
Basketball (unchanged):   m=-1.5  MaxBet=1.90  Admiral=1.90  ← EXACT MATCH
```

**Bookmaker convention summary**:
| Bookmaker | Football 3-way | Basketball 2-way | Notes |
|-----------|---------------|-----------------|-------|
| Admiral   | ✓ standard    | ✓ standard      | Raw sBV, no transformation |
| MaxBet    | ✓ FIXED       | ✓ already correct| 3-way now negated; 2-way was already negated |
| Merkur    | ✓ standard    | ✓ already correct| Same code as MaxBet but raw API params differ |
| SuperBet  | ✓ standard    | ✓ standard      | Uses 2-way Asian HC for football |
| TopBet    | ✓ standard    | N/A             | Computes margin = home_hc - away_hc |
| Mozzart   | (untested)    | (untested)      | Uses Playwright, likely standard |

**File**: `PythonScraper/core/scrapers/maxbet.py` line ~824

---

### BUG #4: TopBet goal range format mismatch (MODERATE)

**Evidence** from live data:
```
bt25 [0-2]        ---   ---   ---   ---   ---  2.30   ← TopBet uses "0-2"
bt25 [1-2]       2.65  2.55  2.62  2.50  2.55   ---   ← Others use "1-2"

bt25 [2+]         ---   ---   ---   ---   ---  1.15   ← TopBet uses "2+"
bt25 [1+]         ---  1.04  1.06  1.06  1.05   ---   ← Others use "1+"
```

TopBet's goal range selections differ from other bookmakers for some ranges. `0-2` vs `1-2` and `2+` vs `1+` represent **different bets**, so these are not format mismatches — TopBet just offers different range groupings. However, matching ranges (like `3+`) should be compared.

---

### BUG #5: Admiral uses exact counts vs ranges for goal markets (MINOR) — FIXED

**Status**: FIXED. Admiral's bt25 standalone digits (`0`, `1`, `2`, `3`, `4`, `5`) are now remapped to bt26 (exact_goals) with T-prefix normalization.

**File**: `PythonScraper/core/scrapers/admiral.py` — `_parse_selection()` method

**Fix**: When `bt == 25` and the selection matches `^\d+$`, the odds are emitted as `bt26` instead. The `_normalize_selection()` function applies T-prefix to standalone digits for bt26, producing `T0`, `T1`, etc.

**Result**: Admiral now has 2,639 odds in bt26, matching MaxBet/Merkur/Soccerbet format.

---

## 3. Football Bet Type Coverage Matrix

Coverage indicates number of odds across all matches. `--` = not mapped.

| Bet Type | Name | Admiral | MaxBet | Merkur | Soccerbet | SuperBet | TopBet | BalkanBet |
|----------|------|---------|--------|--------|-----------|----------|--------|-----------|
| bt2 | 1X2 | 414 | 653 | 453 | 539 | 1,407 | 456 | 786 |
| bt3 | H1 1X2 | 414 | 653 | 358 | 532 | 915 | -- | 784 |
| bt4 | H2 1X2 | 414 | 653 | 356 | 532 | 915 | -- | 767 |
| bt5 | Total O/U | 2,102 | 3,160 | 2,128 | 2,142 | 6,782 | -- | -- |
| bt6 | H1 Total | 1,155 | 1,913 | 1,073 | 1,585 | 3,781 | -- | -- |
| bt7 | H2 Total | 1,238 | 1,932 | 1,050 | 1,596 | 3,781 | -- | -- |
| bt8 | BTTS | 414 | 644 | 430 | 539 | 1,309 | 455 | 764 |
| bt9 | Handicap | 1,401 | 1,923 | 439 | -- | 4,273 | -- | 1,310 |
| bt13 | Double Chance | 405 | 633 | 434 | 526 | 1,404 | -- | 760 |
| bt14 | Draw No Bet | 397 | 631 | 421 | 533 | 1,392 | -- | 607 |
| bt15 | Odd/Even | 392 | 644 | 336 | 523 | 1,312 | -- | 192 |
| bt16 | Double Win | 392 | 644 | 355 | 521 | -- | -- | 621 |
| bt17 | Win to Nil | 380 | 644 | 355 | 523 | -- | -- | 621 |
| bt18 | First Goal | 413 | 644 | 334 | -- | 793 | -- | 542 |
| bt19 | Half More Goals | 392 | 644 | 358 | 532 | 912 | -- | 784 |
| bt20 | H1 DC | 389 | 631 | 331 | 412 | 915 | -- | 619 |
| bt21 | H1 DNB | 380 | 643 | 334 | 517 | 521 | -- | -- |
| bt23 | Correct Score | 10,117 | 14,704 | 7,641 | 13,075 | 33,825 | -- | 7,800 |
| bt24 | HT/FT | 3,726 | 5,796 | 3,222 | 4,788 | 11,655 | 3,740 | 9,816 |
| bt25 | Goal Range | 11,088 | 9,784 | 6,463 | 8,571 | 13,815 | 4,445 | 28,572 |
| bt26 | Exact Goals | 2,639 | 3,196 | 1,670 | 2,695 | 4,186 | -- | -- |
| bt27 | Team 1 Goals | 4,695 | 11,801 | 7,030 | 10,354 | 2,108 | 4,142 | 8,135 |
| bt28 | Team 2 Goals | 4,695 | 11,754 | 7,031 | 10,303 | 2,108 | 3,937 | 8,040 |
| bt29 | H1 Goal Range | -- | -- | -- | -- | -- | -- | 9,988 |
| bt30 | H2 Goal Range | -- | -- | -- | -- | -- | -- | 10,039 |
| bt31 | Team1 Goals H1 | -- | -- | -- | -- | -- | -- | 4,576 |
| bt32 | Team2 Goals H1 | -- | -- | -- | -- | -- | -- | 4,450 |
| bt33 | Team1 Goals H2 | -- | -- | -- | -- | -- | -- | 4,608 |
| bt34 | Team2 Goals H2 | -- | -- | -- | -- | -- | -- | 4,575 |
| bt35 | Goals H1&H2 | 23,012 | 31,491 | 17,369 | 26,564 | -- | 4,462 | 46,018 |
| bt36 | First Goal+Result | -- | -- | -- | -- | 5,484 | -- | 3,794 |
| bt37 | HT/FT DC | 7,793 | 17,388 | 9,017 | 14,061 | 8,235 | -- | -- |
| bt38 | Result+Total | 24,748 | 34,480 | 18,836 | 34,739 | 42,038 | 4,446 | 38,970 |
| bt39 | Result Combo | -- | -- | -- | -- | -- | -- | 11,178 |
| bt40 | Result+Half Goals | -- | -- | -- | -- | -- | -- | 1,902 |
| bt41 | DC+Total | 27,360 | 28,323 | 15,135 | 25,057 | 43,260 | 4,358 | 32,799 |
| bt42 | DC+Half Goals | -- | -- | -- | -- | 5,478 | -- | 2,853 |
| bt43 | DC Combo | -- | -- | -- | -- | -- | -- | 14,895 |
| bt44 | HT/FT+Total | 29,359 | 47,324 | 23,806 | 55,230 | 103,410 | 4,046 | 37,260 |
| bt45 | HT/FT Combo | -- | -- | -- | -- | -- | -- | 4,968 |
| bt46 | BTTS Combo | 11,673 | 27,150 | 16,575 | 25,068 | 37,111 | 4,166 | 45,950 |
| bt48 | Team1 Total | 1,297 | 644 | 430 | -- | 4,270 | -- | -- |
| bt49 | Team2 Total | 1,138 | 644 | 430 | -- | 4,229 | -- | -- |
| bt75 | H2 DC | 390 | 631 | 331 | 412 | 915 | -- | -- |
| bt76 | H2 DNB | 380 | 643 | 334 | 515 | 521 | -- | -- |
| bt77 | H1 O/E | 380 | -- | -- | -- | 521 | -- | 192 |
| bt78 | H2 O/E | 380 | -- | -- | -- | -- | -- | 192 |
| bt79 | H1 CS | 3,588 | 8,290 | 4,304 | 8,336 | 5,920 | -- | 1,536 |
| bt80 | EU Handicap 3-way | -- | -- | -- | -- | -- | -- | 1,188 |
| bt89 | Last Goal | -- | -- | -- | -- | -- | -- | 192 |
| bt100 | First Goal H1 | -- | -- | -- | -- | -- | -- | 192 |
| bt113 | HT/FT NOT | 1,770 | 2,939 | 1,555 | 2,541 | -- | -- | -- |
| bt114 | OR Combos | 6,574 | 7,712 | 4,062 | 11,692 | 16,890 | -- | 7,920 |
| bt118 | CS Combo | -- | -- | -- | -- | -- | -- | 1,464 |
| bt119 | Team1 H1&H2 | 5,610 | 6,471 | 4,257 | 7,704 | -- | -- | 4,149 |
| bt120 | Team2 H1&H2 | 5,347 | 6,020 | 4,078 | 7,630 | -- | -- | 4,149 |
| bt121 | Win Margin | 780 | 3,864 | 2,004 | 3,790 | -- | -- | -- |
| bt123 | HT Result+BTTS | 2,916 | 3,864 | 2,004 | 3,126 | 3,126 | -- | -- |
| bt124 | HT/FT OR | 3,136 | 5,152 | 3,006 | 4,775 | 2,814 | -- | 13,662 |

| bt84 | Corner Total | Admiral | -- | -- | -- | SuperBet | -- | -- |
| bt88 | Card Total | Admiral | -- | -- | -- | SuperBet | -- | -- |
| bt94 | H1 Corner Total | Admiral | -- | -- | -- | SuperBet | -- | -- |

**Admiral-only markets** (most corners, cards, penalties): bt83, bt85-87, bt89-98, bt105-112 — limited cross-bookmaker comparison (SuperBet now covers bt84, bt88, bt94).

---

## 4. Key Consistency Findings (Football)

### Markets with VERIFIED cross-bookmaker consistency

These markets produce identical keys across all bookmakers that offer them:

| Market | Key Format | Verified Across |
|--------|-----------|----------------|
| bt2 (1X2) | `bt2, sel='', m=0` | All 6 |
| bt5 (Total O/U) | `bt5, sel='', m=2.5` | 5 (all except TopBet) |
| bt8 (BTTS) | `bt8, sel='', m=0, odd1=yes, odd2=no` | All 6 |
| bt13 (Double Chance) | `bt13, sel='', m=0` | 5 |
| bt14 (Draw No Bet) | `bt14, sel='', m=0` | 5 |
| bt23 (Correct Score) | `bt23, sel='1:0', m=0` | 5 (format `X:Y` consistent) |
| bt79 (H1 Correct Score) | `bt79, sel='0:0', m=0` | 4 |

### Markets with CONFIRMED mismatches

| Market | Issue | Bookmakers Affected |
|--------|-------|-------------------|
| bt24 (HT/FT) | TopBet: `1-1` vs others: `1/1` | TopBet vs all others |
| bt35 (Goals H1&H2) | Admiral: `0-1I&0-1II` vs others: `H1:0-1&H2:0-1` | Admiral vs MaxBet/Soccerbet/Merkur |
| bt9 (Handicap) | ~~Sign convention varies~~ **FIXED** | MaxBet 3-way negated to match standard |
| bt38 (Result+Total) | Admiral raw format differs | Admiral vs MaxBet/Soccerbet/Merkur |
| bt41 (DC+Total) | Admiral raw format differs | Admiral vs MaxBet/Soccerbet/Merkur |
| bt44 (HT/FT+Total) | Admiral raw + TopBet raw | Admiral + TopBet vs MaxBet/Soccerbet/Merkur |
| bt46 (BTTS Combo) | Admiral raw format differs | Admiral vs MaxBet/Soccerbet/Merkur |

---

## 5. Recommended Fixes (Priority Order)

### P0 — CRITICAL (blocks cross-bookmaker comparison)

#### Fix 1: TopBet HT/FT selection format

**File**: `PythonScraper/core/scrapers/topbet.py`

In `_parse_selection_compressed` (line 293) and `_parse_selection_full` (line 408), add dash-to-slash conversion for HT/FT markets (bt24, bt37, bt44, bt45):

```python
# In _parse_selection_compressed, after line 300:
if bt_id in (24, 37, 44, 45, 113, 124):
    code = code.replace("-", "/")
```

Same fix in `_parse_selection_full`.

#### Fix 2: Admiral combo selection normalization

**File**: `PythonScraper/core/scrapers/admiral.py`

Create a normalization function for Admiral's combo market raw names:

```python
@staticmethod
def _normalize_admiral_combo_sel(name: str) -> str:
    """Convert Admiral combo format to standard.
    'Više 2.5I&Više 1.5II' → 'H1:3+&H2:2+'
    '0-1I&0-1II' → 'H1:0-1&H2:0-1'
    """
    # Replace I/II suffixes with H1:/H2: prefixes
    # Handle various Admiral naming patterns
    ...
```

Apply this to all `'sel'` parser calls for combo bet types (bt35, bt38, bt41, bt44, bt46, bt114, bt115, bt116, bt119, bt120, bt121, bt122, bt123).

### P1 — MAJOR (affects handicap matching)

#### Fix 3: Handicap sign convention standardization — FIXED

Negated MaxBet `_parse_param_handicaps_3way` sign. Standard: **positive = home advantage**.
Verified across 106 common football matches + 18 common basketball matches.

### P2 — MODERATE (coverage gaps)

#### Fix 4: SuperBet missing markets — FIXED

**Status**: FIXED. SuperBet expanded from 35→43 bet types, 240→351 avg odds/match (+46%).

**Changes** (`PythonScraper/core/scrapers/superbet.py`):
- Added 3 simple markets: bt84 (total corners), bt94 (H1 corners), bt88 (total cards)
- Added 9 combo market handlers: bt114 (2 OR patterns), bt124 (HT/FT OR), bt37 (HT/FT DC), bt44 (HT/FT+range), bt36 (first goal+result), bt41 (DC+range), bt42 (DC+half goals)
- Added 6 parser methods: `_parse_result_or_total`, `_parse_htft_or`, `_parse_htft_dc`, `_parse_htft_range`, `_parse_dc_range`, `_parse_dc_half_goals`

**Still missing** (confirmed not in SuperBet's API): bt16 (Double Win), bt17 (Win to Nil), bt113 (HT/FT NOT), bt119-120 (team H1&H2 combos).

#### Fix 5: Soccerbet missing markets — CLOSED (not fixable)

**Status**: CLOSED. Soccerbet's API platform does not support param-based markets.
- bt9 (Handicap) — Requires `params` dict which Soccerbet doesn't have (only flat `betMap` with fixed margins)
- bt18 (First Goal) — Actually IS mapped (codes 204/205/206 in `FOOTBALL_3WAY`). False positive in original audit.
- bt48/49 (Team Total) — Requires `params` dict (`homeOverUnder`/`awayOverUnder`). Not available.

#### Fix 6: TopBet coverage expansion — CLOSED (low ROI)

**Status**: CLOSED. Overview mode (1 API call) returns 16 bet types. Full mode would add 17 more but requires ~500 individual API calls per sport (500x increase). The extra markets (bt3, bt4, bt13, bt14, bt15, bt23, bt9, etc.) are already covered by 5-6 other bookmakers. TopBet's value is cross-comparison on the 16 basics it provides.

### P3 — MINOR (cosmetic)

#### Fix 7: Admiral exact goals remapping — FIXED

**Status**: FIXED. Admiral bt25 standalone digits now remap to bt26 with T-prefix. See BUG #5 above for details.

---

## 6. Verification Methodology

### How the audit was performed

1. **Live scraping**: Each scraper ran against its real API endpoint, no mocks
2. **Key extraction**: Every scraped odd was converted to `(bet_type_id, selection, margin)` key
3. **Fuzzy matching**: Matches across bookmakers were paired using `rapidfuzz` with 70% similarity threshold
4. **Key comparison**: For each paired match, all keys were compared across bookmakers
5. **818 match groups** were analyzed for football alone

### Audit script

The audit script is at `PythonScraper/audit_scrapers.py`. Usage:

```bash
# Full football audit with cross-comparison
python audit_scrapers.py --sport 1 --match-detail --match-limit 5

# Quick coverage check
python audit_scrapers.py --sport 1

# Specific scrapers
python audit_scrapers.py --sport 1 --scraper admiral soccerbet maxbet

# Dump raw odds
python audit_scrapers.py --sport 1 --dump
```

---

## 7. Next Steps

1. ~~**Fix TopBet HT/FT**~~ (P0) — **DONE** (BUG #1)
2. ~~**Fix Admiral combo selections**~~ (P0) — **DONE** (BUG #2)
3. ~~**Standardize handicap signs**~~ (P1) — **DONE** (BUG #3)
4. ~~**Expand SuperBet mappings**~~ (P2) — **DONE** (Fix 4: 35→43 BTs, +46% avg odds)
5. ~~**Admiral exact goals remapping**~~ (P3) — **DONE** (Fix 7: bt25→bt26, 2,639 odds)
6. ~~**Soccerbet missing markets**~~ (P2) — **CLOSED** (API doesn't support param markets; bt18 was already mapped)
7. ~~**TopBet coverage expansion**~~ (P2) — **CLOSED** (low ROI: 500x API calls for markets covered elsewhere)
8. ~~**Add BalkanBet scraper**~~ — **DONE** (Feb 2026: 786 matches, 385K odds, 46 bet types, 490 avg/match)
