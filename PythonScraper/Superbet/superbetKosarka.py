import requests
import json
from datetime import datetime, timedelta
import time
import concurrent.futures
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches


def fetch_event_ids():
    url = "https://production-superbet-offer-rs.freetls.fastly.net/sb-rs/api/v2/sr-Latn-RS/events/by-date"
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    params = {
        "currentStatus": "active",
        "offerState": "prematch",
        "startDate": current_date,
        "sportId": 4,  # Sport ID for basketball
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        event_ids = []
        if "data" in data:
            for match in data["data"]:
                if "eventId" in match:
                    event_ids.append(match["eventId"])
        return event_ids

    except Exception as e:
        print(f"Error fetching event data: {e}")
        return []


def fetch_event_odds(event_id):
    url = f"https://production-superbet-offer-rs.freetls.fastly.net/sb-rs/api/v2/sr-Latn-RS/events/{event_id}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if "data" not in data or not data["data"]:
            return None

        match_data = data["data"][0]
        match_name = match_data.get("matchName", "")
        match_date = match_data.get("matchDate", "")

        teams = match_name.split("·")
        team1, team2 = [team.strip() for team in teams]

        matches_to_insert = []

        for odd in match_data.get("odds", []):
            market_name = odd.get("marketName")
            code = odd.get("code")
            price = odd.get("price")
            margin = odd.get("specialBetValue")
            
            # Match Winner
            if market_name == "Pobednik (uklj. produžetke)" and code in ["1", "2"]:
                if code == "1":
                    home_odd = price
                elif code == "2":
                    away_odd = price
                    matches_to_insert.append((
                        team1, team2,
                        7,  # Superbet
                        2,  # Basketball
                        1,  # Winner market
                        0,  # No margin
                        float(home_odd),
                        float(away_odd),
                        0,  # No third odd
                        match_date
                    ))

            # Total Points
            elif market_name == "Ukupno poena (uklj. produžetke)":
                if margin:
                    if "+" in code:
                        over_odd = price
                        matches_to_insert.append((
                            team1, team2,
                            7,  # Superbet
                            2,  # Basketball
                            5,  # Total Points
                            float(margin),
                            0,  # Under (placeholder)
                            float(over_odd),
                            0,  # No third odd
                            match_date
                        ))
                    elif "-" in code:
                        under_odd = price
                        matches_to_insert.append((
                            team1, team2,
                            7,  # Superbet
                            2,  # Basketball
                            5,  # Total Points
                            float(margin),
                            float(under_odd),
                            0,  # Over (placeholder)
                            0,  # No third odd
                            match_date
                        ))

            # Handicap
            elif market_name == "Hendikep poena (uklj. produžetke)":
                if margin:
                    if code == "1":
                        home_odd = price
                        matches_to_insert.append((
                            team1, team2,
                            7,  # Superbet
                            2,  # Basketball
                            9,  # Handicap
                            float(margin),
                            float(home_odd),
                            0,  # Away odd (placeholder)
                            0,  # No third odd
                            match_date
                        ))
                    elif code == "2":
                        away_odd = price
                        matches_to_insert.append((
                            team1, team2,
                            7,  # Superbet
                            2,  # Basketball
                            9,  # Handicap
                            float(margin),
                            0,  # Home odd (placeholder)
                            float(away_odd),
                            0,  # No third odd
                            match_date
                        ))

        return matches_to_insert

    except Exception as e:
        print(f"Error fetching odds for event {event_id}: {e}")
        return None


def main():
    start_total = time.time()
    conn = get_db_connection()
    all_matches_to_insert = []

    try:
        # Fetch matches data
        print("Fetching matches data...")
        start_time = time.time()
        event_ids = fetch_event_ids()
        
        if event_ids:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_event = {
                    executor.submit(fetch_event_odds, event_id): event_id
                    for event_id in event_ids
                }

                for future in concurrent.futures.as_completed(future_to_event):
                    event_id = future_to_event[future]
                    try:
                        matches = future.result()
                        if matches:
                            all_matches_to_insert.extend(matches)
                    except Exception as e:
                        print(f"Error processing event {event_id}: {e}")

            print(f"Found {len(all_matches_to_insert)} matches in {time.time() - start_time:.2f} seconds")

            # Insert into database
            if all_matches_to_insert:
                print("Inserting into database...")
                start_time = time.time()
                batch_insert_matches(conn, all_matches_to_insert)
                print(f"Database insertion completed in {time.time() - start_time:.2f} seconds")
            else:
                print("No valid matches data found")

    except Exception as e:
        print(f"Error in main execution: {e}")
    finally:
        conn.close()

    print(f"Total execution time: {time.time() - start_total:.2f} seconds")


if __name__ == "__main__":
    main()
