import requests
import json
import csv

url2 = "https://srboffer.admiralbet.rs/api/offer/getWebEventsSelections"
url_odds = "https://srboffer.admiralbet.rs/api/offer/betsAndGroups"

# Define all possible basketball competitions
competitions = [
    {"name": "ABA Liga", "competitionId": "114", "regionId": "123"},
    {"name": "NBA", "competitionId": "12", "regionId": "122"},
    {"name": "Nemacka Liga", "competitionId": "11", "regionId": "128"},
    {"name": "Francuska Liga", "competitionId": "25", "regionId": "127"},
    {"name": "Evroliga", "competitionId": "3060", "regionId": "123"},
    {"name": "Evrokup", "competitionId": "135", "regionId": "123"},
    {"name": "Italijanska Liga", "competitionId": "14", "regionId": "124"},
    {"name": "Spanska Liga", "competitionId": "22", "regionId": "126"},
]

headers = {
    "Accept": "application/utf8+json, application/json;q=0.9, text/plain;q=0.8, /;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Host": "srboffer.admiralbet.rs",
    "Language": "sr-Latn",
    "Officeid": "138",
    "Origin": "https://admiralbet.rs",
    "Referer": "https://admiralbet.rs/",
    "Sec-Ch-Ua": '"Brave";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

# Update the bet type IDs for basketball
BET_TYPES = {
    "full_time_1x2": 186,  # Winner (Pobednik)
    "total_points": 213,  # Total Points
    "handicap": 191,  # Handicap (Hendikep)
}


try:
    with open(
        "admiral_basketball_matches.csv", "w", newline="", encoding="utf-8"
    ) as csvfile:
        csvwriter = csv.writer(csvfile)

        for competition in competitions:
            params = {
                "pageId": "35",
                "sportId": "2",  # 2 is for basketball
                "regionId": competition["regionId"],
                "competitionId": competition["competitionId"],
                "isLive": "false",
                "dateFrom": "2025-01-18T19:42:15.955",
                "dateTo": "2030-01-18T19:41:45.000",
                "eventMappingTypes": ["1", "2", "3", "4", "5"],
            }

            try:
                response = requests.get(url2, params=params, headers=headers)
                if response.status_code == 200:
                    matches = response.json()

                    for match in matches:
                        if match.get("id") and match.get("name", "").count(" - ") == 1:
                            try:
                                team1, team2 = match["name"].split(" - ")
                                match_datetime = match.get("dateTime", "")  # Get match datetime

                                # Process team names for CSV labeling

                                odds_url = f"{url_odds}/2/{competition['regionId']}/{competition['competitionId']}/{match['id']}"
                                odds_response = requests.get(odds_url, headers=headers)

                                if odds_response.status_code == 200:
                                    odds_data = odds_response.json()
                                    if isinstance(odds_data, dict) and "bets" in odds_data:
                                        bets = odds_data["bets"]

                                        # Process each bet type
                                        for bet in bets:
                                            bet_type_id = bet.get("betTypeId")

                                            # 1. Full time 1X2 (no overtime)
                                            if bet_type_id == BET_TYPES["full_time_1x2"]:
                                                outcomes = sorted(
                                                    bet["betOutcomes"],
                                                    key=lambda x: x["orderNo"],
                                                )
                                                if len(outcomes) >= 2:
                                                    csvwriter.writerow(
                                                        [
                                                            team1,
                                                            team2,
                                                            match_datetime,  # Add datetime
                                                            "12",
                                                            outcomes[0]["odd"],
                                                            outcomes[1]["odd"],
                                                            "",  # No draw in basketball
                                                        ]
                                                    )

                                            # 2. Total Points
                                            elif bet_type_id == BET_TYPES["total_points"]:
                                                for outcome in bet["betOutcomes"]:
                                                    total = outcome.get("sBV")
                                                    if (
                                                        total
                                                    ):  # Only process if we have a total value
                                                        if (
                                                            outcome["name"].lower()
                                                            == "vise"
                                                        ):  # 'Vise' means 'Over'
                                                            over_odd = outcome["odd"]
                                                        elif (
                                                            outcome["name"].lower()
                                                            == "manje"
                                                        ):  # 'Manje' means 'Under'
                                                            under_odd = outcome["odd"]

                                                        if (
                                                            "over_odd" in locals()
                                                            and "under_odd" in locals()
                                                        ):
                                                            csvwriter.writerow(
                                                                [
                                                                    team1,
                                                                    team2,
                                                                    match_datetime,  # Add datetime
                                                                    f"OU{total}",
                                                                    under_odd,
                                                                    over_odd,
                                                                    "",
                                                                ]
                                                            )
                                                            del over_odd, under_odd

                                            # 3. Handicap
                                            elif bet_type_id == BET_TYPES["handicap"]:
                                                handicaps = {}
                                                for outcome in bet["betOutcomes"]:
                                                    handicap = outcome.get("sBV")
                                                    if handicap:
                                                        if handicap not in handicaps:
                                                            handicaps[handicap] = {}
                                                        # Check if it's team1 (1) or team2 (2)
                                                        if (
                                                            outcome["name"] == "1"
                                                        ):  # Team 1
                                                            handicaps[handicap][
                                                                "team1"
                                                            ] = outcome["odd"]
                                                        elif (
                                                            outcome["name"] == "2"
                                                        ):  # Team 2
                                                            handicaps[handicap][
                                                                "team2"
                                                            ] = outcome["odd"]

                                                for handicap, odds in handicaps.items():
                                                    if (
                                                        "team1" in odds
                                                        and "team2" in odds
                                                    ):
                                                        csvwriter.writerow(
                                                            [
                                                                team1,
                                                                team2,
                                                                match_datetime,  # Add datetime
                                                                f"H{handicap}",
                                                                odds["team1"],
                                                                odds["team2"],
                                                                "",
                                                            ]
                                                        )

                            except Exception as e:
                                print(
                                    f"Error processing match {match.get('name', 'Unknown')}: {e}"
                                )
                                continue
            except Exception as e:
                print(f"Error processing competition {competition['name']}: {e}")
                continue

except Exception as e:
    print(f"Error: {e}")