import json
import time
import ssl
import certifi
import os
import csv
from datetime import datetime
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches
from Mozzart.mozzart_shared import browser_manager

ssl._create_default_https_context = ssl._create_unverified_context


def get_all_match_ids(league_id):
    tab_handle = None
    try:
        tab_handle = browser_manager.create_tab()
        script = f"""
        return fetch('https://www.mozzartbet.com/betting/matches', {{
            method: 'POST',
            headers: {{
                'Accept': 'application/json, text/plain, /',
                'Content-Type': 'application/json',
                'Origin': 'https://www.mozzartbet.com',
                'Medium': 'WEB'
            }},
            body: JSON.stringify({{
                "date": "all_days",
                "type": "all",
                "sportIds": [2],
                "competitionIds": [{league_id}],
                "pageSize": 100,
                "currentPage": 0
            }})
        }}).then(response => response.text());
        """

        response = browser_manager.execute_script(script, tab_handle)
        if response:
            data = json.loads(response)
            match_ids = []
            if data.get("items"):
                for match in data["items"]:
                    match_ids.append(match["id"])
            return match_ids
        return []
    finally:
        if tab_handle:
            browser_manager.close_tab(tab_handle)


def get_mozzart_match(match_id, league_id):
    tab_handle = None
    try:
        tab_handle = browser_manager.create_tab()
        script = f"""
        return fetch('https://www.mozzartbet.com/match/{match_id}', {{
            method: 'POST',
            headers: {{
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/json',
                'Origin': 'https://www.mozzartbet.com',
                'Medium': 'WEB'
            }},
            body: JSON.stringify({{
                "date": "all_days",
                "type": "all",
                "sportIds": [2],
                "competitionIds": [{league_id}],
                "pageSize": 100,
                "currentPage": 0
            }})
        }}).then(response => response.text());
        """

        for attempt in range(3):
            response = browser_manager.execute_script(script, tab_handle)
            if response:
                try:
                    data = json.loads(response)
                    if not data.get("error"):
                        return data
                except json.JSONDecodeError:
                    pass
            time.sleep(2)
    finally:
        if tab_handle:
            browser_manager.close_tab(tab_handle)


def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""


def scrape_all_matches():
    try:
        conn = get_db_connection()
        matches_to_insert = []  # List to store match data

        leagues = [
            (23, "NBA"),
            (26, "Evroliga"),
            (1147, "Evrokup"),
            (1699, "ABA Liga"),
            (1615, "Nemacka Liga"),
            (1680, "Grcka Liga"),
            (1656, "Italijanska Liga"),
            (2374, "Argentinska Liga"),
            (1729, "Australijska Liga"),
        ]

        processed_matches = set()

        for league_id, league_name in leagues:
            match_ids = get_all_match_ids(league_id)
            if match_ids:
                for match_id in match_ids:
                    try:
                        match_data = get_mozzart_match(match_id, league_id)

                        if match_data is None:
                            print(f"Skipping match {match_id} due to fetch failure")
                            continue

                        if "match" not in match_data:
                            print(f"No match data found for {match_id}")
                            continue

                        match = match_data["match"]
                        if "specialMatchGroupId" in match:
                            continue

                        home_team = match.get("home", {}).get("name")
                        away_team = match.get("visitor", {}).get("name")
                        kick_off_time = convert_unix_to_iso(match.get("startTime", 0))

                        match_name = f"{home_team} {away_team}"
                        if not match_name or match_name in processed_matches:
                            continue

                        processed_matches.add(match_name)

                        # Winner odds
                        winner_odds = {"1": "0.00", "2": "0.00"}
                        total_points_odds = {}
                        handicap_odds = {}

                        odds_groups = match.get("oddsGroup", [])
                        if not odds_groups:
                            continue

                        for odds_group in odds_groups:
                            group_name = odds_group.get("groupName", "")
                            if "poluvreme" in group_name.lower():
                                continue

                            for odd in odds_group.get("odds", []):
                                game_name = odd.get("game", {}).get("name", "")
                                subgame_name = odd.get("subgame", {}).get("name", "")
                                special_value = odd.get("specialOddValue", "")
                                value_type = odd.get("game", {}).get("specialOddValueType", "")

                                try:
                                    value = f"{float(odd.get('value', '0.00')):.2f}"
                                except:
                                    value = "0.00"

                                if game_name == "Pobednik meča":
                                    if subgame_name in ["1", "2"]:
                                        winner_odds[subgame_name] = value
                                elif value_type == "HANDICAP":
                                    if special_value and subgame_name in ["1", "2"]:
                                        group_name = odd.get("game", {}).get("groupName", "")
                                        if "poluvreme" in group_name.lower():
                                            continue

                                        handicap = special_value
                                        if handicap not in handicap_odds:
                                            handicap_odds[handicap] = {"1": "", "2": ""}
                                        handicap_odds[handicap][subgame_name] = value
                                elif value_type == "MARGIN":
                                    if special_value:
                                        try:
                                            points = float(special_value)
                                            if points > 130:
                                                if subgame_name == "manje":
                                                    total_points_odds[f"{special_value}_under"] = value
                                                elif subgame_name == "više":
                                                    total_points_odds[f"{special_value}_over"] = value
                                        except ValueError:
                                            continue

                        # Store match data instead of immediate insert
                        matches_to_insert.append((
                            home_team,
                            away_team,
                            1,              # bookmaker_id
                            2,              # sport_id
                            1,              # bet_type_id (12)
                            0,              # margin
                            float(winner_odds["1"]),
                            float(winner_odds["2"]),
                            0,
                            kick_off_time
                        ))

                        # Store handicap odds
                        for handicap in sorted(handicap_odds.keys(), key=float):
                            matches_to_insert.append((
                                home_team,
                                away_team,
                                1,              # bookmaker_id
                                2,              # sport_id
                                9,              # bet_type_id (Handicap)
                                float(handicap),
                                float(handicap_odds[handicap]["1"]),
                                float(handicap_odds[handicap]["2"]),
                                0,
                                kick_off_time
                            ))

                        # Store total points odds
                        sorted_points = sorted(set(k.split("_")[0] for k in total_points_odds.keys()), key=float)
                        for points in sorted_points:
                            under_key = f"{points}_under"
                            over_key = f"{points}_over"
                            matches_to_insert.append((
                                home_team,
                                away_team,
                                1,              # bookmaker_id
                                2,              # sport_id
                                10,             # bet_type_id (Total Points)
                                float(points),
                                float(total_points_odds[under_key]),
                                float(total_points_odds[over_key]),
                                0,
                                kick_off_time
                            ))

                    except Exception as e:
                        continue

        # Batch insert all collected matches
        if matches_to_insert:
            batch_insert_matches(conn, matches_to_insert)

    except Exception as e:
        print(f"Critical error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    scrape_all_matches()
