#!/usr/bin/env python3
"""
BetSnipe.ai — Scraper Coverage & Cross-Bookmaker Consistency Audit

Runs scrapers against live APIs, dumps full odds detail, and compares
keys across bookmakers to find coverage gaps and consistency issues.

Usage:
    python audit_scrapers.py --sport 1                # Football audit
    python audit_scrapers.py --sport 2                # Basketball audit
    python audit_scrapers.py --sport 1 --scraper admiral soccerbet  # Subset
    python audit_scrapers.py --sport 1 --dump         # Also dump raw odds per match
    python audit_scrapers.py --sport 1 --match-detail # Dump cross-bookmaker comparison
"""

import argparse
import asyncio
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from rapidfuzz import fuzz
from core.config import BET_TYPES, SPORTS
from core.scrapers.admiral import AdmiralScraper
from core.scrapers.soccerbet import SoccerbetScraper
from core.scrapers.maxbet import MaxbetScraper
from core.scrapers.superbet import SuperbetScraper
from core.scrapers.merkur import MerkurScraper
from core.scrapers.topbet import TopbetScraper

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce noise
logging.getLogger('aiohttp').setLevel(logging.ERROR)

SCRAPERS = {
    'admiral':   AdmiralScraper,
    'soccerbet': SoccerbetScraper,
    'maxbet':    MaxbetScraper,
    'superbet':  SuperbetScraper,
    'merkur':    MerkurScraper,
    'topbet':    TopbetScraper,
    # 'mozzart' excluded: requires Playwright
}

SPORT_NAMES = {
    1: 'Football',
    2: 'Basketball',
    3: 'Tennis',
    4: 'Hockey',
    5: 'Table Tennis',
}


@dataclass
class OddsKey:
    """Represents a unique odds key for cross-bookmaker comparison."""
    bet_type_id: int
    selection: str
    margin: float

    def __hash__(self):
        return hash((self.bet_type_id, self.selection, self.margin))

    def __eq__(self, other):
        return (self.bet_type_id == other.bet_type_id and
                self.selection == other.selection and
                self.margin == other.margin)

    def __repr__(self):
        parts = [f"bt{self.bet_type_id}"]
        if self.selection:
            parts.append(f"sel='{self.selection}'")
        if self.margin:
            parts.append(f"m={self.margin}")
        return " | ".join(parts)


@dataclass
class MatchOdds:
    """All odds for a single match from a single bookmaker."""
    bookmaker: str
    team1: str
    team2: str
    keys: Set[OddsKey] = field(default_factory=set)
    odds_detail: List[dict] = field(default_factory=list)  # full detail for dump

    @property
    def match_label(self):
        return f"{self.team1} vs {self.team2}"


def normalize_team(name: str) -> str:
    """Normalize team name for matching."""
    return name.strip().lower()


def match_similarity(t1a: str, t2a: str, t1b: str, t2b: str) -> float:
    """Score similarity between two matches (team pairs)."""
    score1 = fuzz.ratio(normalize_team(t1a), normalize_team(t1b))
    score2 = fuzz.ratio(normalize_team(t2a), normalize_team(t2b))
    return (score1 + score2) / 2


async def run_scraper(name: str, sport_id: int) -> List[MatchOdds]:
    """Run a single scraper and return MatchOdds objects."""
    scraper_class = SCRAPERS[name]
    scraper = scraper_class()

    try:
        if sport_id not in scraper.get_supported_sports():
            print(f"  {name}: Sport {sport_id} not supported")
            return []

        matches = await scraper.scrape_sport(sport_id)

        results = []
        for m in matches:
            mo = MatchOdds(bookmaker=name, team1=m.team1, team2=m.team2)
            for o in m.odds:
                key = OddsKey(
                    bet_type_id=o.bet_type_id,
                    selection=o.selection,
                    margin=o.margin,
                )
                mo.keys.add(key)
                mo.odds_detail.append({
                    'bt': o.bet_type_id,
                    'sel': o.selection,
                    'margin': o.margin,
                    'odd1': o.odd1,
                    'odd2': o.odd2,
                    'odd3': o.odd3,
                })
            results.append(mo)

        return results

    finally:
        await scraper.close()


