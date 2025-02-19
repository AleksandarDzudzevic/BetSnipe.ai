import requests
import json
import csv
from bs4 import BeautifulSoup
from datetime import datetime
import time
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

DESIRED_TENNIS_REGIONS = {
    "Rusija Liga Pro",
}


def get_auth_token():
    try:
        session = requests.Session()
        main_url = "https://meridianbet.rs/sr/kladjenje/stoni-tenis"

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "sr",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }

        response = session.get(main_url, headers=headers)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            scripts = soup.find_all("script")

            for script in scripts:
                if script.string and "NEW_TOKEN" in script.string:
                    try:
                        json_data = json.loads(script.string)
                        if "NEW_TOKEN" in json_data:
                            token_data = json.loads(json_data["NEW_TOKEN"])
                            if "access_token" in token_data:
                                return token_data["access_token"]
                    except json.JSONDecodeError:
                        continue

    except Exception as e:
        print(f"Error getting auth token: {e}")
    return None


def get_last_name(player_name):
    # Split by comma if exists, otherwise take the last word
    if "," in player_name:
        return player_name.split(",")[0].strip().split()[-1]
    return player_name.strip().split()[-1]


def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""


def get_tennis_odds():
    token = get_auth_token()
    if not token:
        print("Failed to get authentication token")
        return

    url = "https://online.meridianbet.com/betshop/api/v1/standard/sport/89/leagues"
    matches_data = []
    matches_to_insert = []
    event_ids = []
    page = 0
    should_continue = True

    headers = {
        "Accept": "application/json",
        "Accept-Language": "sr",
        "Authorization": f"Bearer {token}",
        "Origin": "https://meridianbet.rs",
        "Referer": "https://meridianbet.rs/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }

    while should_continue:
        params = {"page": str(page), "time": "ALL", "groupIndices": "0,0,0"}
        
        for attempt in range(3):  # Try up to 3 times
            try:
                response = requests.get(url, params=params, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    if "payload" not in data or "leagues" not in data["payload"]:
                        should_continue = False
                        break

                    leagues = data["payload"]["leagues"]
                    if not leagues:
                        should_continue = False
                        break

                    found_matches = False
                    for league in leagues:
                        for event in league.get("events", []):
                            event_id = event.get("header", {}).get("eventId")
                            if event_id:
                                found_matches = True
                                event_ids.append(event_id)

                    if not found_matches:
                        should_continue = False
                    
                    page += 1
                    break  # Success, exit retry loop
                    
                elif response.status_code == 429:  # Too Many Requests
                    if attempt < 2:  # Don't sleep on last attempt
                        time.sleep(0.5)  # Wait before retry
                    continue
                else:
                    should_continue = False
                    break  # Other status codes, exit retry loop
                    
            except requests.Timeout:
                if attempt == 2:  # Last attempt
                    print(f"Timeout on page {page}")
                    should_continue = False
                time.sleep(0.5)  # Wait before retry
            except Exception as e:
                print(f"Error on page {page}: {e}")
                should_continue = False
                break

        if not should_continue:
            break

    # Now fetch odds for each event with retry logic
    for event_id in event_ids:
        event_url = f"https://online.meridianbet.com/betshop/api/v2/events/{event_id}"
        
        for attempt in range(3):  # Try up to 3 times
            try:
                response = requests.get(event_url, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    event_data = response.json()

                    # Get player names and start time
                    header = event_data.get("payload", {}).get("header", {})
                    rivals = header.get("rivals", [])
                    start_time = convert_unix_to_iso(header.get("startTime", 0))  # Get and convert start time

                    if len(rivals) >= 2:
                        player1, player2 = rivals[0], rivals[1]

                        # Look for "Pobednik" market
                        for game in event_data.get("payload", {}).get("games", []):
                            for market in game.get("markets", []):
                                if market.get("name") == "Pobednik":
                                    selections = market.get("selections", [])
                                    if len(selections) >= 2:
                                        matches_data.append(
                                            {
                                                "team1": player1,
                                                "team2": player2,
                                                "dateTime": start_time,
                                                "market": "12",
                                                "odd1": selections[0].get("price", "N/A"),
                                                "odd2": selections[1].get("price", "N/A"),
                                            }
                                        )
                                        matches_to_insert.append((
                                            player1,
                                            player2,
                                            2,  # Meridian
                                            5,  # Table Tennis
                                            1,  # Winner (12)
                                            0,  # No margin
                                            float(selections[0].get("price", 0)),
                                            float(selections[1].get("price", 0)),
                                            0,  # No third odd
                                            start_time
                                        ))
                    break  # Success, exit retry loop
                    
                elif response.status_code == 429:  # Too Many Requests
                    if attempt < 2:  # Don't sleep on last attempt
                        time.sleep(0.5)  # Wait before retry
                    continue
                else:
                    break  # Other status codes, exit retry loop
                    
            except requests.Timeout:
                if attempt == 2:  # Last attempt
                    print(f"Timeout fetching event {event_id}")
                time.sleep(0.5)  # Wait before retry
            except Exception as e:
                print(f"Error fetching event {event_id}: {e}")
                break

    # Database insertion
    if matches_to_insert:  # Only try to insert if we have data
        try:
            conn = get_db_connection()
            batch_insert_matches(conn, matches_to_insert)
            conn.close()
        except Exception as e:
            print(f"Database error: {e}")

    return matches_data


if __name__ == "__main__":
    get_tennis_odds()
