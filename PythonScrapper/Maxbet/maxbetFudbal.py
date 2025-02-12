import requests
import json
import csv

SOCCER_LEAGUES = {
    "champions_league": "136866",
    "europa_league": "136867",
    "conference_league": "180457",
    "premier_league": "152506",
    "england_2": "119606",
    "bundesliga": "117683",
    "bundesliga_2": "132231",
    "ligue_1": "117827",
    "ligue_2": "117861",
    "serie_a": "117689",
    "serie_b": "117690",
    "la_liga": "117709",
    "la_liga_2": "117710",
    "argentina_1": "143555",
    "australia_1": "132134",
    "brazil_1": "135401",
    "netherlands_1": "117808",
    "belgium_1": "152568",
    "saudi_1": "161743",
    "greece_1": "132131",
    "turkey_1": "119607",
}


def fetch_maxbet_matches():
    match_ids = []

    for league_name, league_id in SOCCER_LEAGUES.items():
        url = f"https://www.maxbet.rs/restapi/offer/sr/sport/S/league/{league_id}/mob"

        params = {"annex": "3", "desktopVersion": "1.2.1.10", "locale": "sr"}

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

    for match_id in match_ids:
        match_url = f"https://www.maxbet.rs/restapi/offer/sr/match/{match_id}"
        try:
            response = requests.get(match_url, params=params, headers=headers)
            if response.status_code == 200:
                match_data = response.json()

                home_team = match_data.get("home", "")
                away_team = match_data.get("away", "")
                odds = match_data.get("odds", {})

                # 1X2 odds
                home_win = odds.get("1", "")  # Home win (1)
                draw = odds.get("2", "")  # Draw (X)
                away_win = odds.get("3", "")  # Away win (2)

                # First Half 1X2 odds
                home_win_fh = odds.get("4", "")  # Home win First Half
                draw_fh = odds.get("5", "")  # Draw First Half
                away_win_fh = odds.get("6", "")  # Away win First Half

                # Second Half 1X2 odds
                home_win_sh = odds.get("235", "")  # Home win Second Half
                draw_sh = odds.get("236", "")  # Draw Second Half
                away_win_sh = odds.get("237", "")  # Away win Second Half

                # GGNG odds
                gg = odds.get("272", "")  # Both teams to score - Yes
                ng = odds.get("273", "")  # Both teams to score - No

                if home_win and draw and away_win:
                    matches_odds.append(
                        {
                            "team1": home_team,
                            "team2": away_team,
                            "marketType": "1X2",
                            "odd1": home_win,
                            "oddX": draw,
                            "odd2": away_win,
                        }
                    )

                if home_win_fh and draw_fh and away_win_fh:
                    matches_odds.append(
                        {
                            "team1": home_team,
                            "team2": away_team,
                            "marketType": "1X2F",
                            "odd1": home_win_fh,
                            "oddX": draw_fh,
                            "odd2": away_win_fh,
                        }
                    )

                if home_win_sh and draw_sh and away_win_sh:
                    matches_odds.append(
                        {
                            "team1": home_team,
                            "team2": away_team,
                            "marketType": "1X2S",
                            "odd1": home_win_sh,
                            "oddX": draw_sh,
                            "odd2": away_win_sh,
                        }
                    )

                if gg and ng:
                    matches_odds.append(
                        {
                            "team1": home_team,
                            "team2": away_team,
                            "marketType": "GGNG",
                            "odd1": gg,
                            "odd2": ng,
                        }
                    )

                # Total Goals odds pairs (under/over)
                total_goals_pairs = [
                    ("1.5", "211", "242"),
                    ("2.5", "22", "24"),
                    ("3.5", "219", "25"),
                    ("4.5", "453", "27"),
                    ("5.5", "266", "223"),
                ]

                # First Half Total Goals pairs
                total_goals_first_half_pairs = [
                    ("0.5", "188", "207"),
                    ("1.5", "211", "208"),  # ili 230 umesto 211
                    ("2.5", "472", "209"),
                ]

                # Second Half Total Goals pairs
                total_goals_second_half_pairs = [
                    ("0.5", "269", "213"),
                    ("1.5", "217", "214"),  # ili 390 umesto 217
                    ("2.5", "474", "215"),
                ]

                # Process each type of total goals
                for total, under_code, over_code in total_goals_pairs:
                    under_odd = odds.get(under_code, "")
                    over_odd = odds.get(over_code, "")
                    if under_odd and over_odd:
                        matches_odds.append(
                            {
                                "team1": home_team,
                                "team2": away_team,
                                "marketType": f"{total}",
                                "odd1": under_odd,
                                "odd2": over_odd,
                            }
                        )

                for total, under_code, over_code in total_goals_first_half_pairs:
                    under_odd = odds.get(under_code, "")
                    over_odd = odds.get(over_code, "")
                    if under_odd and over_odd:
                        matches_odds.append(
                            {
                                "team1": home_team,
                                "team2": away_team,
                                "marketType": f"{total}F",
                                "odd1": under_odd,
                                "odd2": over_odd,
                            }
                        )

                for total, under_code, over_code in total_goals_second_half_pairs:
                    under_odd = odds.get(under_code, "")
                    over_odd = odds.get(over_code, "")
                    if under_odd and over_odd:
                        matches_odds.append(
                            {
                                "team1": home_team,
                                "team2": away_team,
                                "marketType": f"{total}S",
                                "odd1": under_odd,
                                "odd2": over_odd,
                            }
                        )

            else:
                print(f"Failed to fetch match ID {match_id}: {response.status_code}")
        except Exception as e:
            print(f"Error fetching match ID {match_id}: {str(e)}")
            continue

    # Save to CSV
    if matches_odds:
        with open("maxbet_football_matches.csv", "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["team1", "team2", "marketType", "odd1", "oddX", "odd2"]
            )
            # Clean up empty oddX values before writing
            for match in matches_odds:
                # Handle both GGNG and total goals markets
                if match["marketType"] == "GGNG" or any(
                    x in match["marketType"]
                    for x in ["0.5", "1.5", "2.5", "3.5", "4.5", "5.5"]
                ):
                    match["oddX"] = match["odd2"]
                    match["odd2"] = ""
            writer.writerows(matches_odds)
    else:
        print("No odds data to save")

    return matches_odds


if __name__ == "__main__":
    fetch_maxbet_matches()
