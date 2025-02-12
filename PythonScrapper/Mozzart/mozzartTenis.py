import undetected_chromedriver as uc
import json
import atexit
import time
import ssl
import certifi
import os
import csv
from mozzart_shared import BrowserManager

ssl._create_default_https_context = ssl._create_unverified_context

def get_tennis_leagues():
    """Fetch current tennis leagues from Mozzart"""
    try:
        driver = BrowserManager.get_browser()
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
                "sportId": 5,
                "date": "all_days",
                "type": "prematch"
            })
        }).then(response => response.text());
        """

        response = driver.execute_script(script)
        leagues = []
        
        if response:
            data = json.loads(response)
            for competition in data.get('competitions', []):
                league_id = competition.get('id')
                league_name = competition.get('name')
                if league_id and league_name:
                    leagues.append((league_id, league_name))
        
        return leagues

    except Exception as e:
        print(f"Error fetching leagues: {str(e)}")
        return []


def get_all_match_ids(league_id):
    try:
        driver = BrowserManager.get_browser()
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
                "sportIds": [5],
                "competitionIds": [{league_id}],
                "pageSize": 100,
                "currentPage": 0
            }})
        }}).then(response => response.text());
        """

        for attempt in range(3):  # Try up to 3 times
            try:
                response = driver.execute_script(script)
                if response:
                    try:
                        data = json.loads(response)
                        match_ids = []
                        if data.get("items"):
                            for match in data["items"]:
                                match_ids.append(match["id"])
                        return match_ids if match_ids else []  # Return empty list if no matches found
                    except json.JSONDecodeError:
                        print(f"Failed to parse JSON on attempt {attempt + 1}")
                time.sleep(2)
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                time.sleep(3)
                
        return []  # Return empty list if all attempts fail

    except Exception as e:
        print(f"Error getting match IDs for league {league_id}: {str(e)}")
        return []  # Return empty list on error


def get_mozzart_match(match_id, league_id):
    try:
        driver = BrowserManager.get_browser()
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
                "sportIds": [5],
                "competitionIds": [{league_id}],
                "pageSize": 100,
                "currentPage": 0
            }})
        }}).then(response => response.text());
        """

        for attempt in range(3):  # Try up to 3 times
            response = driver.execute_script(script)
            if response:
                try:
                    data = json.loads(response)
                    if not data.get("error"):
                        return data
                except json.JSONDecodeError:
                    pass
            time.sleep(2)  # Wait between retries

    except Exception as e:
        print(f"Error fetching match {match_id}: {str(e)}")
    
    return None


def get_mozzart_sports():
    try:
        leagues = get_tennis_leagues()
        
        if not leagues:
            print("No leagues found or error occurred while fetching leagues")
            return

        matches_data = []  # List to store match data for CSV
        processed_matches = set()

        for league_id, league_name in leagues:
            try:
                match_ids = get_all_match_ids(league_id)
                
                if not match_ids:
                    print(f"No matches found for league {league_name}")
                    continue

                for match_id in match_ids:
                    try:
                        match_data = get_mozzart_match(match_id, league_id)
                        
                        if not match_data or "match" not in match_data:
                            print(f"No valid data for match {match_id}")
                            continue
                            
                        match = match_data["match"]
                        
                        if "home" not in match or "visitor" not in match:
                            print(f"Missing team data for match {match_id}")
                            continue
                            
                        home_team = match["home"].get("name")
                        away_team = match["visitor"].get("name")

                        if not home_team or not away_team:
                            print(f"Invalid team names for match {match_id}")
                            continue

                        match_id = f"{home_team}, {away_team}"
                        if match_id in processed_matches:
                            continue

                        processed_matches.add(match_id)

                        # Initialize odds dictionaries with default values
                        match_odds = {"1": "0.00", "2": "0.00"}
                        first_set_odds = {"1": "0.00", "2": "0.00"}
                        
                        # Process odds from oddsGroup instead of odds
                        for odds_group in match.get("oddsGroup", []):
                            for odd in odds_group.get("odds", []):
                                game_name = odd.get("game", {}).get("name", "")
                                subgame_name = odd.get("subgame", {}).get("name", "")
                                try:
                                    value = f"{float(odd.get('value', '0.00')):.2f}"
                                except:
                                    value = "0.00"
                                
                                if game_name == "Konačan ishod":
                                    if subgame_name == "1":
                                        match_odds["1"] = value
                                    elif subgame_name == "2":
                                        match_odds["2"] = value
                                elif game_name == "Prvi set":
                                    if subgame_name == "1":
                                        first_set_odds["1"] = value
                                    elif subgame_name == "2":
                                        first_set_odds["2"] = value

                        matches_data.append(
                            [match_id, "12", match_odds["1"], match_odds["2"]]
                        )
                        matches_data.append(
                            [match_id, "12set1", first_set_odds["1"], first_set_odds["2"]]
                        )

                    except Exception as e:
                        print(f"Error processing match {match_id}: {str(e)}")
                        continue

            except Exception as e:
                print(f"Error processing league {league_name}: {str(e)}")
                continue

        # Write to CSV only if we have data
        if matches_data:
            with open("mozzart_tennis_matches.csv", "w", newline="", encoding="utf-8") as f:
                f.write("Match,BetType,Odd1,Odd2\n")
                for row in matches_data:
                    f.write(f"{row[0]},{row[1]},{row[2]},{row[3]}\n")
        else:
            print("No match data collected")

    except Exception as e:
        print(f"Critical error: {str(e)}")
    finally:
        BrowserManager.cleanup()


if __name__ == "__main__":
    get_mozzart_sports()
