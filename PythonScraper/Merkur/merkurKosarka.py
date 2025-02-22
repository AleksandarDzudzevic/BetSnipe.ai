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
async def get_basketball_leagues(session):
    """Fetch current basketball leagues from Merkur"""
    # Updated URL to match the working endpoint
    url = "https://www.merkurxtip.rs/restapi/offer/sr/categories/sport/B/g"
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
        async with aiohttp.ClientSession() as session:
            leagues = await get_basketball_leagues(session)
            print(f"Found {len(leagues)} leagues")
            if not leagues:
                print("No leagues found!")
                return
            
            for league_id, league_name in leagues:
                url = f"https://www.merkurxtip.rs/restapi/offer/sr/sport/B/league-group/{league_id}/mob"
                params = {"annex": "0", "desktopVersion": "1.3.2.6", "locale": "sr"}

                try:
                    async with session.get(url, params=params) as response:
                        data = await response.json()

                        if "esMatches" in data and len(data["esMatches"]) > 0:
                            matches = data["esMatches"]
                            
                            for match in matches:
                                match_id = match["id"]
                                match_url = f"https://www.merkurxtip.rs/restapi/offer/sr/match/{match_id}"
                                
                                async with session.get(match_url, params=params) as match_response:
                                    match_data = await match_response.json()
                                    
                                    home_team = match_data["home"]
                                    away_team = match_data["away"]
                                    kick_off_time = convert_unix_to_iso(match_data.get("kickOffTime", 0))
                                    odds = match_data.get("odds", {})

                                    # Winner odds (1X2)
                                    if "50291" in odds and "50293" in odds:
                                        matches_data.append({
                                            "Team1": home_team,
                                            "Team2": away_team,
                                            "dateTime": kick_off_time,
                                            "market": "12",
                                            "odd1": odds["50291"],
                                            "odd2": odds["50293"],
                                            "odd3": "",
                                        })
                                        matches_to_insert.append((
                                            home_team,
                                            away_team,
                                            5,  # Merkur
                                            2,  # Basketball
                                            1,  # Winner
                                            0,  # No margin
                                            float(odds["50291"]),
                                            float(odds["50293"]),
                                            0,  # No draw in basketball
                                            kick_off_time
                                        ))

                                    # Handicap
                                    if "50431" in odds and "50430" in odds:
                                        handicap = float(match_data.get("params", {}).get("handicapOvertime", "0").replace(",", "."))
                                        matches_data.append({
                                            "Team1": home_team,
                                            "Team2": away_team,
                                            "dateTime": kick_off_time,
                                            "market": f"H{handicap}",
                                            "odd1": odds["50430"],
                                            "odd2": odds["50431"],
                                            "odd3": "",
                                        })
                                        matches_to_insert.append((
                                            home_team,
                                            away_team,
                                            5,  # Merkur
                                            2,  # Basketball
                                            9,  # Handicap
                                            handicap,
                                            float(odds["50430"]),
                                            float(odds["50431"]),
                                            0,
                                            kick_off_time
                                        ))

                                    # Total Points
                                    if "50444" in odds and "50445" in odds:
                                        total = float(match_data.get("params", {}).get("overUnderOvertime", "0").replace(",", "."))
                                        matches_data.append({
                                            "Team1": home_team,
                                            "Team2": away_team,
                                            "dateTime": kick_off_time,
                                            "market": f"OU{total}",
                                            "odd1": odds["50444"],
                                            "odd2": odds["50445"],
                                            "odd3": "",
                                        })
                                        matches_to_insert.append((
                                            home_team,
                                            away_team,
                                            5,  # Merkur
                                            2,  # Basketball
                                            10,  # Total Points
                                            total,
                                            float(odds["50444"]),
                                            float(odds["50445"]),
                                            0,
                                            kick_off_time
                                        ))

                                await asyncio.sleep(0.05)  # Small delay between matches

                except Exception as e:
                    print(f"Error processing league {league_name}: {str(e)}")
                    continue

            print(f"Total matches to insert: {len(matches_to_insert)}")
            if matches_to_insert:
                try:
                    conn = get_db_connection()
                    batch_insert_matches(conn, matches_to_insert)
                    conn.close()
                    print("Successfully inserted matches into database")
                except Exception as e:
                    print(f"Database error: {e}")
            else:
                print("No matches found to insert!")

    except Exception as e:
        print(f"Error in async operations: {e}")

    return matches_data

if __name__ == "__main__":
    asyncio.run(get_merkur_api())