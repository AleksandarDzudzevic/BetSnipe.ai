import concurrent.futures
import requests
import json
from datetime import datetime, timedelta
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
        "sportId": "5",  # Soccer ID is 5
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        # Extract event IDs from the data array
        event_ids = []
        if "data" in data:
            for match in data["data"]:
                # Changed to check for sportId == 5
                if "eventId" in match and match.get("sportId") == 5:
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
            print(f"No data found for event {event_id}")  # Debug print
            return None

        match_data = data["data"][0]
        match_name = match_data.get("matchName", "")
        match_date = match_data.get("matchDate", "")

        teams = match_name.split("·")
        if len(teams) != 2:
            return None
            
        team1, team2 = [team.strip() for team in teams]
        
        matches_to_insert = []
        odds_count = len(match_data.get("odds", []))  # Debug print

        # Initialize odds dictionaries for all markets
        markets = {
            "1X2": {"1": None, "X": None, "2": None},
            "1X2F": {"1": None, "X": None, "2": None},
            "1X2S": {"1": None, "X": None, "2": None},
            "GGNG": {"GG": None, "NG": None},
            "TG": {},  # Total Goals
            "TGF": {},  # First Half Total Goals
            "TGS": {}  # Second Half Total Goals
        }

        for odd in match_data.get("odds", []):
            market_name = odd.get("marketName")
            code = odd.get("code")
            price = odd.get("price")
            margin = odd.get("specialBetValue")
            
            if market_name == "Konačan ishod" and code in ["1", "0", "2"]:
                markets["1X2"]["1" if code == "1" else "X" if code == "0" else "2"] = price
            elif market_name == "1. poluvreme - 1X2" and code in ["1", "0", "2"]:
                markets["1X2F"]["1" if code == "1" else "X" if code == "0" else "2"] = price
            elif market_name == "2. poluvreme - 1X2" and code in ["1", "0", "2"]:
                markets["1X2S"]["1" if code == "1" else "X" if code == "0" else "2"] = price
            elif market_name == "Oba tima daju gol (GG)" and code in ["1", "2"]:
                markets["GGNG"]["GG" if code == "1" else "NG"] = price
            elif market_name == "Ukupno golova":
                if margin:
                    if margin not in markets["TG"]:
                        markets["TG"][margin] = {"under": None, "over": None}
                    if "Manje" in odd.get("name", ""):
                        markets["TG"][margin]["under"] = price
                    elif "Više" in odd.get("name", ""):
                        markets["TG"][margin]["over"] = price
            elif market_name == "1. poluvreme - ukupno golova":
                if margin:
                    if margin not in markets["TGF"]:
                        markets["TGF"][margin] = {"under": None, "over": None}
                    if "Manje" in odd.get("name", ""):
                        markets["TGF"][margin]["under"] = price
                    elif "Više" in odd.get("name", ""):
                        markets["TGF"][margin]["over"] = price
            elif market_name == "2. poluvreme - ukupno golova":
                if margin:
                    if margin not in markets["TGS"]:
                        markets["TGS"][margin] = {"under": None, "over": None}
                    if "Manje" in odd.get("name", ""):
                        markets["TGS"][margin]["under"] = price
                    elif "Više" in odd.get("name", ""):
                        markets["TGS"][margin]["over"] = price

        # Add matches to insert list for each market type
        if all(markets["1X2"].values()):
            matches_to_insert.append((
                team1, team2,
                7,  # Superbet
                1,  # Football
                2,  # 1X2
                0,  # No margin
                float(markets["1X2"]["1"]),
                float(markets["1X2"]["X"]),
                float(markets["1X2"]["2"]),
                match_date
            ))

        if all(markets["1X2F"].values()):
            matches_to_insert.append((
                team1, team2,
                7,  # Superbet
                1,  # Football
                3,  # First Half 1X2
                0,  # No margin
                float(markets["1X2F"]["1"]),
                float(markets["1X2F"]["X"]),
                float(markets["1X2F"]["2"]),
                match_date
            ))

        if all(markets["1X2S"].values()):
            matches_to_insert.append((
                team1, team2,
                7,  # Superbet
                1,  # Football
                4,  # Second Half 1X2
                0,  # No margin
                float(markets["1X2S"]["1"]),
                float(markets["1X2S"]["X"]),
                float(markets["1X2S"]["2"]),
                match_date
            ))

        if all(markets["GGNG"].values()):
            matches_to_insert.append((
                team1, team2,
                7,  # Superbet
                1,  # Football
                8,  # GGNG
                0,  # No margin
                float(markets["GGNG"]["GG"]),
                float(markets["GGNG"]["NG"]),
                0,  # No third odd
                match_date
            ))

        # Add Total Goals markets
        for margin, odds in markets["TG"].items():
            if all(odds.values()):
                matches_to_insert.append((
                    team1, team2,
                    7,  # Superbet
                    1,  # Football
                    5,  # Total Goals
                    float(margin),
                    float(odds["under"]),
                    float(odds["over"]),
                    0,  # No third odd
                    match_date
                ))

        # Add First Half Total Goals
        for margin, odds in markets["TGF"].items():
            if all(odds.values()):
                matches_to_insert.append((
                    team1, team2,
                    7,  # Superbet
                    1,  # Football
                    6,  # First Half Total
                    float(margin),
                    float(odds["under"]),
                    float(odds["over"]),
                    0,  # No third odd
                    match_date
                ))

        # Add Second Half Total Goals
        for margin, odds in markets["TGS"].items():
            if all(odds.values()):
                matches_to_insert.append((
                    team1, team2,
                    7,  # Superbet
                    1,  # Football
                    7,  # Second Half Total
                    float(margin),
                    float(odds["under"]),
                    float(odds["over"]),
                    0,  # No third odd
                    match_date
                ))
            
        return matches_to_insert

    except requests.exceptions.RequestException as e:
        print(f"Error fetching odds for event {event_id}: {e}")
        return None


if __name__ == "__main__":
    start_total = time.time()
    all_matches_to_insert = []

    try:
        event_ids = fetch_event_ids()
        
        if event_ids:

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
            
            # Insert into database
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                batch_insert_matches(conn, all_matches_to_insert)
            except Exception as e:
                print(f"Database error: {e}")
            finally:
                cursor.close()
                conn.close()

    except Exception as e:
        print(f"Error in main execution: {e}")