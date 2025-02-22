import cloudscraper
import asyncio
import json
from datetime import datetime
import sys
from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor
import random
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

# Create a global scraper instance
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'mobile': False
    },
    delay=2
)

async def fetch_with_cloudscraper(url, params=None):
    """Helper function to make async requests using cloudscraper"""
    await asyncio.sleep(random.uniform(1, 3))
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        try:
            response = await loop.run_in_executor(
                executor,
                lambda: scraper.get(url, params=params, timeout=30)
            )
            return response.json()
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

async def fetch_table_tennis_leagues():
    url = "https://1xbet.rs/service-api/LineFeed/GetChampsZip"
    params = {
        "sport": "10",  # Table Tennis sport ID
        "lng": "en",
        "country": "168",
        "partner": "321",
        "virtualSports": "true",
        "groupChamps": "true"
    }
    
    data = await fetch_with_cloudscraper(url, params)
    if not data:
        return []
        
    league_ids = []
    for category in data.get('Value', []):
        if 'LI' in category:
            league_ids.append(str(category['LI']))
        for subcategory in category.get('SC', []):
            if 'LI' in subcategory:
                league_ids.append(str(subcategory['LI']))
    
    return league_ids

async def fetch_league_matches(league):
    url = "https://1xbet.rs/service-api/LineFeed/Get1x2_VZip"
    params = {
        "sports": "10",  # Table Tennis sport ID
        "champs": league,
        "count": "50",
        "lng": "en",
        "mode": "4",
        "partner": "321",
        "getEmpty": "true",
        "virtualSports": "true"
    }
    
    data = await fetch_with_cloudscraper(url, params)
    if data:
        return [item['N'] for item in data.get('Value', []) if 'N' in item]
    return []

async def fetch_match_details(match_id):
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
    
    return await fetch_with_cloudscraper(match_url, match_params)

async def fetch_1xbet_table_tennis_data_async():
    matches_to_insert = []
    conn = get_db_connection()
    
    try:
        # First, fetch all table tennis leagues
        leagues = await fetch_table_tennis_leagues()
        print(f"Found {len(leagues)} table tennis leagues")
        
        # Fetch all match IDs concurrently - Fixed the league parameter
        match_ids = []
        for league in leagues:
            league_matches = await fetch_league_matches(league)
            match_ids.extend(league_matches)
        print(f"Found {len(match_ids)} table tennis matches")
        
        # Fetch match details concurrently
        tasks = [fetch_match_details(match_id) for match_id in match_ids]
        match_details = await asyncio.gather(*tasks)
        
        # Process match details
        for match_data in match_details:
            if not match_data:
                continue
                
            try:
                value = match_data.get('Value', {})
                home_player = value.get('O1')
                away_player = value.get('O2')
                start_timestamp = value.get('S')
                
                if not home_player or not away_player or not start_timestamp:
                    continue
                    
                start_time = datetime.fromtimestamp(start_timestamp)
                game_events = value.get('GE', [])
                
                for event in game_events:
                    # Winner/Loser market (1/2)
                    if event.get('G') == 1 and event.get('GS') == 1:
                        odds = event.get('E', [])
                        if len(odds) >= 2:  # Table Tennis has only 2 outcomes (no draw)
                            odd1 = odds[0][0].get('C') if odds[0] else None
                            odd2 = odds[1][0].get('C') if odds[1] else None
                            
                            if odd1 and odd2:
                                matches_to_insert.append((
                                    home_player, 
                                    away_player, 
                                    7,  # 1xBet ID
                                    5,  # Table Tennis sport ID
                                    1,  # Winner market type
                                    0,  # No margin
                                    float(odd1), 
                                    float(odd2), 
                                    0,  # No third odd
                                    start_time
                                ))
                
            except Exception as e:
                print(f"Error processing match data: {e}")
    
    except Exception as e:
        print(f"Error in async operations: {e}")
    
    # Batch insert all collected matches
    try:
        if matches_to_insert:
            batch_insert_matches(conn, matches_to_insert)
            print(f"Inserted {len(matches_to_insert)} table tennis matches")
    except Exception as e:
        print(f"Error inserting matches into database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(fetch_1xbet_table_tennis_data_async())
    print(f"Total execution time: {time.time() - start_time:.2f} seconds")
