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
        script = (
            """
        return fetch('https://www.mozzartbet.com/betting/matches', {
            method: 'POST',
            headers: {
                'Accept': 'application/json, text/plain, /',
                'Content-Type': 'application/json',
                'Origin': 'https://www.mozzartbet.com',
                'Medium': 'WEB'
            },
            body: JSON.stringify({
                "date": "all_days",
                "type": "all",
                "sportIds": [2],
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
                "sportIds": [2],
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
    
    print(f"Failed to fetch match {match_id} after all attempts")
    return None  # Explicit return None


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
    try:
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

        csv_data = []
        processed_matches = set()

        for league_id, league_name in leagues:
            match_ids = get_all_match_ids(league_id)
            if match_ids:
                for match_id in match_ids:
                    try:
                        match_data = get_mozzart_match(match_id, league_id)
                        
                        if match_data is None:  # Explicit check for None
                            print(f"Skipping match {match_id} due to fetch failure")
                            continue
                        
                        if "match" not in match_data:  # Additional validation
                            print(f"No match data found for {match_id}")
                            continue

                        match = match_data["match"]
                        if "specialMatchGroupId" in match:
                            continue

                        home_team = match.get("home", {}).get("name")
                        away_team = match.get("visitor", {}).get("name")

                        match_name = process_team_names(home_team, away_team)
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
                            # Skip handicaps for first and second halftime
                            group_name = odds_group.get("groupName", "")
                            if "poluvreme" in group_name.lower():
                                continue

                            for odd in odds_group.get("odds", []):
                                game_name = odd.get("game", {}).get("name", "")
                                subgame_name = odd.get("subgame", {}).get("name", "")
                                special_value = odd.get("specialOddValue", "")
                                value_type = odd.get("game", {}).get(
                                    "specialOddValueType", ""
                                )

                                try:
                                    value = f"{float(odd.get('value', '0.00')):.2f}"
                                except:
                                    value = "0.00"

                                if game_name == "Pobednik meča":
                                    if subgame_name in ["1", "2"]:
                                        winner_odds[subgame_name] = value
                                elif value_type == "HANDICAP":
                                    if special_value and subgame_name in ["1", "2"]:
                                        # Skip first and second halftime handicaps
                                        group_name = odd.get("game", {}).get(
                                            "groupName", ""
                                        )
                                        if "poluvreme" in group_name.lower():
                                            continue

                                        handicap = special_value
                                        if handicap not in handicap_odds:
                                            handicap_odds[handicap] = {
                                                "1": "",
                                                "2": "",
                                            }
                                        handicap_odds[handicap][subgame_name] = value
                                elif value_type == "MARGIN":
                                    if special_value:
                                        try:
                                            points = float(special_value)
                                            if points > 130:
                                                if subgame_name == "manje":
                                                    total_points_odds[
                                                        f"{special_value}_under"
                                                    ] = value
                                                elif subgame_name == "više":
                                                    total_points_odds[
                                                        f"{special_value}_over"
                                                    ] = value
                                        except ValueError:
                                            continue

                        # Add winner bet
                        csv_data.append(
                            [match_name, "12", winner_odds["1"], winner_odds["2"], ""]
                        )

                        # Add total points bets
                        sorted_points = sorted(
                            set(k.split("_")[0] for k in total_points_odds.keys()),
                            key=float,
                        )
                        for handicap in sorted(handicap_odds.keys(), key=float):
                            csv_data.append(
                                [
                                    match_name,
                                    f"H{handicap}",
                                    handicap_odds[handicap]["1"],
                                    handicap_odds[handicap]["2"],
                                    "",
                                ]
                            )

                        for points in sorted_points:
                            under_key = f"{points}_under"
                            over_key = f"{points}_over"
                            csv_data.append(
                                [
                                    match_name,
                                    f"OU{points}",
                                    total_points_odds.get(under_key, "0.00"),
                                    total_points_odds.get(over_key, "0.00"),
                                    "",
                                ]
                            )

                    except Exception as e:
                        continue  # Skip this match and continue with next one

        if not csv_data:
            print("No data collected to write to CSV")
            return

        with open("mozzart_basketball_matches.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Match", "BetType", "Odd1", "Odd2", "Odd3"])
            writer.writerows(csv_data)

    except Exception as e:
        print(f"Critical error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        BrowserManager.cleanup()


if __name__ == "__main__":
    scrape_all_matches()