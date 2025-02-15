import aiohttp
import asyncio
import json
from datetime import datetime
import sys
from pathlib import Path
import time
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

headers = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Origin": "https://www.maxbet.rs",
    "Referer": "https://www.maxbet.rs/betting",
}

def convert_unix_to_iso(unix_ms):
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""

async def fetch_table_tennis_leagues(session):
    """Fetch current table tennis leagues from MaxBet"""
    url = "https://www.maxbet.rs/restapi/offer/sr/categories/sport/TT/l"
    params = {"annex": "3", "desktopVersion": "1.2.1.10", "locale": "sr"}
    
    try:
        async with session.get(url, params=params, headers=headers) as response:
            data = await response.json()
            leagues = {}
            
            for category in data.get('categories', []):
                league_id = category.get('id')
                league_name = category.get('name')
                if league_id and league_name:
                    leagues[league_name.lower().replace(" ", "_")] = league_id
            
            return leagues
    except Exception as e:
        print(f"Error fetching leagues: {str(e)}")
        return {}

async def fetch_match_details(session, match_id, params):
    match_url = f"https://www.maxbet.rs/restapi/offer/sr/match/{match_id}"
    async with session.get(match_url, params=params, headers=headers) as response:
        return await response.json()

async def fetch_league_matches(session, league_id, params):
    url = f"https://www.maxbet.rs/restapi/offer/sr/sport/TT/league/{league_id}/mob"
    async with session.get(url, params=params, headers=headers) as response:
        return await response.json()

async def fetch_maxbet_table_tennis_matches():
    matches_to_insert = []
    conn = get_db_connection()
    params = {"annex": "3", "desktopVersion": "1.2.1.10", "locale": "sr"}
    
    try:
        async with aiohttp.ClientSession() as session:
            # First get the leagues
            table_tennis_leagues = await fetch_table_tennis_leagues(session)
            
            if not table_tennis_leagues:
                print("No leagues found")
                return
            
            # Fetch matches for all leagues concurrently
            league_tasks = []
            for league_name, league_id in table_tennis_leagues.items():
                league_tasks.append(fetch_league_matches(session, league_id, params))
            
            leagues_data = await asyncio.gather(*league_tasks)
            
            # Collect all match IDs
            match_ids = []
            for league_data in leagues_data:
                if "esMatches" in league_data:
                    for match in league_data["esMatches"]:
                        match_ids.append(match["id"])
            
            # Fetch match details concurrently
            match_tasks = []
            for match_id in match_ids:
                match_tasks.append(fetch_match_details(session, match_id, params))
            
            matches_data = await asyncio.gather(*match_tasks)
            
            # Process matches
            for match_data in matches_data:
                try:
                    home_team = match_data.get("home", "")
                    away_team = match_data.get("away", "")
                    kick_off_time = convert_unix_to_iso(match_data.get("kickOffTime", 0))
                    odds = match_data.get("odds", {})
                    
                    # Winner odds (1-2)
                    home_win = odds.get("1", "")
                    away_win = odds.get("3", "")
                    
                    if home_win and away_win:
                        matches_to_insert.append((
                            home_team,
                            away_team,
                            3,  # Maxbet
                            5,  # Table Tennis
                            1,  # Winner
                            0,  # No margin
                            float(home_win),
                            float(away_win),
                            0,  # No third odd
                            kick_off_time
                        ))
                
                except Exception as e:
                    print(f"Error processing match: {e}")
                    continue
    
    except Exception as e:
        print(f"Error in async operations: {e}")
    
    try:
        batch_insert_matches(conn, matches_to_insert)
    except Exception as e:
        print(f"Error inserting matches into database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(fetch_maxbet_table_tennis_matches())
