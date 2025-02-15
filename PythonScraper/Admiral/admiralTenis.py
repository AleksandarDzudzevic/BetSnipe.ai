import aiohttp
import asyncio
import json
import ssl
import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_utils import get_db_connection, batch_insert_matches

ssl._create_default_https_context = ssl._create_unverified_context

url1 = "https://srboffer.admiralbet.rs/api/offer/BetTypeSelections?sportId=3&pageId=35"
url2 = "https://srboffer.admiralbet.rs/api/offer/getWebEventsSelections"
url_odds = "https://srboffer.admiralbet.rs/api/offer/betsAndGroups"

headers = {
    "Accept": "application/utf8+json, application/json;q=0.9, text/plain;q=0.8, /;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "Host": "srboffer.admiralbet.rs",
    "Language": "sr-Latn",
    "Officeid": "138",
    "Origin": "https://admiralbet.rs",
    "Referer": "https://admiralbet.rs/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

async def fetch_tennis_leagues(session):
    """Fetch current tennis leagues from Admiral"""
    url = "https://srboffer.admiralbet.rs/api/offer/webTree/null/true/true/true/2025-02-10T20:48:46.651/2030-02-10T20:48:16.000/false"
    params = {"eventMappingTypes": ["1", "2", "3", "4", "5"]}
    
    try:
        async with session.get(url, params=params, headers=headers) as response:
            data = await response.json()
            leagues = []
            
            # Find tennis in the sports list
            for sport in data:
                if sport.get("id") == 3:  # Tennis
                    for region in sport.get("regions", []):
                        for competition in region.get("competitions", []):
                            leagues.append({
                                "regionId": competition.get("regionId"),
                                "competitionId": competition.get("competitionId"),
                                "name": competition.get("competitionName"),
                            })
            return leagues
    except Exception as e:
        print(f"Error fetching leagues: {str(e)}")
        return []

async def fetch_match_odds(session, url_odds, competition, match):
    odds_url = f"{url_odds}/3/{competition['regionId']}/{competition['competitionId']}/{match['id']}"
    async with session.get(odds_url, headers=headers) as response:
        return await response.json()

async def fetch_matches(session, url2, competition, params):
    async with session.get(url2, params=params, headers=headers) as response:
        return await response.json()

async def fetch_admiral_tennis():
    matches_to_insert = []
    conn = get_db_connection()
    
    try:
        async with aiohttp.ClientSession() as session:
            # First get the leagues
            competitions = await fetch_tennis_leagues(session)
            
            if not competitions:
                print("No leagues found")
                return
            
            # Fetch matches for all competitions concurrently
            fetch_tasks = []
            for competition in competitions:
                params = {
                    "pageId": "35",
                    "sportId": "3",  # Tennis
                    "regionId": competition["regionId"],
                    "competitionId": competition["competitionId"],
                    "isLive": "false",
                    "dateFrom": "2025-01-18T19:42:15.955",
                    "dateTo": "2030-01-18T19:41:45.000",
                    "eventMappingTypes": ["1", "2", "3", "4", "5"],
                }
                fetch_tasks.append(fetch_matches(session, url2, competition, params))
            
            matches_data = await asyncio.gather(*fetch_tasks)
            
            # Process each match one at a time
            for comp_idx, matches in enumerate(matches_data):
                competition = competitions[comp_idx]
                for match in matches:
                    match_name = match.get("name", "")
                    if " - " not in match_name:
                        continue
                        
                    try:
                        team1, team2 = match_name.split(" - ")
                        match_datetime = match.get("dateTime", "")
                        if match_datetime.endswith('Z'):
                            match_datetime = match_datetime[:-1]
                        
                        # Fetch odds for this match
                        odds_result = await fetch_match_odds(session, url_odds, competition, match)
                        
                        # Process bets
                        for bet in odds_result.get("bets", []):
                            bet_type = bet.get("betTypeName")
                            outcomes = bet.get("betOutcomes", [])
                            
                            if bet_type == "Pobednik" and len(outcomes) >= 2:
                                odd1 = outcomes[0].get("odd", "0.00")
                                odd2 = outcomes[1].get("odd", "0.00")
                                matches_to_insert.append((
                                    team1, team2,
                                    4,              # Admiral
                                    3,              # Tennis
                                    1,              # 12
                                    0,              # margin
                                    float(odd1),
                                    float(odd2),
                                    0,              # no odd3 for tennis
                                    match_datetime
                                ))
                            
                            elif bet_type == "1.set - Pobednik" and len(outcomes) >= 2:
                                odd1 = outcomes[0].get("odd", "0.00")
                                odd2 = outcomes[1].get("odd", "0.00")
                                matches_to_insert.append((
                                    team1, team2,
                                    4,             # Admiral
                                    3,              # Tennis
                                    11,             # 12set1
                                    0,              # margin
                                    float(odd1),
                                    float(odd2),
                                    0,              # no odd3 for tennis
                                    match_datetime
                                ))
                    
                    except Exception as e:
                        print(f"Error processing match: {e}")
                        continue
    
    except Exception as e:
        print(f"Error in admiralTenis: {e}")
        return
    
    # Batch insert all matches
    try:
        batch_insert_matches(conn, matches_to_insert)
    except Exception as e:
        print(f"Error inserting matches into database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(fetch_admiral_tennis())
