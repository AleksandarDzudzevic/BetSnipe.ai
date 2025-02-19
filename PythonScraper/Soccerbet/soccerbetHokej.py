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


async def get_hockey_leagues(session):
    """Fetch current hockey leagues from Soccerbet"""
    url = "https://www.soccerbet.rs/restapi/offer/sr/categories/ext/sport/H/g"
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


async def get_soccerbet_sports():
    matches_data = []
    matches_to_insert = []

    try:
        async with aiohttp.ClientSession() as session:
            # First get all leagues
            leagues = await get_hockey_leagues(session)
            if not leagues:
                return

            for league_id, league_name in leagues:
                url = f"https://www.soccerbet.rs/restapi/offer/sr/sport/H/league-group/{league_id}/mob"
                params = {"annex": "0", "desktopVersion": "2.36.3.7", "locale": "sr"}

                try:
                    async with session.get(url, params=params) as response:
                        data = await response.json()

                        if "esMatches" in data and data["esMatches"]:
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
                                    home_team = match_data.get("home", "")
                                    away_team = match_data.get("away", "")
                                    kick_off_time = convert_unix_to_iso(match_data.get("kickOffTime", 0))

                                    if home_team and away_team:
                                        # Get 1-X-2 odds
                                        home_win = bet_map.get("1", {}).get("NULL", {}).get("ov", "N/A")
                                        draw = bet_map.get("2", {}).get("NULL", {}).get("ov", "N/A")
                                        away_win = bet_map.get("3", {}).get("NULL", {}).get("ov", "N/A")

                                        if home_win != "N/A" and draw != "N/A" and away_win != "N/A":
                                            matches_data.append([
                                                home_team,
                                                away_team,
                                                kick_off_time,
                                                "1X2",
                                                home_win,
                                                draw,
                                                away_win,
                                            ])
                                            matches_to_insert.append((
                                                home_team,
                                                away_team,
                                                5,  # Soccerbet
                                                4,  # Hockey
                                                2,  # 1X2
                                                0,  # No margin
                                                float(home_win),
                                                float(draw),
                                                float(away_win),
                                                kick_off_time
                                            ))

                                await asyncio.sleep(0.05)  # Small delay between batches

                except Exception as e:
                    print(f"Error processing league {league_name}: {str(e)}")
                    continue

    except Exception as e:
        pass

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

    return matches_data


if __name__ == "__main__":
    asyncio.run(get_soccerbet_sports())
