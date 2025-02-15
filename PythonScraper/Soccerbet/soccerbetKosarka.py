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

# Keep existing leagues list
leagues = [
    ("2521548", "NBA"),
    ("2530816", "NCAA"),
    ("2516963", "Evroliga"),
    ("2521028", "Evrokup"),
    ("2516003", "ABA Liga"),
    ("2516499", "Spanska Liga"),
    ("2516070", "Nemačka Liga"),
    ("2517240", "Italija Liga"),
    ("2521125", "Grčka Liga"),
    ("2516277", "Francuska Liga"),
]

def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""

async def get_soccerbet_api():
    matches_data = []
    matches_to_insert = []

    try:
        async with aiohttp.ClientSession() as session:
            for league_id, league_name in leagues:
                url = f"https://www.soccerbet.rs/restapi/offer/sr/sport/B/league/{league_id}/mob"
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
                batch_insert_matches(conn, matches_to_insert)
                conn.close()
            except Exception as e:
                print(f"Database error: {e}")

    except Exception as e:
        print(f"Error in async operations: {e}")

    return matches_data

if __name__ == "__main__":
    asyncio.run(get_soccerbet_api())
