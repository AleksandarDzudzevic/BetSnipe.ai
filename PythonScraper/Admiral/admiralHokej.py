import aiohttp
import asyncio
import json
import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_utils import get_db_connection, batch_insert_matches

url1 = "https://srboffer.admiralbet.rs/api/offer/BetTypeSelections?sportId=4&pageId=35"
url2 = "https://srboffer.admiralbet.rs/api/offer/getWebEventsSelections"
url_odds = "https://srboffer.admiralbet.rs/api/offer/betsAndGroups"

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

async def fetch_hockey_leagues(session):
    """Fetch current hockey leagues from Admiral"""
    url = "https://srboffer.admiralbet.rs/api/offer/webTree/null/true/true/true/2025-02-10T20:48:46.651/2030-02-10T20:48:16.000/false"
    params = {"eventMappingTypes": ["1", "2", "3", "4", "5"]}
    
    try:
        async with session.get(url, params=params, headers=headers) as response:
            data = await response.json()
            leagues = []
            
            # Find hockey in the sports list
            for sport in data:
                if sport.get("id") == 4:  # Hockey
                    # Iterate through regions
                    for region in sport.get("regions", []):
                        # Get competitions from each region
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
    odds_url = f"{url_odds}/4/{competition['regionId']}/{competition['competitionId']}/{match['id']}"
    async with session.get(odds_url, headers=headers) as response:
        return await response.json()

async def fetch_matches(session, url2, competition, params):
    async with session.get(url2, params=params, headers=headers) as response:
        return await response.json()

async def fetch_admiral_hockey():
    matches_to_insert = []
    conn = get_db_connection()
    
    try:
        async with aiohttp.ClientSession() as session:
            # First get the leagues
            competitions = await fetch_hockey_leagues(session)
            
            if not competitions:
                print("No leagues found")
                return
            
            # Fetch matches for all competitions concurrently
            fetch_tasks = []
            for competition in competitions:
                params = {
                    "pageId": "35",
                    "sportId": "4",  # Hockey
                    "regionId": competition["regionId"],
                    "competitionId": competition["competitionId"],
                    "isLive": "false",
                    "dateFrom": "2025-01-18T19:42:15.955",
                    "dateTo": "2030-01-18T19:41:45.000",
                    "eventMappingTypes": ["1", "2", "3", "4", "5"],
                }
                fetch_tasks.append(fetch_matches(session, url2, competition, params))
            
            matches_data = await asyncio.gather(*fetch_tasks)
            
            # Process each match one at a time instead of gathering all odds at once
            for comp_idx, matches in enumerate(matches_data):
                competition = competitions[comp_idx]
                for match in matches:
                    match_name = match.get("name", "")
                    if " - " in match_name:
                        try:
                            team1, team2 = match_name.split(" - ")
                            match_datetime = match.get("dateTime", "")
                            if match_datetime.endswith('Z'):
                                match_datetime = match_datetime[:-1]
                            
                            # Fetch odds for this match
                            odds_result = await fetch_match_odds(session, url_odds, competition, match)
                            
                            # Look for final result odds
                            for bet in odds_result.get("bets", []):
                                if bet.get("betTypeName") == "Konacan ishod":
                                    outcomes = bet.get("betOutcomes", [])
                                    if len(outcomes) >= 3:
                                        odd1 = outcomes[0].get("odd", "0.00")
                                        oddX = outcomes[1].get("odd", "0.00")
                                        odd2 = outcomes[2].get("odd", "0.00")
                                        
                                        matches_to_insert.append((
                                            team1,
                                            team2,
                                            4,              # bookmaker_id (Admiral)
                                            4,              # sport_id (Hockey)
                                            2,              # bet_type_id (1X2)
                                            0,              # margin
                                            float(odd1),
                                            float(oddX),
                                            float(odd2),
                                            match_datetime
                                        ))
                                        break
                        
                        except Exception as e:
                            print(f"Error processing match: {e}")
                            continue
    
    except Exception as e:
        print(f"Error in admiralHokej: {e}")
        return
    
    # Batch insert all matches
    try:
        conn = get_db_connection()
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

if __name__ == "__main__":
    asyncio.run(fetch_admiral_hockey())
