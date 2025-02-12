import requests
import json
from bs4 import BeautifulSoup
import csv

DESIRED_LEAGUES = {
    ("Premier Liga", "Engleska"),
    ("Championship", "Engleska"),
    ("La Liga", "Španija"),
    ("La Liga 2", "Španija"),
    ("Bundesliga", "Nemačka"),
    ("2. Bundesliga", "Nemačka"),
    ("Serija A", "Italija"),
    ("Serija B", "Italija"),
    ("Liga 1", "Francuska"),
    ("Liga 2", "Francuska"),
    ("Liga Profesional", "Argentina"),
    ("A-Liga", "Australija"),
    ("Paulista Serija A", "Brazil"),
    ("Prva Liga Eredivisie", "Holandija"),
    ("Prva Divizija A", "Belgija"),
    ("Prva Divizija", "Saudijska Arabija"),
    ("Superliga", "Grčka"),
    ("Super Liga", "Turska"),
    "UEFA Liga Šampiona",
    "UEFA Liga Evrope",
    "UEFA Liga Konferencija",
}


def get_auth_token():
    try:
        session = requests.Session()
        main_url = "https://meridianbet.rs/sr/kladjenje/fudbal"

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "sr",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }

        response = session.get(main_url, headers=headers)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for script in soup.find_all("script"):
                if script.string and "NEW_TOKEN" in script.string:
                    try:
                        json_data = json.loads(script.string)
                        if "NEW_TOKEN" in json_data:
                            token_data = json.loads(json_data["NEW_TOKEN"])
                            if "access_token" in token_data:
                                return token_data["access_token"]
                    except json.JSONDecodeError:
                        continue

    except Exception:
        return None
    return None


