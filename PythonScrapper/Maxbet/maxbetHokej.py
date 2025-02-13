import requests
import csv
from datetime import datetime
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches


def get_hockey_leagues():
    """Fetch current hockey leagues from MaxBet"""
    url = "https://www.maxbet.rs/restapi/offer/sr/categories/sport/H/l"

    params = {"annex": "3", "desktopVersion": "1.2.1.10", "locale": "sr"}

    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Origin": "https://www.maxbet.rs",
        "Referer": "https://www.maxbet.rs/betting",
        "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            leagues = {}

            for category in data.get("categories", []):
                league_id = category.get("id")
                league_name = category.get("name")
                if league_id and league_name:
                    # Use league name as key and ID as value
                    leagues[league_name.lower().replace(" ", "_")] = league_id

            return leagues
        else:
            print(f"Failed to fetch leagues with status code: {response.status_code}")
            return {}

    except Exception as e:
        print(f"Error fetching leagues: {str(e)}")
        return {}


def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""


def fetch_maxbet_hockey_matches():
    hockey_leagues = get_hockey_leagues()
    matches_data = []
    matches_to_insert = []  # List for database insertion

    if not hockey_leagues:
        print("No leagues found or error occurred while fetching leagues")
        return []

    params = {"annex": "3", "desktopVersion": "1.2.1.10", "locale": "sr"}
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Origin": "https://www.maxbet.rs",
        "Referer": "https://www.maxbet.rs/betting",
        "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

    for league_name, league_id in hockey_leagues.items():
        url = f"https://www.maxbet.rs/restapi/offer/sr/sport/H/league/{league_id}/mob"

        try:
            response = requests.get(url, params=params, headers=headers)

            if response.status_code == 200:
                data = response.json()

                if "esMatches" in data:
                    for match in data["esMatches"]:
                        home_team = match.get("home", "")
                        away_team = match.get("away", "")
                        kick_off_time = convert_unix_to_iso(match.get("kickOffTime", 0))  # Convert Unix timestamp
                        odds = match.get("odds", {})

                        # 1X2 odds
                        home_win = odds.get("1", "")  # Home win (1)
                        draw = odds.get("2", "")  # Draw (X)
                        away_win = odds.get("3", "")  # Away win (2)

                        if home_win and draw and away_win:
                            matches_data.append(
                                {
                                    "team1": home_team,
                                    "team2": away_team,
                                    "dateTime": kick_off_time,
                                    "odd1": home_win,
                                    "oddX": draw,
                                    "odd2": away_win,
                                }
                            )
                            matches_to_insert.append((
                                home_team,
                                away_team,
                                3,  # Maxbet
                                4,  # Hockey
                                2,  # 1X2
                                0,  # No margin
                                float(home_win),
                                float(draw),
                                float(away_win),
                                kick_off_time
                            ))

            else:
                print(
                    f"Failed to fetch {league_name} with status code: {response.status_code}"
                )

        except Exception as e:
            print(f"Error fetching {league_name}: {str(e)}")
            continue

    # Replace CSV writing with database insertion
    try:
        conn = get_db_connection()
        batch_insert_matches(conn, matches_to_insert)
        conn.close()
    except Exception as e:
        print(f"Database error: {e}")

    return matches_data


if __name__ == "__main__":
    fetch_maxbet_hockey_matches()
