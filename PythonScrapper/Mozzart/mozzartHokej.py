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
                "sportIds": [4],
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
                "sportIds": [4],
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
                        if not data.get("error"):
                            return data
                    except json.JSONDecodeError:
                        print(f"Failed to parse JSON on attempt {attempt + 1}")
                time.sleep(2)
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                time.sleep(3)

    except Exception as e:
        print(f"Error fetching match {match_id}: {str(e)}")
    return None


def process_team_names(home_team, away_team):
    """Convert team names to combined format"""
    try:
        teams = [home_team, away_team]
        processed_names = []

        for team in teams:
            team = team.strip()
            words = team.split()

            if not words:
                return None

            # If team name has only one word and it's 3 characters, use it
            if len(words) == 1 and len(words[0]) == 3:
                processed_name = words[0][0].upper() + words[0][1:]
            else:
                # Find first word longer than 3 characters
                first_long_word = next((word for word in words if len(word) > 2), None)
                if not first_long_word:
                    return None
                processed_name = first_long_word[0].upper() + first_long_word[1:]

            processed_names.append(processed_name)

        if len(processed_names) == 2:
            return f"{processed_names[0]}{processed_names[1]}"
        return None

    except Exception as e:
        print(f"Error processing names {home_team} vs {away_team}: {e}")
        return None


def get_hockey_leagues():
    """Fetch current hockey leagues from Mozzart"""
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
                "sportId": 4,
                "date": "all_days",
                "type": "prematch"
            })
        }).then(response => response.text());
        """

        response = driver.execute_script(script)
        leagues = []
        
        if response:
            try:
                data = json.loads(response)
                if 'competitions' in data:
                    for competition in data['competitions']:
                        league_id = competition.get('id')
                        league_name = competition.get('name')
                        if league_id and league_name:
                            leagues.append((league_id, league_name))
            except json.JSONDecodeError as e:
                print(f"Error parsing leagues response: {e}")
        
        return leagues

    except Exception as e:
        print(f"Error fetching leagues: {str(e)}")
        return []


def scrape_all_matches():
    try:
        leagues = get_hockey_leagues()
        
        if not leagues:
            print("No leagues found or error occurred while fetching leagues")
            return

        csv_data = []
        processed_matches = set()  # Track processed match names

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

                        if match.get("sport", {}).get("id") != 4:  # Check if hockey
                            print(f"Skipping non-hockey match {match_id}")
                            continue

                        if "home" not in match or "visitor" not in match:
                            print(f"Missing team data for match {match_id}")
                            continue

                        home_team = match["home"].get("name")
                        away_team = match["visitor"].get("name")

                        if not home_team or not away_team:
                            print(f"Invalid team names for match {match_id}")
                            continue

                        match_name = process_team_names(home_team, away_team)
                        if not match_name:
                            print(f"Could not process team names for {home_team} vs {away_team}")
                            continue
                            
                        if match_name in processed_matches:
                            print(f"Skipping duplicate match {match_name}")
                            continue

                        processed_matches.add(match_name)

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

                        csv_data.append([
                            match_name,
                            winner_odds["1"],
                            winner_odds["X"],
                            winner_odds["2"]
                        ])

                    except Exception as e:
                        continue

            except Exception as e:
                print(f"Error processing league {league_name}: {str(e)}")
                continue

        # Write to CSV only if we have data
        if csv_data:
            with open("mozzart_hockey_matches.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Match", "Odds 1", "X", "Odds 2"])
                writer.writerows(csv_data)
        else:
            print("No match data collected")

    except Exception as e:
        print(f"Critical error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        BrowserManager.cleanup()


if __name__ == "__main__":
    scrape_all_matches()
