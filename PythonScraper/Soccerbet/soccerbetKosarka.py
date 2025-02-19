import aiohttp
import asyncio
import json
import ssl
from datetime import datetime
import sys
from pathlib import Path
import time
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

ssl._create_default_https_context = ssl._create_unverified_context

def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""

async def get_basketball_leagues(session):
    """Fetch current basketball leagues from Soccerbet"""
    url = "https://www.soccerbet.rs/restapi/offer/sr/categories/ext/sport/B/g"
    params = {"annex": "0", "desktopVersion": "2.36.3.9", "locale": "sr"}
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
            for category in data.get("categories", []):
                league_id = category.get("id")
                league_name = category.get("name")
                if league_id and league_name:
                    leagues.append((league_id, league_name))
            return leagues
    except Exception as e:
        print(f"Error fetching leagues: {str(e)}")
        return []

async def get_soccerbet_api():
    matches_data = []
    matches_to_insert = []

    try:
        async with aiohttp.ClientSession() as session:
            # First get all leagues
            leagues = await get_basketball_leagues(session)
            if not leagues:
                return

            for league_id, league_name in leagues:
                url = f"https://www.soccerbet.rs/restapi/offer/sr/sport/B/league-group/{league_id}/mob"
                params = {"annex": "0", "desktopVersion": "2.36.3.7", "locale": "sr"}

                try:
                    async with session.get(url, params=params) as response:
                        data = await response.json()

                        if "esMatches" in data and len(data["esMatches"]) > 0:
                            # Process matches in batches
                            batch_size = 10
                            matches = data["esMatches"]
                            
                            for i in range(0, len(matches), batch_size):
                                batch = matches[i:i + batch_size]
                                match_tasks = []
                                
                                for match in batch:
                                    match_id = match["id"]
                                    match_url = f"https://www.soccerbet.rs/restapi/offer/sr/match/{match_id}"
                                    match_tasks.append(session.get(match_url, params=params))
                                
                                match_responses = await asyncio.gather(*match_tasks)
                                match_data_tasks = [resp.json() for resp in match_responses]
                                match_details = await asyncio.gather(*match_data_tasks)

                                # Process each match in the batch
                                for match, match_data in zip(batch, match_details):
                                    bet_map = match_data.get("betMap", {})
                                    home_team = match["home"]
                                    away_team = match["away"]
                                    kick_off_time = convert_unix_to_iso(match_data.get("kickOffTime", 0))

                                    # Winner odds
                                    match_winner = {
                                        "Team1": home_team,
                                        "Team2": away_team,
                                        "dateTime": kick_off_time,
                                        "market": "12",
                                        "odd1": bet_map.get("50291", {}).get("NULL", {}).get("ov", "N/A"),
                                        "odd2": bet_map.get("50293", {}).get("NULL", {}).get("ov", "N/A"),
                                        "odd3": "",
                                    }

                                    # Process handicaps
                                    handicap_code = "50431"
                                    handicap_code2 = "50430"
                                    if handicap_code in bet_map and handicap_code2 in bet_map:
                                        handicap_data = bet_map[handicap_code]
                                        for key in handicap_data:
                                            if key.startswith("hcp="):
                                                handicap = key.split("=")[1]
                                                odds1 = bet_map.get(handicap_code, {}).get(key, {}).get("ov", "N/A")
                                                odds2 = bet_map.get(handicap_code2, {}).get(key, {}).get("ov", "N/A")

                                                if odds1 != "N/A" and odds2 != "N/A":
                                                    matches_data.append({
                                                        "Team1": home_team,
                                                        "Team2": away_team,
                                                        "dateTime": kick_off_time,
                                                        "market": f"H{handicap}",
                                                        "odd1": odds2,
                                                        "odd2": odds1,
                                                        "odd3": "",
                                                    })
                                                    matches_to_insert.append((
                                                        home_team,
                                                        away_team,
                                                        5,  # Soccerbet
                                                        2,  # Basketball
                                                        9,  # Handicap
                                                        float(handicap),
                                                        float(odds2),
                                                        float(odds1),
                                                        0,
                                                        kick_off_time
                                                    ))

                                    # Process total points
                                    total_points_code = "50444"
                                    if total_points_code in bet_map:
                                        total_data = bet_map[total_points_code]
                                        for key in total_data:
                                            if key.startswith("total="):
                                                points = key.split("=")[1]
                                                under_odds = bet_map.get(total_points_code, {}).get(key, {}).get("ov", "N/A")
                                                over_odds = bet_map.get("50445", {}).get(key, {}).get("ov", "N/A")

                                                if under_odds != "N/A" and over_odds != "N/A":
                                                    matches_data.append({
                                                        "Team1": home_team,
                                                        "Team2": away_team,
                                                        "dateTime": kick_off_time,
                                                        "market": f"OU{points}",
                                                        "odd1": under_odds,
                                                        "odd2": over_odds,
                                                        "odd3": "",
                                                    })
                                                    matches_to_insert.append((
                                                        home_team,
                                                        away_team,
                                                        5,  # Soccerbet
                                                        2,  # Basketball
                                                        10,  # Total Points
                                                        float(points),
                                                        float(under_odds),
                                                        float(over_odds),
                                                        0,
                                                        kick_off_time
                                                    ))

                                    # Insert match winner odds
                                    if match_winner["odd1"] != "N/A" and match_winner["odd2"] != "N/A":
                                        matches_data.append(match_winner)
                                        matches_to_insert.append((
                                            home_team,
                                            away_team,
                                            5,  # Soccerbet
                                            2,  # Basketball
                                            1,  # Winner
                                            0,  # No margin
                                            float(match_winner["odd1"]),
                                            float(match_winner["odd2"]),
                                            0,  # No third odd
                                            kick_off_time
                                        ))

                                await asyncio.sleep(0.05)  # Small delay between batches

                except Exception as e:
                    print(f"Error processing league {league_name}: {str(e)}")
                    continue

            # Database insertion
            try:
                conn = get_db_connection()
                # Try to insert with explicit transaction handling
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
        print(f"Error in async operations: {e}")

    return matches_data

if __name__ == "__main__":
    asyncio.run(get_soccerbet_api())
