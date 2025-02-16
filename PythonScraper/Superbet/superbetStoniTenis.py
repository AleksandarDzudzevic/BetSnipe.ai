import concurrent.futures
import requests
import json
from datetime import datetime
import time
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches


def fetch_single_event(event_id):
    try:
        odds_data = fetch_event_odds(event_id)
        return odds_data if odds_data else None
    except:
        return None


def fetch_event_ids():
    url = "https://production-superbet-offer-rs.freetls.fastly.net/sb-rs/api/v2/sr-Latn-RS/events/by-date"

    # Get current date in the required format
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Query parameters
    params = {
        "currentStatus": "active",
        "offerState": "prematch",
        "startDate": current_date,
        "sportId": 24,  # Sport ID for table tennis
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

    except requests.exceptions.RequestException as e:
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
        odds_1 = None
        odds_2 = None

        # Find 1-2 market odds
        if "odds" in match_data:
            for odd in match_data["odds"]:
                if odd.get("marketName") == "Pobednik meča":
                    if odd.get("code") == "1":
                        odds_1 = odd.get("price")
                    elif odd.get("code") == "2":
                        odds_2 = odd.get("price")

        if odds_1 and odds_2:
            matches_to_insert.append((
                team1,
                team2,
                7,  # Superbet
                5,  # Table Tennis
                1,  # Winner (1-2)
                0,  # No margin
                float(odds_1),
                float(odds_2),
                0,  # No third odd
                match_date
            ))

        return matches_to_insert

    except requests.exceptions.RequestException as e:
        print(f"Error fetching odds for event {event_id}: {e}")
        return None


def main():
    start_total = time.time()
    conn = get_db_connection()
    all_matches_to_insert = []

    try:
        print("Fetching event IDs...")
        start_time = time.time()
        event_ids = fetch_event_ids()
        print(f"Found {len(event_ids)} events in {time.time() - start_time:.2f} seconds")

        if event_ids:
            print("Fetching odds for all events...")
            start_time = time.time()

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                future_to_event = {
                    executor.submit(fetch_single_event, event_id): event_id
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

            print(f"Fetched odds for {len(all_matches_to_insert)} matches in {time.time() - start_time:.2f} seconds")

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
