import aiohttp
import asyncio
import json
import csv
import ssl
import sys
from pathlib import Path
import time

sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

ssl._create_default_https_context = ssl._create_unverified_context

url1 = "https://srboffer.admiralbet.rs/api/offer/BetTypeSelections?sportId=1&pageId=35"
url2 = "https://srboffer.admiralbet.rs/api/offer/getWebEventsSelections"
url_odds = "https://srboffer.admiralbet.rs/api/offer/betsAndGroups"

# Define all possible soccer competitions
competitions = [
    {"name": "Premier League", "competitionId": "1", "regionId": "1"},
    {"name": "Druga Engleska Liga", "competitionId": "2", "regionId": "1"},
    {"name": "La Liga", "competitionId": "3103", "regionId": "24"},
    {"name": "La Liga 2", "competitionId": "604", "regionId": "24"},
    {"name": "Bundesliga", "competitionId": "614", "regionId": "22"},
    {"name": "Bundesliga B", "competitionId": "612", "regionId": "22"},
    {"name": "Serie A", "competitionId": "597", "regionId": "23"},
    {"name": "Serie B", "competitionId": "600", "regionId": "23"},
    {"name": "Ligue 1", "competitionId": "564", "regionId": "4"},
    {"name": "Ligue 2", "competitionId": "581", "regionId": "4"},
    {"name": "Champions League", "competitionId": "764", "regionId": "104"},
    {"name": "Europa League", "competitionId": "1333", "regionId": "104"},
    {"name": "Argentiska Liga", "competitionId": "649", "regionId": "32"},
    {"name": "Liga Konferencije", "competitionId": "20951", "regionId": "104"},
    {"name": "Holandija Liga", "competitionId": "608", "regionId": "27"},
    {"name": "Brazilska Liga", "competitionId": "788", "regionId": "10"},
    {"name": "Australijska Liga", "competitionId": "670", "regionId": "26"},
    {"name": "Belgijska Liga", "competitionId": "606", "regionId": "25"},
    {"name": "Saudi Liga", "competitionId": "858", "regionId": "81"},
    {"name": "Grcka Liga", "competitionId": "666", "regionId": "38"},
    {"name": "Turska Liga", "competitionId": "641", "regionId": "30"},
]

