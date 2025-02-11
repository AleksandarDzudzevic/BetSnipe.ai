import requests
import json
import csv
import ssl

ssl._create_default_https_context = ssl._create_unverified_context


def process_team_name(name):
    """Process team name to get appropriate word based on singles/doubles"""
    try:
        name = name.strip()
        if "/" in name:  # Doubles match
            # Split partners and get first word from each
            partners = name.split("/")
            names = []
            for partner in partners:
                partner = partner.strip()
                if "," in partner:
                    lastname = partner.split(",")[0].strip()
                    names.append(lastname.split()[0])  # Get first word
                else:
                    names.append(partner.split()[0])  # Get first word
            return names[0]  # Return first player's name
        else:
            # Singles match - get last word
            words = name.split()
            if "," in name:
                lastname = name.split(",")[0].strip()
                return lastname.split()[-1]  # Get last word of lastname
            else:
                return words[-1]  # Get last word
    except Exception as e:
        print(f"Error processing name {name}: {e}")
        return None


def get_table_tennis_leagues():
    """Fetch current table tennis leagues from Soccerbet"""
    url = "https://www.soccerbet.rs/restapi/offer/sr/categories/ext/sport/TT/g"
    
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
    leagues = get_table_tennis_leagues()
    
    if not leagues:
        print("No leagues found or error occurred while fetching leagues")
        return

    all_matches_data = []

    try:
        for league_id, league_name in leagues:
            url = f"https://www.soccerbet.rs/restapi/offer/sr/sport/TT/league-group/{league_id}/mob"
            
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
                        home_team = match["home"]
                        away_team = match["away"]

                        match_name = f"{home_team}, {away_team}"

                        # Get winner odds
                        match_data = [
                            match_name,
                            "12",  # Add Type column
                            match["betMap"]
                            .get("1", {})
                            .get("NULL", {})
                            .get("ov", "N/A"),
                            match["betMap"]
                            .get("3", {})
                            .get("NULL", {})
                            .get("ov", "N/A"),
                            ""  # Empty Odds 3 column
                        ]

                        all_matches_data.append(match_data)

            except Exception as e:
                continue

        # Save to CSV
        if all_matches_data:
            with open("soccerbet_tabletennis_matches.csv", "w", newline="", encoding="utf-8") as f:
                for row in all_matches_data:
                    f.write(f"{row[0]},{row[1]},{row[2]},{row[3]},{row[4]}\n")

    except Exception as e:
        print(f"Error in main execution: {str(e)}")


if __name__ == "__main__":
    get_soccerbet_sports()
