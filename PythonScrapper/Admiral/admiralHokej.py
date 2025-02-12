import requests
import json
import csv

url1 = "https://srboffer.admiralbet.rs/api/offer/BetTypeSelections?sportId=4&pageId=35"
url2 = "https://srboffer.admiralbet.rs/api/offer/getWebEventsSelections"

# Define all possible hockey competitions


def get_hockey_leagues():
    """Fetch current table tennis leagues from Admiral"""
    url = "https://srboffer.admiralbet.rs/api/offer/webTree/null/true/true/true/2025-02-10T20:48:46.651/2030-02-10T20:48:16.000/false"

    params = {"eventMappingTypes": ["1", "2", "3", "4", "5"]}

    headers = {
        "Accept": "application/utf8+json, application/json;q=0.9, text/plain;q=0.8, /;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Host": "srboffer.admiralbet.rs",
        "Language": "sr-Latn",
        "Officeid": "138",
        "Origin": "https://admiralbet.rs",
        "Referer": "https://admiralbet.rs/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            leagues = []

            # Find table tennis in the sports list
            for sport in data:
                if sport.get("id") == 4:
                    # Iterate through regions
                    for region in sport.get("regions", []):
                        # Get competitions from each region
                        for competition in region.get("competitions", []):
                            leagues.append(
                                {
                                    "regionId": competition.get("regionId"),
                                    "competitionId": competition.get("competitionId"),
                                    "name": competition.get("competitionName"),
                                }
                            )
            return leagues
        else:
            print(f"Failed to fetch leagues with status code: {response.status_code}")
            return []

    except Exception as e:
        print(f"Error fetching leagues: {str(e)}")
        return []


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


competitions = get_hockey_leagues()

# Move matches list outside competition loop
matches = []  # List to store ALL matches

try:
    # First get the bet types to find the hockey final result bet type ID
    response1 = requests.get(url1, headers=headers)

    if response1.status_code == 200:
        data1 = response1.json()

        # Find the final result bet type ID for hockey
        result_bet_type = None
        for bet_type in data1:
            if bet_type.get("betTypeName") == "Konacan ishod":
                result_bet_type = bet_type.get("betTypeId")
                break

        if result_bet_type:
            # Process each competition
            for competition in competitions:
                params = {
                    "pageId": "35",
                    "sportId": "4",
                    "regionId": competition["regionId"],
                    "competitionId": competition["competitionId"],
                    "isLive": "false",
                    "dateFrom": "2025-01-18T18:58:08.080",
                    "dateTo": "2030-01-18T18:57:38.000",
                    "eventMappingTypes": ["1", "2", "3", "4", "5"],
                }

                try:
                    response2 = requests.get(url2, params=params, headers=headers)

                    if response2.status_code == 200:
                        data2 = response2.json()

                        # Process each match
                        for match in data2:
                            match_name = match.get("name", "")

                            if " - " in match_name:
                                team1, team2 = match_name.split(" - ")

                                # Get first valid word for each team

                                # Create game label

                                # Look for final result odds
                                for bet in match.get("bets", []):
                                    if bet.get("betTypeId") == result_bet_type:
                                        outcomes = bet.get("betOutcomes", [])
                                        if len(outcomes) >= 3:
                                            odd1 = outcomes[0].get("odd")
                                            oddX = outcomes[1].get("odd")
                                            odd2 = outcomes[2].get("odd")

                                            matches.append(
                                                {
                                                    "Team1": team1,
                                                    "Team2": team2,
                                                    "Bet Type": "1X2",
                                                    "Odds 1": odd1,
                                                    "Odds X": oddX,
                                                    "Odds 2": odd2,
                                                }
                                            )

                except requests.exceptions.RequestException:
                    continue

            # Save ALL matches to CSV
            if matches:
                with open(
                    "admiral_hockey_matches.csv", "w", newline="", encoding="utf-8"
                ) as f:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=[
                            "Team1",
                            "Team2",
                            "Bet Type",
                            "Odds 1",
                            "Odds X",
                            "Odds 2",
                        ],
                    )
                    writer.writeheader()
                    for match in matches:
                        writer.writerow(match)
                print(
                    f"\nSuccessfully saved {len(matches)} matches to admiral_hockey_matches.csv"
                )

except requests.exceptions.RequestException as e:
    print("Initial request failed:", e)
except json.JSONDecodeError as e:
    print("JSON parsing failed:", e)
