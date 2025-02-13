import requests
import json
import csv
from datetime import datetime
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches

BASKETBALL_LEAGUES = {"nba": "144532", "euroleague": "131600", "eurocup": "131596"}


def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""


def fetch_maxbet_matches():
    matches_data = []
    matches_to_insert = []  # List for database insertion

    # Updated handicap mapping
    handicap_mapping = {
        "handicapOvertime": ("50458", "50459"),
        "handicapOvertime2": ("50432", "50433"),
        "handicapOvertime3": ("50434", "50435"),
        "handicapOvertime4": ("50436", "50437"),
        "handicapOvertime5": ("50438", "50439"),
        "handicapOvertime6": ("50440", "50441"),
        "handicapOvertime7": ("50442", "50443"),
        "handicapOvertime8": ("50981", "50982"),
        "handicapOvertime9": ("51626", "51627"),
    }

    # Add total points mapping
    total_points_mapping = {
        "overUnderOvertime3": ("50448", "50449"),
        "overUnderOvertime4": ("50450", "50451"),
        "overUnderOvertime5": ("50452", "50453"),
        "overUnderOvertime6": ("50454", "50455"),
    }

    for league_name, league_id in BASKETBALL_LEAGUES.items():
        url = f"https://www.maxbet.rs/restapi/offer/sr/sport/B/league/{league_id}/mob"

        params = {"annex": "3", "desktopVersion": "1.2.1.9", "locale": "sr"}

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
            "Origin": "https://www.maxbet.rs",
            "Referer": "https://www.maxbet.rs/betting",
        }

        try:
            response = requests.get(url, params=params, headers=headers)

            if response.status_code == 200:
                data = response.json()

                if "esMatches" in data:
                    for match in data["esMatches"]:
                        match_id = match["id"]
                        match_url = f"https://www.maxbet.rs/restapi/offer/sr/match/{match_id}"
                        try:
                            response = requests.get(match_url, params=params, headers=headers)
                            if response.status_code == 200:
                                match_data = response.json()

                                home_team = match_data.get("home", "")
                                away_team = match_data.get("away", "")
                                kick_off_time = convert_unix_to_iso(match_data.get("kickOffTime", 0))  # Convert Unix timestamp
                                odds = match_data.get("odds", {})
                                params = match_data.get("params", {})

                                # Match winner odds
                                home_odd = odds.get("50291", "")
                                away_odd = odds.get("50293", "")

                                if home_odd and away_odd:
                                    matches_data.append(
                                        {
                                            "team1": home_team,
                                            "team2": away_team,
                                            "dateTime": kick_off_time,
                                            "marketType": "12",
                                            "oddHome": home_odd,
                                            "oddAway": away_odd,
                                        }
                                    )
                                    matches_to_insert.append((
                                        home_team,
                                        away_team,
                                        3,  # Maxbet
                                        2,  # Basketball
                                        1,  # Winner (12)
                                        0,  # No margin
                                        float(home_odd),
                                        float(away_odd),
                                        0,  # No third odd
                                        kick_off_time
                                    ))

                                # Process handicap odds
                                for handicap_key, (home_code, away_code) in handicap_mapping.items():
                                    if home_code in odds and away_code in odds:
                                        handicap_value = params.get(handicap_key)
                                        if handicap_value:
                                            # Flip the handicap sign
                                            if handicap_value.startswith("-"):
                                                flipped_handicap = handicap_value[1:]  # Remove the minus
                                            else:
                                                flipped_handicap = f"-{handicap_value}"  # Add the minus

                                            matches_data.append(
                                                {
                                                    "team1": home_team,
                                                    "team2": away_team,
                                                    "dateTime": kick_off_time,
                                                    "marketType": f"H{flipped_handicap}",
                                                    "oddHome": odds[home_code],
                                                    "oddAway": odds[away_code],
                                                }
                                            )
                                            matches_to_insert.append((
                                                home_team,
                                                away_team,
                                                3,  # Maxbet
                                                2,  # Basketball
                                                9,  # Handicap
                                                float(flipped_handicap),  # Handicap value as margin
                                                float(odds[home_code]),
                                                float(odds[away_code]),
                                                0,  # No third odd
                                                kick_off_time
                                            ))

                                # Process total points odds
                                for total_key, (under_code, over_code) in total_points_mapping.items():
                                    if under_code in odds and over_code in odds:
                                        total_value = params.get(total_key)
                                        if total_value:
                                            matches_data.append(
                                                {
                                                    "team1": home_team,
                                                    "team2": away_team,
                                                    "dateTime": kick_off_time,
                                                    "marketType": f"OU{total_value}",
                                                    "oddHome": odds[under_code],  # Under
                                                    "oddAway": odds[over_code],  # Over
                                                }
                                            )
                                            matches_to_insert.append((
                                                home_team,
                                                away_team,
                                                3,  # Maxbet
                                                2,  # Basketball
                                                10,  # Total Points
                                                float(total_value),  # Points line as margin
                                                float(odds[under_code]),
                                                float(odds[over_code]),
                                                0,  # No third odd
                                                kick_off_time
                                            ))
                            else:
                                print(f"Failed to fetch match ID {match_id}: {response.status_code}")
                        except Exception as e:
                            print(f"Error fetching match ID {match_id}: {str(e)}")
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
    fetch_maxbet_matches()
