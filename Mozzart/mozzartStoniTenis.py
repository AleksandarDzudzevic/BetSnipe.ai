import undetected_chromedriver as uc
import json
import atexit
import time
import ssl
import certifi
import os
import csv

ssl._create_default_https_context = ssl._create_unverified_context


def process_team_name(name):
    """Process team name to get the first word"""
    try:
        name = name.strip()
        if "/" in name:  # Doubles match
            # Split partners and get first word (lastname) from each
            partners = name.split("/")
            names = []
            for partner in partners:
                if "," in partner:
                    lastname = partner.split(",")[0].strip()
                    names.append(lastname.split()[0])  # Get first word of lastname
                else:
                    names.append(partner.strip().split()[0])  # Get first word
            return names[0]  # Return first player's lastname
        else:
            # Singles match - get word before comma or first word
            if "," in name:
                lastname = name.split(",")[0].strip()
                return lastname.split()[0]  # Get first word of lastname
            else:
                return name.strip().split()[0]  # Get first word
    except Exception as e:
        print(f"Error processing name {name}: {e}")
        return None


def get_table_tennis_leagues(driver):
    """Fetch current table tennis leagues from Mozzart"""
    try:
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


def get_mozzart_sports():
    driver = None
    try:
        options = uc.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-logging")

        driver = uc.Chrome(options=options, version_main=131)
        atexit.register(lambda: driver.quit() if driver else None)
        
        driver.get("https://www.mozzartbet.com/sr/kladjenje")

        leagues = get_table_tennis_leagues(driver)
        
        if not leagues:
            print("No leagues found or error occurred while fetching leagues")
            return

        matches_data = []
        processed_matches = set()

        for league_id, league_name in leagues:
            script = f"""
            return fetch('https://www.mozzartbet.com/betting/matches', {{
                method: 'POST',
                headers: {{
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Content-Type': 'application/json',
                    'Origin': 'https://www.mozzartbet.com',
                    'Referer': 'https://www.mozzartbet.com/sr/kladjenje/competitions/48/{league_id}',
                    'User-Agent': navigator.userAgent,
                    'X-Requested-With': 'XMLHttpRequest',
                    'Medium': 'WEB'
                }},
                credentials: 'include',
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
                response = driver.execute_script(script)
                if not response:
                    print(f"No response for league {league_name}")
                    continue

                try:
                    data = json.loads(response)
                    if not data.get("items"):
                        print(f"No matches found in league {league_name}")
                        continue

                    for match in data["items"]:
                        try:
                            home_team = match["home"]["name"]
                            away_team = match["visitor"]["name"]
                            match_name = f"{home_team}, {away_team}"

                            if match_name in processed_matches:
                                continue

                            processed_matches.add(match_name)
                            match_odds = {"1": "N/A", "2": "N/A"}

                            for odd in match.get("odds", []):
                                if odd["game"]["name"] == "Konačan ishod":
                                    if odd["subgame"]["name"] == "1":
                                        match_odds["1"] = odd["value"]
                                    elif odd["subgame"]["name"] == "2":
                                        match_odds["2"] = odd["value"]

                            matches_data.append(
                                [match_name, "12", match_odds["1"], match_odds["2"], ""]
                            )
                        except Exception as e:
                            print(f"Error processing match: {e}")
                            continue

                except json.JSONDecodeError as e:
                    print(f"Error parsing matches response for league {league_name}: {e}")
                    continue

            except Exception as e:
                print(f"Error fetching matches for league {league_name}: {e}")
                continue

        print(f"Total matches found: {len(matches_data)}")
        
        if matches_data:
            with open("mozzart_tabletennis_matches.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerows(matches_data)
        else:
            print("No matches data to write to CSV")

    except Exception as e:
        print(f"Critical error: {str(e)}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
            atexit.unregister(lambda: driver.quit() if driver else None)


if __name__ == "__main__":
    get_mozzart_sports()