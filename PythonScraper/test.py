"""
Quick validation: test the expanded MaxBet scraper against a real match
"""
import asyncio
import sys
import aiohttp

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Import the scraper's parse function
sys.path.insert(0, '.')
from core.scrapers.maxbet import MaxbetScraper


BASE_URL = "https://www.maxbet.rs/restapi/offer/sr"
PARAMS = {"desktopVersion": "1.17.1.16", "locale": "sr"}
HEADERS = {"Accept": "*/*", "User-Agent": "Mozilla/5.0"}


async def main():
    scraper = MaxbetScraper()
    async with aiohttp.ClientSession() as session:
        # Test Football
        print("=" * 80)
        print("FOOTBALL TEST - Match 22850918")
        print("=" * 80)
        url = f"{BASE_URL}/match/22850918"
        async with session.get(url, params={**PARAMS, "annex": "3"}, headers=HEADERS) as resp:
            match_data = await resp.json()

        print(f"Match: {match_data.get('home')} vs {match_data.get('away')}")
        print(f"Raw odds codes: {len(match_data.get('odds', {}))}")

        odds = scraper.parse_football_odds(match_data)
        print(f"Parsed odds: {len(odds)}")

        # Group by bet_type_id
        by_type = {}
        for o in odds:
            bt = o.bet_type_id
            if bt not in by_type:
                by_type[bt] = []
            by_type[bt].append(o)

        for bt in sorted(by_type.keys()):
            items = by_type[bt]
            first = items[0]
            if first.selection:
                print(f"  bet_type={bt:>2d}: {len(items):>3d} selections "
                      f"(first: sel='{first.selection}', odd1={first.odd1:.2f})")
            elif first.odd3:
                print(f"  bet_type={bt:>2d}: {len(items):>3d} lines "
                      f"(first: {first.odd1:.2f}/{first.odd2:.2f}/{first.odd3:.2f}, margin={first.margin})")
            else:
                print(f"  bet_type={bt:>2d}: {len(items):>3d} lines "
                      f"(first: {first.odd1:.2f}/{first.odd2:.2f}, margin={first.margin})")

        # Test Basketball
        print("\n" + "=" * 80)
        print("BASKETBALL TEST")
        print("=" * 80)
        bball_url = f"{BASE_URL}/categories/sport/B/l"
        async with session.get(bball_url, params=PARAMS, headers=HEADERS) as resp:
            bball_data = await resp.json()

        # Find a non-bonus league with matches
        for league in bball_data.get("categories", []):
            name = league.get("name", "")
            if "Bonus" in name or "Max Bonus" in name:
                continue
            league_url = f"{BASE_URL}/sport/B/league/{league['id']}/mob"
            async with session.get(league_url, params=PARAMS, headers=HEADERS) as resp:
                league_data = await resp.json()
            matches = league_data.get("esMatches", [])
            if matches:
                mid = matches[0]["id"]
                match_url = f"{BASE_URL}/match/{mid}"
                async with session.get(match_url, params={**PARAMS, "annex": "3"}, headers=HEADERS) as resp:
                    bball_match = await resp.json()

                print(f"Match: {bball_match.get('home')} vs {bball_match.get('away')}")
                print(f"Raw odds: {len(bball_match.get('odds', {}))}, Params: {len(bball_match.get('params', {}))}")

                bball_odds = scraper.parse_basketball_odds(bball_match)
                print(f"Parsed odds: {len(bball_odds)}")
                for o in bball_odds[:10]:
                    print(f"  bt={o.bet_type_id}, odd1={o.odd1:.2f}, odd2={o.odd2:.2f}, margin={o.margin}")
                if len(bball_odds) > 10:
                    print(f"  ... +{len(bball_odds)-10} more")
                break

        # Test Tennis
        print("\n" + "=" * 80)
        print("TENNIS TEST")
        print("=" * 80)
        tennis_url = f"{BASE_URL}/categories/sport/T/l"
        async with session.get(tennis_url, params=PARAMS, headers=HEADERS) as resp:
            tennis_data = await resp.json()

        for league in tennis_data.get("categories", []):
            league_url = f"{BASE_URL}/sport/T/league/{league['id']}/mob"
            async with session.get(league_url, params=PARAMS, headers=HEADERS) as resp:
                league_data = await resp.json()
            matches = league_data.get("esMatches", [])
            if matches:
                mid = matches[0]["id"]
                match_url = f"{BASE_URL}/match/{mid}"
                async with session.get(match_url, params={**PARAMS, "annex": "3"}, headers=HEADERS) as resp:
                    tennis_match = await resp.json()

                print(f"Match: {tennis_match.get('home')} vs {tennis_match.get('away')}")
                print(f"Raw odds: {len(tennis_match.get('odds', {}))}")

                tennis_odds = scraper.parse_tennis_odds(tennis_match)
                print(f"Parsed odds: {len(tennis_odds)}")
                for o in tennis_odds[:15]:
                    sel = f", sel='{o.selection}'" if o.selection else ""
                    o3 = f"/{o.odd3:.2f}" if o.odd3 else ""
                    o2 = f"{o.odd2:.2f}" if o.odd2 else "0.00"
                    print(f"  bt={o.bet_type_id}, odd1={o.odd1:.2f}/{o2}{o3}, margin={o.margin}{sel}")
                if len(tennis_odds) > 15:
                    print(f"  ... +{len(tennis_odds)-15} more")
                break

        # Test Hockey
        print("\n" + "=" * 80)
        print("HOCKEY TEST")
        print("=" * 80)
        hockey_url = f"{BASE_URL}/categories/sport/H/l"
        async with session.get(hockey_url, params=PARAMS, headers=HEADERS) as resp:
            hockey_data = await resp.json()

        for league in hockey_data.get("categories", []):
            league_url = f"{BASE_URL}/sport/H/league/{league['id']}/mob"
            async with session.get(league_url, params=PARAMS, headers=HEADERS) as resp:
                league_data = await resp.json()
            matches = league_data.get("esMatches", [])
            if matches:
                mid = matches[0]["id"]
                match_url = f"{BASE_URL}/match/{mid}"
                async with session.get(match_url, params={**PARAMS, "annex": "3"}, headers=HEADERS) as resp:
                    hockey_match = await resp.json()

                print(f"Match: {hockey_match.get('home')} vs {hockey_match.get('away')}")
                print(f"Raw odds: {len(hockey_match.get('odds', {}))}")

                hockey_odds = scraper.parse_hockey_odds(hockey_match)
                print(f"Parsed odds: {len(hockey_odds)}")
                for o in hockey_odds[:15]:
                    sel = f", sel='{o.selection}'" if o.selection else ""
                    o3 = f"/{o.odd3:.2f}" if o.odd3 else ""
                    o2 = f"{o.odd2:.2f}" if o.odd2 else "0.00"
                    print(f"  bt={o.bet_type_id}, odd1={o.odd1:.2f}/{o2}{o3}, margin={o.margin}{sel}")
                if len(hockey_odds) > 15:
                    print(f"  ... +{len(hockey_odds)-15} more")
                break


if __name__ == "__main__":
    asyncio.run(main())
