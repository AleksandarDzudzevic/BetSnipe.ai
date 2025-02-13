import json
import atexit
import time
import ssl
import certifi
import os
from datetime import datetime
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, insert_match, batch_insert_matches
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
                "sportIds": [1],
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
        time.sleep(0.5)
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
                "sportIds": [1],
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
        matches_to_insert = []  # Will store tuples of match data
        
        leagues = [
            # European Competitions
            (60, "Liga Šampiona"),  # matches Maxbet's "champions_league"
            (1080, "Liga Evrope"),  # matches Maxbet's "europa_league"
            (13748, "Liga Konferencije"),  # matches Maxbet's "conference_league"
            # England
            (20, "Engleska 1"),  # matches Maxbet's "premier_league"
            (32, "Druga Engleska Liga"),  # matches Maxbet's "england_2"
            # Spain
            (22, "Španija 1"),  # matches Maxbet's "la_liga"
            (45, "Španija 2"),  # matches Maxbet's "la_liga_2"
            # Italy
            (19, "Italija 1"),  # matches Maxbet's "serie_a"
            (42, "Italija 2"),  # matches Maxbet's "serie_b"
            # Germany
            (21, "Nemačka 1"),  # matches Maxbet's "bundesliga"
            (39, "Nemačka 2"),  # matches Maxbet's "bundesliga_2"
            # France
            (13, "Francuska 1"),  # matches Maxbet's "ligue_1"
            (14, "Francuska 2"),  # matches Maxbet's "ligue_2"
            # Other Major Leagues
            (34, "Holandija 1"),  # matches Maxbet's "netherlands_1"
            (15, "Belgija 1"),  # matches Maxbet's "belgium_1"
            (46, "Turska 1"),  # matches Maxbet's "turkey_1"
            (53, "Grčka 1"),  # matches Maxbet's "greece_1"
            # Middle East
            (878, "Saudijska Arabija 1"),  # matches Maxbet's "saudi_1"
            # South America
            (797, "Argentina 1"),  # matches Maxbet's "argentina_1"
            (3648, "Brazil 1"),  # matches Maxbet's "brazil_1"
            # Australia
            (634, "Australija 1"),  # matches Maxbet's "australia_1"
        ]

        for league_id, league_name in leagues:
            match_ids = get_all_match_ids(league_id)

            if not match_ids:
                continue

            for match_id in match_ids:
                try:
                    match_data = get_mozzart_match(match_id, league_id)

                    if not match_data or "match" not in match_data:
                        continue

                    match = match_data["match"]
                    home_team = match["home"].get("name")
                    away_team = match["visitor"].get("name")
                    kick_off_time = convert_unix_to_iso(match.get("startTime", 0))

                    if "specialMatchGroupId" in match:
                        continue

                    odds_1x2 = {"1": "0.00", "X": "0.00", "2": "0.00"}
                    odds_1x2_first = {"1": "0.00", "X": "0.00", "2": "0.00"}
                    odds_1x2_second = {"1": "0.00", "X": "0.00", "2": "0.00"}
                    odds_gg_ng = {"gg": "0.00", "ng": "0.00"}
                    total_goals_odds = {}
                    total_goals_first = {}
                    total_goals_second = {}
                    for odds_group in match.get("oddsGroup", []):
                        group_name = odds_group.get("groupName", "")

                        for odd in odds_group.get("odds", []):
                            game_name = odd.get("game", {}).get("name", "")
                            subgame_name = odd.get("subgame", {}).get("name", "")
                            try:
                                value = f"{float(odd.get('value', '0.00')):.2f}"
                            except:
                                value = "0.00"
                            if game_name == "Konačan ishod" and subgame_name in [
                                "1",
                                "X",
                                "2",
                            ]:
                                odds_1x2[subgame_name] = value
                            elif game_name == "Prvo poluvreme" and subgame_name in [
                                "1",
                                "X",
                                "2",
                            ]:
                                odds_1x2_first[subgame_name] = value
                            elif game_name == "Drugo poluvreme" and subgame_name in [
                                "1",
                                "X",
                                "2",
                            ]:
                                odds_1x2_second[subgame_name] = value
                            elif game_name == "Oba tima daju gol":
                                if subgame_name == "gg":
                                    odds_gg_ng["gg"] = value
                                elif subgame_name == "ng":
                                    odds_gg_ng["ng"] = value
                            elif game_name == "Ukupno golova":
                                total_goals_odds[subgame_name] = value
                            elif game_name == "Ukupno golova prvo poluvreme":
                                total_goals_first[subgame_name] = value
                            elif game_name == "Ukupno golova drugo poluvreme":
                                total_goals_second[subgame_name] = value
                    kick_off_time = convert_unix_to_iso(match.get("startTime", 0))  # Get and convert kickoff time

                    # Convert and write full match total goals
                    under_odds = {}
                    over_odds = {}
                    # First handle the under odds
                    for subgame_name, odd in total_goals_odds.items():
                        if subgame_name.startswith("0-"):  # Under odds
                            goals = float(subgame_name.split("-")[1])
                            under_odds[goals + 0.5] = odd
                        elif subgame_name.endswith("+"):  # Over odds
                            goals = float(subgame_name[:-1])
                            over_odds[goals - 0.5] = odd

                    # Add special case for under 1.5 if we have 0-1
                    if "0-1" in total_goals_odds:
                        under_odds[1.5] = total_goals_odds["0-1"]

                    # Similar conversion for first half totals
                    under_odds_first = {}
                    over_odds_first = {}
                    for subgame_name, odd in total_goals_first.items():
                        if subgame_name.startswith("0-"):
                            goals = float(subgame_name.split("-")[1])
                            under_odds_first[goals + 0.5] = odd
                        elif subgame_name.endswith("+"):
                            goals = float(subgame_name[:-1])
                            over_odds_first[goals - 0.5] = odd

                    # Add special cases for first half
                    if "0-0" in total_goals_first:
                        under_odds_first[0.5] = total_goals_first["0-0"]
                    if "0-1" in total_goals_first:
                        under_odds_first[1.5] = total_goals_first["0-1"]
                    if "1+" in total_goals_first:
                        over_odds_first[0.5] = total_goals_first["1+"]

                    # Similar conversion for second half totals
                    under_odds_second = {}
                    over_odds_second = {}
                    for subgame_name, odd in total_goals_second.items():
                        if subgame_name.startswith("0-"):
                            goals = float(subgame_name.split("-")[1])
                            under_odds_second[goals + 0.5] = odd
                        elif subgame_name.endswith("+"):
                            goals = float(subgame_name[:-1])
                            over_odds_second[goals - 0.5] = odd

                    # Add special cases for second half
                    if "0-0" in total_goals_second:
                        under_odds_second[0.5] = total_goals_second["0-0"]
                    if "0-1" in total_goals_second:
                        under_odds_second[1.5] = total_goals_second["0-1"]
                    if "1+" in total_goals_second:
                        over_odds_second[0.5] = total_goals_second["1+"]

                    # Match and insert the over/under pairs for full match
                    for total in sorted(set(under_odds.keys()) & set(over_odds.keys())):
                        matches_to_insert.append((
                            home_team,
                            away_team,
                            1,              # bookmaker_id
                            1,              # sport_id (Football)
                            5,              # bet_type_id (Total Goals)
                            total,          # margin
                            float(under_odds[total]),  # Under odds first
                            float(over_odds[total]),   # Over odds second
                            0,
                            kick_off_time
                        ))

                    # Match and insert the over/under pairs for first half
                    for total in sorted(set(under_odds_first.keys()) & set(over_odds_first.keys())):
                        matches_to_insert.append((
                            home_team,
                            away_team,
                            1,              # bookmaker_id
                            1,              # sport_id (Football)
                            6,              # bet_type_id (Total Goals First Half)
                            total,          # margin
                            float(under_odds_first[total]),  # Under odds first
                            float(over_odds_first[total]),   # Over odds second
                            0,
                            kick_off_time
                        ))

                    # Match and insert the over/under pairs for second half
                    for total in sorted(set(under_odds_second.keys()) & set(over_odds_second.keys())):
                        matches_to_insert.append((
                            home_team,
                            away_team,
                            1,              # bookmaker_id
                            1,              # sport_id (Football)
                            7,              # bet_type_id (Total Goals Second Half)
                            total,          # margin
                            float(under_odds_second[total]),  # Under odds first
                            float(over_odds_second[total]),   # Over odds second
                            0,
                            kick_off_time
                        ))

                    # Insert match winner odds (1X2)
                    matches_to_insert.append((
                        home_team,
                        away_team,
                        1,              # bookmaker_id
                        1,              # sport_id (Football)
                        2,              # bet_type_id (1X2)
                        0,              # margin
                        float(odds_1x2["1"]),
                        float(odds_1x2["X"]),
                        float(odds_1x2["2"]),
                        kick_off_time
                    ))

                    # Insert first half odds (1X2F)
                    matches_to_insert.append((
                        home_team,
                        away_team,
                        1,              # bookmaker_id
                        1,              # sport_id (Football)
                        3,              # bet_type_id (1X2F)
                        0,              # margin
                        float(odds_1x2_first["1"]),
                        float(odds_1x2_first["X"]),
                        float(odds_1x2_first["2"]),
                        kick_off_time
                    ))

                    # Insert second half odds (1X2S)
                    matches_to_insert.append((
                        home_team,
                        away_team,
                        1,              # bookmaker_id
                        1,              # sport_id (Football)
                        4,              # bet_type_id (1X2S)
                        0,              # margin
                        float(odds_1x2_second["1"]),
                        float(odds_1x2_second["X"]),
                        float(odds_1x2_second["2"]),
                        kick_off_time
                    ))

                    # Insert GG/NG odds
                    matches_to_insert.append((
                        home_team,
                        away_team,
                        1,              # bookmaker_id
                        1,              # sport_id (Football)
                        8,              # bet_type_id (GGNG)
                        0,              # margin
                        float(odds_gg_ng["gg"]),
                        float(odds_gg_ng["ng"]),
                        0,
                        kick_off_time
                    ))

                except Exception as e:
                    continue

        # Single batch insert for all matches
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
