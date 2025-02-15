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
leagues = [
    # European Competitions
    ("2519992", "Liga Šampiona"),  # Champions League
    ("2520043", "Liga Evrope"),  # Europa League
    ("2520044", "Liga Konferencije"),  # Conference League
    ("2516076", "Premijer Liga"),  # Premier League
    ("2515993", "Druga Engleska Liga"),  # Championship
    ("2516061", "La Liga"),  # La Liga
    ("2516062", "La Liga 2"),  # La Liga 2
    ("2516000", "Serie A"),  # Serie A
    ("2516001", "Serie B"),  # Serie B
    ("2515986", "Bundesliga"),  # Bundesliga
    ("2515987", "Bundesliga 2"),  # Bundesliga 2
    ("2515968", "Ligue 1"),  # Ligue 1
    ("2515969", "Ligue 2"),  # Ligue 2
    ("2516055", "Holandija 1"),  # Eredivisie
    ("2516056", "Belgija 1"),  # Belgian Pro League
    ("2516057", "Turska 1"),  # Super Lig
    ("2516058", "Grčka 1"),  # Greek Super League
    ("2516059", "Saudijska Liga"),  # Saudi Pro League
    ("2532290", "Argentiska Liga"),  # Argentina Primera Division
    ("2516060", "Brazil 1"),  # Brasileirao
    ("2516063", "Australija 1"),  # A-League
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
                url = f"https://www.soccerbet.rs/restapi/offer/sr/sport/S/league/{league_id}/mob"
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

                                    # Keep all your existing market processing logic
                                    # 1X2
                                    match_1x2 = {
                                        "team1": home_team,
                                        "team2": away_team,
                                        "dateTime": kick_off_time,
                                        "market": "1X2",
                                        "odd1": bet_map.get("1", {}).get("NULL", {}).get("ov", "N/A"),
                                        "odd2": bet_map.get("2", {}).get("NULL", {}).get("ov", "N/A"),
                                        "odd3": bet_map.get("3", {}).get("NULL", {}).get("ov", "N/A"),
                                    }

                                    # First Half 1X2
                                    match_1x2_first = {
                                        "team1": home_team,
                                        "team2": away_team,
                                        "dateTime": kick_off_time,
                                        "market": "1X2F",
                                        "odd1": bet_map.get("4", {}).get("NULL", {}).get("ov", "N/A"),
                                        "odd2": bet_map.get("5", {}).get("NULL", {}).get("ov", "N/A"),
                                        "odd3": bet_map.get("6", {}).get("NULL", {}).get("ov", "N/A"),
                                    }

                                    # Second Half 1X2
                                    match_1x2_second = {
                                        "team1": home_team,
                                        "team2": away_team,
                                        "dateTime": kick_off_time,
                                        "market": "1X2S",
                                        "odd1": bet_map.get("235", {}).get("NULL", {}).get("ov", "N/A"),
                                        "odd2": bet_map.get("236", {}).get("NULL", {}).get("ov", "N/A"),
                                        "odd3": bet_map.get("237", {}).get("NULL", {}).get("ov", "N/A"),
                                    }

                                    # GGNG
                                    match_ggng = {
                                        "team1": home_team,
                                        "team2": away_team,
                                        "dateTime": kick_off_time,
                                        "market": "GGNG",
                                        "odd1": bet_map.get("272", {}).get("NULL", {}).get("ov", "N/A"),
                                        "odd2": bet_map.get("273", {}).get("NULL", {}).get("ov", "N/A"),
                                        "odd3": "",
                                    }

                                    # Process all your total goals markets
                                    # Full match total goals
                                    total_goals_map = {
                                        1.5: {"under": "21", "over": "242"},
                                        2.5: {"under": "22", "over": "24"},
                                        3.5: {"under": "219", "over": "25"},
                                        4.5: {"under": "453", "over": "27"},
                                    }

                                    # Process each total goals market
                                    for total, codes in total_goals_map.items():
                                        under_odd = bet_map.get(codes["under"], {}).get("NULL", {}).get("ov", "N/A")
                                        over_odd = bet_map.get(codes["over"], {}).get("NULL", {}).get("ov", "N/A")

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
                                                5,  # Soccerbet
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
                                        under_odd = bet_map.get(codes["under"], {}).get("NULL", {}).get("ov", "N/A")
                                        over_odd = bet_map.get(codes["over"], {}).get("NULL", {}).get("ov", "N/A")

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
                                                5,  # Soccerbet
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
                                        under_odd = bet_map.get(codes["under"], {}).get("NULL", {}).get("ov", "N/A")
                                        over_odd = bet_map.get(codes["over"], {}).get("NULL", {}).get("ov", "N/A")

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
                                                5,  # Soccerbet
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
                                            5,  # Soccerbet
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
                                            5,  # Soccerbet
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
                                            5,  # Soccerbet
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
                                            5,  # Soccerbet
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