def get_markets_for_event(event_id, token):
    url = f"https://online.meridianbet.com/betshop/api/v2/events/{event_id}/markets"

    headers = {
        "Accept": "application/json",
        "Accept-Language": "sr",
        "Authorization": f"Bearer {token}",
        "Origin": "https://meridianbet.rs",
        "Referer": "https://meridianbet.rs/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }

    params = {"gameGroupId": "all"}

    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            return data.get("payload", [])  # Return the payload array directly
    except Exception:
        pass
    return None


def get_soccer_odds():
    token = get_auth_token()
    if not token:
        return []

    url = "https://online.meridianbet.com/betshop/api/v1/standard/sport/58/leagues"
    headers = {
        "Accept": "application/json",
        "Accept-Language": "sr",
        "Authorization": f"Bearer {token}",
        "Origin": "https://meridianbet.rs",
        "Referer": "https://meridianbet.rs/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }

    matches_data = []
    page = 0

    while True:
        try:
            response = requests.get(
                url,
                params={"page": str(page), "time": "ALL", "groupIndices": "0,0,0"},
                headers=headers,
            )
            if response.status_code != 200:
                break

            data = response.json()
            if "payload" not in data or "leagues" not in data["payload"]:
                break

            leagues = data["payload"]["leagues"]
            if not leagues:
                break

            for league in leagues:
                league_name = league.get("leagueName")
                region_name = league.get("regionName", "")
                is_desired = (
                    league_name in ["UEFA Liga Šampiona", "UEFA Liga Evrope"]
                    or (league_name, region_name) in DESIRED_LEAGUES
                )

                if is_desired:
                    events = league.get("events", [])
                    for event in events:
                        event_id = event.get("header", {}).get("eventId")
                        rivals = event.get("header", {}).get("rivals", [])

                        if event_id and len(rivals) >= 2:
                            market_data = get_markets_for_event(event_id, token)
                            if market_data:
                                team1, team2 = rivals[0], rivals[1]
                                odds_1x2 = None
                                odds_ggng = None
                                odds_1x2f = None
                                odds_1x2s = None
                                odds_ou = []
                                odds_fht = []  # First Half Total
                                odds_sht = []  # Second Half Total

                                for market_group in market_data:
                                    market_name = market_group.get("marketName")
                                    if market_name == "Konačan Ishod":
                                        for market in market_group.get("markets", []):
                                            selections = market.get("selections", [])
                                            if len(selections) >= 3:
                                                odds_1x2 = {
                                                    "team1": team1,
                                                    "team2": team2,
                                                    "marketType": "1X2",
                                                    "odd1": selections[0].get("price"),
                                                    "oddX": selections[1].get("price"),
                                                    "odd2": selections[2].get("price"),
                                                }

                                    elif market_name == "I Pol. Konačan Ishod":
                                        for market in market_group.get("markets", []):
                                            selections = market.get("selections", [])
                                            if len(selections) >= 3:
                                                odds_1x2f = {
                                                    "team1": team1,
                                                    "team2": team2,
                                                    "marketType": "1X2F",
                                                    "odd1": selections[0].get("price"),
                                                    "oddX": selections[1].get("price"),
                                                    "odd2": selections[2].get("price"),
                                                }

                                    elif market_name == "II Pol. Konačan Ishod":
                                        for market in market_group.get("markets", []):
                                            selections = market.get("selections", [])
                                            if len(selections) >= 3:
                                                odds_1x2s = {
                                                    "team1": team1,
                                                    "team2": team2,
                                                    "marketType": "1X2S",
                                                    "odd1": selections[0].get("price"),
                                                    "oddX": selections[1].get("price"),
                                                    "odd2": selections[2].get("price"),
                                                }

                                    elif market_name == "Oba Tima Daju Gol":
                                        for market in market_group.get("markets", []):
                                            selections = market.get("selections", [])
                                            gg = next(
                                                (
                                                    s.get("price")
                                                    for s in selections
                                                    if s.get("name") == "GG"
                                                ),
                                                None,
                                            )
                                            ng = next(
                                                (
                                                    s.get("price")
                                                    for s in selections
                                                    if s.get("name") == "NG"
                                                ),
                                                None,
                                            )
                                            if gg and ng:
                                                odds_ggng = {
                                                    "team1": team1,
                                                    "team2": team2,
                                                    "marketType": "GGNG",
                                                    "odd1": gg,
                                                    "odd2": ng,
                                                }

                                    elif market_name == "Ukupno":
                                        for market in market_group.get("markets", []):
                                            over_under = market.get("overUnder")
                                            selections = market.get("selections", [])
                                            if over_under and len(selections) >= 2:
                                                odds_ou.append(
                                                    {
                                                        "team1": team1,
                                                        "team2": team2,
                                                        "marketType": f"{over_under}",
                                                        "odd1": selections[0].get(
                                                            "price"
                                                        ),  # Over
                                                        "odd2": selections[1].get(
                                                            "price"
                                                        ),  # Under
                                                    }
                                                )
                                    elif market_name == "I Pol. Ukupno":
                                        for market in market_group.get("markets", []):
                                            over_under = market.get("overUnder")
                                            selections = market.get("selections", [])
                                            if over_under and len(selections) >= 2:
                                                odds_fht.append(
                                                    {
                                                        "team1": team1,
                                                        "team2": team2,
                                                        "marketType": f"{over_under}F",
                                                        "odd1": selections[0].get(
                                                            "price"
                                                        ),  # Under
                                                        "odd2": selections[1].get(
                                                            "price"
                                                        ),  # Over
                                                    }
                                                )
                                    elif market_name == "II Pol. Ukupno":
                                        for market in market_group.get("markets", []):
                                            over_under = market.get("overUnder")
                                            selections = market.get("selections", [])
                                            if over_under and len(selections) >= 2:
                                                odds_sht.append(
                                                    {
                                                        "team1": team1,
                                                        "team2": team2,
                                                        "marketType": f"{over_under}S",
                                                        "odd1": selections[0].get(
                                                            "price"
                                                        ),  # Under
                                                        "odd2": selections[1].get(
                                                            "price"
                                                        ),  # Over
                                                    }
                                                )

                                if odds_1x2:
                                    matches_data.append(odds_1x2)
                                if odds_1x2f:
                                    matches_data.append(odds_1x2f)
                                if odds_1x2s:
                                    matches_data.append(odds_1x2s)
                                if odds_ggng:
                                    matches_data.append(odds_ggng)
                                matches_data.extend(odds_ou)
                                matches_data.extend(odds_fht)  # Add first half totals
                                matches_data.extend(odds_sht)  # Add second half totals

            page += 1

        except Exception:
            break

    with open("meridian_football_matches.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for match in matches_data:
            # Get first long word from each team name
            if match["marketType"] in ["1X2", "1X2F", "1X2S"]:
                writer.writerow(
                    [
                        match["team1"],
                        match["team2"],
                        match["marketType"],
                        match["odd1"],
                        match["oddX"],
                        match["odd2"],
                    ]
                )
            else:  # GGNG and OU markets
                writer.writerow(
                    [
                        match["team1"],
                        match["team2"],
                        match["marketType"],
                        match["odd1"],
                        match["odd2"],
                    ]
                )

    return matches_data


if __name__ == "__main__":
    get_soccer_odds()
