import concurrent.futures
import requests
import json
from datetime import datetime, timedelta
import csv
import time
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches


def fetch_single_competition(competition_id):
    url = "https://scorealarm-stats.freetls.fastly.net/soccer/competition/details/rssuperbetsport/sr-Latn-RS"
    params = {"competition_id": competition_id}

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        axilis_ids = []
        for mapping in data.get("tournament_mappings", []):
            if mapping.get("axilis") and len(mapping.get("axilis", [])) > 0:
                axilis_id = mapping.get("axilis", [])[0].split(":")[-1]
                axilis_ids.append(axilis_id)
        return axilis_ids
    except:
        return []


def fetch_single_event(event_id):
    try:
        odds_data = fetch_event_odds(event_id)
        return odds_data if odds_data else None
    except:
        return None


def fetch_axilis_tournament_ids():
    print("Starting to fetch tournament IDs...")
    start_time = time.time()

    competition_ids = [
        "br:competition:7",  # Champions League
        "br:competition:17",  # Premier League
        "br:competition:18",  # Championship
        "br:competition:8",  # La Liga
        "br:competition:54",  # La Liga 2
        "br:competition:35",  # Bundesliga
        "br:competition:44",  # Bundesliga 2
        "br:competition:23",  # Serie A
        "br:competition:53",  # Serie B
        "br:competition:34",  # Ligue 1
        "br:competition:182",  # Ligue 2
        "br:competition:679",  # Europa League
        "br:competition:155",  # Argentine League
        "br:competition:34480",  # Conference League
        "br:competition:37",  # Eredivisie
        "br:competition:325",  # Brazilian League
        "br:competition:136",  # Australian League
        "br:competition:38",  # Belgian League
        "br:competition:185",  # Greek League
        "br:competition:955",  # Saudi League
        "br:competition:52",  # Turkish League
    ]

    all_axilis_ids = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_competition = {
            executor.submit(fetch_single_competition, competition_id): competition_id
            for competition_id in competition_ids
        }

        for future in concurrent.futures.as_completed(future_to_competition):
            competition_id = future_to_competition[future]
            try:
                axilis_ids = future.result()
                all_axilis_ids.extend(axilis_ids)
            except Exception as e:
                print(f"Error fetching competition {competition_id}: {e}")

    print(f"Fetched tournament IDs in {time.time() - start_time:.2f} seconds")
    return list(dict.fromkeys(all_axilis_ids))


def fetch_event_ids(tournament_ids):
    url = "https://production-superbet-offer-rs.freetls.fastly.net/sb-rs/api/v2/sr-Latn-RS/events/by-date"

    # Join tournament IDs with commas
    tournament_ids_str = ",".join(tournament_ids)

    # Get current date in the required format
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Query parameters
    params = {
        "currentStatus": "active",
        "offerState": "prematch",
        "tournamentIds": tournament_ids_str,
        "startDate": current_date,
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        # Extract event IDs from the data array
        event_ids = []
        if "data" in data:
            for match in data["data"]:
                if "eventId" in match:  # or 'offerId', they're the same
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


def update_csv_file(matches_data):
    fieldnames = [
        "Home", "Away", "Market", "Odds 1", "Odds X", "Odds 2", "time"
    ]

    try:
        with open("superbet_football_matches.csv", "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(fieldnames)
            for match in matches_data:
                home, away = match["match"].split(",")
                
                # Write full time 1X2 odds
                writer.writerow([
                    home, away,
                    match["market_1x2"],
                    match["odds_1"], match["odds_x"], match["odds_2"],
                    match["time"]
                ])
                
                # Write first half 1X2 odds if available
                if all(v is not None for v in [match["odds_1f"], match["odds_xf"], match["odds_2f"]]):
                    writer.writerow([
                        home, away,
                        match["market_1x2f"],
                        match["odds_1f"], match["odds_xf"], match["odds_2f"],
                        match["time"]
                    ])
                
                # Write second half 1X2 odds if available
                if all(v is not None for v in [match["odds_1s"], match["odds_xs"], match["odds_2s"]]):
                    writer.writerow([
                        home, away,
                        match["market_1x2s"],
                        match["odds_1s"], match["odds_xs"], match["odds_2s"],
                        match["time"]
                    ])
                
                # Write GGNG odds if available
                if all(v is not None for v in [match["odds_gg"], match["odds_ng"]]):
                    writer.writerow([
                        home, away,
                        match["market_ggng"],
                        match["odds_gg"], match["odds_ng"], None,
                        match["time"]
                    ])
                
                # Write Total Goals odds
                for margin, odds in match["total_goals"].items():
                    if all(v is not None for v in [odds["under"], odds["over"]]):
                        writer.writerow([
                            home, away,
                            f"TG{margin}",
                            odds["under"], odds["over"], None,
                            match["time"]
                        ])
                
                # Write First Half Total Goals odds
                for margin, odds in match["total_goals_first"].items():
                    if all(v is not None for v in [odds["under"], odds["over"]]):
                        writer.writerow([
                            home, away,
                            f"TG{margin}F",
                            odds["under"], odds["over"], None,
                            match["time"]
                        ])
                
                # Write Second Half Total Goals odds
                for margin, odds in match["total_goals_second"].items():
                    if all(v is not None for v in [odds["under"], odds["over"]]):
                        writer.writerow([
                            home, away,
                            f"TG{margin}S",
                            odds["under"], odds["over"], None,
                            match["time"]
                        ])
    except IOError as e:
        print(f"Error writing to CSV file: {e}")


if __name__ == "__main__":
    start_total = time.time()
    conn = get_db_connection()
    all_matches_to_insert = []

    try:
        # First fetch Axilis tournament IDs
        axilis_ids = fetch_axilis_tournament_ids()
        print(f"Found {len(axilis_ids)} tournament IDs")

        if axilis_ids:
            # Then use those IDs to fetch event IDs
            print("Fetching event IDs...")
            start_time = time.time()
            event_ids = fetch_event_ids(axilis_ids)
            print(f"Found {len(event_ids)} events in {time.time() - start_time:.2f} seconds")

            if event_ids:
                # Fetch odds for each event in parallel
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
