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
        "sports": "3",  # Basketball
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

async def fetch_1xbet_basketball_async():
    
    leagues = ["13589"]  # NBA
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
                        # Match Winner (1/2)
                        if event.get('G') == 101 and event.get('GS') == 38:
                            odds = event.get('E', [])
                            if odds and len(odds) >= 2:
                                home_odd = odds[0][0].get('C') if odds[0] else None
                                away_odd = odds[1][0].get('C') if odds[1] else None
                                
                                if home_odd and away_odd:
                                    matches_to_insert.append((
                                        home_team, away_team, 6, 2, 1,  # 6=1xBet, 2=Basketball, 1=MoneyLine
                                        0, home_odd, away_odd, 0, start_time
                                    ))
                        
                        # Total Points Over/Under
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
                                                    home_team, away_team, 6, 2, 10,  # 10=TotalPoints
                                                    margin, under_odd, over_odd, 0, start_time
                                                ))
                                                break
                        
                        # Handicap
                        if event.get('G') == 2 and event.get('GS') == 3:
                            odds = event.get('E', [])
                            if len(odds) >= 2:
                                home_odds = odds[0]
                                away_odds = odds[1]
                                
                                for home_bet in home_odds:
                                    if home_bet.get('P') and str(home_bet.get('P')).endswith('.5'):
                                        margin = home_bet.get('P')
                                        home_odd = home_bet.get('C')
                                        
                                        for away_bet in away_odds:
                                            if abs(float(away_bet.get('P', 0))) == abs(float(margin)):
                                                away_odd = away_bet.get('C')
                                                matches_to_insert.append((
                                                    home_team, away_team, 6, 2, 9,  # 9=Handicap
                                                    margin, home_odd, away_odd, 0, start_time
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
    asyncio.run(fetch_1xbet_basketball_async())
