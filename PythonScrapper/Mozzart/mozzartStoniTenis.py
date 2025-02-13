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
from Mozzart.mozzart_shared import browser_manager

ssl._create_default_https_context = ssl._create_unverified_context


def get_browser():
    options = uc.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    return uc.Chrome(options=options, version_main=132)


def get_table_tennis_leagues():
    """Fetch current table tennis leagues from Mozzart"""
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
                "sportId": 48,
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


def get_mozzart_sports():
    conn = None
    tab_handle = None
    try:
        conn = get_db_connection()
        matches_to_insert = []
        leagues = get_table_tennis_leagues()

        if not leagues:
            print("No leagues found")
            return

        for league_id, league_name in leagues:
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
                        "sportIds": [48],
                        "competitionIds": [{league_id}],
                        "pageSize": 100,
                        "currentPage": 0
                    }})
                }}).then(response => response.text());
                """

                try:
                    response = browser_manager.execute_script(script, tab_handle)
                    if not response:
                        continue

                    data = json.loads(response)
                    if not data.get("items"):
                        continue

                    for match in data["items"]:
                        try:
                            home_team = match["home"]["name"]
                            away_team = match["visitor"]["name"]
                            kick_off_time = convert_unix_to_iso(match.get("startTime", 0))

                            match_odds = {"1": "0.00", "2": "0.00"}

                            for odd in match.get("odds", []):
                                if odd["game"]["name"] == "Konačan ishod":
                                    if odd["subgame"]["name"] == "1":
                                        match_odds["1"] = odd["value"]
                                    elif odd["subgame"]["name"] == "2":
                                        match_odds["2"] = odd["value"]

                            # Store match data instead of immediate insert
                            matches_to_insert.append((
                                home_team,
                                away_team,
                                1,              # bookmaker_id
                                5,              # sport_id (Table Tennis)
                                1,              # bet_type_id (12)
                                0,              # margin
                                float(match_odds["1"]),
                                float(match_odds["2"]),
                                0,              # odd3
                                kick_off_time
                            ))

                        except Exception as e:
                            print(f"Error processing match: {e}")
                            continue

                except json.JSONDecodeError as e:
                    print(f"Error parsing matches response for league {league_name}: {e}")
                    continue

            except Exception as e:
                print(f"Error fetching matches for league {league_name}: {e}")
                continue
            finally:
                if tab_handle:
                    browser_manager.close_tab(tab_handle)
                tab_handle = None

        if matches_to_insert:
            batch_insert_matches(conn, matches_to_insert)

    except Exception as e:
        print(f"Critical error: {str(e)}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    get_mozzart_sports()
