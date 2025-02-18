import aiohttp
import asyncio
import json
import csv
import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_utils import get_db_connection, batch_insert_matches

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

# Update the bet type IDs for basketball
BET_TYPES = {
    "full_time_1x2": 186,  # Winner (Pobednik)
    "total_points": 213,  # Total Points
    "handicap": 191,  # Handicap (Hendikep)
}

async def fetch_match_odds(session, url_odds, competition, match):
    odds_url = f"{url_odds}/2/{competition['regionId']}/{competition['competitionId']}/{match['id']}"
    async with session.get(odds_url, headers=headers) as response:
        return await response.json()

async def fetch_matches(session, url2, competition, params):
    async with session.get(url2, params=params, headers=headers) as response:
        return await response.json()

async def fetch_basketball_leagues(session):
    """Fetch current basketball leagues from Admiral"""
    url = "https://srboffer.admiralbet.rs/api/offer/webTree/null/true/true/true/2025-02-10T20:48:46.651/2030-02-10T20:48:16.000/false"
    params = {"eventMappingTypes": ["1", "2", "3", "4", "5"]}
    
    try:
        async with session.get(url, params=params, headers=headers) as response:
            data = await response.json()
            leagues = []
            
            # Find basketball in the sports list
            for sport in data:
                if sport.get("id") == 2:  # Basketball
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

async def fetch_admiral_basketball():
    matches_to_insert = []
    conn = get_db_connection()
    
    try:
        async with aiohttp.ClientSession() as session:
            # First get the leagues
            competitions = await fetch_basketball_leagues(session)
            
            if not competitions:
                print("No leagues found")
                return
            
            # Fetch matches for all competitions concurrently
            fetch_tasks = []
            for competition in competitions:
                params = {
                    "pageId": "35",
                    "sportId": "2",  # Basketball
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
                        if isinstance(odds_result, dict) and "bets" in odds_result:
                            bets = odds_result["bets"]
                            
                            for bet in bets:
                                bet_type_id = bet.get("betTypeId")
                                
                                # 1. Winner (12)
                                if bet_type_id == BET_TYPES["full_time_1x2"]:
                                    outcomes = sorted(bet["betOutcomes"], key=lambda x: x["orderNo"])
                                    if len(outcomes) >= 2:
                                        matches_to_insert.append((
                                            team1,
                                            team2,
                                            4,              # bookmaker_id (Admiral)
                                            2,              # sport_id (Basketball)
                                            1,              # bet_type_id (12)
                                            0,              # margin
                                            float(outcomes[0]["odd"]),
                                            float(outcomes[1]["odd"]),
                                            0,              # no odd3 for basketball
                                            match_datetime
                                        ))

                                # 2. Total Points
                                elif bet_type_id == BET_TYPES["total_points"]:
                                    totals = {}
                                    for outcome in bet["betOutcomes"]:
                                        total = outcome.get("sBV")
                                        if total:
                                            if total not in totals:
                                                totals[total] = {}
                                            if outcome["name"].lower() == "vise":
                                                totals[total]["over"] = outcome["odd"]
                                            elif outcome["name"].lower() == "manje":
                                                totals[total]["under"] = outcome["odd"]

                                    for total, odds in totals.items():
                                        if "over" in odds and "under" in odds:
                                            matches_to_insert.append((
                                                team1,
                                                team2,
                                                4,              # bookmaker_id
                                                2,              # sport_id
                                                10,             # bet_type_id (Total Points)
                                                float(total),   # margin is the total
                                                float(odds["under"]),
                                                float(odds["over"]),
                                                0,
                                                match_datetime
                                            ))

                                # 3. Handicap
                                elif bet_type_id == BET_TYPES["handicap"]:
                                    handicaps = {}
                                    for outcome in bet["betOutcomes"]:
                                        handicap = outcome.get("sBV")
                                        if handicap:
                                            if handicap not in handicaps:
                                                handicaps[handicap] = {}
                                            if outcome["name"] == "1":
                                                handicaps[handicap]["team1"] = outcome["odd"]
                                            elif outcome["name"] == "2":
                                                handicaps[handicap]["team2"] = outcome["odd"]

                                    for handicap, odds in handicaps.items():
                                        if "team1" in odds and "team2" in odds:
                                            matches_to_insert.append((
                                                team1,
                                                team2,
                                                4,              # bookmaker_id
                                                2,              # sport_id
                                                9,              # bet_type_id (Handicap)
                                                float(handicap),
                                                float(odds["team1"]),
                                                float(odds["team2"]),
                                                0,
                                                match_datetime
                                            ))

                    except Exception as e:
                        print(f"Error processing match: {e}")
                        continue
    
    except Exception as e:
        print(f"Error in admiralKosarka: {e}")
        return
    
    # Batch insert all matches
    try:
        batch_insert_matches(conn, matches_to_insert)
    except Exception as e:
        print(f"Error inserting matches into database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(fetch_admiral_basketball())