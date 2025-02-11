import requests
import json
import csv
from bs4 import BeautifulSoup
from datetime import datetime
import time

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


def process_match_id(player1, player2):
    # Check if it's a doubles match
    if "/" in player1 and "/" in player2:
        # Split both teams
        team1_players = player1.split("/")
        team2_players = player2.split("/")

        # Get last names for all players
        team1_names = [get_last_name(p) for p in team1_players]
        team2_names = [get_last_name(p) for p in team2_players]

        # Combine all four last names
        return f"{team1_names[0]}{team1_names[1]}{team2_names[0]}{team2_names[1]}"
    else:
        # Singles match - get last names
        name1 = get_last_name(player1)
        name2 = get_last_name(player2)
        return f"{name1}{name2}"


def get_tennis_odds():
    token = get_auth_token()
    if not token:
        print("Failed to get authentication token")
        return

    url = "https://online.meridianbet.com/betshop/api/v1/standard/sport/89/leagues"
    matches_data = []

    headers = {
        "Accept": "application/json",
        "Accept-Language": "sr",
        "Authorization": f"Bearer {token}",
        "Origin": "https://meridianbet.rs",
        "Referer": "https://meridianbet.rs/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }

    # First get all event IDs
    event_ids = []
    page = 0

    while True:
        params = {"page": str(page), "time": "ALL", "groupIndices": "0,0,0"}
        try:
            response = requests.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if "payload" not in data or "leagues" not in data["payload"]:
                    break

                leagues = data["payload"]["leagues"]
                if not leagues:
                    break

                for league in leagues:
                    for event in league.get("events", []):
                        event_id = event.get("header", {}).get("eventId")
                        if event_id:
                            event_ids.append(event_id)

            elif response.status_code == 429:
                time.sleep(2)
                continue
            else:
                print(f"Error: Status Code {response.status_code}")
                break

        except Exception as e:
            print(f"Error on page {page}: {e}")
            break
        page += 1

    # Now fetch odds for each event
    for event_id in event_ids:
        try:
            event_url = f"https://online.meridianbet.com/betshop/api/v2/events/{event_id}"
            response = requests.get(event_url, headers=headers)
            
            if response.status_code == 200:
                event_data = response.json()
                
                # Get player names
                rivals = event_data.get("payload", {}).get("header", {}).get("rivals", [])
                if len(rivals) >= 2:
                    player1, player2 = rivals[0], rivals[1]
                    match_name = f"{player1}, {player2}"
                    
                    # Look for "Pobednik" market
                    for game in event_data.get("payload", {}).get("games", []):
                        for market in game.get("markets", []):
                            if market.get("name") == "Pobednik":
                                selections = market.get("selections", [])
                                if len(selections) >= 2:
                                    matches_data.append({
                                        "match": match_name,
                                        "market": "12",
                                        "odd1": selections[0].get("price", "N/A"),
                                        "odd2": selections[1].get("price", "N/A")
                                    })

            elif response.status_code == 429:
                time.sleep(2)
                continue

        except Exception as e:
            continue

    # Save to CSV without quotes
    if matches_data:
        with open("meridian_tabletennis_matches.csv", "w", newline="", encoding="utf-8") as f:
            for match in matches_data:
                f.write(f"{match['match']},{match['market']},{match['odd1']},{match['odd2']},\n")


if __name__ == "__main__":
    get_tennis_odds()
