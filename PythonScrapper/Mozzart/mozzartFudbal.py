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
                "sportIds": [1],
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
        print(f"Critical error fetching match {match_id}: {str(e)}")
    
    print(f"Failed to fetch match {match_id} after all attempts")
    return None


def get_first_valid_word(team_name):
    """Process team name with special cases for abbreviated names"""
    try:
        team_name = team_name.strip()

        # Special cases mapping
        special_cases = {
            "Ath.": "Atletico",
            "Man.": "Manchester",
            "Eintr.": "Eintracht",
            "St.Gilloise": "Royale",
        }

        # Check for special cases first
        for abbrev, full_name in special_cases.items():
            if team_name.startswith(abbrev):
                return full_name

        # If no special case, get first word
        words = team_name.split()
        if words:
            return words[0]
        return None
    except Exception as e:
        print(f"Error processing team name {team_name}: {e}")
        return None


def scrape_all_matches():
    try:
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

        csv_data = []
        current_league = None

        for league_id, league_name in leagues:
            
            match_ids = get_all_match_ids(league_id)
            
            if not match_ids:
                continue

            for match_id in match_ids:
                
                try:
                    match_data = get_mozzart_match(match_id, league_id)
                    
                    if match_data is None:
                        continue
                        
                    if "match" not in match_data:
                        continue

                    match = match_data["match"]

                    if "specialMatchGroupId" in match:
                        continue

                    home_team = match["home"].get("name")
                    away_team = match["visitor"].get("name")
                    
                    if not home_team or not away_team:
                        print(f"Invalid team names for match {match_id}")
                        continue

                    team1_name = get_first_valid_word(home_team)
                    team2_name = get_first_valid_word(away_team)
                    
                    if not team1_name or not team2_name:
                        print(f"Could not process team names for match {match_id}")
                        continue

                    match_name = f"{team1_name}{team2_name}"
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
                    csv_data.append(
                        [
                            match_name,
                            "1X2",
                            odds_1x2["1"],
                            odds_1x2["X"],
                            odds_1x2["2"],
                        ]
                    )
                    csv_data.append(
                        [
                            match_name,
                            "1X2F",
                            odds_1x2_first["1"],
                            odds_1x2_first["X"],
                            odds_1x2_first["2"],
                        ]
                    )
                    csv_data.append(
                        [
                            match_name,
                            "1X2S",
                            odds_1x2_second["1"],
                            odds_1x2_second["X"],
                            odds_1x2_second["2"],
                        ]
                    )
                    csv_data.append(
                        [
                            match_name,
                            "GGNG",
                            odds_gg_ng["gg"],
                            odds_gg_ng["ng"],
                        ]
                    )
                    # Convert and write full match total goals
                    under_odds = {}
                    over_odds = {}
                    # First handle the under odds
                    for subgame_name, odd in total_goals_odds.items():
                        if subgame_name.startswith("0-"):  # Under odds
                            goals = float(subgame_name.split("-")[1])
                            under_odds[goals + 0.5] = (
                                odd  # Changed from goals - 0.5 to goals + 0.5
                            )
                        elif subgame_name.endswith("+"):  # Over odds
                            goals = float(subgame_name[:-1])
                            over_odds[goals - 0.5] = odd
                    # Add special case for under 1.5 if we have 0-1
                    if "0-1" in total_goals_odds:
                        under_odds[1.5] = total_goals_odds["0-1"]
                    # Match and write the over/under pairs
                    for total in sorted(set(under_odds.keys()) & set(over_odds.keys())):
                        csv_data.append(
                            [
                                match_name,
                                f"{total:.1f}",
                                under_odds[total],
                                over_odds[total],
                            ]
                        )
                    # Similar conversion for first half totals
                    under_odds_first = {}
                    over_odds_first = {}
                    for subgame_name, odd in total_goals_first.items():
                        if subgame_name.startswith("0-"):
                            goals = float(subgame_name.split("-")[1])
                            under_odds_first[goals + 0.5] = (
                                odd  # Changed from goals - 0.5 to goals + 0.5
                            )
                        elif subgame_name.endswith("+"):
                            goals = float(subgame_name[:-1])
                            over_odds_first[goals - 0.5] = odd
                    # Add special cases for first half
                    if "0-0" in total_goals_first:
                        under_odds_first[0.5] = total_goals_first["0-0"]
                    if "0-1" in total_goals_first:
                        under_odds_first[1.5] = total_goals_first["0-1"]
                    # Add over 0.5 from 1+ if available
                    if "1+" in total_goals_first:
                        over_odds_first[0.5] = total_goals_first["1+"]
                    for total in sorted(
                        set(under_odds_first.keys()) | set(over_odds_first.keys())
                    ):
                        if total in under_odds_first and total in over_odds_first:
                            csv_data.append(
                                [
                                    match_name,
                                    f"{total:.1f}F",
                                    under_odds_first[total],
                                    over_odds_first[total],
                                ]
                            )
                    # Similar conversion for second half totals
                    under_odds_second = {}
                    over_odds_second = {}
                    for subgame_name, odd in total_goals_second.items():
                        if subgame_name.startswith("0-"):
                            goals = float(subgame_name.split("-")[1])
                            under_odds_second[goals + 0.5] = (
                                odd  # Changed from goals - 0.5 to goals + 0.5
                            )
                        elif subgame_name.endswith("+"):
                            goals = float(subgame_name[:-1])
                            over_odds_second[goals - 0.5] = odd
                    # Add special cases for second half
                    if "0-0" in total_goals_second:
                        under_odds_second[0.5] = total_goals_second["0-0"]
                    if "0-1" in total_goals_second:
                        under_odds_second[1.5] = total_goals_second["0-1"]
                    # Add over 0.5 from 1+ if available
                    if "1+" in total_goals_second:
                        over_odds_second[0.5] = total_goals_second["1+"]
                    for total in sorted(
                        set(under_odds_second.keys()) | set(over_odds_second.keys())
                    ):
                        if total in under_odds_second and total in over_odds_second:
                            csv_data.append(
                                [
                                    match_name,
                                    f"{total:.1f}S",
                                    under_odds_second[total],
                                    over_odds_second[total],
                                ]
                            )

                except Exception as e:
                    continue

        with open(
            "mozzart_football_matches.csv", "w", newline="", encoding="utf-8"
        ) as f:
            f.write("Match,BetType,Odd1,Odd2,Odd3\n")
            for row in csv_data:
                f.write(",".join(row) + "\n")

    except Exception as e:
        print(f"Critical error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        BrowserManager.cleanup()


if __name__ == "__main__":
    scrape_all_matches()
