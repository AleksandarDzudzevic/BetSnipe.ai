import requests
import csv


def get_hockey_leagues():
    """Fetch current hockey leagues from MaxBet"""
    url = "https://www.maxbet.rs/restapi/offer/sr/categories/sport/H/l"

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
        "sec-ch-ua-platform": '"Windows"',
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            leagues = {}

            for category in data.get("categories", []):
                league_id = category.get("id")
                league_name = category.get("name")
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


def fetch_maxbet_hockey_matches():
    # Get leagues dynamically instead of using hardcoded HOCKEY_LEAGUES
    hockey_leagues = get_hockey_leagues()

    if not hockey_leagues:
        print("No leagues found or error occurred while fetching leagues")
        return []

    matches_odds = []

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
        "sec-ch-ua-platform": '"Windows"',
    }

    for league_name, league_id in hockey_leagues.items():
        url = f"https://www.maxbet.rs/restapi/offer/sr/sport/H/league/{league_id}/mob"

        try:
            response = requests.get(url, params=params, headers=headers)

            if response.status_code == 200:
                data = response.json()

                if "esMatches" in data:
                    for match in data["esMatches"]:
                        home_team = match.get("home", "")
                        away_team = match.get("away", "")
                        odds = match.get("odds", {})

                        # 1X2 odds
                        home_win = odds.get("1", "")  # Home win (1)
                        draw = odds.get("2", "")  # Draw (X)
                        away_win = odds.get("3", "")  # Away win (2)

                        if home_win and draw and away_win:
                            matches_odds.append(
                                {
                                    "team1": home_team,
                                    "team2": away_team,
                                    "odd1": home_win,
                                    "oddX": draw,
                                    "odd2": away_win,
                                }
                            )

            else:
                print(
                    f"Failed to fetch {league_name} with status code: {response.status_code}"
                )

        except Exception as e:
            print(f"Error fetching {league_name}: {str(e)}")
            continue

    # Save to CSV
    if matches_odds:
        with open("maxbet_hockey_matches.csv", "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["team1", "team2", "odd1", "oddX", "odd2"]
            )
            writer.writerows(matches_odds)
    else:
        print("No hockey odds data to save")

    return matches_odds


if __name__ == "__main__":
    fetch_maxbet_hockey_matches()
