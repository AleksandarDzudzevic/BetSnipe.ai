import requests
import json
import csv
import ssl

ssl._create_default_https_context = ssl._create_unverified_context


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
    # Get leagues dynamically instead of hardcoded list
    leagues = get_tennis_leagues()

    if not leagues:
        print("No leagues found or error occurred while fetching leagues")
        return

    all_matches_data = []
    match_ids = []  # First collect all match IDs

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
                        match_ids.append(match["id"])

            except Exception as e:
                print(f"Error getting matches from league {league_name}: {str(e)}")
                continue

        # Now process each match individually
        for match_id in match_ids:
            match_url = f"https://www.soccerbet.rs/restapi/offer/sr/match/{match_id}"
            try:
                response = requests.get(match_url, params=params)
                if response.status_code == 200:
                    match_data = response.json()
                    bet_map = match_data.get("betMap", {})

                    home_team = match_data.get("home", "")
                    away_team = match_data.get("away", "")

                    if home_team and away_team:

                        # Get match winner odds
                        home_win = bet_map.get("1", {}).get("NULL", {}).get("ov", "N/A")
                        away_win = bet_map.get("3", {}).get("NULL", {}).get("ov", "N/A")

                        # Add match winner odds
                        if home_win != "N/A" and away_win != "N/A":
                            all_matches_data.append(
                                [home_team, away_team, "12", home_win, away_win]
                            )

                        # Get first set winner odds
                        first_set_home = (
                            bet_map.get("50510", {}).get("NULL", {}).get("ov", "N/A")
                        )
                        first_set_away = (
                            bet_map.get("50511", {}).get("NULL", {}).get("ov", "N/A")
                        )

                        # Add first set winner odds
                        if first_set_home != "N/A" and first_set_away != "N/A":
                            all_matches_data.append(
                                [
                                    home_team,
                                    away_team,
                                    "12set1",
                                    first_set_home,
                                    first_set_away,
                                ]
                            )

            except Exception as e:
                print(f"Error processing match ID {match_id}: {str(e)}")
                continue

        # Save to CSV
        if all_matches_data:
            with open(
                "soccerbet_tennis_matches.csv", "w", newline="", encoding="utf-8"
            ) as f:
                for row in all_matches_data:
                    f.write(f"{row[0]},{row[1]},{row[2]},{row[3]},{row[4]}\n")
        else:
            print("No matches data to save")

    except Exception as e:
        print(f"Error in main execution: {str(e)}")


if __name__ == "__main__":
    get_soccerbet_sports()
