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

# Basketball leagues for Merkur
leagues = [
    ("2314399", "NBA"),  # This is the correct ID for NBA
    ("2313823", "NCAA"),  # Need to verify this ID
    # Comment out other leagues until we verify their IDs
    #("2316963", "Evroliga"),
    #("2321028", "Evrokup"),
    #("2316003", "ABA Liga"),
    #("2316499", "Spanska Liga"),
    #("2316070", "Nemačka Liga"),
    #("2317240", "Italija Liga"),
    #("2321125", "Grčka Liga"),
    #("2316277", "Francuska Liga"),
]

def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""

async def get_merkur_api():
    matches_data = []
    matches_to_insert = []

    try:
        async with aiohttp.ClientSession() as session:
            for league_id, league_name in leagues:
                url = f"https://www.merkurxtip.rs/restapi/offer/sr/sport/B/league/{league_id}/mob"
                params = {"annex": "0", "desktopVersion": "1.3.2.6", "locale": "sr"}

                try:
                    print(f"Fetching league {league_name} with ID {league_id}")
                    async with session.get(url, params=params) as response:
                        data = await response.json()
                        print(f"Response status: {response.status}")
                        print(f"Response data keys: {data.keys()}")

                        if "esMatches" in data and len(data["esMatches"]) > 0:
                            print(f"Found {len(data['esMatches'])} matches")
                            batch_size = 10
                            matches = data["esMatches"]
                            
                            for i in range(0, len(matches), batch_size):
                                batch = matches[i:i + batch_size]
                                print(f"Processing batch of {len(batch)} matches")
                                match_tasks = []
                                
                                for match in batch:
                                    match_id = match["id"]
                                    print(f"Getting details for match ID: {match_id}")
                                    match_url = f"https://www.merkurxtip.rs/restapi/offer/sr/match/{match_id}"
                                    match_tasks.append(session.get(match_url, params=params))
                                
                                match_responses = await asyncio.gather(*match_tasks)
                                match_data_tasks = [resp.json() for resp in match_responses]
                                match_details = await asyncio.gather(*match_data_tasks)
                                
                                for match, match_data in zip(batch, match_details):
                                    odds = match_data.get("odds", {})
                                    print(f"Odds keys: {odds.keys()}")  # Debug log
                                    
                                    home_team = match["home"]
                                    away_team = match["away"]
                                    kick_off_time = convert_unix_to_iso(match_data.get("kickOffTime", 0))
                                    print(f"Processing match: {home_team} vs {away_team}")

                                    # Winner odds
                                    match_winner = {
                                        "Team1": home_team,
                                        "Team2": away_team,
                                        "dateTime": kick_off_time,
                                        "market": "12",
                                        "odd1": odds.get("50291", "N/A"),
                                        "odd2": odds.get("50293", "N/A"), 
                                        "odd3": "",
                                    }
                                    print(f"Winner odds: {match_winner['odd1']} vs {match_winner['odd2']}")

                                    # Process handicaps
                                    handicap_code = "50431"
                                    handicap_code2 = "50430"
                                    if handicap_code in odds and handicap_code2 in odds:
                                        # Handle the case where handicap_data is a float
                                        handicap_data = odds.get(handicap_code, {})
                                        if isinstance(handicap_data, dict):
                                            for key in handicap_data:
                                                if key.startswith("hcp="):
                                                    handicap = key.split("=")[1]
                                                    odds1 = odds.get(handicap_code, {}).get(key, "N/A")
                                                    odds2 = odds.get(handicap_code2, {}).get(key, "N/A")

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
                                                            8,  # Merkur
                                                            2,  # Basketball
                                                            9,  # Handicap
                                                            float(handicap),
                                                            float(odds2),
                                                            float(odds1),
                                                            0,
                                                            kick_off_time
                                                        ))
                                        elif isinstance(handicap_data, (int, float)):
                                            # Handle direct odds values
                                            odds1 = handicap_data
                                            odds2 = odds.get(handicap_code2, "N/A")
                                            if odds1 != "N/A" and odds2 != "N/A":
                                                matches_data.append({
                                                    "Team1": home_team,
                                                    "Team2": away_team,
                                                    "dateTime": kick_off_time,
                                                    "market": "H",  # Default handicap
                                                    "odd1": odds2,
                                                    "odd2": odds1,
                                                    "odd3": "",
                                                })
                                                matches_to_insert.append((
                                                    home_team,
                                                    away_team,
                                                    8,  # Merkur
                                                    2,  # Basketball
                                                    9,  # Handicap
                                                    0,  # Default handicap value
                                                    float(odds2),
                                                    float(odds1),
                                                    0,
                                                    kick_off_time
                                                ))

                                    # Process total points
                                    total_points_code = "50444"
                                    if total_points_code in odds:
                                        total_data = odds[total_points_code]
                                        if isinstance(total_data, dict):
                                            for key in total_data:
                                                if key.startswith("total="):
                                                    points = key.split("=")[1]
                                                    under_odds = odds.get(total_points_code, {}).get(key, "N/A")
                                                    over_odds = odds.get("50445", {}).get(key, "N/A")

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
                                                            8,  # Merkur
                                                            2,  # Basketball
                                                            10,  # Total Points
                                                            float(points),
                                                            float(under_odds),
                                                            float(over_odds),
                                                            0,
                                                            kick_off_time
                                                        ))
                                        elif isinstance(total_data, (int, float)):
                                            # Handle direct odds values
                                            under_odds = total_data
                                            over_odds = odds.get("50445", "N/A")
                                            if under_odds != "N/A" and over_odds != "N/A":
                                                # Use a default total points value or get it from somewhere else
                                                points = "0"  # You might want to adjust this
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
                                                    8,  # Merkur
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
                                            8,  # Merkur
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

            print(f"Total matches to insert: {len(matches_to_insert)}")  # Debug log
            try:
                conn = get_db_connection()
                batch_insert_matches(conn, matches_to_insert)
                print("Successfully inserted matches into database")
                conn.close()
            except Exception as e:
                print(f"Database error: {e}")

    except Exception as e:
        print(f"Error in async operations: {e}")

    return matches_data

if __name__ == "__main__":
    asyncio.run(get_merkur_api())
