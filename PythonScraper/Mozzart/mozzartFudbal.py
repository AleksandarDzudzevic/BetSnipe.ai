import json
import time
from datetime import datetime
import sys
from pathlib import Path
import asyncio
import aiohttp
from cloudscraper import create_scraper as CF_Solver

sys.path.append(str(Path(__file__).parent.parent))
from database_utils import get_db_connection, insert_match, batch_insert_matches

# Initialize CF_Solver
cf = CF_Solver()

async def get_all_match_ids(session, league_id):
    try:
        url = 'https://www.mozzartbet.com/betting/matches'
        payload = {
            "date": "all_days",
            "type": "all",
            "sportIds": [1],
            "competitionIds": [league_id],
            "pageSize": 100,
            "currentPage": 0
        }
        
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-US,en;q=0.7',
            'Content-Type': 'application/json',
            'Origin': 'https://www.mozzartbet.com',
            'Referer': 'https://www.mozzartbet.com/sr/kladjenje/competitions/1/60?date=all_days',
            'Sec-Ch-Ua': '"Not(A:Brand";v="99", "Brave";v="133", "Chromium";v="133"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'Medium': 'WEB'
        }
        
        async with session.post(url, json=payload, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("items"):
                    return [match["id"] for match in data["items"]]
        return []
    except Exception as e:
        return []

async def get_mozzart_match(session, match_id, league_id):
    try:
        url = f'https://www.mozzartbet.com/match/{match_id}'
        payload = {
            "date": "all_days",
            "type": "all",
            "sportIds": [1],
            "competitionIds": [league_id],
            "pageSize": 100,
            "currentPage": 0
        }
        
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-US,en;q=0.7',
            'Content-Type': 'application/json',
            'Origin': 'https://www.mozzartbet.com',
            'Referer': 'https://www.mozzartbet.com/sr/kladjenje/competitions/1/60?date=all_days',
            'Sec-Ch-Ua': '"Not(A:Brand";v="99", "Brave";v="133", "Chromium";v="133"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'Medium': 'WEB'
        }
        
        for attempt in range(3):
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                        if not data.get("error"):
                            return data
                    except json.JSONDecodeError:
                        pass
            await asyncio.sleep(2)
        return None
    except Exception as e:
        return None

def convert_unix_to_iso(unix_ms):
    """Convert Unix timestamp in milliseconds to ISO format datetime string"""
    try:
        return datetime.fromtimestamp(unix_ms / 1000).isoformat()
    except:
        return ""

async def process_league(session, league_id, league_name, matches_to_insert):
    match_ids = await get_all_match_ids(session, league_id)
    
    if not match_ids:
        return

    # Process matches concurrently with a semaphore to limit concurrent requests
    sem = asyncio.Semaphore(5)  # Limit to 5 concurrent requests
    async def process_match(match_id):
        async with sem:
            match_data = await get_mozzart_match(session, match_id, league_id)
            if match_data and "match" in match_data:
                await process_match_data(match_data, matches_to_insert)

    await asyncio.gather(*[process_match(match_id) for match_id in match_ids])

