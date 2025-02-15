import aiohttp
import asyncio
import json
import csv
from datetime import datetime
import sys
from pathlib import Path
import time
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

BASKETBALL_LEAGUES = {"nba": "144532", "euroleague": "131600", "eurocup": "131596"}

headers = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Origin": "https://www.maxbet.rs",
    "Referer": "https://www.maxbet.rs/betting",
}

def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""

async def fetch_match_details(session, match_id, params):
    match_url = f"https://www.maxbet.rs/restapi/offer/sr/match/{match_id}"
    async with session.get(match_url, params=params, headers=headers) as response:
        return await response.json()

async def fetch_league_matches(session, league_id, params):
    url = f"https://www.maxbet.rs/restapi/offer/sr/sport/B/league/{league_id}/mob"
    async with session.get(url, params=params, headers=headers) as response:
        return await response.json()

async def fetch_maxbet_matches():
    matches_to_insert = []
    conn = get_db_connection()
    params = {"annex": "3", "desktopVersion": "1.2.1.9", "locale": "sr"}
    
    # Updated handicap mapping
    handicap_mapping = {
        "handicapOvertime": ("50458", "50459"),
        "handicapOvertime2": ("50432", "50433"),
        "handicapOvertime3": ("50434", "50435"),
        "handicapOvertime4": ("50436", "50437"),
        "handicapOvertime5": ("50438", "50439"),
        "handicapOvertime6": ("50440", "50441"),
        "handicapOvertime7": ("50442", "50443"),
        "handicapOvertime8": ("50981", "50982"),
        "handicapOvertime9": ("51626", "51627"),
    }

    # Add total points mapping
    total_points_mapping = {
        "overUnderOvertime3": ("50448", "50449"),
        "overUnderOvertime4": ("50450", "50451"),
        "overUnderOvertime5": ("50452", "50453"),
        "overUnderOvertime6": ("50454", "50455"),
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            league_tasks = []
            for league_name, league_id in BASKETBALL_LEAGUES.items():
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
                    params = match_data.get("params", {})
                    
                    # Match winner odds
                    home_odd = odds.get("50291", "")
                    away_odd = odds.get("50293", "")
                    
                    if home_odd and away_odd:
                        matches_to_insert.append((
                            home_team, away_team,
                            3,  # Maxbet
                            2,  # Basketball
                            1,  # Winner (12)
                            0,  # No margin
                            float(home_odd),
                            float(away_odd),
                            0,  # No third odd
                            kick_off_time
                        ))
                    
                    # Process handicap odds
                    for handicap_key, (home_code, away_code) in handicap_mapping.items():
                        if home_code in odds and away_code in odds:
                            handicap_value = params.get(handicap_key)
                            if handicap_value:
                                # Flip the handicap sign
                                flipped_handicap = handicap_value[1:] if handicap_value.startswith("-") else f"-{handicap_value}"
                                matches_to_insert.append((
                                    home_team, away_team,
                                    3,  # Maxbet
                                    2,  # Basketball
                                    9,  # Handicap
                                    float(flipped_handicap),
                                    float(odds[home_code]),
                                    float(odds[away_code]),
                                    0,  # No third odd
                                    kick_off_time
                                ))
                    
                    # Process total points odds
                    for total_key, (under_code, over_code) in total_points_mapping.items():
                        if under_code in odds and over_code in odds:
                            total_value = params.get(total_key)
                            if total_value:
                                matches_to_insert.append((
                                    home_team, away_team,
                                    3,  # Maxbet
                                    2,  # Basketball
                                    10,  # Total Points
                                    float(total_value),
                                    float(odds[under_code]),
                                    float(odds[over_code]),
                                    0,  # No third odd
                                    kick_off_time
                                ))
                
                except Exception as e:
                    pass
    
    except Exception as e:
        pass
    
    try:
        batch_insert_matches(conn, matches_to_insert)
    except Exception as e:
        print(f"Error inserting matches into database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(fetch_maxbet_matches())
