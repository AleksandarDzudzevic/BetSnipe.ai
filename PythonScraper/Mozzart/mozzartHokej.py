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

async def get_hockey_leagues(session):
    """Fetch current hockey leagues from Mozzart"""
    try:
        url = 'https://www.mozzartbet.com/betting/get-competitions'
        payload = {
            "sportId": 4,  # Hockey sport ID
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
        return []

async def get_all_match_ids(session, league_id):
    try:
        url = 'https://www.mozzartbet.com/betting/matches'
        payload = {
            "date": "all_days",
            "type": "all",
            "sportIds": [4],  # Hockey sport ID
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
            "sportIds": [4],  # Hockey sport ID
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
    home_team = match["home"].get("name")
    away_team = match["visitor"].get("name")
    match_id = f"{home_team}, {away_team}"
    
    if not home_team or not away_team or match_id in processed_matches:
        return
    
    processed_matches.add(match_id)
    kick_off_time = convert_unix_to_iso(match.get("startTime", 0))

    # Initialize odds dictionary with default values
    winner_odds = {"1": "0.00", "X": "0.00", "2": "0.00"}

    # Process odds from oddsGroup
    for odds_group in match.get("oddsGroup", []):
        for odd in odds_group.get("odds", []):
            game_name = odd.get("game", {}).get("name", "")
            subgame_name = odd.get("subgame", {}).get("name", "")
            try:
                value = f"{float(odd.get('value', '0.00')):.2f}"
            except:
                value = "0.00"

            if game_name == "Konačan ishod" and subgame_name in ["1", "X", "2"]:
                winner_odds[subgame_name] = value

    # Store match data
    matches_to_insert.append((
        home_team,
        away_team,
        1,              # bookmaker_id
        4,              # sport_id (Hockey)
        2,              # bet_type_id (1X2)
        0,              # margin
        float(winner_odds["1"]),
        float(winner_odds["X"]),
        float(winner_odds["2"]),
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

async def scrape_all_matches():
    try:
        conn = get_db_connection()
        matches_to_insert = []
        processed_matches = set()

        async with aiohttp.ClientSession() as session:
            # Get hockey leagues
            leagues = await get_hockey_leagues(session)
            
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
