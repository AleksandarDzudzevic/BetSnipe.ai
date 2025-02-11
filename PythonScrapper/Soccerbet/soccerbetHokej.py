import requests
import json
import csv
import ssl

ssl._create_default_https_context = ssl._create_unverified_context


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
    """Fetch current hockey leagues from Soccerbet"""
    url = "https://www.soccerbet.rs/restapi/offer/sr/categories/ext/sport/H/g?annex=0&desktopVersion=2.36.3.9&locale=sr"
    params = {
        "annex": "0",
        "desktopVersion": "2.36.3.9",
        "locale": "sr"
    }
    
    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            leagues = []
            
            for category in data.get('categories', []):
                league_id = category.get('id')
                league_name = category.get('name')
                if league_id and league_name:
                    leagues.append((league_id, league_name))
            
            return leagues
        else:
            print(f"Failed to fetch leagues with status code: {response.status_code}")
            return []

    except Exception as e:
        print(f"Error fetching leagues: {str(e)}")
        return []


def get_soccerbet_sports():
    # Get leagues dynamically instead of hardcoded list
    leagues = get_hockey_leagues()
    
    if not leagues:
        print("No leagues found or error occurred while fetching leagues")
        return

    all_matches_data = []

    try:
        for league_id, league_name in leagues:
            # Changed URL structure to use league-group instead of league
            url = f"https://www.soccerbet.rs/restapi/offer/sr/sport/H/league-group/{league_id}/mob"
            
            params = {
                "annex": "0",
                "desktopVersion": "2.36.3.7",
                "locale": "sr"
            }

            try:
                response = requests.get(url, params=params)
                data = response.json()

                if "esMatches" in data and data["esMatches"]:
                    for match in data["esMatches"]:
                        home_team = match.get("home")
                        away_team = match.get("away")
                        
                        if not home_team or not away_team:
                            continue

                        match_name = process_team_names(home_team, away_team)
                        if not match_name:
                            continue

                        # Get 1-X-2 odds from betMap
                        bet_map = match.get("betMap", {})
                        home_win = bet_map.get("1", {}).get("NULL", {}).get("ov", "N/A")
                        draw = bet_map.get("2", {}).get("NULL", {}).get("ov", "N/A")
                        away_win = bet_map.get("3", {}).get("NULL", {}).get("ov", "N/A")

                        if home_win != "N/A" and draw != "N/A" and away_win != "N/A":
                            match_data = [
                                match_name,
                                home_win,
                                draw,
                                away_win,
                            ]
                            all_matches_data.append(match_data)

            except Exception as e:
                print(f"Error getting matches from league {league_name}: {str(e)}")
                continue

        # Save to CSV
        if all_matches_data:
            with open("soccerbet_hockey_matches.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Match", "Odds 1", "X", "Odds 2"])
                writer.writerows(all_matches_data)
        else:
            print("No matches data to save")

    except Exception as e:
        print(f"Error in main execution: {str(e)}")


if __name__ == "__main__":
    get_soccerbet_sports()
