import requests
import json
import csv
import ssl
from datetime import datetime
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

ssl._create_default_https_context = ssl._create_unverified_context


def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""


def get_tennis_leagues():
    """Fetch current tennis leagues from Soccerbet"""
    url = "https://www.soccerbet.rs/restapi/offer/sr/categories/ext/sport/T/g"

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
    leagues = get_tennis_leagues()
    matches_data = []
    matches_to_insert = []

    if not leagues:
        print("No leagues found or error occurred while fetching leagues")
        return

    try:
        # First get all match IDs from each league
        for league_id, league_name in leagues:
            url = f"https://www.soccerbet.rs/restapi/offer/sr/sport/T/league-group/{league_id}/mob"

            params = {"annex": "0", "desktopVersion": "2.36.3.7", "locale": "sr"}

            try:
                response = requests.get(url, params=params)
                data = response.json()

                if "esMatches" in data and data["esMatches"]:
                    for match in data["esMatches"]:
                        match_id = match["id"]
                        match_url = f"https://www.soccerbet.rs/restapi/offer/sr/match/{match_id}"
                        try:
                            response = requests.get(match_url, params=params)
                            if response.status_code == 200:
                                match_data = response.json()
                                bet_map = match_data.get("betMap", {})
                                kick_off_time = convert_unix_to_iso(match_data.get("kickOffTime", 0))  # Get and convert kickoff time

                                home_team = match_data.get("home", "")
                                away_team = match_data.get("away", "")

                                if home_team and away_team:
                                    # Get match winner odds
                                    home_win = bet_map.get("1", {}).get("NULL", {}).get("ov", "N/A")
                                    away_win = bet_map.get("3", {}).get("NULL", {}).get("ov", "N/A")

                                    # Add match winner odds
                                    if home_win != "N/A" and away_win != "N/A":
                                        matches_data.append([
                                            home_team,
                                            away_team,
                                            kick_off_time,
                                            "12",
                                            home_win,
                                            away_win,
                                        ])
                                        matches_to_insert.append((
                                            home_team,
                                            away_team,
                                            5,  # Soccerbet
                                            3,  # Tennis
                                            1,  # Winner
                                            0,  # No margin
                                            float(home_win),
                                            float(away_win),
                                            0,  # No third odd
                                            kick_off_time
                                        ))

                                    # Get first set winner odds
                                    first_set_home = (
                                        bet_map.get("50510", {}).get("NULL", {}).get("ov", "N/A")
                                    )
                                    first_set_away = (
                                        bet_map.get("50511", {}).get("NULL", {}).get("ov", "N/A")
                                    )

                                    # Add first set winner odds
                                    if first_set_home != "N/A" and first_set_away != "N/A":
                                        matches_data.append([
                                            home_team,
                                            away_team,
                                            kick_off_time,
                                            "12set1",
                                            first_set_home,
                                            first_set_away,
                                        ])
                                        matches_to_insert.append((
                                            home_team,
                                            away_team,
                                            5,  # Soccerbet
                                            3,  # Tennis
                                            11,  # First Set Winner
                                            0,  # No margin
                                            float(first_set_home),
                                            float(first_set_away),
                                            0,  # No third odd
                                            kick_off_time
                                        ))

                        except Exception as e:
                            print(f"Error processing match ID {match_id}: {str(e)}")
                            continue
            except Exception as e:
                print(f"Error getting matches from league {league_name}: {str(e)}")
                continue

        # Replace CSV writing with database insertion
        try:
            conn = get_db_connection()
            batch_insert_matches(conn, matches_to_insert)
            conn.close()
        except Exception as e:
            print(f"Database error: {e}")

        return matches_data

    except Exception as e:
        print(f"Error in main execution: {str(e)}")


if __name__ == "__main__":
    get_soccerbet_sports()
