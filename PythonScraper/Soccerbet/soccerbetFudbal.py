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

async def get_football_leagues(session):
    """Fetch current football leagues from Soccerbet"""
    url = "https://www.soccerbet.rs/restapi/offer/sr/categories/ext/sport/S/g"
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

async def get_soccerbet_api():
    matches_data = []
    matches_to_insert = []

    try:
        async with aiohttp.ClientSession() as session:
            # First get all leagues
            leagues = await get_football_leagues(session)
            if not leagues:
                return

            for league_id, league_name in leagues:
                url = f"https://www.soccerbet.rs/restapi/offer/sr/sport/S/league-group/{league_id}/mob"
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

                                    
                                    # 1X2
                                    try:
                                        odd1 = bet_map.get("1", {}).get("NULL", {}).get("ov", "N/A")
                                        odd2 = bet_map.get("2", {}).get("NULL", {}).get("ov", "N/A")
                                        odd3 = bet_map.get("3", {}).get("NULL", {}).get("ov", "N/A")
                                        
                                        if all(x != "N/A" for x in [odd1, odd2, odd3]):
                                            matches_to_insert.append((
                                                home_team, away_team,
                                                5, 1, 2, 0,
                                                float(odd1), float(odd2), float(odd3),
                                                kick_off_time
                                            ))
                                    except Exception as e:
                                        print(f"Error processing 1X2: {e}")

                                    # First Half 1X2
                                    try:
                                        odd1 = bet_map.get("4", {}).get("NULL", {}).get("ov", "N/A")
                                        odd2 = bet_map.get("5", {}).get("NULL", {}).get("ov", "N/A")
                                        odd3 = bet_map.get("6", {}).get("NULL", {}).get("ov", "N/A")
                                        
                                        if all(x != "N/A" for x in [odd1, odd2, odd3]):
                                            matches_to_insert.append((
                                                home_team, away_team,
                                                5, 1, 3, 0,
                                                float(odd1), float(odd2), float(odd3),
                                                kick_off_time
                                            ))
                                    except Exception as e:
                                        print(f"Error processing 1X2F: {e}")

                                    # Second Half 1X2
                                    try:
                                        odd1 = bet_map.get("235", {}).get("NULL", {}).get("ov", "N/A")
                                        odd2 = bet_map.get("236", {}).get("NULL", {}).get("ov", "N/A")
                                        odd3 = bet_map.get("237", {}).get("NULL", {}).get("ov", "N/A")
                                        
                                        if all(x != "N/A" for x in [odd1, odd2, odd3]):
                                            matches_to_insert.append((
                                                home_team, away_team,
                                                5, 1, 4, 0,
                                                float(odd1), float(odd2), float(odd3),
                                                kick_off_time
                                            ))
                                    except Exception as e:
                                        print(f"Error processing 1X2S: {e}")

                                    # GGNG
                                    try:
                                        gg = bet_map.get("272", {}).get("NULL", {}).get("ov", "N/A")
                                        ng = bet_map.get("273", {}).get("NULL", {}).get("ov", "N/A")
                                        
                                        if all(x != "N/A" for x in [gg, ng]):
                                            matches_to_insert.append((
                                                home_team, away_team,
                                                5, 1, 8, 0,
                                                float(gg), float(ng), 0,
                                                kick_off_time
                                            ))
                                    except Exception as e:
                                        print(f"Error processing GGNG: {e}")

                                    # Full match total goals
                                    total_goals_map = {
                                        1.5: {"under": "21", "over": "242"},
                                        2.5: {"under": "22", "over": "24"},
                                        3.5: {"under": "219", "over": "25"},
                                        4.5: {"under": "453", "over": "27"},
                                    }

                                    for total, codes in total_goals_map.items():
                                        try:
                                            under_odd = bet_map.get(codes["under"], {}).get("NULL", {}).get("ov", "N/A")
                                            over_odd = bet_map.get(codes["over"], {}).get("NULL", {}).get("ov", "N/A")
                                            
                                            if all(x != "N/A" for x in [under_odd, over_odd]):
                                                matches_to_insert.append((
                                                    home_team, away_team,
                                                    5, 1, 5, float(total),
                                                    float(under_odd), float(over_odd), 0,
                                                    kick_off_time
                                                ))
                                        except Exception as e:
                                            print(f"Error processing Total Goals {total}: {e}")

                                    # First half total goals
                                    total_goals_first_map = {
                                        0.5: {"under": "267", "over": "207"},
                                        1.5: {"under": "211", "over": "208"},
                                        2.5: {"under": "472", "over": "209"},
                                    }

                                    for total, codes in total_goals_first_map.items():
                                        try:
                                            under_odd = bet_map.get(codes["under"], {}).get("NULL", {}).get("ov", "N/A")
                                            over_odd = bet_map.get(codes["over"], {}).get("NULL", {}).get("ov", "N/A")
                                            
                                            if all(x != "N/A" for x in [under_odd, over_odd]):
                                                matches_to_insert.append((
                                                    home_team, away_team,
                                                    5, 1, 6, float(total),
                                                    float(under_odd), float(over_odd), 0,
                                                    kick_off_time
                                                ))
                                        except Exception as e:
                                            print(f"Error processing First Half Total Goals {total}: {e}")

                                    # Second half total goals
                                    total_goals_second_map = {
                                        0.5: {"under": "269", "over": "213"},
                                        1.5: {"under": "217", "over": "214"},
                                        2.5: {"under": "474", "over": "215"},
                                    }

                                    for total, codes in total_goals_second_map.items():
                                        try:
                                            under_odd = bet_map.get(codes["under"], {}).get("NULL", {}).get("ov", "N/A")
                                            over_odd = bet_map.get(codes["over"], {}).get("NULL", {}).get("ov", "N/A")
                                            
                                            if all(x != "N/A" for x in [under_odd, over_odd]):
                                                matches_to_insert.append((
                                                    home_team, away_team,
                                                    5, 1, 7, float(total),
                                                    float(under_odd), float(over_odd), 0,
                                                    kick_off_time
                                                ))
                                        except Exception as e:
                                            print(f"Error processing Second Half Total Goals {total}: {e}")

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
