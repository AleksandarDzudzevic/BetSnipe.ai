import requests
import json
import csv

BASKETBALL_LEAGUES = {"nba": "144532", "euroleague": "131600", "eurocup": "131596"}


def process_team_names(home_team, away_team):
    """Convert team names to combined format"""
    try:
        teams = [home_team, away_team]
        processed_names = []

        for team in teams:
            team = team.strip()
            words = team.split()

            if not words:
                return None

            # If team name has only one word and it's 3 characters, use it
            if len(words) == 1 and len(words[0]) == 3:
                processed_name = words[0][0].upper() + words[0][1:]
            else:
                # Find first word longer than 3 characters
                first_long_word = next((word for word in words if len(word) > 2), None)
                if not first_long_word:
                    return None
                processed_name = first_long_word[0].upper() + first_long_word[1:]

            processed_names.append(processed_name)

        if len(processed_names) == 2:
            return f"{processed_names[0]}{processed_names[1]}"
        return None

    except Exception as e:
        print(f"Error processing names {home_team} vs {away_team}: {e}")
        return None


def fetch_maxbet_matches():
    match_ids = []

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
                        match_ids.append(match["id"])
            else:
                print(
                    f"Failed to fetch {league_name} with status code: {response.status_code}"
                )

        except Exception as e:
            print(f"Error fetching {league_name}: {str(e)}")
            continue

    # Process matches and extract odds
    matches_odds = []

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

    for match_id in match_ids:
        match_url = f"https://www.maxbet.rs/restapi/offer/sr/match/{match_id}"
        try:
            response = requests.get(match_url, params=params, headers=headers)
            if response.status_code == 200:
                match_data = response.json()

                home_team = match_data.get("home", "")
                away_team = match_data.get("away", "")
                odds = match_data.get("odds", {})
                params = match_data.get("params", {})

                # Match winner odds
                home_odd = odds.get("50291", "")
                away_odd = odds.get("50293", "")

                if home_odd and away_odd:
                    matches_odds.append(
                        {
                            "team1": home_team,
                            "team2": away_team,
                            "marketType": "12",
                            "oddHome": home_odd,
                            "oddAway": away_odd,
                        }
                    )

                # Process handicap odds
                for handicap_key, (home_code, away_code) in handicap_mapping.items():
                    if home_code in odds and away_code in odds:
                        handicap_value = params.get(handicap_key)
                        if handicap_value:
                            # Flip the handicap sign
                            if handicap_value.startswith("-"):
                                flipped_handicap = handicap_value[
                                    1:
                                ]  # Remove the minus
                            else:
                                flipped_handicap = f"-{handicap_value}"  # Add the minus

                            matches_odds.append(
                                {
                                    "team1": home_team,
                                    "team2": away_team,
                                    "marketType": f"H{flipped_handicap}",
                                    "oddHome": odds[home_code],
                                    "oddAway": odds[away_code],
                                }
                            )

                # Process total points odds
                for total_key, (under_code, over_code) in total_points_mapping.items():
                    if under_code in odds and over_code in odds:
                        total_value = params.get(total_key)
                        if total_value:
                            matches_odds.append(
                                {
                                    "team1": home_team,
                                    "team2": away_team,
                                    "marketType": f"OU{total_value}",
                                    "oddHome": odds[under_code],  # Under
                                    "oddAway": odds[over_code],  # Over
                                }
                            )
            else:
                print(f"Failed to fetch match ID {match_id}: {response.status_code}")
        except Exception as e:
            print(f"Error fetching match ID {match_id}: {str(e)}")
            continue

    # Save to CSV
    with open("maxbet_basketball_matches.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["matchId", "marketType", "oddHome", "oddAway"])
        for match in matches_odds:
            combined_name = process_team_names(match["team1"], match["team2"])
            if combined_name:
                writer.writerow(
                    [
                        combined_name,
                        match["marketType"],
                        match["oddHome"],
                        match["oddAway"],
                    ]
                )
    return matches_odds


if __name__ == "__main__":
    fetch_maxbet_matches()
