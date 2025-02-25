import requests
import sys
from pathlib import Path
from datetime import datetime
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

def fetch_topbet_data():
    base_url = "https://sports-sm-distribution-api.de-2.nsoftcdn.com/api/v1/events"
    
    # Using URL parameters exactly as they appear in the working URL
    params = {
        "deliveryPlatformId": "3",
        "dataFormat": '{"default":"object","events":"array","outcomes":"array"}',
        "language": '{"default":"sr-Latn","events":"sr-Latn","sport":"sr-Latn","category":"sr-Latn","tournament":"sr-Latn","team":"sr-Latn","market":"sr-Latn"}',
        "timezone": "Europe/Budapest",
        "company": "{}",
        "companyUuid": "4dd61a16-9691-4277-9027-8cd05a647844",
        "filter[sportId]": "3",
        "filter[from]": "2025-02-25T20:25:51",
        "sort": "categoryPosition,categoryName,tournamentPosition,tournamentName,startsAt",
        "offerTemplate": "WEB_OVERVIEW",
        "shortProps": "1"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://topbet.rs",
        "Referer": "https://topbet.rs/"
    }
    
    matches_to_insert = []
    conn = get_db_connection()
    
    try:
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if 'data' in data and 'events' in data['data']:
            events = data['data']['events']
            
            for event in events:
                try:
                    home_away = event.get('j', '').split(' - ')
                    if len(home_away) != 2:
                        continue
                        
                    home_team, away_team = home_away
                    start_time = datetime.strptime(event.get('n'), "%Y-%m-%dT%H:%M:%S.%fZ")
                    
                    # Process markets in event['o']
                    for market_id, market_data in event.get('o', {}).items():
                        # 1X2 market
                        if market_data.get('b') == 6 and market_data.get('d') == 1:
                            odds = market_data.get('h', [])
                            if len(odds) == 3:
                                odd1 = next((o['g'] for o in odds if o['e'] == '1'), None)
                                oddX = next((o['g'] for o in odds if o['e'] == 'X'), None)
                                odd2 = next((o['g'] for o in odds if o['e'] == '2'), None)
                                
                                if all([odd1, oddX, odd2]):
                                    matches_to_insert.append((
                                        home_team, away_team, 10, 1, 2,
                                        0, odd1, oddX, odd2, start_time
                                    ))
                        
                        # GG/NG market (Both Teams To Score)
                        if market_data.get('h'):
                            odds = market_data.get('h', [])
                            gg_odd = next((o['g'] for o in odds if o['e'] == 'GG'), None)
                            ng_odd = next((o['g'] for o in odds if o['e'] == 'NG'), None)
                            
                            if gg_odd and ng_odd:
                                matches_to_insert.append((
                                    home_team, away_team, 10, 1, 8,
                                    0, gg_odd, ng_odd, 0, start_time
                                ))
                
                except Exception as e:
                    print(f"Error processing match {event.get('j', 'Unknown')}: {e}")
        
        # Batch insert all collected matches
        if matches_to_insert:
            batch_insert_matches(conn, matches_to_insert)
            print(f"Successfully inserted {len(matches_to_insert)} matches")
        else:
            print("No matches to insert")
            
    except Exception as e:
        print(f"Error fetching data: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fetch_topbet_data()