def group_cross_bookmaker(all_results: Dict[str, List[MatchOdds]],
                          threshold: float = 70.0) -> List[Dict[str, MatchOdds]]:
    """Group matches across bookmakers by team name similarity."""
    groups: List[Dict[str, MatchOdds]] = []

    # Start with the bookmaker that has the most matches as anchor
    anchor_name = max(all_results.keys(), key=lambda k: len(all_results[k]))
    anchor_matches = all_results[anchor_name]

    for anchor_match in anchor_matches:
        group = {anchor_name: anchor_match}

        for other_name, other_matches in all_results.items():
            if other_name == anchor_name:
                continue

            best_score = 0
            best_match = None

            for om in other_matches:
                score = match_similarity(
                    anchor_match.team1, anchor_match.team2,
                    om.team1, om.team2
                )
                if score > best_score:
                    best_score = score
                    best_match = om

            if best_match and best_score >= threshold:
                group[other_name] = best_match

        if len(group) >= 2:
            groups.append(group)

    return groups


def analyze_coverage(all_results: Dict[str, List[MatchOdds]]) -> Dict[str, dict]:
    """Analyze per-bookmaker coverage statistics."""
    stats = {}

    for name, matches in all_results.items():
        if not matches:
            stats[name] = {
                'match_count': 0,
                'total_odds': 0,
                'avg_odds_per_match': 0,
                'bet_types_seen': set(),
                'bt_distribution': defaultdict(int),
            }
            continue

        total_odds = sum(len(m.keys) for m in matches)
        bt_seen = set()
        bt_dist = defaultdict(int)

        for m in matches:
            for k in m.keys:
                bt_seen.add(k.bet_type_id)
                bt_dist[k.bet_type_id] += 1

        stats[name] = {
            'match_count': len(matches),
            'total_odds': total_odds,
            'avg_odds_per_match': total_odds / len(matches) if matches else 0,
            'bet_types_seen': bt_seen,
            'bt_distribution': bt_dist,
        }

    return stats


def analyze_cross_bookmaker(groups: List[Dict[str, MatchOdds]]) -> dict:
    """Analyze cross-bookmaker key consistency."""
    mismatches = []
    selection_issues = []

    # For each match group, find bet_type_ids that appear in multiple bookmakers
    for group in groups:
        if len(group) < 2:
            continue

        bookmakers = list(group.keys())
        match_label = next(iter(group.values())).match_label

        # Collect all bet_type_ids present across bookmakers
        bt_by_bookmaker: Dict[int, Dict[str, Set[OddsKey]]] = defaultdict(lambda: defaultdict(set))

        for bm_name, mo in group.items():
            for key in mo.keys:
                bt_by_bookmaker[key.bet_type_id][bm_name].add(key)

        # For each bet_type_id present in 2+ bookmakers, compare keys
        for bt_id, bm_keys in bt_by_bookmaker.items():
            if len(bm_keys) < 2:
                continue

            bt_name = BET_TYPES.get(bt_id, {}).get('name', f'unknown_{bt_id}')
            bt_outcomes = BET_TYPES.get(bt_id, {}).get('outcomes', 0)

            # For selection-based markets (outcomes=1), compare selection strings
            if bt_outcomes == 1:
                all_selections_by_bm = {}
                for bm_name, keys in bm_keys.items():
                    all_selections_by_bm[bm_name] = {k.selection for k in keys}

                # Find selections that exist in some but not all bookmakers
                all_sels = set()
                for sels in all_selections_by_bm.values():
                    all_sels |= sels

                for sel in sorted(all_sels):
                    present_in = [bm for bm, sels in all_selections_by_bm.items() if sel in sels]
                    missing_from = [bm for bm in all_selections_by_bm if bm not in present_in]

                    # Only flag if it's present in some but missing from others
                    # (don't flag if just one bookmaker has extra exotic selections)
                    if missing_from and len(present_in) >= 2:
                        selection_issues.append({
                            'match': match_label,
                            'bet_type': f"bt{bt_id} ({bt_name})",
                            'selection': sel,
                            'present_in': present_in,
                            'missing_from': missing_from,
                        })

            # For margin-based markets (O/U, handicap), compare margins
            else:
                all_margins_by_bm = {}
                for bm_name, keys in bm_keys.items():
                    all_margins_by_bm[bm_name] = {k.margin for k in keys}

                # Find common margins (present in 2+ bookmakers)
                all_margins = set()
                for margins in all_margins_by_bm.values():
                    all_margins |= margins

                for margin in sorted(all_margins):
                    present_in = [bm for bm, margins in all_margins_by_bm.items() if margin in margins]
                    if len(present_in) >= 2:
                        # This is fine — same margin across multiple bookmakers
                        pass
                    # Check for sign convention issues (e.g., -1.5 vs 1.5)
                    neg_margin = -margin if margin != 0 else None
                    if neg_margin is not None and neg_margin in all_margins:
                        # Both positive and negative versions exist — possible sign convention issue
                        for bm_name, margins in all_margins_by_bm.items():
                            if margin in margins and neg_margin not in margins:
                                mismatches.append({
                                    'match': match_label,
                                    'bet_type': f"bt{bt_id} ({bt_name})",
                                    'issue': f"Sign convention: {bm_name} has margin={margin} "
                                             f"but others have margin={neg_margin}",
                                    'bookmakers': list(all_margins_by_bm.keys()),
                                })

    return {
        'mismatches': mismatches,
        'selection_issues': selection_issues,
    }


