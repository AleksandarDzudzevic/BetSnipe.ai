import requests
import json
import ssl
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_utils import get_db_connection, batch_insert_matches

ssl._create_default_https_context = ssl._create_unverified_context


def get_table_tennis_leagues():
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
                if sport.get("id") == 17:  # Table Tennis
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


def get_admiral_stoni_tenis():
    try:
        conn = get_db_connection()
        matches_to_insert = []  # List to store match data

        # Get leagues dynamically
        leagues = get_table_tennis_leagues()

        if not leagues:
            print("No leagues found or error occurred while fetching leagues")
            return

        url2 = "https://srboffer.admiralbet.rs/api/offer/getWebEventsSelections"
        url3 = "https://srboffer.admiralbet.rs/api/offer/betsAndGroups"

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

        # Process each league
        for league in leagues:
            params = {
                "pageId": "35",
                "sportId": "17",  # Table Tennis
                "regionId": league["regionId"],
                "competitionId": league["competitionId"],
                "isLive": "false",
                "dateFrom": "2025-01-18T18:58:08.080",
                "dateTo": "2030-01-18T18:57:38.000",
                "eventMappingTypes": ["1", "2", "3", "4", "5"],
            }

            try:
                response = requests.get(url2, params=params, headers=headers)
                if response.status_code == 200:
                    matches = response.json()

                    for match in matches:
                        match_name = match.get("name", "")
                        match_datetime = match.get("dateTime", "")
                        if " - " not in match_name:
                            continue

                        team1, team2 = match_name.split(" - ")

                        # Get detailed bet information for each match
                        bets_url = f"{url3}/{17}/{league['regionId']}/{league['competitionId']}/{match.get('id')}"
                        bets_response = requests.get(bets_url, headers=headers)

                        if bets_response.status_code == 200:
                            bets_data = bets_response.json()

                            # Process bets - only looking for match winner (Pobednik)
                            for bet in bets_data.get("bets", []):
                                if bet.get("betTypeName") == "Pobednik":
                                    outcomes = bet.get("betOutcomes", [])
                                    if len(outcomes) >= 2:
                                        odd1 = outcomes[0].get("odd", "0.00")
                                        odd2 = outcomes[1].get("odd", "0.00")
                                        matches_to_insert.append((
                                            team1,
                                            team2,
                                            2,              # bookmaker_id (Admiral)
                                            5,              # sport_id (Table Tennis)
                                            1,              # bet_type_id (12)
                                            0,              # margin
                                            float(odd1),
                                            float(odd2),
                                            0,              # no odd3 for table tennis
                                            match_datetime
                                        ))
                                        break

            except Exception as e:
                print(f"Error processing league {league['name']}: {str(e)}")
                continue

        # Single batch insert for all matches
        if matches_to_insert:
            batch_insert_matches(conn, matches_to_insert)

    except Exception as e:
        print(f"Error in main execution: {str(e)}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    get_admiral_stoni_tenis()