async def process_match_data(match_data, matches_to_insert):
    match = match_data["match"]
    home_team = match["home"].get("name")
    away_team = match["visitor"].get("name")

    kick_off_time = convert_unix_to_iso(match.get("startTime", 0))

    if "specialMatchGroupId" in match:
        return

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

    # Convert and write full match total goals
    under_odds = {}
    over_odds = {}
    # First handle the under odds
    for subgame_name, odd in total_goals_odds.items():
        if subgame_name.startswith("0-"):  # Under odds
            goals = float(subgame_name.split("-")[1])
            under_odds[goals + 0.5] = odd
        elif subgame_name.endswith("+"):  # Over odds
            goals = float(subgame_name[:-1])
            over_odds[goals - 0.5] = odd

    # Add special case for under 1.5 if we have 0-1
    if "0-1" in total_goals_odds:
        under_odds[1.5] = total_goals_odds["0-1"]

    # Similar conversion for first half totals
    under_odds_first = {}
    over_odds_first = {}
    for subgame_name, odd in total_goals_first.items():
        if subgame_name.startswith("0-"):
            goals = float(subgame_name.split("-")[1])
            under_odds_first[goals + 0.5] = odd
        elif subgame_name.endswith("+"):
            goals = float(subgame_name[:-1])
            over_odds_first[goals - 0.5] = odd

    # Add special cases for first half
    if "0-0" in total_goals_first:
        under_odds_first[0.5] = total_goals_first["0-0"]
    if "0-1" in total_goals_first:
        under_odds_first[1.5] = total_goals_first["0-1"]
    if "1+" in total_goals_first:
        over_odds_first[0.5] = total_goals_first["1+"]

    # Similar conversion for second half totals
    under_odds_second = {}
    over_odds_second = {}
    for subgame_name, odd in total_goals_second.items():
        if subgame_name.startswith("0-"):
            goals = float(subgame_name.split("-")[1])
            under_odds_second[goals + 0.5] = odd
        elif subgame_name.endswith("+"):
            goals = float(subgame_name[:-1])
            over_odds_second[goals - 0.5] = odd

    # Add special cases for second half
    if "0-0" in total_goals_second:
        under_odds_second[0.5] = total_goals_second["0-0"]
    if "0-1" in total_goals_second:
        under_odds_second[1.5] = total_goals_second["0-1"]
    if "1+" in total_goals_second:
        over_odds_second[0.5] = total_goals_second["1+"]

    # Match and insert the over/under pairs for full match
    for total in sorted(set(under_odds.keys()) & set(over_odds.keys())):
        matches_to_insert.append((
            home_team,
            away_team,
            1,              # bookmaker_id
            1,              # sport_id (Football)
            5,              # bet_type_id (Total Goals)
            total,          # margin
            float(under_odds[total]),  # Under odds first
            float(over_odds[total]),   # Over odds second
            0,
            kick_off_time
        ))

    # Match and insert the over/under pairs for first half
    for total in sorted(set(under_odds_first.keys()) & set(over_odds_first.keys())):
        matches_to_insert.append((
            home_team,
            away_team,
            1,              # bookmaker_id
            1,              # sport_id (Football)
            6,              # bet_type_id (Total Goals First Half)
            total,          # margin
            float(under_odds_first[total]),  # Under odds first
            float(over_odds_first[total]),   # Over odds second
            0,
            kick_off_time
        ))

    # Match and insert the over/under pairs for second half
    for total in sorted(set(under_odds_second.keys()) & set(over_odds_second.keys())):
        matches_to_insert.append((
            home_team,
            away_team,
            1,              # bookmaker_id
            1,              # sport_id (Football)
            7,              # bet_type_id (Total Goals Second Half)
            total,          # margin
            float(under_odds_second[total]),  # Under odds first
            float(over_odds_second[total]),   # Over odds second
            0,
            kick_off_time
        ))

    # Insert match winner odds (1X2)
    matches_to_insert.append((
        home_team,
        away_team,
        1,              # bookmaker_id
        1,              # sport_id (Football)
        2,              # bet_type_id (1X2)
        0,              # margin
        float(odds_1x2["1"]),
        float(odds_1x2["X"]),
        float(odds_1x2["2"]),
        kick_off_time
    ))

    # Insert first half odds (1X2F)
    matches_to_insert.append((
        home_team,
        away_team,
        1,              # bookmaker_id
        1,              # sport_id (Football)
        3,              # bet_type_id (1X2F)
        0,              # margin
        float(odds_1x2_first["1"]),
        float(odds_1x2_first["X"]),
        float(odds_1x2_first["2"]),
        kick_off_time
    ))

    # Insert second half odds (1X2S)
    matches_to_insert.append((
        home_team,
        away_team,
        1,              # bookmaker_id
        1,              # sport_id (Football)
        4,              # bet_type_id (1X2S)
        0,              # margin
        float(odds_1x2_second["1"]),
        float(odds_1x2_second["X"]),
        float(odds_1x2_second["2"]),
        kick_off_time
    ))

    # Insert GG/NG odds
    matches_to_insert.append((
        home_team,
        away_team,
        1,              # bookmaker_id
        1,              # sport_id (Football)
        8,              # bet_type_id (GGNG)
        0,              # margin
        float(odds_gg_ng["gg"]),
        float(odds_gg_ng["ng"]),
        0,
        kick_off_time
    ))

async def scrape_all_matches():
    try:
        conn = get_db_connection()
        matches_to_insert = []

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

        async with aiohttp.ClientSession() as session:
            # Process leagues concurrently
            await asyncio.gather(*[
                process_league(session, league_id, league_name, matches_to_insert)
                for league_id, league_name in leagues
            ])

        if matches_to_insert:
            batch_insert_matches(conn, matches_to_insert)
        else:
            print("No matches to insert!")

    except Exception as e:
        print(f"Critical error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    asyncio.run(scrape_all_matches())