def print_coverage_report(stats: Dict[str, dict], sport_name: str):
    """Print coverage statistics."""
    print(f"\n{'='*80}")
    print(f"  COVERAGE REPORT — {sport_name}")
    print(f"{'='*80}")

    # Summary table
    print(f"\n  {'Bookmaker':<12} {'Matches':>8} {'Total Odds':>12} {'Avg/Match':>10} {'Bet Types':>10}")
    print(f"  {'-'*12} {'-'*8} {'-'*12} {'-'*10} {'-'*10}")

    for name in sorted(stats.keys()):
        s = stats[name]
        print(f"  {name:<12} {s['match_count']:>8} {s['total_odds']:>12} "
              f"{s['avg_odds_per_match']:>10.1f} {len(s['bet_types_seen']):>10}")

    # Bet type coverage matrix
    all_bt = set()
    for s in stats.values():
        all_bt |= s['bet_types_seen']

    print(f"\n  Bet Type Coverage Matrix:")
    print(f"  {'Bet Type':<6} {'Name':<30}", end="")
    for name in sorted(stats.keys()):
        print(f" {name[:6]:>6}", end="")
    print()
    print(f"  {'-'*6} {'-'*30}", end="")
    for _ in sorted(stats.keys()):
        print(f" {'-'*6}", end="")
    print()

    for bt_id in sorted(all_bt):
        bt_info = BET_TYPES.get(bt_id, {})
        bt_name = bt_info.get('name', '?')[:30]
        print(f"  bt{bt_id:<3} {bt_name:<30}", end="")
        for name in sorted(stats.keys()):
            count = stats[name]['bt_distribution'].get(bt_id, 0)
            if count > 0:
                print(f" {count:>6}", end="")
            else:
                print(f" {'--':>6}", end="")
        print()


