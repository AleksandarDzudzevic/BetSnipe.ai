import requests
import json
from bs4 import BeautifulSoup
from datetime import datetime
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, batch_insert_matches
import aiohttp
import asyncio


def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""


def get_auth_token():
    try:
        main_url = "https://meridianbet.rs/sr/kladjenje/fudbal"
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "sr",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }

        response = requests.get(main_url, headers=headers)
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


async def get_markets_for_event(session, event_id, token):
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
        # Add timeout and retry logic
        for attempt in range(3):  # Try up to 3 times
            try:
                async with session.get(url, headers=headers, params=params, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("payload", [])
                    elif response.status == 429:  # Too Many Requests
                        await asyncio.sleep(0.5)  # Wait before retry
                        continue
                    else:
                        break
            except asyncio.TimeoutError:
                if attempt == 2:  # Last attempt
                    print(f"Timeout fetching markets for event {event_id}")
                await asyncio.sleep(0.5)  # Wait before retry
            except Exception as e:
                print(f"Error fetching markets for event {event_id}: {e}")
                break
    except Exception as e:
        print(f"Outer error for event {event_id}: {e}")
    return None


async def get_soccer_odds():
    token = get_auth_token()
    if not token:
        return []

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
        matches_data = []
        matches_to_insert = []
        page = 0

        while True:
            try:
                url = "https://online.meridianbet.com/betshop/api/v1/standard/sport/58/leagues"
                headers = {
                    "Accept": "application/json",
                    "Accept-Language": "sr",
                    "Authorization": f"Bearer {token}",
                    "Origin": "https://meridianbet.rs",
                    "Referer": "https://meridianbet.rs/",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                }

                async with session.get(
                    url,
                    params={"page": str(page), "time": "ALL", "groupIndices": "0,0,0"},
                    headers=headers,
                ) as response:
                    if response.status != 200:
                        break

                    data = await response.json()
                    if "payload" not in data or "leagues" not in data["payload"]:
                        break

                    leagues = data["payload"]["leagues"]
                    if not leagues:
                        break

                    # Create tasks for fetching market data for all events
                    market_tasks = []
                    for league in leagues:
                        events = league.get("events", [])
                        for event in events:
                            event_id = event.get("header", {}).get("eventId")
                            if event_id:
                                task = asyncio.create_task(get_markets_for_event(session, event_id, token))
                                market_tasks.append((event, task))

                    # Process all tasks
                    for event, task in market_tasks:
                        market_data = await task
                        if market_data:
                            rivals = event.get("header", {}).get("rivals", [])
                            start_time = convert_unix_to_iso(event.get("header", {}).get("startTime", 0))
                            
                            if len(rivals) >= 2:
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

                                    elif market_name == "Ukupno Golova":
                                        for market in market_group.get("markets", []):
                                            over_under = market.get("overUnder")
                                            selections = market.get("selections", [])
                                            if over_under and len(selections) >= 2:
                                                odds_ou.append(
                                                    {
                                                        "team1": team1,
                                                        "team2": team2,
                                                        "marketType": f"TG{over_under}",
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
                                                        "marketType": f"TG{over_under}F",
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
                                                        "marketType": f"TG{over_under}S",
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
                                    matches_to_insert.append((
                                        odds_1x2["team1"],
                                        odds_1x2["team2"],
                                        2,  # Meridian
                                        1,  # Football
                                        2,  # 1X2
                                        0,  # No margin
                                        float(odds_1x2["odd1"]),
                                        float(odds_1x2["oddX"]),
                                        float(odds_1x2["odd2"]),
                                        start_time
                                    ))

                                if odds_1x2f:
                                    matches_data.append(odds_1x2f)
                                    matches_to_insert.append((
                                        odds_1x2f["team1"],
                                        odds_1x2f["team2"],
                                        2,  # Meridian
                                        1,  # Football
                                        3,  # First Half 1X2
                                        0,  # No margin
                                        float(odds_1x2f["odd1"]),
                                        float(odds_1x2f["oddX"]),
                                        float(odds_1x2f["odd2"]),
                                        start_time
                                    ))

                                if odds_1x2s:
                                    matches_data.append(odds_1x2s)
                                    matches_to_insert.append((
                                        odds_1x2s["team1"],
                                        odds_1x2s["team2"],
                                        2,  # Meridian
                                        1,  # Football
                                        4,  # Second Half 1X2
                                        0,  # No margin
                                        float(odds_1x2s["odd1"]),
                                        float(odds_1x2s["oddX"]),
                                        float(odds_1x2s["odd2"]),
                                        start_time
                                    ))

                                if odds_ggng:
                                    matches_data.append(odds_ggng)
                                    matches_to_insert.append((
                                        odds_ggng["team1"],
                                        odds_ggng["team2"],
                                        2,  # Meridian
                                        1,  # Football
                                        8,  # GGNG
                                        0,  # No margin
                                        float(odds_ggng["odd1"]),
                                        float(odds_ggng["odd2"]),
                                        0,  # No third odd
                                        start_time
                                    ))

                                for ou in odds_ou:
                                    matches_data.append(ou)
                                    matches_to_insert.append((
                                        ou["team1"],
                                        ou["team2"],
                                        2,  # Meridian
                                        1,  # Football
                                        5,  # Total Goals
                                        float(ou["marketType"][2:]),  # Extract goals number
                                        float(ou["odd1"]),
                                        float(ou["odd2"]),
                                        0,  # No third odd
                                        start_time
                                    ))

                                for fht in odds_fht:
                                    matches_data.append(fht)
                                    matches_to_insert.append((
                                        fht["team1"],
                                        fht["team2"],
                                        2,  # Meridian
                                        1,  # Football
                                        6,  # First Half Total
                                        float(fht["marketType"][2:-1]),  # Extract goals number
                                        float(fht["odd1"]),
                                        float(fht["odd2"]),
                                        0,  # No third odd
                                        start_time
                                    ))

                                for sht in odds_sht:
                                    matches_data.append(sht)
                                    matches_to_insert.append((
                                        sht["team1"],
                                        sht["team2"],
                                        2,  # Meridian
                                        1,  # Football
                                        7,  # Second Half Total
                                        float(sht["marketType"][2:-1]),  # Extract goals number
                                        float(sht["odd1"]),
                                        float(sht["odd2"]),
                                        0,  # No third odd
                                        start_time
                                    ))

                    page += 1

            except Exception as e:
                print(f"Error occurred: {e}")
                break

        try:
            conn = get_db_connection()
            batch_insert_matches(conn, matches_to_insert)
            conn.close()
        except Exception as e:
            print(f"Database error: {e}")

        return matches_data


if __name__ == "__main__":
    asyncio.run(get_soccer_odds())