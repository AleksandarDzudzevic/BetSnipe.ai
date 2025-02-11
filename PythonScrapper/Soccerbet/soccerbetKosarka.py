import requests
import json
import csv
import ssl

ssl._create_default_https_context = ssl._create_unverified_context


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


def get_soccerbet_api():
    # Define leagues with their IDs
    leagues = [
        ("2521548", "NBA"),
        ("2530816", "NCAA"),
        ("2516963", "Evroliga"),
        ("2521028", "Evrokup"),
        ("2516003", "ABA Liga"),
        ("2516499", "Spanska Liga"),
        ("2516070", "Nemačka Liga"),
        ("2517240", "Italija Liga"),
        ("2521125", "Grčka Liga"),
        ("2516277", "Francuska Liga"),
    ]

    all_matches_data = []

    for league_id, league_name in leagues:
        url = f"https://www.soccerbet.rs/restapi/offer/sr/sport/B/league/{league_id}/mob?annex=0&desktopVersion=2.36.3.7&locale=sr"
        try:
            response = requests.get(url)
            data = response.json()

            if "esMatches" in data and len(data["esMatches"]) > 0:
                for match in data["esMatches"]:
                    match_id = match["id"]

                    # Get detailed match odds
                    match_url = f"https://www.soccerbet.rs/restapi/offer/sr/match/{match_id}?annex=0&desktopVersion=2.36.3.7&locale=sr"
                    match_response = requests.get(match_url)
                    match_data = match_response.json()
                    home_team = match["home"]
                    away_team = match["away"]
                    match_name = process_team_names(home_team, away_team)
                    bet_map = match_data.get("betMap", {})

                    # Format winner odds row
                    match_winner = {
                        "match": match_name,
                        "market": "12",
                        "odd1": bet_map.get("50291", {})
                        .get("NULL", {})
                        .get("ov", "N/A"),
                        "odd2": bet_map.get("50293", {})
                        .get("NULL", {})
                        .get("ov", "N/A"),
                        "odd3": "",
                    }

                    # Find all handicap values from the API
                    handicap_code = "50431"  # Main handicap code
                    handicap_code2 = (
                        "50430"  # Second handicap code for other team's odds
                    )
                    if handicap_code in bet_map and handicap_code2 in bet_map:
                        handicap_data = bet_map[handicap_code]
                        for key in handicap_data:
                            if key.startswith("hcp="):
                                handicap = key.split("=")[
                                    1
                                ]  # Extract handicap value (e.g., '14.5')
                                odds1 = (
                                    bet_map.get(handicap_code, {})
                                    .get(key, {})
                                    .get("ov", "N/A")
                                )
                                odds2 = (
                                    bet_map.get(handicap_code2, {})
                                    .get(key, {})
                                    .get("ov", "N/A")
                                )

                                # Create single handicap row with both teams' odds
                                match_handicap = {
                                    "match": match_name,
                                    "market": f"H{handicap}",
                                    "odd1": odds2,  # Flipped: Team 2's odds go in odd1
                                    "odd2": odds1,  # Flipped: Team 1's odds go in odd2
                                    "odd3": "",
                                }
                                all_matches_data.append(match_handicap)

                    # Find all total points values from the API
                    total_points_code = "50444"  # Total points code
                    if total_points_code in bet_map:
                        total_data = bet_map[total_points_code]
                        for key in total_data:
                            if key.startswith("total="):
                                points = key.split("=")[
                                    1
                                ]  # Extract points value (e.g., '220.5')
                                odds = (
                                    bet_map.get(total_points_code, {})
                                    .get(key, {})
                                    .get("ov", "N/A")
                                )

                                match_total = {
                                    "match": match_name,
                                    "market": f"OU{points}",
                                    "odd1": odds,  # Under odds
                                    "odd2": bet_map.get("50445", {})
                                    .get(key, {})
                                    .get("ov", "N/A"),  # Over odds
                                    "odd3": "",
                                }
                                all_matches_data.append(match_total)

                    all_matches_data.append(match_winner)

        except Exception as e:
            print(f"Error processing league {league_name}: {str(e)}")
            continue

    # Save to CSV
    if all_matches_data:
        with open(
            "soccerbet_basketball_matches.csv", "w", newline="", encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["match", "market", "odd1", "odd2", "odd3"],
            )
            writer.writeheader()
            writer.writerows(all_matches_data)

if __name__ == "__main__":
    get_soccerbet_api()