def print_cross_bookmaker_report(analysis: dict, groups: List[Dict[str, MatchOdds]]):
    """Print cross-bookmaker consistency findings."""
    print(f"\n{'='*80}")
    print(f"  CROSS-BOOKMAKER CONSISTENCY REPORT")
    print(f"{'='*80}")

    print(f"\n  Matched groups: {len(groups)} matches found across 2+ bookmakers")

    # Key count comparison for matched groups
    if groups:
        print(f"\n  Sample matched matches (first 10):")
        for i, group in enumerate(groups[:10]):
            anchor = next(iter(group.values()))
            print(f"\n    [{i+1}] {anchor.match_label}")
            for bm_name in sorted(group.keys()):
                mo = group[bm_name]
                key_count = len(mo.keys)
                print(f"        {bm_name:<12}: {key_count:>4} odds")

    # Mismatches
    mismatches = analysis['mismatches']
    if mismatches:
        print(f"\n  MARGIN/SIGN MISMATCHES ({len(mismatches)} found):")
        for m in mismatches[:20]:
            print(f"    {m['match']}")
            print(f"      {m['bet_type']}: {m['issue']}")
    else:
        print(f"\n  No margin/sign mismatches found.")

    # Selection format issues (top issues)
    sel_issues = analysis['selection_issues']
    if sel_issues:
        # Aggregate: which bet types have the most issues?
        bt_issue_count = defaultdict(int)
        for s in sel_issues:
            bt_issue_count[s['bet_type']] += 1

        print(f"\n  SELECTION AVAILABILITY DIFFERENCES ({len(sel_issues)} total across all matches):")
        print(f"  (Top bet types with differences:)")
        for bt, count in sorted(bt_issue_count.items(), key=lambda x: -x[1])[:15]:
            print(f"    {bt}: {count} selection differences across matches")

        # Show a few examples
        print(f"\n  Example selection differences (first 10):")
        for s in sel_issues[:10]:
            print(f"    {s['bet_type']} sel='{s['selection']}': "
                  f"present in {s['present_in']}, missing from {s['missing_from']}")
    else:
        print(f"\n  No selection format differences found.")


def dump_match_odds(match_odds: MatchOdds):
    """Dump all odds for a single match."""
    print(f"\n  [{match_odds.bookmaker}] {match_odds.match_label} ({len(match_odds.keys)} odds)")
    sorted_detail = sorted(match_odds.odds_detail, key=lambda x: (x['bt'], x['sel'], x['margin']))
    for d in sorted_detail:
        bt_name = BET_TYPES.get(d['bt'], {}).get('name', '?')
        sel_str = f" sel='{d['sel']}'" if d['sel'] else ""
        margin_str = f" m={d['margin']}" if d['margin'] else ""
        o2 = f" / {d['odd2']:.2f}" if d['odd2'] else ""
        o3 = f" / {d['odd3']:.2f}" if d['odd3'] else ""
        print(f"    bt{d['bt']:>3} {bt_name:<25}{sel_str}{margin_str} | {d['odd1']:.2f}{o2}{o3}")


def dump_cross_comparison(group: Dict[str, MatchOdds]):
    """Dump side-by-side comparison for a matched group."""
    anchor = next(iter(group.values()))
    print(f"\n{'='*80}")
    print(f"  CROSS-COMPARISON: {anchor.match_label}")
    print(f"  Bookmakers: {', '.join(sorted(group.keys()))}")
    print(f"{'='*80}")

    # Collect all keys across all bookmakers
    all_keys: Set[OddsKey] = set()
    for mo in group.values():
        all_keys |= mo.keys

    # Build lookup: (bet_type_id, selection, margin) -> {bookmaker: odds_detail}
    detail_lookup: Dict[OddsKey, Dict[str, dict]] = defaultdict(dict)
    for bm_name, mo in group.items():
        for d in mo.odds_detail:
            key = OddsKey(d['bt'], d['sel'], d['margin'])
            detail_lookup[key][bm_name] = d

    sorted_keys = sorted(all_keys, key=lambda k: (k.bet_type_id, k.selection, k.margin))
    bm_names = sorted(group.keys())

    # Print header
    print(f"\n  {'Key':<50}", end="")
    for bm in bm_names:
        print(f" {bm[:8]:>10}", end="")
    print()
    print(f"  {'-'*50}", end="")
    for _ in bm_names:
        print(f" {'-'*10}", end="")
    print()

    for key in sorted_keys:
        bt_name = BET_TYPES.get(key.bet_type_id, {}).get('name', '?')
        key_str = f"bt{key.bet_type_id} {bt_name[:20]}"
        if key.selection:
            key_str += f" [{key.selection}]"
        if key.margin:
            key_str += f" m={key.margin}"
        key_str = key_str[:50]

        print(f"  {key_str:<50}", end="")
        for bm in bm_names:
            if bm in detail_lookup[key]:
                d = detail_lookup[key][bm]
                print(f" {d['odd1']:>10.2f}", end="")
            else:
                print(f" {'---':>10}", end="")
        print()


