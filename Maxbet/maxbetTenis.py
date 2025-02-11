import requests
import csv


def get_tennis_leagues():
    """Fetch current tennis leagues from MaxBet"""
    url = "https://www.maxbet.rs/restapi/offer/sr/categories/sport/T/l"
    
    params = {
        "annex": "3",
        "desktopVersion": "1.2.1.10",
        "locale": "sr"
    }
    
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Origin": "https://www.maxbet.rs",
        "Referer": "https://www.maxbet.rs/betting",
        "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            leagues = {}
            
            for category in data.get('categories', []):
                league_id = category.get('id')
                league_name = category.get('name')
                if league_id and league_name:
                    # Use league name as key and ID as value
                    leagues[league_name.lower().replace(" ", "_")] = league_id
            
            return leagues
        else:
            print(f"Failed to fetch leagues with status code: {response.status_code}")
            return {}

    except Exception as e:
        print(f"Error fetching leagues: {str(e)}")
        return {}


def fetch_maxbet_tennis_matches():
    # Get leagues dynamically instead of using hardcoded TENNIS_LEAGUES
    tennis_leagues = get_tennis_leagues()
    
    if not tennis_leagues:
        print("No leagues found or error occurred while fetching leagues")
        return []

    # First collect all match IDs
    match_ids = []
    params = {"annex": "3", "desktopVersion": "1.2.1.10", "locale": "sr"}
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Origin": "https://www.maxbet.rs",
        "Referer": "https://www.maxbet.rs/betting",
        "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }

    for league_name, league_id in tennis_leagues.items():
        url = f"https://www.maxbet.rs/restapi/offer/sr/sport/T/league/{league_id}/mob"

        try:
            response = requests.get(url, params=params, headers=headers)

            if response.status_code == 200:
                data = response.json()

                if "esMatches" in data:
                    for match in data["esMatches"]:
                        match_ids.append(match["id"])
            else:
                print(f"Failed to fetch {league_name} with status code: {response.status_code}")

        except Exception as e:
            print(f"Error fetching {league_name}: {str(e)}")
            continue

    # Now process each match individually
    matches_odds = []

    for match_id in match_ids:
        match_url = f"https://www.maxbet.rs/restapi/offer/sr/match/{match_id}"
        try:
            response = requests.get(match_url, params=params, headers=headers)
            if response.status_code == 200:
                match_data = response.json()

                home_team = match_data.get("home", "")
                away_team = match_data.get("away", "")
                odds = match_data.get("odds", {})

                # Match Winner odds (1-2)
                home_win = odds.get("1", "")  # Player 1 win
                away_win = odds.get("3", "")  # Player 2 win

                if home_win and away_win:
                    matches_odds.append(
                        {
                            "homeTeam": home_team,
                            "awayTeam": away_team,
                            "market": "12",
                            "odd1": home_win,
                            "oddX": away_win,
                            "odd2": "",
                        }
                    )

                # First Set Winner odds
                first_set_home = odds.get("50510", "")  # First set player 1 win
                first_set_away = odds.get("50511", "")  # First set player 2 win

                if first_set_home and first_set_away:
                    matches_odds.append(
                        {
                            "homeTeam": home_team,
                            "awayTeam": away_team,
                            "market": "12set1",
                            "odd1": first_set_home,
                            "oddX": first_set_away,
                            "odd2": "",
                        }
                    )

            else:
                print(f"Failed to fetch match ID {match_id}: {response.status_code}")
        except Exception as e:
            print(f"Error fetching match ID {match_id}: {str(e)}")
            continue

    # Save to CSV
    if matches_odds:
        with open("maxbet_tennis_matches.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["homeTeam", "awayTeam", "market", "odd1", "oddX", "odd2"])
            writer.writerows(matches_odds)
    else:
        print("No tennis odds data to save")

    return matches_odds


if __name__ == "__main__":
    fetch_maxbet_tennis_matches()
