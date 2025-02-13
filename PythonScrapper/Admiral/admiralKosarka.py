import requests
import json
import csv
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_utils import get_db_connection, batch_insert_matches

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
    conn = get_db_connection()
    matches_to_insert = []  # List to store match data

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
                            match_datetime = match.get("dateTime", "")

                            odds_url = f"{url_odds}/2/{competition['regionId']}/{competition['competitionId']}/{match['id']}"
                            odds_response = requests.get(odds_url, headers=headers)

                            if odds_response.status_code == 200:
                                odds_data = odds_response.json()
                                if isinstance(odds_data, dict) and "bets" in odds_data:
                                    bets = odds_data["bets"]

                                    for bet in bets:
                                        bet_type_id = bet.get("betTypeId")

                                        # 1. Winner (12)
                                        if bet_type_id == BET_TYPES["full_time_1x2"]:
                                            outcomes = sorted(bet["betOutcomes"], key=lambda x: x["orderNo"])
                                            if len(outcomes) >= 2:
                                                matches_to_insert.append((
                                                    team1,
                                                    team2,
                                                    2,              # bookmaker_id (Admiral)
                                                    2,              # sport_id (Basketball)
                                                    1,              # bet_type_id (12)
                                                    0,              # margin
                                                    float(outcomes[0]["odd"]),
                                                    float(outcomes[1]["odd"]),
                                                    0,              # no odd3 for basketball
                                                    match_datetime
                                                ))

                                        # 2. Total Points
                                        elif bet_type_id == BET_TYPES["total_points"]:
                                            totals = {}
                                            for outcome in bet["betOutcomes"]:
                                                total = outcome.get("sBV")
                                                if total:
                                                    if total not in totals:
                                                        totals[total] = {}
                                                    if outcome["name"].lower() == "vise":
                                                        totals[total]["over"] = outcome["odd"]
                                                    elif outcome["name"].lower() == "manje":
                                                        totals[total]["under"] = outcome["odd"]

                                            for total, odds in totals.items():
                                                if "over" in odds and "under" in odds:
                                                    matches_to_insert.append((
                                                        team1,
                                                        team2,
                                                        2,              # bookmaker_id
                                                        2,              # sport_id
                                                        10,             # bet_type_id (Total Points)
                                                        float(total),   # margin is the total
                                                        float(odds["under"]),
                                                        float(odds["over"]),
                                                        0,
                                                        match_datetime
                                                    ))

                                        # 3. Handicap
                                        elif bet_type_id == BET_TYPES["handicap"]:
                                            handicaps = {}
                                            for outcome in bet["betOutcomes"]:
                                                handicap = outcome.get("sBV")
                                                if handicap:
                                                    if handicap not in handicaps:
                                                        handicaps[handicap] = {}
                                                    if outcome["name"] == "1":
                                                        handicaps[handicap]["team1"] = outcome["odd"]
                                                    elif outcome["name"] == "2":
                                                        handicaps[handicap]["team2"] = outcome["odd"]

                                            for handicap, odds in handicaps.items():
                                                if "team1" in odds and "team2" in odds:
                                                    matches_to_insert.append((
                                                        team1,
                                                        team2,
                                                        2,              # bookmaker_id
                                                        2,              # sport_id
                                                        9,              # bet_type_id (Handicap)
                                                        float(handicap),
                                                        float(odds["team1"]),
                                                        float(odds["team2"]),
                                                        0,
                                                        match_datetime
                                                    ))

                        except Exception as e:
                            print(f"Error processing match {match.get('name', 'Unknown')}: {e}")
                            continue

        except Exception as e:
            print(f"Error processing competition {competition['name']}: {e}")
            continue

    # Single batch insert for all matches
    if matches_to_insert:
        batch_insert_matches(conn, matches_to_insert)

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()