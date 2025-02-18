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
        "sportId": 2,  # Sport ID for tennis
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
        teams = match_name.split("·")
        team1, team2 = [team.strip() for team in teams]
        match_date = match_data.get("matchDate", "")

        matches_to_insert = []
        match_winner_odds = {"1": None, "2": None}
        first_set_odds = {"1": None, "2": None}

        for odd in match_data.get("odds", []):
            market_name = odd.get("marketName")
            code = odd.get("code")
            price = odd.get("price")

            # Match Winner
            if market_name == "Konačan ishod":
                if code in ["1", "2"]:
                    match_winner_odds[code] = price

            # First Set Winner
            elif market_name == "1. Set - Pobednik":
                if code in ["1", "2"]:
                    first_set_odds[code] = price

        # Add Match Winner market if both odds are available
        if all(match_winner_odds.values()):
            matches_to_insert.append((
                team1,
                team2,
                7,  # Superbet
                3,  # Tennis
                1,  # Winner (1-2)
                0,  # No margin
                float(match_winner_odds["1"]),
                float(match_winner_odds["2"]),
                0,  # No third odd
                match_date
            ))

        # Add First Set Winner market if both odds are available
        if all(first_set_odds.values()):
            matches_to_insert.append((
                team1,
                team2,
                7,  # Superbet
                3,  # Tennis
                11,  # First Set Winner
                0,  # No margin
                float(first_set_odds["1"]),
                float(first_set_odds["2"]),
                0,  # No third odd
                match_date
            ))

        return matches_to_insert

    except requests.exceptions.RequestException as e:
        print(f"Error fetching odds for event {event_id}: {e}")
        return None


def main():
    conn = get_db_connection()
    all_matches_to_insert = []

    try:
        event_ids = fetch_event_ids()

        if event_ids:
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

            if all_matches_to_insert:
                batch_insert_matches(conn, all_matches_to_insert)
            else:
                print("No valid matches data found")

    except Exception as e:
        print(f"Error in main execution: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