headers = {
    "Accept": "application/utf8+json, application/json;q=0.9, text/plain;q=0.8, /;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Host": "srboffer.admiralbet.rs",
    "Language": "sr-Latn",
    "Officeid": "138",
    "Origin": "https://admiralbet.rs",
    "Referer": "https://admiralbet.rs/",
    "Sec-Ch-Ua": '"Brave";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

async def fetch_match_odds(session, url_odds, competition, match):
    odds_url = f"{url_odds}/1/{competition['regionId']}/{competition['competitionId']}/{match['id']}"
    async with session.get(odds_url, headers=headers) as response:
        return await response.json()

async def fetch_matches(session, url2, competition, params):
    async with session.get(url2, params=params, headers=headers) as response:
        return await response.json()

async def fetch_admiral_football():
    matches_to_insert = []
    conn = get_db_connection()
    
    try:
        async with aiohttp.ClientSession() as session:
            # Fetch matches for all competitions concurrently
            fetch_tasks = []
            for competition in competitions:
                params = {
                    "pageId": "35",
                    "sportId": "1",
                    "regionId": competition["regionId"],
                    "competitionId": competition["competitionId"],
                    "isLive": "false",
                    "dateFrom": "2025-01-18T19:42:15.955",
                    "dateTo": "2030-01-18T19:41:45.000",
                    "eventMappingTypes": ["1", "2", "3", "4", "5"],
                }
                fetch_tasks.append(fetch_matches(session, url2, competition, params))
            
            matches_data = await asyncio.gather(*fetch_tasks)
            
            # Process matches and fetch odds concurrently
            odds_tasks = []
            for comp_idx, matches in enumerate(matches_data):
                competition = competitions[comp_idx]
                for match in matches:
                    if match.get("name", "").count(" - ") == 1:
                        odds_tasks.append(fetch_match_odds(session, url_odds, competition, match))
            
            odds_data = await asyncio.gather(*odds_tasks)
            
            # Process all the data
            match_idx = 0
            for comp_idx, matches in enumerate(matches_data):
                competition = competitions[comp_idx]
                for match in matches:
                    if match.get("name", "").count(" - ") == 1:
                        try:
                            team1, team2 = match["name"].split(" - ")
                            match_datetime = match.get("dateTime", "")
                            if match_datetime.endswith('Z'):
                                match_datetime = match_datetime[:-1]
                            
                            odds_result = odds_data[match_idx]
                            match_idx += 1
                            
                            if isinstance(odds_result, dict) and "bets" in odds_result:
                                bets = odds_result["bets"]
                                
                                for bet in bets:
                                    bet_type_id = bet.get("betTypeId")
                                    
                                    # 1X2 Full Time
                                    if bet_type_id == 135:
                                        outcomes = sorted(bet["betOutcomes"], key=lambda x: x["orderNo"])
                                        if len(outcomes) >= 3:
                                            matches_to_insert.append((
                                                team1,
                                                team2,
                                                4,  # Admiral
                                                1,  # Football
                                                2,  # 1X2
                                                0,
                                                float(outcomes[0]["odd"]),
                                                float(outcomes[1]["odd"]),
                                                float(outcomes[2]["odd"]),
                                                match_datetime
                                            ))

                                    # 1X2 First Half
                                    elif bet_type_id == 148:
                                        outcomes = sorted(bet["betOutcomes"], key=lambda x: x["orderNo"])
                                        if len(outcomes) >= 3:
                                            matches_to_insert.append((
                                                team1,
                                                team2,
                                                4,
                                                1,
                                                3,   # 1X2F
                                                0,
                                                float(outcomes[0]["odd"]),
                                                float(outcomes[1]["odd"]),
                                                float(outcomes[2]["odd"]),
                                                match_datetime
                                            ))

                                    # 1X2 Second Half
                                    elif bet_type_id == 149:
                                        outcomes = sorted(bet["betOutcomes"], key=lambda x: x["orderNo"])
                                        if len(outcomes) >= 3:
                                            matches_to_insert.append((
                                                team1,
                                                team2,
                                                4,
                                                1,
                                                4,   # 1X2S
                                                0,
                                                float(outcomes[0]["odd"]),
                                                float(outcomes[1]["odd"]),
                                                float(outcomes[2]["odd"]),
                                                match_datetime
                                            ))

                                    # GGNG
                                    elif bet_type_id == 151:
                                        outcomes = sorted(bet["betOutcomes"], key=lambda x: x["orderNo"])
                                        if len(outcomes) >= 2:
                                            matches_to_insert.append((
                                                team1,
                                                team2,
                                                4,
                                                1,
                                                8,   # GGNG
                                                0,
                                                float(outcomes[0]["odd"]),
                                                float(outcomes[1]["odd"]),
                                                0,
                                                match_datetime
                                            ))

                                    # Total Goals
                                    elif bet_type_id in [137, 143, 144]:  # Full time, First half, Second half
                                        totals = {}
                                        for outcome in bet["betOutcomes"]:
                                            total = outcome["sBV"]
                                            if total not in totals:
                                                totals[total] = {}
                                            
                                            if outcome["name"].lower().startswith("vi"):
                                                totals[total]["over"] = outcome["odd"]
                                            else:
                                                totals[total]["under"] = outcome["odd"]

                                        for total, odds in totals.items():
                                            if "over" in odds and "under" in odds:
                                                bet_type = 5  # TG
                                                if bet_type_id == 143:
                                                    bet_type = 6  # TGF
                                                elif bet_type_id == 144:
                                                    bet_type = 7  # TGS

                                                matches_to_insert.append((
                                                    team1,
                                                    team2,
                                                    4,
                                                    1,
                                                    bet_type,
                                                    float(total),
                                                    float(odds["under"]),
                                                    float(odds["over"]),
                                                    0,
                                                    match_datetime
                                                ))

                        except Exception as e:
                            print(f"Error processing match: {e}")
                            continue
    
    except Exception as e:
        print(f"Error in async operations: {e}")
    
    # Batch insert all matches
    try:
        batch_insert_matches(conn, matches_to_insert)
    except Exception as e:
        print(f"Error inserting matches into database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(fetch_admiral_football())