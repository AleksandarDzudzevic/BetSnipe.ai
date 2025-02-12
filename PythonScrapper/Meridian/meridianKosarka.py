import requests
import json
from bs4 import BeautifulSoup
import csv

DESIRED_LEAGUES = {
    "NBA",
    "NCAA",
    "Evroliga",
    "Evrokup",
    "ABA Liga",  # ABA League
    "ACB Liga",  # Spain
    "BBL Liga",  # Germany
    "LNB Pro A",  # France
    "A1 Liga",  # Greece
    "Lega A",  # Italy
}


def get_auth_token():
    try:
        session = requests.Session()
        main_url = "https://meridianbet.rs/sr/kladjenje/kosarka"
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
            return data.get("payload", [])
    except Exception:
        pass
    return None


def get_basketball_odds():
    token = get_auth_token()
    if not token:
        return []

    url = "https://online.meridianbet.com/betshop/api/v1/standard/sport/55/leagues"
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
                url, params={"page": str(page), "time": "ALL"}, headers=headers
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
                league_name = league.get("leagueName", "")
                if any(desired in league_name for desired in DESIRED_LEAGUES):
                    events = league.get("events", [])
                    for event in events:
                        event_id = event.get("header", {}).get("eventId")
                        rivals = event.get("header", {}).get("rivals", [])

                        if event_id and len(rivals) >= 2:
                            market_data = get_markets_for_event(event_id, token)
                            if market_data:
                                team1, team2 = rivals[0], rivals[1]
                                odds_12 = None
                                odds_total = []  # For different total lines
                                odds_handicap = []  # For different handicap lines

                                for market_group in market_data:
                                    market_name = market_group.get("marketName")
                                    if market_name == "Pobednik (uklj.OT )":
                                        for market in market_group.get("markets", []):
                                            selections = market.get("selections", [])
                                            if len(selections) >= 2:
                                                odds_12 = {
                                                    "team1": team1,
                                                    "team2": team2,
                                                    "marketType": "12",
                                                    "odd1": selections[0].get("price"),
                                                    "odd2": selections[1].get("price"),
                                                }

                                    elif market_name == "Ukupno (uklj.OT) ":
                                        for market in market_group.get("markets", []):
                                            over_under = market.get("overUnder")
                                            selections = market.get("selections", [])
                                            if over_under and len(selections) >= 2:
                                                odds_total.append(
                                                    {
                                                        "team1": team1,
                                                        "team2": team2,
                                                        "marketType": f"{over_under}",
                                                        "odd1": selections[1].get(
                                                            "price"
                                                        ),  # Over
                                                        "odd2": selections[0].get(
                                                            "price"
                                                        ),  # Under
                                                    }
                                                )

                                    elif market_name == "Hendikep (uklj. OT)":
                                        for market in market_group.get("markets", []):
                                            handicap = market.get("handicap")
                                            selections = market.get("selections", [])
                                            if (
                                                handicap is not None
                                                and len(selections) >= 2
                                            ):
                                                odds_handicap.append(
                                                    {
                                                        "team1": team1,
                                                        "team2": team2,
                                                        "marketType": f"H{handicap}",
                                                        "odd1": selections[0].get(
                                                            "price"
                                                        ),  # Home
                                                        "odd2": selections[1].get(
                                                            "price"
                                                        ),  # Away
                                                    }
                                                )

                                if odds_12:
                                    matches_data.append(odds_12)
                                matches_data.extend(odds_total)
                                matches_data.extend(odds_handicap)

            page += 1

        except Exception:
            break

    with open(
        "meridian_basketball_matches.csv", "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.writer(f)
        for match in matches_data:

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
    get_basketball_odds()
