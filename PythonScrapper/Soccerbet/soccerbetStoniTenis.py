import requests
import json
import csv
import ssl
from datetime import datetime

ssl._create_default_https_context = ssl._create_unverified_context


def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""


def get_table_tennis_leagues():
    """Fetch current table tennis leagues from Soccerbet"""
    url = "https://www.soccerbet.rs/restapi/offer/sr/categories/ext/sport/TT/g"

    params = {"annex": "0", "desktopVersion": "2.36.3.9", "locale": "sr"}

    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            leagues = []

            for category in data.get("categories", []):
                league_id = category.get("id")
                league_name = category.get("name")
                if league_id and league_name:
                    leagues.append((league_id, league_name))

            return leagues
        else:
            print(f"Failed to fetch leagues with status code: {response.status_code}")
            return []

    except Exception as e:
        print(f"Error fetching leagues: {str(e)}")
        return []


def get_soccerbet_sports():
    # Get leagues dynamically instead of hardcoded list
    leagues = get_table_tennis_leagues()

    if not leagues:
        print("No leagues found or error occurred while fetching leagues")
        return

    all_matches_data = []

    try:
        for league_id, league_name in leagues:
            url = f"https://www.soccerbet.rs/restapi/offer/sr/sport/TT/league-group/{league_id}/mob"

            params = {"annex": "0", "desktopVersion": "2.36.3.7", "locale": "sr"}

            try:
                response = requests.get(url, params=params)
                data = response.json()

                if "esMatches" in data and data["esMatches"]:
                    for match in data["esMatches"]:
                        match_id = match["id"]
                        # Get detailed match odds
                        match_url = f"https://www.soccerbet.rs/restapi/offer/sr/match/{match_id}"
                        match_response = requests.get(match_url, params=params)
                        match_data = match_response.json()
                        kick_off_time = convert_unix_to_iso(match_data.get("kickOffTime", 0))  # Get and convert kickoff time

                        home_team = match["home"]
                        away_team = match["away"]

                        # Get winner odds
                        match_data = [
                            home_team,
                            away_team,
                            kick_off_time,  # Add datetime
                            "12",  # Add Type column
                            match["betMap"]
                            .get("1", {})
                            .get("NULL", {})
                            .get("ov", "N/A"),
                            match["betMap"]
                            .get("3", {})
                            .get("NULL", {})
                            .get("ov", "N/A"),
                            "",  # Empty Odds 3 column
                        ]

                        all_matches_data.append(match_data)

            except Exception as e:
                continue

        # Save to CSV
        if all_matches_data:
            with open(
                "soccerbet_tabletennis_matches.csv", "w", newline="", encoding="utf-8"
            ) as f:
                writer = csv.writer(f)
                writer.writerow(["Team1", "Team2", "DateTime", "Bet Type", "Odds 1", "Odds 2"])  # Add DateTime
                writer.writerows(all_matches_data)

    except Exception as e:
        print(f"Error in main execution: {str(e)}")


if __name__ == "__main__":
    get_soccerbet_sports()
