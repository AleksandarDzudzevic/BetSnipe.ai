import requests
import json
from datetime import datetime, timedelta
import csv

def fetch_axilis_tournament_ids():
    url = "https://scorealarm-stats.freetls.fastly.net/soccer/competition/details/rssuperbetsport/sr-Latn-RS"
    params = {
        "competition_id": "br:competition:7"
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Extract Axilis tournament IDs from tournament_mappings
        axilis_ids = []
        for mapping in data.get('tournament_mappings', []):
            # Extract the number from ax:tournament:XXXX format
            axilis_id = mapping.get('axilis', [])[0].split(':')[-1]
            axilis_ids.append(axilis_id)
        return axilis_ids
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Axilis data: {e}")
        return []

def fetch_event_ids(tournament_ids):
    url = "https://production-superbet-offer-rs.freetls.fastly.net/sb-rs/api/v2/sr-Latn-RS/events/by-date"
    
    # Join tournament IDs with commas
    tournament_ids_str = ','.join(tournament_ids)
    
    # Get current date in the required format
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Query parameters
    params = {
        "currentStatus": "active",
        "offerState": "prematch",
        "tournamentIds": tournament_ids_str,
        "startDate": current_date
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Extract event IDs from the data array
        event_ids = []
        if 'data' in data:
            for match in data['data']:
                if 'eventId' in match:  # or 'offerId', they're the same
                    event_ids.append(match['eventId'])
        return event_ids
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching event data: {e}")
        return []

def fetch_event_odds(event_id):
    url = f"https://production-superbet-offer-rs.freetls.fastly.net/sb-rs/api/v2/sr-Latn-RS/events/{event_id}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        if 'data' not in data or not data['data']:
            return None
            
        match_data = data['data'][0]
        match_name = match_data.get('matchName', '')
        
        # Split teams by the dot character and join with comma
        teams = match_name.split('·')
        match_name = ','.join(team.strip() for team in teams)
        
        # Find the "Konačan ishod" market
        winner_odds = {'1': None, 'X': None, '2': None}
        market_id = '12'  # Market ID for 1X2 betting
        for odd in match_data.get('odds', []):
            if odd.get('marketName') == 'Konačan ishod':
                code = odd.get('code')
                if code in ['1', '0', '2']:
                    price = odd.get('price')
                    if code == '0':
                        winner_odds['X'] = price
                    else:
                        winner_odds[code] = price
        
        if all(winner_odds.values()):
            return {
                'match': match_name,
                'market': market_id,
                'odds_1': winner_odds['1'],
                'odds_x': winner_odds['X'],
                'odds_2': winner_odds['2']
            }
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching odds for event {event_id}: {e}")
        return None

def update_csv_file(matches_data):
    fieldnames = ['Home', 'Away', 'Market', 'Odds 1', 'Odds X', 'Odds 2']
    
    try:
        with open('superbet_football_matches.csv', 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(fieldnames)
            for match in matches_data:
                # Split match name into home and away teams
                home, away = match['match'].split(',')
                writer.writerow([
                    home,
                    away,
                    match['market'],
                    match['odds_1'],
                    match['odds_x'],
                    match['odds_2']
                ])
    except IOError as e:
        print(f"Error writing to CSV file: {e}")

if __name__ == "__main__":
    # First fetch Axilis tournament IDs
    axilis_ids = fetch_axilis_tournament_ids()
    
    if axilis_ids:
        # Then use those IDs to fetch event IDs
        event_ids = fetch_event_ids(axilis_ids)
        
        if event_ids:
            # Fetch odds for each event
            matches_data = []
            for event_id in event_ids:
                match_odds = fetch_event_odds(event_id)
                if match_odds:
                    matches_data.append(match_odds)
            
            # Update the CSV file with the new data
            if matches_data:
                update_csv_file(matches_data)
            else:
                print("No valid matches data found")