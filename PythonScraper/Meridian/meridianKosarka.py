import requests
import json
from bs4 import BeautifulSoup
import csv
from datetime import datetime
import sys
from pathlib import Path
import time
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

DESIRED_LEAGUES = {
    "NBA",
    "NCAA",
    "Evroliga",
    "Evrokup",
    "ABA Liga",  # ABA League
    "ACB Liga",  # Spain
    "BBL Liga",  # Germany
    "LNB Pro A",  # France
    "A1 Liga",  # Greece
    "Lega A",  # Italy
}


def get_auth_token():
    try:
        session = requests.Session()
        main_url = "https://meridianbet.rs/sr/kladjenje/kosarka"
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "sr",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }
        response = session.get(main_url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for script in soup.find_all("script"):
                if script.string and "NEW_TOKEN" in script.string:
                    try:
                        json_data = json.loads(script.string)
                        if "NEW_TOKEN" in json_data:
                            token_data = json.loads(json_data["NEW_TOKEN"])
                            if "access_token" in token_data:
                                return token_data["access_token"]
                    except json.JSONDecodeError:
                        continue
    except Exception:
        return None
    return None


def get_markets_for_event(event_id, token):
    url = f"https://online.meridianbet.com/betshop/api/v2/events/{event_id}/markets"
    headers = {
        "Accept": "application/json",
        "Accept-Language": "sr",
        "Authorization": f"Bearer {token}",
        "Origin": "https://meridianbet.rs",
        "Referer": "https://meridianbet.rs/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }
    params = {"gameGroupId": "all"}

    for attempt in range(3):  # Try up to 3 times
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data.get("payload", [])
            elif response.status_code == 429:  # Too Many Requests
                if attempt < 2:  # Don't sleep on last attempt
                    time.sleep(0.5)  # Wait before retry
                continue
            else:
                break
                
        except requests.Timeout:
            if attempt == 2:  # Last attempt
                print(f"Timeout fetching markets for event {event_id}")
            time.sleep(0.5)  # Wait before retry
        except Exception as e:
            print(f"Error fetching markets for event {event_id}: {e}")
            break
    return None


def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""


def get_basketball_odds():
    token = get_auth_token()
    if not token:
        return []

    url = "https://online.meridianbet.com/betshop/api/v1/standard/sport/55/leagues"
    headers = {
        "Accept": "application/json",
        "Accept-Language": "sr",
        "Authorization": f"Bearer {token}",
        "Origin": "https://meridianbet.rs",
        "Referer": "https://meridianbet.rs/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }

    matches_data = []
    matches_to_insert = []
    page = 0
    should_continue = True

    while should_continue:
        for attempt in range(3):  # Try up to 3 times
            try:
                response = requests.get(url, params={"page": str(page), "time": "ALL"}, headers=headers, timeout=30)
                
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
                        league_name = league.get("leagueName", "")
                        if any(desired in league_name for desired in DESIRED_LEAGUES):
                            events = league.get("events", [])
                            for event in events:
                                found_matches = True
                                event_id = event.get("header", {}).get("eventId")
                                rivals = event.get("header", {}).get("rivals", [])
                                start_time = convert_unix_to_iso(event.get("header", {}).get("startTime", 0))  # Get and convert start time

                                if event_id and len(rivals) >= 2:
                                    market_data = get_markets_for_event(event_id, token)
                                    if market_data:
                                        team1, team2 = rivals[0], rivals[1]
                                        odds_12 = None
                                        odds_total = []  # For different total lines
                                        odds_handicap = []  # For different handicap lines

                                        for market_group in market_data:
                                            market_name = market_group.get("marketName")
                                            if market_name == "Pobednik (uklj.OT )":
                                                for market in market_group.get("markets", []):
                                                    selections = market.get("selections", [])
                                                    if len(selections) >= 2:
                                                        odds_12 = {
                                                            "team1": team1,
                                                            "team2": team2,
                                                            "dateTime": start_time,  # Add datetime
                                                            "marketType": "12",
                                                            "odd1": selections[0].get("price"),
                                                            "odd2": selections[1].get("price"),
                                                        }

                                            elif market_name == "Ukupno (uklj.OT) ":
                                                for market in market_group.get("markets", []):
                                                    over_under = market.get("overUnder")
                                                    selections = market.get("selections", [])
                                                    if over_under and len(selections) >= 2:
                                                        odds_total.append(
                                                            {
                                                                "team1": team1,
                                                                "team2": team2,
                                                                "dateTime": start_time,  # Add datetime
                                                                "marketType": f"{over_under}",
                                                                "odd1": selections[1].get(
                                                                    "price"
                                                                ),  # Over
                                                                "odd2": selections[0].get(
                                                                    "price"
                                                                ),  # Under
                                                            }
                                                        )

                                            elif market_name == "Hendikep (uklj. OT)":
                                                for market in market_group.get("markets", []):
                                                    handicap = market.get("handicap")
                                                    selections = market.get("selections", [])
                                                    if (
                                                        handicap is not None
                                                        and len(selections) >= 2
                                                    ):
                                                        odds_handicap.append(
                                                            {
                                                                "team1": team1,
                                                                "team2": team2,
                                                                "dateTime": start_time,  # Add datetime
                                                                "marketType": f"H{handicap}",
                                                                "odd1": selections[0].get(
                                                                    "price"
                                                                ),  # Home
                                                                "odd2": selections[1].get(
                                                                    "price"
                                                                ),  # Away
                                                            }
                                                        )

                                        if odds_12:
                                            matches_data.append(odds_12)
                                            matches_to_insert.append((
                                                odds_12["team1"],
                                                odds_12["team2"],
                                                2,  # Meridian
                                                2,  # Basketball
                                                1,  # 12 (Winner)
                                                0,  # No margin
                                                float(odds_12["odd1"]),
                                                float(odds_12["odd2"]),
                                                0,  # No third odd
                                                start_time
                                            ))

                                        for total in odds_total:
                                            matches_data.append(total)
                                            matches_to_insert.append((
                                                total["team1"],
                                                total["team2"],
                                                2,  # Meridian
                                                2,  # Basketball
                                                10,  # Total Points
                                                float(total["marketType"]),  # Points line as margin
                                                float(total["odd1"]),
                                                float(total["odd2"]),
                                                0,  # No third odd
                                                start_time
                                            ))

                                        for handicap in odds_handicap:
                                            matches_data.append(handicap)
                                            matches_to_insert.append((
                                                handicap["team1"],
                                                handicap["team2"],
                                                2,  # Meridian
                                                2,  # Basketball
                                                9,  # Handicap
                                                float(handicap["marketType"][1:]),  # Handicap line as margin
                                                float(handicap["odd1"]),
                                                float(handicap["odd2"]),
                                                0,  # No third odd
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
            print(f"Successfully inserted {len(matches_to_insert)} basketball matches")
        except Exception as e:
            print(f"Database error: {e}")

    return matches_data


if __name__ == "__main__":
    get_basketball_odds()
