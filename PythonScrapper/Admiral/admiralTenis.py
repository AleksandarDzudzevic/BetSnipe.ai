import requests
import json
import csv
import ssl
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_utils import get_db_connection, batch_insert_matches

ssl._create_default_https_context = ssl._create_unverified_context


def process_team_name(name):
    """Process team name to get appropriate word based on singles/doubles"""
    try:
        name = name.strip()
        if "/" in name:  # Doubles match
            # Split partners and get first word from each
            partners = name.split("/")
            names = []
            for partner in partners:
                partner = partner.strip()
                if "," in partner:
                    lastname = partner.split(",")[0].strip()
                    names.append(lastname.split()[0])  # Get first word
                else:
                    names.append(partner.split()[0])  # Get first word
            return names[0]  # Return first player's name
        else:
            # Singles match - get last word
            words = name.split()
            if "," in name:
                lastname = name.split(",")[0].strip()
                return lastname.split()[-1]  # Get last word of lastname
            else:
                return words[-1]  # Get last word
    except Exception as e:
        print(f"Error processing name {name}: {e}")
        return None


def get_tennis_leagues():
    """Fetch current tennis leagues from Admiral"""
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

            # Find tennis in the sports list
            for sport in data:
                if sport.get("id") == 3:  # Tennis
                    # Iterate through regions (ATP, WTA, etc.)
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


def get_admiral_tennis():
    try:
        conn = get_db_connection()
        matches_to_insert = []  # List to store match data
        
        # Get leagues dynamically
        leagues = get_tennis_leagues()

        if not leagues:
            print("No leagues found or error occurred while fetching leagues")
            return

        url1 = (
            "https://srboffer.admiralbet.rs/api/offer/BetTypeSelections?sportId=3&pageId=35"
        )
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
                "sportId": "3",
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
                        bets_url = f"{url3}/{3}/{league['regionId']}/{league['competitionId']}/{match.get('id')}"
                        bets_response = requests.get(bets_url, headers=headers)

                        if bets_response.status_code == 200:
                            bets_data = bets_response.json()

                            # Process bets
                            for bet in bets_data.get("bets", []):
                                bet_type = bet.get("betTypeName")
                                outcomes = bet.get("betOutcomes", [])

                                if bet_type == "Pobednik" and len(outcomes) >= 2:
                                    odd1 = outcomes[0].get("odd", "0.00")
                                    odd2 = outcomes[1].get("odd", "0.00")
                                    matches_to_insert.append((
                                        team1,
                                        team2,
                                        2,              # bookmaker_id (Admiral)
                                        3,              # sport_id (Tennis)
                                        1,              # bet_type_id (12)
                                        0,              # margin
                                        float(odd1),
                                        float(odd2),
                                        0,              # no odd3 for tennis
                                        match_datetime
                                    ))

                                elif bet_type == "1.set - Pobednik" and len(outcomes) >= 2:
                                    odd1 = outcomes[0].get("odd", "0.00")
                                    odd2 = outcomes[1].get("odd", "0.00")
                                    matches_to_insert.append((
                                        team1,
                                        team2,
                                        2,              # bookmaker_id (Admiral)
                                        3,              # sport_id (Tennis)
                                        11,             # bet_type_id (12set1)
                                        0,              # margin
                                        float(odd1),
                                        float(odd2),
                                        0,              # no odd3 for tennis
                                        match_datetime
                                    ))

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
    get_admiral_tennis()
