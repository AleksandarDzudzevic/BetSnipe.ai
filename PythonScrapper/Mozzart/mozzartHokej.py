import undetected_chromedriver as uc
import json
import atexit
import time
import ssl
import certifi
import os
import csv
from datetime import datetime
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, insert_match, batch_insert_matches

ssl._create_default_https_context = ssl._create_unverified_context


def get_browser():
    options = uc.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    return uc.Chrome(options=options, version_main=132)


def get_all_match_ids(league_id):
    tab_handle = None
    try:
        tab_handle = browser_manager.create_tab()
        script = f"""
        return fetch('https://www.mozzartbet.com/betting/matches', {{
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
                "sportIds": [4],
                "competitionIds": [{league_id}],
                "pageSize": 100,
                "currentPage": 0
            }})
        }}).then(response => response.text());
        """

        for attempt in range(3):
            try:
                response = browser_manager.execute_script(script, tab_handle)
                if response:
                    try:
                        data = json.loads(response)
                        match_ids = []
                        if data.get("items"):
                            for match in data["items"]:
                                match_ids.append(match["id"])
                        return match_ids if match_ids else []
                    except json.JSONDecodeError:
                        print(f"Failed to parse JSON on attempt {attempt + 1}")
                time.sleep(2)
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                time.sleep(3)
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
                "sportIds": [4],
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


def get_hockey_leagues():
    """Fetch current hockey leagues from Mozzart"""
    tab_handle = None
    try:
        tab_handle = browser_manager.create_tab()
        script = """
        return fetch('https://www.mozzartbet.com/betting/get-competitions', {
            method: 'POST',
            headers: {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.5',
                'Content-Type': 'application/json',
                'Origin': 'https://www.mozzartbet.com',
                'Referer': 'https://www.mozzartbet.com/sr/kladjenje',
                'User-Agent': navigator.userAgent,
                'X-Requested-With': 'XMLHttpRequest',
                'Medium': 'WEB'
            },
            credentials: 'include',
            body: JSON.stringify({
                "sportId": 4,
                "date": "all_days",
                "type": "prematch"
            })
        }).then(response => response.text());
        """

        response = browser_manager.execute_script(script, tab_handle)
        leagues = []

        if response:
            try:
                data = json.loads(response)
                if "competitions" in data:
                    for competition in data["competitions"]:
                        league_id = competition.get("id")
                        league_name = competition.get("name")
                        if league_id and league_name:
                            leagues.append((league_id, league_name))
            except json.JSONDecodeError as e:
                print(f"Error parsing leagues response: {e}")

        return leagues

    except Exception as e:
        print(f"Error fetching leagues: {str(e)}")
        return []
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
        leagues = get_hockey_leagues()
        matches_to_insert = []  # Will store tuples of match data

        if not leagues:
            print("No leagues found or error occurred while fetching leagues")
            return

        for league_id, league_name in leagues:
            match_ids = get_all_match_ids(league_id)

            if not match_ids:
                print(f"No matches found for league {league_name}")
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

                    # Winner odds (1X2)
                    winner_odds = {"1": "0.00", "X": "0.00", "2": "0.00"}
                    for odds_group in match.get("oddsGroup", []):
                        for odd in odds_group.get("odds", []):
                            game_name = odd.get("game", {}).get("name", "")
                            subgame_name = odd.get("subgame", {}).get("name", "")
                            try:
                                value = f"{float(odd.get('value', '0.00')):.2f}"
                            except:
                                value = "0.00"

                            if game_name == "Konačan ishod" and subgame_name in ["1", "X", "2"]:
                                winner_odds[subgame_name] = value

                    # Append tuple of match data
                    matches_to_insert.append((
                        home_team,
                        away_team,
                        1,              # bookmaker_id
                        3,              # sport_id (Hockey)
                        2,              # bet_type_id (1X2)
                        0,              # margin
                        float(winner_odds["1"]),
                        float(winner_odds["X"]),
                        float(winner_odds["2"]),
                        kick_off_time
                    ))

                except Exception as e:
                    print(f"Error processing match: {e}")
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
