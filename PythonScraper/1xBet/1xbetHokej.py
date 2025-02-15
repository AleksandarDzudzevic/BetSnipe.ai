import aiohttp
import asyncio
import json
from datetime import datetime
import sys
from pathlib import Path
import time

sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

async def fetch_hockey_leagues(session):
    url = "https://1xbet.rs/service-api/LineFeed/GetChampsZip"
    params = {
        "sport": "2",  # Hockey sport ID
        "lng": "en",
        "country": "168",
        "partner": "321",
        "virtualSports": "true",
        "groupChamps": "true"
    }
    
    try:
        async with session.get(url, params=params) as response:
            data = await response.json()
            league_ids = []
            
            # Extract league IDs from all categories
            for category in data.get('Value', []):
                # Direct league entries
                if 'LI' in category:
                    league_ids.append(str(category.get('LI')))
                # Subcategory league entries
                if 'SC' in category:
                    for subcategory in category.get('SC', []):
                        league_ids.append(str(subcategory.get('LI')))
            
            return league_ids
    except Exception as e:
        print(f"Error fetching hockey leagues: {e}")
        return []

async def fetch_league_matches(session, league):
    url = "https://1xbet.rs/service-api/LineFeed/Get1x2_VZip"
    params = {
        "sports": "2",  # Hockey sport ID
        "champs": league,
        "count": "50",
        "lng": "en",
        "mode": "4",
        "partner": "321",
        "getEmpty": "true",
        "virtualSports": "true"
    }
    
    try:
        async with session.get(url, params=params) as response:
            data = await response.json()
            return [item['N'] for item in data.get('Value', []) if 'N' in item]
    except Exception as e:
        print(f"Error fetching league {league} matches: {e}")
        return []

async def fetch_match_details(session, match_id):
    match_url = "https://1xbet.rs/service-api/LineFeed/GetGameZip"
    match_params = {
        "id": str(match_id),
        "lng": "en",
        "isSubGames": "true",
        "GroupEvents": "true",
        "countevents": "250",
        "grMode": "4",
        "partner": "321",
        "topGroups": "",
        "marketType": "1"
    }
    
    try:
        async with session.get(match_url, params=match_params) as response:
            return await response.json()
    except Exception as e:
        print(f"Error fetching match {match_id} details: {e}")
        return None

async def fetch_1xbet_hockey_data_async():
    matches_to_insert = []
    conn = get_db_connection()
    
    try:
        async with aiohttp.ClientSession() as session:
            # First, fetch all hockey leagues
            leagues = await fetch_hockey_leagues(session)
            print(f"Found {len(leagues)} hockey leagues")
            
            # Fetch all match IDs concurrently
            tasks = [fetch_league_matches(session, league) for league in leagues]
            match_ids_lists = await asyncio.gather(*tasks)
            match_ids = [id for sublist in match_ids_lists for id in sublist]
            print(f"Found {len(match_ids)} hockey matches")
            
            # Fetch match details concurrently
            tasks = [fetch_match_details(session, match_id) for match_id in match_ids]
            match_details = await asyncio.gather(*tasks)
            
            # Process match details
            for match_data in match_details:
                if not match_data:
                    continue
                    
                try:
                    value = match_data.get('Value', {})
                    home_team = value.get('O1')
                    away_team = value.get('O2')
                    start_timestamp = value.get('S')
                    
                    if not home_team or not away_team or not start_timestamp:
                        continue
                        
                    start_time = datetime.fromtimestamp(start_timestamp)
                    game_events = value.get('GE', [])
                    
                    for event in game_events:
                        # 1X2 market
                        if event.get('G') == 1 and event.get('GS') == 1:
                            odds = event.get('E', [])
                            if len(odds) >= 3:  # Hockey has 3 outcomes (home, draw, away)
                                odd1 = odds[0][0].get('C') if odds[0] else None
                                oddX = odds[1][0].get('C') if odds[1] else None
                                odd2 = odds[2][0].get('C') if odds[2] else None
                                
                                if odd1 and oddX and odd2:
                                    matches_to_insert.append((
                                        home_team, away_team, 2, 2, 1,  # 2 for hockey, 1 for market type
                                        odd1, oddX, odd2, 0, start_time
                                    ))
                
                except Exception as e:
                    print(f"Error processing match data: {e}")
    
    except Exception as e:
        print(f"Error in async operations: {e}")
    
    # Batch insert all collected matches
    try:
        if matches_to_insert:
            batch_insert_matches(conn, matches_to_insert)
            print(f"Inserted {len(matches_to_insert)} hockey matches")
    except Exception as e:
        print(f"Error inserting matches into database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(fetch_1xbet_hockey_data_async())
    print(f"Total execution time: {time.time() - start_time:.2f} seconds")
