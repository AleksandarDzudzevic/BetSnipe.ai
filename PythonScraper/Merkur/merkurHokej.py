import aiohttp
import asyncio
import json
import ssl
from datetime import datetime
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

ssl._create_default_https_context = ssl._create_unverified_context

def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""

async def get_hockey_groups(session):
    """Get list of hockey groups (NHL, etc.)."""
    url = "https://www.merkurxtip.rs/restapi/offer/sr/categories/sport/H/g"
    params = {"annex": "0", "desktopVersion": "1.3.2.6", "locale": "sr"}
    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }
    
    try:
        async with session.get(url, params=params, headers=headers) as response:
            data = await response.json()
            groups = []
            
            if "categories" in data:
                for category in data["categories"]:
                    group_id = category.get("id")
                    group_name = category.get("name")
                    if group_id and group_name:
                        groups.append((group_id, group_name))
            
            return groups
    except Exception as e:
        print(f"Error getting hockey groups: {e}")
        return []

async def get_group_leagues(session, group_id):
    """Get leagues/tournaments for a specific group."""
    url = f"https://www.merkurxtip.rs/restapi/offer/sr/categories/sport/H/group/{group_id}/l"
    params = {"annex": "0", "desktopVersion": "1.3.2.6", "locale": "sr"}
    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }
    
    try:
        async with session.get(url, params=params, headers=headers) as response:
            data = await response.json()
            leagues = []
            
            if "categories" in data:
                for category in data["categories"]:
                    league_id = category.get("id")
                    league_name = category.get("name")
                    if league_id and league_name:
                        leagues.append((league_id, league_name))
            
            return leagues
    except Exception as e:
        print(f"Error getting leagues for group {group_id}: {e}")
        return []

async def get_merkur_api():
    matches_data = []
    matches_to_insert = []

    try:
        async with aiohttp.ClientSession() as session:
            groups = await get_hockey_groups(session)
            
            for group_id, group_name in groups:
                leagues = await get_group_leagues(session, group_id)
                
                for league_id, league_name in leagues:
                    url = f"https://www.merkurxtip.rs/restapi/offer/sr/sport/H/league/{league_id}/mob"
                    params = {"annex": "0", "desktopVersion": "1.3.2.6", "locale": "sr"}

                    try:
                        async with session.get(url, params=params) as response:
                            data = await response.json()

                            if "esMatches" in data and data["esMatches"]:
                                batch_size = 10
                                matches = data["esMatches"]
                                
                                for i in range(0, len(matches), batch_size):
                                    batch = matches[i:i + batch_size]
                                    match_tasks = []
                                    
                                    for match in batch:
                                        match_id = match["id"]
                                        match_url = f"https://www.merkurxtip.rs/restapi/offer/sr/match/{match_id}"
                                        match_tasks.append(session.get(match_url, params=params))
                                    
                                    match_responses = await asyncio.gather(*match_tasks)
                                    match_data_tasks = [resp.json() for resp in match_responses]
                                    match_details = await asyncio.gather(*match_data_tasks)

                                    for match, match_data in zip(batch, match_details):
                                        home_team = match_data.get("home", "")
                                        away_team = match_data.get("away", "")
                                        kick_off_time = convert_unix_to_iso(match_data.get("kickOffTime", 0))
                                        odds = match_data.get("odds", {})

                                        if home_team and away_team and "1" in odds and "2" in odds and "3" in odds:
                                            matches_data.append([
                                                home_team,
                                                away_team,
                                                kick_off_time,
                                                "1X2",
                                                odds["1"],
                                                odds["2"],
                                                odds["3"]
                                            ])
                                            matches_to_insert.append((
                                                home_team,
                                                away_team,
                                                8,  # Merkur
                                                4,  # Hockey
                                                1,  # 1X2
                                                0,  # No margin
                                                float(odds["1"]),
                                                float(odds["3"]),
                                                float(odds["2"]),
                                                kick_off_time
                                            ))

                                await asyncio.sleep(0.05)

                    except Exception as e:
                        print(f"Error processing league {league_name}: {e}")
                        continue

            try:
                conn = get_db_connection()
                conn.autocommit = False
                try:
                    batch_insert_matches(conn, matches_to_insert)
                    conn.commit()
                except Exception as insert_error:
                    conn.rollback()
                    print(f"Insert error details: {type(insert_error).__name__}: {str(insert_error)}")
                    raise
                finally:
                    conn.close()
                    
            except Exception as e:
                print(f"Database connection/operation error: {type(e).__name__}: {str(e)}")
                raise

    except Exception as e:
        print(f"Main error: {type(e).__name__}: {str(e)}")
        raise

    return matches_data

if __name__ == "__main__":
    asyncio.run(get_merkur_api()) 