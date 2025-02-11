import requests
import json
import csv
import undetected_chromedriver as uc
import ssl
import csv

ssl._create_default_https_context = ssl._create_unverified_context


def get_first_valid_word(team_name):
    """Get first valid word longer than 2 letters with special case for Atletico"""
    try:
        team_name = team_name.strip()

        # Special case for Atletico
        if team_name.startswith("Ath"):
            return "Atletico"
        if team_name.startswith("Bodo/Glimt"):
            return "Bodo"
        words = team_name.split()
        return next(
            (word for word in words if len(word) > 2 and "." not in word), words[-1]
        )
    except Exception as e:
        print(f"Error processing team name {team_name}: {e}")
        return None


def get_soccerbet_api():
    # Define all leagues
    leagues = [
    # European Competitions
    ("2519992", "Liga Šampiona"),        # Champions League
    ("2520043", "Liga Evrope"),          # Europa League
    ("2520044", "Liga Konferencije"),    # Conference League
    ("2516076", "Premijer Liga"),        # Premier League
    ("2515993", "Druga Engleska Liga"),  # Championship
    ("2516061", "La Liga"),              # La Liga
    ("2516062", "La Liga 2"),            # La Liga 2
    ("2516000", "Serie A"),              # Serie A
    ("2516001", "Serie B"),              # Serie B
    ("2515986", "Bundesliga"),           # Bundesliga
    ("2515987", "Bundesliga 2"),         # Bundesliga 2
    ("2515968", "Ligue 1"),              # Ligue 1
    ("2515969", "Ligue 2"),              # Ligue 2
    ("2516055", "Holandija 1"),          # Eredivisie
    ("2516056", "Belgija 1"),            # Belgian Pro League
    ("2516057", "Turska 1"),             # Super Lig
    ("2516058", "Grčka 1"),              # Greek Super League
    ("2516059", "Saudijska Liga"),       # Saudi Pro League
    ("2532290", "Argentiska Liga"),      # Argentina Primera Division
    ("2516060", "Brazil 1"),             # Brasileirao
    ("2516063", "Australija 1"),         # A-League
]

    all_matches_data = []

    for league_id, league_name in leagues:
        url = f"https://www.soccerbet.rs/restapi/offer/sr/sport/S/league/{league_id}/mob?annex=0&desktopVersion=2.36.3.7&locale=sr"
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

                    bet_map = match_data.get("betMap", {})
                    home_team = match["home"]
                    away_team = match["away"]
                    team1_name = get_first_valid_word(home_team)
                    team2_name = get_first_valid_word(away_team)
                    match_name = f"{team1_name}{team2_name}"

                    # Format 1X2 odds row
                    match_1x2 = {
                        "match": match_name,
                        "market": "1X2",
                        "odd1": bet_map.get("1", {}).get("NULL", {}).get("ov", "N/A"),
                        "odd2": bet_map.get("2", {}).get("NULL", {}).get("ov", "N/A"),
                        "odd3": bet_map.get("3", {}).get("NULL", {}).get("ov", "N/A"),
                    }
                    # Format First Half 1X2 odds row
                    match_1x2_first = {
                        "match": match_name,
                        "market": "1X2F",
                        "odd1": bet_map.get("4", {})
                        .get("NULL", {})
                        .get("ov", "N/A"),  # Home first half
                        "odd2": bet_map.get("5", {})
                        .get("NULL", {})
                        .get("ov", "N/A"),  # draw first half
                        "odd3": bet_map.get("6", {})
                        .get("NULL", {})
                        .get("ov", "N/A"),  # away first half
                    }

                    # Format Second Half 1X2 odds row
                    match_1x2_second = {
                        "match": match_name,
                        "market": "1X2S",
                        "odd1": bet_map.get("235", {})
                        .get("NULL", {})
                        .get("ov", "N/A"),  # Home second half
                        "odd2": bet_map.get("236", {})
                        .get("NULL", {})
                        .get("ov", "N/A"),  # Away second half
                        "odd3": bet_map.get("237", {})
                        .get("NULL", {})
                        .get("ov", "N/A"),  # Draw second half
                    }

                    # Format GG/NG odds row
                    match_ggng = {
                        "match": match_name,
                        "market": "GGNG",
                        "odd1": bet_map.get("272", {}).get("NULL", {}).get("ov", "N/A"),
                        "odd2": bet_map.get("273", {}).get("NULL", {}).get("ov", "N/A"),
                        "odd3": "",
                    }

                    # Process full match total goals
                    total_goals_map = {
                        1.5: {"under": "21", "over": "242"},  # 1+ (1.19) and 2+ (1.65)
                        2.5: {"under": "22", "over": "24"},  # 2+ (1.19) and 3+ (1.65)
                        3.5: {"under": "219", "over": "25"},  # 0-2 (2.10) and 4+ (2.55)
                        4.5: {"under": "453", "over": "27"},
                    }

                    for total, codes in total_goals_map.items():
                        under_odd = (
                            bet_map.get(codes.get("under", ""), {})
                            .get("NULL", {})
                            .get("ov", "N/A")
                        )
                        over_odd = (
                            bet_map.get(codes.get("over", ""), {})
                            .get("NULL", {})
                            .get("ov", "N/A")
                        )

                        if under_odd != "N/A" or over_odd != "N/A":
                            match_total = {
                                "match": match_name,
                                "market": str(total),
                                "odd1": under_odd,
                                "odd2": over_odd,
                                "odd3": "",
                            }
                            all_matches_data.append(match_total)

                    # Process first half total goals
                    total_goals_first_map = {
                        0.5: {
                            "under": "267",
                            "over": "207",
                        },  # 0-1F (1.55) and 1+F (1.13)
                        1.5: {"under": "211", "over": "208"},
                        2.5: {"under": "472", "over": "209"},  # 3+F (2.28)
                    }

                    for total, codes in total_goals_first_map.items():
                        under_odd = (
                            bet_map.get(codes.get("under", ""), {})
                            .get("NULL", {})
                            .get("ov", "N/A")
                        )
                        over_odd = (
                            bet_map.get(codes.get("over", ""), {})
                            .get("NULL", {})
                            .get("ov", "N/A")
                        )

                        if under_odd != "N/A" or over_odd != "N/A":
                            match_total = {
                                "match": match_name,
                                "market": f"{total}F",
                                "odd1": under_odd,
                                "odd2": over_odd,
                                "odd3": "",
                            }
                            all_matches_data.append(match_total)

                    # Process second half total goals
                    total_goals_second_map = {
                        0.5: {"under": "269", "over": "213"},
                        1.5: {
                            "under": "217",
                            "over": "214",
                        },  # 0-1S (1.23) and 1+S (1.75)
                        2.5: {"under": "474", "over": "215"},
                    }

                    for total, codes in total_goals_second_map.items():
                        under_odd = (
                            bet_map.get(codes.get("under", ""), {})
                            .get("NULL", {})
                            .get("ov", "N/A")
                        )
                        over_odd = (
                            bet_map.get(codes.get("over", ""), {})
                            .get("NULL", {})
                            .get("ov", "N/A")
                        )

                        if under_odd != "N/A" or over_odd != "N/A":
                            match_total = {
                                "match": match_name,
                                "market": f"{total}S",
                                "odd1": under_odd,
                                "odd2": over_odd,
                                "odd3": "",
                            }
                            all_matches_data.append(match_total)

                    all_matches_data.extend(
                        [match_1x2, match_1x2_first, match_1x2_second, match_ggng]
                    )

        except Exception as e:
            print(f"Error processing league {league_name}: {str(e)}")
            continue

    # Save to CSV
    if all_matches_data:
        with open(
            "soccerbet_football_matches.csv", "w", newline="", encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["match", "market", "odd1", "odd2", "odd3"],
            )
            writer.writerows(all_matches_data)


if __name__ == "__main__":
    get_soccerbet_api()
