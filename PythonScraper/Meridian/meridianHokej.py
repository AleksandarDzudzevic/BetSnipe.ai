import requests
import json
from bs4 import BeautifulSoup
from datetime import datetime
import time
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches


def get_auth_token():
    try:
        session = requests.Session()
        main_url = "https://meridianbet.rs/sr/kladjenje/hokej-na-ledu"

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


def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""


def get_hockey_odds():
    token = get_auth_token()
    if not token:
        print("Failed to get authentication token")
        return

    url = "https://online.meridianbet.com/betshop/api/v1/standard/sport/59/leagues"
    matches_data = []
    matches_to_insert = []
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
                            found_matches = True
                            header = event.get("header", {})
                            rivals = header.get("rivals", [])
                            start_time = convert_unix_to_iso(header.get("startTime", 0))

                            if len(rivals) >= 2:
                                for position in event.get("positions", []):
                                    for group in position.get("groups", []):
                                        if group.get("name") == "Konačan Ishod":
                                            selections = group.get("selections", [])
                                            if len(selections) >= 3:
                                                match_data = {
                                                    "team1": rivals[0],
                                                    "team2": rivals[1],
                                                    "dateTime": start_time,
                                                    "marketType": "1X2",
                                                    "odd1": selections[0].get("price"),
                                                    "oddX": selections[1].get("price"),
                                                    "odd2": selections[2].get("price"),
                                                }
                                                matches_data.append(match_data)
                                                matches_to_insert.append((
                                                    rivals[0],
                                                    rivals[1],
                                                    2,  # Meridian
                                                    4,  # Hockey
                                                    2,  # 1X2
                                                    0,  # No margin
                                                    float(selections[0].get("price", 0)),
                                                    float(selections[1].get("price", 0)),
                                                    float(selections[2].get("price", 0)),
                                                    start_time
                                                ))

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
    get_hockey_odds()
