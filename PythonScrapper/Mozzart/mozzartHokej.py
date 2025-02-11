import undetected_chromedriver as uc
import json
import atexit
import time
import ssl
import certifi
import os
import csv

ssl._create_default_https_context = ssl._create_unverified_context


def get_all_match_ids(driver, league_id):
    try:
        script = (
            """
        return fetch('https://www.mozzartbet.com/betting/matches', {
            method: 'POST',
            headers: {
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/json',
                'Origin': 'https://www.mozzartbet.com',
                'Medium': 'WEB'
            },
            body: JSON.stringify({
                "date": "all_days",
                "type": "all",
                "sportIds": [4],
                "competitionIds": ["""
            + str(league_id)
            + """],
                "pageSize": 100,
                "currentPage": 0
            })
        }).then(response => response.text());
        """
        )

        response = driver.execute_script(script)
        if response:
            data = json.loads(response)
            match_ids = []

            if data.get("items"):
                for match in data["items"]:
                    match_ids.append(match["id"])

            return match_ids
    except Exception as e:
        return []


def get_mozzart_match(match_id, league_id, driver):
    try:
        script = f"""
        return fetch('https://www.mozzartbet.com/match/{match_id}', {{
            method: 'POST',
            headers: {{
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Origin': 'https://www.mozzartbet.com',
                'Medium': 'WEB',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Ch-Ua': '"Not A(Brand";v="8", "Chromium";v="132", "Brave";v="132"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"'
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

        for _ in range(3):
            response = driver.execute_script(script)
            if response:
                data = json.loads(response)
                if not data.get("error"):
                    return data
            time.sleep(2)

    except Exception as e:
        return None

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


def scrape_all_matches():
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
        time.sleep(2)

        leagues = [(1627, "KHL"), (30, "NHL"), (1652, "AHL")]

        csv_data = []
        processed_matches = set()  # Track processed match names

        for league_id, _ in leagues:
            match_ids = get_all_match_ids(driver, league_id)
            if match_ids:  # Check if not None
                for match_id in match_ids:
                    match_data = get_mozzart_match(match_id, league_id, driver)
                    if match_data and "match" in match_data:
                        match = match_data["match"]

                        if match.get("sport", {}).get("id") != 4:  # Check if hockey
                            continue

                        home_team = match["home"]["name"]
                        away_team = match["visitor"]["name"]

                        match_name = process_team_names(home_team, away_team)
                        if not match_name or match_name in processed_matches:
                            continue

                        processed_matches.add(match_name)

                        winner_odds = {"1": "0.00", "X": "0.00", "2": "0.00"}

                        for odd in match.get("odds", []):
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
                                winner_odds[subgame_name] = value

                        csv_data.append(
                            [
                                match_name,
                                winner_odds["1"],
                                winner_odds["X"],
                                winner_odds["2"],
                            ]
                        )

        with open("mozzart_hockey_matches.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Match", "Odds 1", "X", "Odds 2"])
            writer.writerows(csv_data)

    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
            try:
                os.system('taskkill /f /im chromedriver.exe')
            except:
                pass


if __name__ == "__main__":
    scrape_all_matches()
