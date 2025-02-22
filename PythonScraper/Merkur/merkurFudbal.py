import aiohttp
import asyncio
import json
import csv
import ssl
from datetime import datetime
import sys
from pathlib import Path
import time
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

ssl._create_default_https_context = ssl._create_unverified_context

# Keep existing leagues list
async def get_football_leagues(session):
    """Fetch current football leagues from Soccerbet"""
    url = "https://www.merkurxtip.rs/restapi/offer/sr/categories/ext/sport/S/g"
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
        async with aiohttp.ClientSession() as session:# First get all leagues
            leagues = await get_football_leagues(session)
            if not leagues:
                return
            for league_id, league_name in leagues:
                url = f"https://www.merkurxtip.rs/restapi/offer/sr/sport/S/league-group/{league_id}/mob"
                params = {"annex": "0", "desktopVersion": "1.3.2.6", "locale": "sr"}

                try:
                    async with session.get(url, params=params) as response:
                        data = await response.json()

                        if "esMatches" in data and len(data["esMatches"]) > 0:
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
                                    odds = match_data.get("odds", {})
                                    home_team = match["home"]
                                    away_team = match["away"]
                                    kick_off_time = convert_unix_to_iso(match_data.get("kickOffTime", 0))

                                    # 1X2
                                    match_1x2 = {
                                        "team1": home_team,
                                        "team2": away_team,
                                        "dateTime": kick_off_time,
                                        "market": "1X2",
                                        "odd1": odds.get("1", "N/A"),
                                        "odd2": odds.get("2", "N/A"),
                                        "odd3": odds.get("3", "N/A"),
                                    }

                                    # First Half 1X2
                                    match_1x2_first = {
                                        "team1": home_team,
                                        "team2": away_team,
                                        "dateTime": kick_off_time,
                                        "market": "1X2F",
                                        "odd1": odds.get("4", "N/A"),
                                        "odd2": odds.get("5", "N/A"),
                                        "odd3": odds.get("6", "N/A"),
                                    }

                                    # Second Half 1X2
                                    match_1x2_second = {
                                        "team1": home_team,
                                        "team2": away_team,
                                        "dateTime": kick_off_time,
                                        "market": "1X2S",
                                        "odd1": odds.get("235", "N/A"),
                                        "odd2": odds.get("236", "N/A"),
                                        "odd3": odds.get("237", "N/A"),
                                    }

                                    # GGNG
                                    match_ggng = {
                                        "team1": home_team,
                                        "team2": away_team,
                                        "dateTime": kick_off_time,
                                        "market": "GGNG",
                                        "odd1": odds.get("272", "N/A"),
                                        "odd2": odds.get("273", "N/A"),
                                        "odd3": "",
                                    }

                                    # Process all total goals markets
                                    total_goals_map = {
                                        1.5: {"under": "21", "over": "242"},
                                        2.5: {"under": "22", "over": "24"},
                                        3.5: {"under": "219", "over": "25"},
                                        4.5: {"under": "453", "over": "27"},
                                    }

                                    # Process each total goals market
                                    for total, codes in total_goals_map.items():
                                        under_odd = odds.get(codes["under"], "N/A")
                                        over_odd = odds.get(codes["over"], "N/A")

                                        if under_odd != "N/A" or over_odd != "N/A":
                                            matches_data.append({
                                                "team1": home_team,
                                                "team2": away_team,
                                                "dateTime": kick_off_time,
                                                "market": f"TG{total}",
                                                "odd1": under_odd,
                                                "odd2": over_odd,
                                                "odd3": "",
                                            })
                                            matches_to_insert.append((
                                                home_team,
                                                away_team,
                                                8,  # Merkur
                                                1,  # Football
                                                5,  # Total Goals
                                                float(total),
                                                float(under_odd),
                                                float(over_odd),
                                                0,
                                                kick_off_time
                                            ))

                                    # First half total goals
                                    total_goals_first_map = {
                                        0.5: {"under": "267", "over": "207"},
                                        1.5: {"under": "211", "over": "208"},
                                        2.5: {"under": "472", "over": "209"},
                                    }

                                    # Process first half totals
                                    for total, codes in total_goals_first_map.items():
                                        under_odd = odds.get(codes["under"], "N/A")
                                        over_odd = odds.get(codes["over"], "N/A")

                                        if under_odd != "N/A" or over_odd != "N/A":
                                            matches_data.append({
                                                "team1": home_team,
                                                "team2": away_team,
                                                "dateTime": kick_off_time,
                                                "market": f"TG{total}F",
                                                "odd1": under_odd,
                                                "odd2": over_odd,
                                                "odd3": "",
                                            })
                                            matches_to_insert.append((
                                                home_team,
                                                away_team,
                                                8,  # Merkur
                                                1,  # Football
                                                6,  # First Half Total
                                                float(total),
                                                float(under_odd),
                                                float(over_odd),
                                                0,
                                                kick_off_time
                                            ))

                                    # Second half total goals
                                    total_goals_second_map = {
                                        0.5: {"under": "269", "over": "213"},
                                        1.5: {"under": "217", "over": "214"},
                                        2.5: {"under": "474", "over": "215"},
                                    }

                                    # Process second half totals
                                    for total, codes in total_goals_second_map.items():
                                        under_odd = odds.get(codes["under"], "N/A")
                                        over_odd = odds.get(codes["over"], "N/A")

                                        if under_odd != "N/A" or over_odd != "N/A":
                                            matches_data.append({
                                                "team1": home_team,
                                                "team2": away_team,
                                                "dateTime": kick_off_time,
                                                "market": f"TG{total}S",
                                                "odd1": under_odd,
                                                "odd2": over_odd,
                                                "odd3": "",
                                            })
                                            matches_to_insert.append((
                                                home_team,
                                                away_team,
                                                8,  # Merkur
                                                1,  # Football
                                                7,  # Second Half Total
                                                float(total),
                                                float(under_odd),
                                                float(over_odd),
                                                0,
                                                kick_off_time
                                            ))

                                    # Insert 1X2 odds
                                    if all(x != "N/A" for x in [match_1x2["odd1"], match_1x2["odd2"], match_1x2["odd3"]]):
                                        matches_data.append(match_1x2)
                                        matches_to_insert.append((
                                            home_team,
                                            away_team,
                                            8,  # Merkur
                                            1,  # Football
                                            2,  # 1X2
                                            0,  # No margin
                                            float(match_1x2["odd1"]),
                                            float(match_1x2["odd2"]),
                                            float(match_1x2["odd3"]),
                                            kick_off_time
                                        ))

                                    # Insert First Half 1X2
                                    if all(x != "N/A" for x in [match_1x2_first["odd1"], match_1x2_first["odd2"], match_1x2_first["odd3"]]):
                                        matches_data.append(match_1x2_first)
                                        matches_to_insert.append((
                                            home_team,
                                            away_team,
                                            8,  # Merkur
                                            1,  # Football
                                            3,  # First Half 1X2
                                            0,  # No margin
                                            float(match_1x2_first["odd1"]),
                                            float(match_1x2_first["odd2"]),
                                            float(match_1x2_first["odd3"]),
                                            kick_off_time
                                        ))

                                    # Insert Second Half 1X2
                                    if all(x != "N/A" for x in [match_1x2_second["odd1"], match_1x2_second["odd2"], match_1x2_second["odd3"]]):
                                        matches_data.append(match_1x2_second)
                                        matches_to_insert.append((
                                            home_team,
                                            away_team,
                                            8,  # Merkur
                                            1,  # Football
                                            4,  # Second Half 1X2
                                            0,  # No margin
                                            float(match_1x2_second["odd1"]),
                                            float(match_1x2_second["odd2"]),
                                            float(match_1x2_second["odd3"]),
                                            kick_off_time
                                        ))

                                    # Insert GGNG
                                    if match_ggng["odd1"] != "N/A" and match_ggng["odd2"] != "N/A":
                                        matches_data.append(match_ggng)
                                        matches_to_insert.append((
                                            home_team,
                                            away_team,
                                            8,  # Merkur
                                            1,  # Football
                                            8,  # GGNG
                                            0,  # No margin
                                            float(match_ggng["odd1"]),
                                            float(match_ggng["odd2"]),
                                            0,  # No third odd
                                            kick_off_time
                                        ))

                                await asyncio.sleep(0.05)  # Small delay between batches

                except Exception as e:
                    print(e)
                    continue

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
    asyncio.run(get_merkur_api())
