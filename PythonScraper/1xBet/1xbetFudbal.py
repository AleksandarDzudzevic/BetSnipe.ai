import aiohttp
import asyncio
import json
from datetime import datetime
import sys
from pathlib import Path
import time

sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

async def fetch_league_matches(session, league):
    url = "https://1xbet.rs/service-api/LineFeed/Get1x2_VZip"
    params = {
        "sports": "1",
        "champs": league,
        "count": "50",
        "lng": "en",
        "mode": "4",
        "partner": "321",
        "getEmpty": "true",
        "virtualSports": "true"
    }
    
    async with session.get(url, params=params) as response:
        data = await response.json()
        return [item['N'] for item in data.get('Value', []) if 'N' in item]

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
    
    async with session.get(match_url, params=match_params) as response:
        return await response.json()

async def fetch_1xbet_data_async():
    leagues = [
        # European competitions
        "118587",  # Champions League
        "118593",  # Europa League
        #"2252762", # Konferencija, ne odkomentarisati ovo je pakleno

        # England
        "88637",   # Premier League
        "105759",  # Championship
        
        # Italy
        "110163",  # Serie A
        "7067",    # Serie B
        
        # Germany
        "96463",   # Bundesliga
        "109313",  # 2. Bundesliga
        
        # Spain
        "127733",  # La Liga
        
        # France
        "12821",   # Ligue 1
        "12829",   # Ligue 2
        
        # Netherlands
        "2018750", # Eredivisie
        
        # Other countries
        "119599",  # Argentina
        "104509",  # Australia
        "28787",   # Belgium
        "16819",   # Saudi Arabia
        "8777",    # Greece
        "11113"    # Turkey
    ]
    
    matches_to_insert = []
    conn = get_db_connection()
    
    try:
        async with aiohttp.ClientSession() as session:
            # Fetch all match IDs concurrently
            tasks = [fetch_league_matches(session, league) for league in leagues]
            match_ids_lists = await asyncio.gather(*tasks)
            match_ids = [id for sublist in match_ids_lists for id in sublist]
            
            # Fetch match details concurrently
            tasks = [fetch_match_details(session, match_id) for match_id in match_ids]
            match_details = await asyncio.gather(*tasks)
            
            # Process match details
            for match_data in match_details:
                try:
                    value = match_data.get('Value', {})
                    home_team = value.get('O1')
                    away_team = value.get('O2')
                    start_timestamp = value.get('S')
                    
                    if not home_team or not away_team or "Home" in home_team or "Away" in away_team:
                        continue
                    
                    if not start_timestamp:
                        continue
                        
                    start_time = datetime.fromtimestamp(start_timestamp)
                    game_events = value.get('GE', [])
                    
                    for event in game_events:
                        # Full time 1X2 market
                        if event.get('G') == 1 and event.get('GS') == 1:
                            odds = event.get('E', [])
                            if odds:
                                odd1 = odds[0][0].get('C') if odds[0] else None
                                odd2 = odds[1][0].get('C') if odds[1] else None
                                odd3 = odds[2][0].get('C') if odds[2] else None
                                
                                matches_to_insert.append((
                                    home_team, away_team, 6, 1, 2,
                                    0, odd1, odd2, odd3, start_time
                                ))
                        
                        # Both Teams To Score market (GGNG)
                        if event.get('G') == 19 and event.get('GS') == 21:
                            odds = event.get('E', [])
                            if odds:
                                yes_odd = odds[0][0].get('C') if odds[0] else None
                                no_odd = odds[1][0].get('C') if odds[1] else None
                                
                                matches_to_insert.append((
                                    home_team, away_team, 6, 1, 8,
                                    0, yes_odd, no_odd, 0, start_time
                                ))
                        
                        # First Half 1X2 market
                        if event.get('G') == 3007 and event.get('GS') == 1075:
                            odds = event.get('E', [])
                            if odds:
                                odd1 = odds[0][0].get('C') if odds[0] else None
                                odd2 = odds[1][0].get('C') if odds[1] else None
                                odd3 = odds[2][0].get('C') if odds[2] else None
                                
                                matches_to_insert.append((
                                    home_team, away_team, 6, 1, 3,
                                    0, odd1, odd2, odd3, start_time
                                ))
                        
                        # Total Goals market (Full match)
                        if event.get('G') == 17 and event.get('GS') == 4:
                            odds = event.get('E', [])
                            if len(odds) >= 2:
                                over_odds = odds[0]
                                under_odds = odds[1]
                                
                                for i in range(len(over_odds)):
                                    over_bet = over_odds[i]
                                    if over_bet.get('P') and str(over_bet.get('P')).endswith('.5'):
                                        margin = over_bet.get('P')
                                        over_odd = over_bet.get('C')
                                        
                                        for under_bet in under_odds:
                                            if under_bet.get('P') == margin:
                                                under_odd = under_bet.get('C')
                                                
                                                matches_to_insert.append((
                                                    home_team, away_team, 6, 1, 5,
                                                    margin, under_odd, over_odd, 0, start_time
                                                ))
                                                break
                        
                        # First Half Total Goals
                        if event.get('G') == 15 and event.get('GS') == 5:
                            odds = event.get('E', [])
                            if len(odds) >= 2:
                                over_odds = odds[0]
                                under_odds = odds[1]
                                
                                for i in range(len(over_odds)):
                                    over_bet = over_odds[i]
                                    if over_bet.get('P') and str(over_bet.get('P')).endswith('.5'):
                                        margin = over_bet.get('P')
                                        over_odd = over_bet.get('C')
                                        
                                        for under_bet in under_odds:
                                            if under_bet.get('P') == margin:
                                                under_odd = under_bet.get('C')
                                                
                                                matches_to_insert.append((
                                                    home_team, away_team, 6, 1, 6,
                                                    margin, under_odd, over_odd, 0, start_time
                                                ))
                                                break
                        
                        # Second Half Total Goals
                        if event.get('G') == 62 and event.get('GS') == 6:
                            odds = event.get('E', [])
                            if len(odds) >= 2:
                                over_odds = odds[0]
                                under_odds = odds[1]
                                
                                for i in range(len(over_odds)):
                                    over_bet = over_odds[i]
                                    if over_bet.get('P') and str(over_bet.get('P')).endswith('.5'):
                                        margin = over_bet.get('P')
                                        over_odd = over_bet.get('C')
                                        
                                        for under_bet in under_odds:
                                            if under_bet.get('P') == margin:
                                                under_odd = under_bet.get('C')
                                                
                                                matches_to_insert.append((
                                                    home_team, away_team, 6, 1, 7,
                                                    margin, under_odd, over_odd, 0, start_time
                                                ))
                                                break
                
                except Exception as e:
                    print(f"Error processing match data: {e}")
    
    except Exception as e:
        print(f"Error in async operations: {e}")
    
    # Batch insert all collected matches
    try:
        batch_insert_matches(conn, matches_to_insert)
    except Exception as e:
        print(f"Error inserting matches into database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(fetch_1xbet_data_async())
