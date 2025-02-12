import requests
import json
import csv
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

url1 = "https://srboffer.admiralbet.rs/api/offer/BetTypeSelections?sportId=1&pageId=35"
url2 = "https://srboffer.admiralbet.rs/api/offer/getWebEventsSelections"
url_odds = "https://srboffer.admiralbet.rs/api/offer/betsAndGroups"

# Define all possible soccer competitions
competitions = [
    {"name": "Premier League", "competitionId": "1", "regionId": "1"},
    {"name": "Druga Engleska Liga", "competitionId": "2", "regionId": "1"},
    {"name": "La Liga", "competitionId": "3103", "regionId": "24"},
    {"name": "La Liga 2", "competitionId": "604", "regionId": "24"},
    {"name": "Bundesliga", "competitionId": "614", "regionId": "22"},
    {"name": "Bundesliga B", "competitionId": "612", "regionId": "22"},
    {"name": "Serie A", "competitionId": "597", "regionId": "23"},
    {"name": "Serie B", "competitionId": "600", "regionId": "23"},
    {"name": "Ligue 1", "competitionId": "564", "regionId": "4"},
    {"name": "Ligue 2", "competitionId": "581", "regionId": "4"},
    {"name": "Champions League", "competitionId": "764", "regionId": "104"},
    {"name": "Europa League", "competitionId": "1333", "regionId": "104"},
    {"name": "Argentiska Liga", "competitionId": "649", "regionId": "32"},
    {"name": "Liga Konferencije", "competitionId": "20951", "regionId": "104"},
    {"name": "Holandija Liga", "competitionId": "608", "regionId": "27"},
    {"name": "Brazilska Liga", "competitionId": "788", "regionId": "10"},
    {"name": "Australijska Liga", "competitionId": "670", "regionId": "26"},
    {"name": "Belgijska Liga", "competitionId": "606", "regionId": "25"},
    {"name": "Saudi Liga", "competitionId": "858", "regionId": "81"},
    {"name": "Grcka Liga", "competitionId": "666", "regionId": "38"},
    {"name": "Turska Liga", "competitionId": "641", "regionId": "30"},
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


try:
    matches = []  # List to store all matches

    for competition in competitions:
        params = {
            "pageId": "35",
            "sportId": "1",
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
                data = response.json()

                for match in data:
                    if match.get("name", "").count(" - ") == 1:
                        team1, team2 = match["name"].split(" - ")
                        match_datetime = match.get("dateTime", "")  # Get match datetime

                        # Process team name

                        # Get detailed odds
                        odds_url = f"{url_odds}/1/{competition['regionId']}/{competition['competitionId']}/{match['id']}"
                        odds_response = requests.get(odds_url, headers=headers)

                        if odds_response.status_code == 200:
                            odds_data = odds_response.json()
                            if isinstance(odds_data, dict) and "bets" in odds_data:
                                bets = odds_data["bets"]

                                # Process each bet type
                                for bet in bets:
                                    bet_type_id = bet.get("betTypeId")

                                    # 1X2 Full Time
                                    if bet_type_id == 135:
                                        outcomes = sorted(
                                            bet["betOutcomes"],
                                            key=lambda x: x["orderNo"],
                                        )
                                        if len(outcomes) >= 3:
                                            matches.append(
                                                {
                                                    "Team1": team1,
                                                    "Team2": team2,
                                                    "DateTime": match_datetime,  # Add datetime
                                                    "BetType": "1X2",
                                                    "Odd1": outcomes[0]["odd"],
                                                    "Odd2": outcomes[1]["odd"],
                                                    "Odd3": outcomes[2]["odd"],
                                                }
                                            )

                                    # 1X2 First Half
                                    elif bet_type_id == 148:
                                        outcomes = sorted(
                                            bet["betOutcomes"],
                                            key=lambda x: x["orderNo"],
                                        )
                                        if len(outcomes) >= 3:
                                            matches.append(
                                                {
                                                    "Team1": team1,
                                                    "Team2": team2,
                                                    "DateTime": match_datetime,  # Add datetime
                                                    "BetType": "1X2F",
                                                    "Odd1": outcomes[0]["odd"],
                                                    "Odd2": outcomes[1]["odd"],
                                                    "Odd3": outcomes[2]["odd"],
                                                }
                                            )

                                    # 1X2 Second Half
                                    elif bet_type_id == 149:
                                        outcomes = sorted(
                                            bet["betOutcomes"],
                                            key=lambda x: x["orderNo"],
                                        )
                                        if len(outcomes) >= 3:
                                            matches.append(
                                                {
                                                    "Team1": team1,
                                                    "Team2": team2,
                                                    "DateTime": match_datetime,  # Add datetime
                                                    "BetType": "1X2S",
                                                    "Odd1": outcomes[0]["odd"],
                                                    "Odd2": outcomes[1]["odd"],
                                                    "Odd3": outcomes[2]["odd"],
                                                }
                                            )

                                    # GGNG (Both Teams to Score)
                                    elif bet_type_id == 151:
                                        outcomes = sorted(
                                            bet["betOutcomes"],
                                            key=lambda x: x["orderNo"],
                                        )
                                        if len(outcomes) >= 2:
                                            matches.append(
                                                {
                                                    "Team1": team1,
                                                    "Team2": team2,
                                                    "DateTime": match_datetime,  # Add datetime
                                                    "BetType": "GGNG",
                                                    "Odd1": outcomes[0]["odd"],
                                                    "Odd2": outcomes[1]["odd"],
                                                    "Odd3": "",
                                                }
                                            )

                                    # Total Goals
                                    elif bet_type_id in [
                                        137,
                                        143,
                                        144,
                                    ]:  # Full time, First half, Second half
                                        suffix = ""
                                        if bet_type_id == 143:
                                            suffix = "F"
                                        elif bet_type_id == 144:
                                            suffix = "S"

                                        totals = {}
                                        for outcome in bet["betOutcomes"]:
                                            total = outcome["sBV"]
                                            if total not in totals:
                                                totals[total] = {}

                                            if outcome["name"].lower().startswith("vi"):
                                                totals[total]["over"] = outcome["odd"]
                                            else:
                                                totals[total]["under"] = outcome["odd"]

                                        for total, odds in totals.items():
                                            if "over" in odds and "under" in odds:
                                                matches.append(
                                                    {
                                                        "Team1": team1,
                                                        "Team2": team2,
                                                        "DateTime": match_datetime,  # Add datetime
                                                        "BetType": f"TG{total}{suffix}",
                                                        "Odd1": odds["under"],
                                                        "Odd2": odds["over"],
                                                        "Odd3": "",
                                                    }
                                                )

        except Exception as e:
            print(f"Error processing competition {competition['name']}: {e}")
            continue

    # Save to CSV
    if matches:
        with open(
            "admiral_football_matches.csv", "w", newline="", encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(
                f, fieldnames=["Team1", "Team2", "DateTime", "BetType", "Odd1", "Odd2", "Odd3"]
            )
            writer.writeheader()
            writer.writerows(matches)

except Exception as e:
    print(f"Error in main execution: {e}")