async def main():
    parser = argparse.ArgumentParser(description='BetSnipe.ai Scraper Audit')
    parser.add_argument('--sport', type=int, default=1, help='Sport ID (1=Football)')
    parser.add_argument('--scraper', nargs='+', help='Specific scrapers to test')
    parser.add_argument('--dump', action='store_true', help='Dump raw odds per match')
    parser.add_argument('--match-detail', action='store_true',
                        help='Dump cross-bookmaker comparison for matched matches')
    parser.add_argument('--match-limit', type=int, default=5,
                        help='Max matched groups to show in detail (default 5)')
    parser.add_argument('--threshold', type=float, default=70.0,
                        help='Fuzzy match threshold (default 70.0)')
    args = parser.parse_args()

    sport_name = SPORT_NAMES.get(args.sport, f"Sport {args.sport}")
    scraper_names = args.scraper or list(SCRAPERS.keys())

    # Validate scraper names
    for name in scraper_names:
        if name not in SCRAPERS:
            print(f"Unknown scraper: {name}. Available: {', '.join(SCRAPERS.keys())}")
            return

    print(f"{'='*80}")
    print(f"  BetSnipe.ai — Scraper Coverage & Consistency Audit")
    print(f"  Sport: {sport_name} (ID={args.sport})")
    print(f"  Scrapers: {', '.join(scraper_names)}")
    print(f"{'='*80}")

    # Run all scrapers concurrently
    print(f"\n  Running scrapers...")
    all_results: Dict[str, List[MatchOdds]] = {}

    tasks = {name: run_scraper(name, args.sport) for name in scraper_names}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    for name, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            print(f"  {name}: ERROR - {result}")
            all_results[name] = []
        else:
            print(f"  {name}: {len(result)} matches scraped")
            all_results[name] = result

    # Dump raw odds if requested
    if args.dump:
        for name, matches in all_results.items():
            print(f"\n{'='*80}")
            print(f"  RAW ODDS DUMP — {name.upper()}")
            print(f"{'='*80}")
            for m in matches[:5]:  # first 5 matches
                dump_match_odds(m)
            if len(matches) > 5:
                print(f"\n  ... and {len(matches) - 5} more matches")

    # Coverage analysis
    stats = analyze_coverage(all_results)
    print_coverage_report(stats, sport_name)

    # Cross-bookmaker matching
    active_results = {k: v for k, v in all_results.items() if v}
    if len(active_results) >= 2:
        print(f"\n  Matching across bookmakers (threshold={args.threshold})...")
        groups = group_cross_bookmaker(active_results, threshold=args.threshold)

        analysis = analyze_cross_bookmaker(groups)
        print_cross_bookmaker_report(analysis, groups)

        # Detailed comparison if requested
        if args.match_detail:
            print(f"\n{'='*80}")
            print(f"  DETAILED CROSS-BOOKMAKER COMPARISONS (top {args.match_limit})")
            print(f"{'='*80}")

            # Pick groups with the most bookmakers
            sorted_groups = sorted(groups, key=lambda g: -len(g))
            for group in sorted_groups[:args.match_limit]:
                dump_cross_comparison(group)
    else:
        print(f"\n  Need 2+ active scrapers for cross-bookmaker comparison.")

    # Summary
    print(f"\n{'='*80}")
    print(f"  AUDIT SUMMARY")
    print(f"{'='*80}")
    for name in sorted(stats.keys()):
        s = stats[name]
        print(f"  {name:<12}: {s['match_count']:>4} matches, {s['total_odds']:>6} odds, "
              f"{s['avg_odds_per_match']:>6.1f} avg/match, {len(s['bet_types_seen']):>3} bet types")

    if len(active_results) >= 2:
        print(f"\n  Cross-bookmaker: {len(groups)} matched groups")
        print(f"  Margin mismatches: {len(analysis['mismatches'])}")
        print(f"  Selection differences: {len(analysis['selection_issues'])}")

    print(f"\n  Done.")


if __name__ == "__main__":
    asyncio.run(main())
