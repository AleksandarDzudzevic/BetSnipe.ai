import json
import time
from datetime import datetime
import sys
from pathlib import Path
import asyncio
import aiohttp
from cloudscraper import create_scraper as CF_Solver

sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

# Initialize CF_Solver
cf = CF_Solver()

async def get_all_match_ids(session, league_id):
    try:
        url = 'https://www.mozzartbet.com/betting/matches'
        payload = {
            "date": "all_days",
            "type": "all",
            "sportIds": [2],  # Changed to 2 for basketball
            "competitionIds": [league_id],
            "pageSize": 100,
            "currentPage": 0
        }
        
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-US,en;q=0.7',
            'Content-Type': 'application/json',
            'Origin': 'https://www.mozzartbet.com',
            'Referer': 'https://www.mozzartbet.com/sr/kladjenje/competitions/1/60?date=all_days',
            'Sec-Ch-Ua': '"Not(A:Brand";v="99", "Brave";v="133", "Chromium";v="133"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'Medium': 'WEB'
        }
        
        async with session.post(url, json=payload, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("items"):
                    return [match["id"] for match in data["items"]]
        return []
    except Exception as e:
        return []

async def get_mozzart_match(session, match_id, league_id):
    try:
        url = f'https://www.mozzartbet.com/match/{match_id}'
        payload = {
            "date": "all_days",
            "type": "all",
            "sportIds": [2],  # Changed to 2 for basketball
            "competitionIds": [league_id],
            "pageSize": 100,
            "currentPage": 0
        }
        
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-US,en;q=0.7',
            'Content-Type': 'application/json',
            'Origin': 'https://www.mozzartbet.com',
            'Referer': 'https://www.mozzartbet.com/sr/kladjenje/competitions/1/60?date=all_days',
            'Sec-Ch-Ua': '"Not(A:Brand";v="99", "Brave";v="133", "Chromium";v="133"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'Medium': 'WEB'
        }
        
        for attempt in range(3):
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                        if not data.get("error"):
                            return data
                    except json.JSONDecodeError:
                        pass
            await asyncio.sleep(2)
        return None
    except Exception as e:
        return None

def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""

async def process_match_data(match_data, matches_to_insert, processed_matches):
    match = match_data["match"]
    if "specialMatchGroupId" in match:
        return

    home_team = match["home"].get("name")
    away_team = match["visitor"].get("name")
    match_name = f"{home_team} {away_team}"
    
    if not match_name or match_name in processed_matches:
        return
    
    processed_matches.add(match_name)
    kick_off_time = convert_unix_to_iso(match.get("startTime", 0))

    # Winner odds
    winner_odds = {"1": "0.00", "2": "0.00"}
    total_points_odds = {}
    handicap_odds = {}

    for odds_group in match.get("oddsGroup", []):
        group_name = odds_group.get("groupName", "")
        if "poluvreme" in group_name.lower():
            continue

        for odd in odds_group.get("odds", []):
            game_name = odd.get("game", {}).get("name", "")
            subgame_name = odd.get("subgame", {}).get("name", "")
            special_value = odd.get("specialOddValue", "")
            value_type = odd.get("game", {}).get("specialOddValueType", "")

            try:
                value = f"{float(odd.get('value', '0.00')):.2f}"
            except:
                value = "0.00"

            if game_name == "Pobednik meča":
                if subgame_name in ["1", "2"]:
                    winner_odds[subgame_name] = value
            elif value_type == "HANDICAP":
                if special_value and subgame_name in ["1", "2"]:
                    group_name = odd.get("game", {}).get("groupName", "")
                    if "poluvreme" in group_name.lower():
                        continue

                    handicap = special_value
                    if handicap not in handicap_odds:
                        handicap_odds[handicap] = {"1": "", "2": ""}
                    handicap_odds[handicap][subgame_name] = value
            elif value_type == "MARGIN":
                if special_value:
                    try:
                        points = float(special_value)
                        if points > 130:
                            if subgame_name == "manje":
                                total_points_odds[f"{special_value}_under"] = value
                            elif subgame_name == "više":
                                total_points_odds[f"{special_value}_over"] = value
                    except ValueError:
                        continue

    # Store match data
    matches_to_insert.append((
        home_team,
        away_team,
        1,              # bookmaker_id
        2,              # sport_id
        1,              # bet_type_id (12)
        0,              # margin
        float(winner_odds["1"]),
        float(winner_odds["2"]),
        0,
        kick_off_time
    ))

    # Store handicap odds
    for handicap in sorted(handicap_odds.keys(), key=float):
        matches_to_insert.append((
            home_team,
            away_team,
            1,              # bookmaker_id
            2,              # sport_id
            9,              # bet_type_id (Handicap)
            float(handicap),
            float(handicap_odds[handicap]["1"]),
            float(handicap_odds[handicap]["2"]),
            0,
            kick_off_time
        ))

    # Store total points odds
    sorted_points = sorted(set(k.split("_")[0] for k in total_points_odds.keys()), key=float)
    for points in sorted_points:
        under_key = f"{points}_under"
        over_key = f"{points}_over"
        matches_to_insert.append((
            home_team,
            away_team,
            1,              # bookmaker_id
            2,              # sport_id
            10,             # bet_type_id (Total Points)
            float(points),
            float(total_points_odds[under_key]),
            float(total_points_odds[over_key]),
            0,
            kick_off_time
        ))

async def process_league(session, league_id, league_name, matches_to_insert, processed_matches):
    match_ids = await get_all_match_ids(session, league_id)
    
    if not match_ids:
        return

    # Process matches concurrently with a semaphore to limit concurrent requests
    sem = asyncio.Semaphore(5)  # Limit to 5 concurrent requests
    async def process_match(match_id):
        async with sem:
            match_data = await get_mozzart_match(session, match_id, league_id)
            if match_data and "match" in match_data:
                await process_match_data(match_data, matches_to_insert, processed_matches)

    await asyncio.gather(*[process_match(match_id) for match_id in match_ids])

async def get_basketball_leagues(session):
    """Fetch current basketball leagues from Mozzart"""
    try:
        url = 'https://www.mozzartbet.com/betting/get-competitions'
        payload = {
            "sportId": 2,  # 2 for basketball (instead of 5 for tennis)
            "date": "all_days",
            "type": "prematch"
        }
        
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-US,en;q=0.7',
            'Content-Type': 'application/json',
            'Origin': 'https://www.mozzartbet.com',
            'Referer': 'https://www.mozzartbet.com/sr/kladjenje',
            'Sec-Ch-Ua': '"Not(A:Brand";v="99", "Brave";v="133", "Chromium";v="133"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'Medium': 'WEB'
        }
        
        async with session.post(url, json=payload, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                leagues = []
                for competition in data.get("competitions", []):
                    league_id = competition.get("id")
                    league_name = competition.get("name")
                    if league_id and league_name:
                        leagues.append((league_id, league_name))
                return leagues
        return []
    except Exception as e:
        print(f"Error fetching leagues: {str(e)}")
        return []

async def scrape_all_matches():
    try:
        conn = get_db_connection()
        matches_to_insert = []
        processed_matches = set()

        async with aiohttp.ClientSession() as session:
            # Get basketball leagues
            leagues = await get_basketball_leagues(session)
            
            if not leagues:
                print("No leagues found")
                return

            # Process leagues concurrently
            await asyncio.gather(*[
                process_league(session, league_id, league_name, matches_to_insert, processed_matches)
                for league_id, league_name in leagues
            ])

        if matches_to_insert:
            batch_insert_matches(conn, matches_to_insert)

    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    asyncio.run(scrape_all_matches())
