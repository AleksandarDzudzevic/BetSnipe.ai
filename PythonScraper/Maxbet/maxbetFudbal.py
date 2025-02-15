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

SOCCER_LEAGUES = {
    "champions_league": "136866",
    "europa_league": "136867",
    "conference_league": "180457",
    "premier_league": "152506",
    "england_2": "119606",
    "bundesliga": "117683",
    "bundesliga_2": "132231",
    "ligue_1": "117827",
    "ligue_2": "117861",
    "serie_a": "117689",
    "serie_b": "117690",
    "la_liga": "117709",
    "la_liga_2": "117710",
    "argentina_1": "143555",
    "australia_1": "132134",
    "brazil_1": "135401",
    "netherlands_1": "117808",
    "belgium_1": "152568",
    "saudi_1": "161743",
    "greece_1": "132131",
    "turkey_1": "119607",
}

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
    url = f"https://www.maxbet.rs/restapi/offer/sr/sport/S/league/{league_id}/mob"
    async with session.get(url, params=params, headers=headers) as response:
        return await response.json()

async def fetch_maxbet_matches():
    matches_to_insert = []
    conn = get_db_connection()
    params = {"annex": "3", "desktopVersion": "1.2.1.10", "locale": "sr"}
    
    try:
        async with aiohttp.ClientSession() as session:
            league_tasks = []
            for league_name, league_id in SOCCER_LEAGUES.items():
                league_tasks.append(fetch_league_matches(session, league_id, params))
            
            leagues_data = await asyncio.gather(*league_tasks)
            
            match_ids = []
            for league_data in leagues_data:
                if "esMatches" in league_data:
                    for match in league_data["esMatches"]:
                        match_ids.append(match["id"])
            
            match_tasks = []
            for match_id in match_ids:
                match_tasks.append(fetch_match_details(session, match_id, params))
            
            matches_data = await asyncio.gather(*match_tasks)
            
            for match_data in matches_data:
                try:
                    home_team = match_data.get("home", "")
                    away_team = match_data.get("away", "")
                    kick_off_time = convert_unix_to_iso(match_data.get("kickOffTime", 0))
                    odds = match_data.get("odds", {})
                    
                    home_win = odds.get("1", "")
                    draw = odds.get("2", "")
                    away_win = odds.get("3", "")
                    
                    if home_win and draw and away_win:
                        matches_to_insert.append((
                            home_team, away_team,
                            3,  # Maxbet
                            1,  # Football
                            2,  # 1X2
                            0,  # No margin
                            float(home_win),
                            float(draw),
                            float(away_win),
                            kick_off_time
                        ))
                    
                    home_win_fh = odds.get("4", "")
                    draw_fh = odds.get("5", "")
                    away_win_fh = odds.get("6", "")
                    
                    if home_win_fh and draw_fh and away_win_fh:
                        matches_to_insert.append((
                            home_team, away_team,
                            3,  # Maxbet
                            1,  # Football
                            3,  # First Half 1X2
                            0,  # No margin
                            float(home_win_fh),
                            float(draw_fh),
                            float(away_win_fh),
                            kick_off_time
                        ))
                    
                    home_win_sh = odds.get("235", "")
                    draw_sh = odds.get("236", "")
                    away_win_sh = odds.get("237", "")
                    
                    if home_win_sh and draw_sh and away_win_sh:
                        matches_to_insert.append((
                            home_team, away_team,
                            3,  # Maxbet
                            1,  # Football
                            4,  # Second Half 1X2
                            0,  # No margin
                            float(home_win_sh),
                            float(draw_sh),
                            float(away_win_sh),
                            kick_off_time
                        ))
                    
                    gg = odds.get("272", "")
                    ng = odds.get("273", "")
                    
                    if gg and ng:
                        matches_to_insert.append((
                            home_team, away_team,
                            3,  # Maxbet
                            1,  # Football
                            8,  # GGNG
                            0,  # No margin
                            float(gg),
                            float(ng),
                            0,  # No third odd
                            kick_off_time
                        ))
                    
                    total_goals_pairs = [
                        ("1.5", "211", "242"),
                        ("2.5", "22", "24"),
                        ("3.5", "219", "25"),
                        ("4.5", "453", "27"),
                        ("5.5", "266", "223"),
                    ]
                    
                    total_goals_first_half_pairs = [
                        ("0.5", "188", "207"),
                        ("1.5", "211", "208"),  # ili 230 umesto 211
                        ("2.5", "472", "209"),
                    ]
                    
                    total_goals_second_half_pairs = [
                        ("0.5", "269", "213"),
                        ("1.5", "217", "214"),  # ili 390 umesto 217
                        ("2.5", "474", "215"),
                    ]
                    
                    for total, under_code, over_code in total_goals_pairs:
                        under_odd = odds.get(under_code, "")
                        over_odd = odds.get(over_code, "")
                        if under_odd and over_odd:
                            matches_to_insert.append((
                                home_team, away_team,
                                3,  # Maxbet
                                1,  # Football
                                5,  # Total Goals
                                float(total),  # Goals line as margin
                                float(under_odd),
                                float(over_odd),
                                0,  # No third odd
                                kick_off_time
                            ))
                    
                    for total, under_code, over_code in total_goals_first_half_pairs:
                        under_odd = odds.get(under_code, "")
                        over_odd = odds.get(over_code, "")
                        if under_odd and over_odd:
                            matches_to_insert.append((
                                home_team, away_team,
                                3,  # Maxbet
                                1,  # Football
                                6,  # First Half Total
                                float(total),  # Goals line as margin
                                float(under_odd),
                                float(over_odd),
                                0,  # No third odd
                                kick_off_time
                            ))
                    
                    for total, under_code, over_code in total_goals_second_half_pairs:
                        under_odd = odds.get(under_code, "")
                        over_odd = odds.get(over_code, "")
                        if under_odd and over_odd:
                            matches_to_insert.append((
                                home_team, away_team,
                                3,  # Maxbet
                                1,  # Football
                                7,  # Second Half Total
                                float(total),  # Goals line as margin
                                float(under_odd),
                                float(over_odd),
                                0,  # No third odd
                                kick_off_time
                            ))
                    
                except Exception as e:
                    print(f"Error processing match: {e}")
                    continue
    
    except Exception as e:
        print(f"Error in async operations: {e}")
    
    try:
        batch_insert_matches(conn, matches_to_insert)
    except Exception as e:
        print(f"Error inserting matches into database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(fetch_maxbet_matches())
