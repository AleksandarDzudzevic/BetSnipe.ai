from datetime import datetime, timedelta
from fuzzywuzzy import fuzz
import itertools
from database_utils import get_db_connection
import csv
from decimal import Decimal
import time
import asyncio
from async_run import run_full_scrape  # Import the correct function


def get_all_matches():
    # Connect to the database using database_utils
    conn = get_db_connection()
    cursor = conn.cursor()

    # Select all records from AllMatches table
    cursor.execute("SELECT * FROM AllMatches")
    matches_list = cursor.fetchall()

    conn.close()
    return matches_list


    """
    Groups matches with similar team names using fuzzy string matching.
    Groups by unique bookmaker and consolidates different bet types.
    Matches are considered the same if they occur on the same day.

    Args:
        matches_list: List of matches from database
        similarity_threshold: Minimum similarity score to consider matches as same (default 85)

    Returns:
        List of grouped matches with their available bet types
    """

    def same_day(time1, time2):
        """Check if two datetime objects are on the same day"""
        return (
            time1.year == time2.year
            and time1.month == time2.month
            and time1.day == time2.day
        )

    grouped_matches = []
    processed_indices = set()

    for i, match1 in enumerate(matches_list):
        if i in processed_indices:
            continue

        team1_1, team2_1 = match1[1], match1[2]
        start_time1 = match1[-1]

        current_group = {"matches": [], "bet_types": set()}

        current_group["matches"].append(match1)
        current_group["bet_types"].add((match1[4], match1[5]))
        processed_indices.add(i)

        for j, match2 in enumerate(matches_list[i + 1 :], start=i + 1):
            if j in processed_indices:
                continue

            team1_2, team2_2 = match2[1], match2[2]
            start_time2 = match2[-1]

            similarity1 = (
                fuzz.ratio(team1_1.lower(), team1_2.lower())
                + fuzz.ratio(team2_1.lower(), team2_2.lower())
            ) / 2

            similarity2 = (
                fuzz.ratio(team1_1.lower(), team2_2.lower())
                + fuzz.ratio(team2_1.lower(), team1_2.lower())
            ) / 2

            if max(similarity1, similarity2) >= similarity_threshold and same_day(
                start_time1, start_time2
            ):
                bookmaker_ids = {match[3] for match in current_group["matches"]}
                if match2[3] not in bookmaker_ids:
                    current_group["matches"].append(match2)
                current_group["bet_types"].add((match2[4], match2[5]))
                processed_indices.add(j)

        if len(current_group["matches"]) > 1:
            grouped_matches.append(current_group)

    return grouped_matches


def calculate_two_way_arbitrage(odds1, odds2):
    """Calculate if arbitrage exists between two odds and return stake distribution"""
    try:
        odds1, odds2 = float(odds1), float(odds2)
        prob1 = 1 / odds1
        prob2 = 1 / odds2
        total_prob = prob1 + prob2

        if total_prob < 1:  # FIXED: Arbitrage exists when total probability is less than 1
            stake1 = (1 / total_prob) * prob1 * 100
            stake2 = (1 / total_prob) * prob2 * 100
            profit_percentage = ((1 / total_prob) - 1) * 100
            return True, stake1, stake2, profit_percentage
        return False, 0, 0, 0
    except (ValueError, ZeroDivisionError):
        return False, 0, 0, 0

def calculate_three_way_arbitrage(odds1, odds2, odds3):
    """Calculate if three-way arbitrage exists between odds"""
    try:
        odds1, odds2, odds3 = float(odds1), float(odds2), float(odds3)
        prob1 = 1 / odds1
        prob2 = 1 / odds2
        prob3 = 1 / odds3
        total_prob = prob1 + prob2 + prob3

        if total_prob < 1:  # FIXED: Arbitrage exists when total probability is less than 1
            stake1 = (1 / total_prob) * prob1 * 100
            stake2 = (1 / total_prob) * prob2 * 100
            stake3 = (1 / total_prob) * prob3 * 100
            profit_percentage = ((1 / total_prob) - 1) * 100
            return True, stake1, stake2, stake3, profit_percentage
        return False, 0, 0, 0, 0
    except (ValueError, ZeroDivisionError):
        return False, 0, 0, 0, 0

def find_arbitrage_opportunities(matches_list, similarity_threshold=85):
    print(f"Total matches to process: {len(matches_list)}")
    
    processed_matches = []
    for match in matches_list:
        match = list(match)
        match[7] = float(match[7]) if match[7] else 0  # odd1
        match[8] = float(match[8]) if match[8] else 0  # odd2
        match[9] = float(match[9]) if match[9] else 0  # odd3
        
        if isinstance(match[-1], str):
            match[-1] = datetime.strptime(match[-1], '%Y-%m-%d %H:%M:%S.%f')
            
        processed_matches.append(match)
    
    matches_list = sorted(processed_matches, key=lambda x: x[-1])
    
    def same_time(time1, time2, tolerance_minutes=60):
        time_diff = abs((time1 - time2).total_seconds() / 60)
        return time_diff <= tolerance_minutes

    def is_same_bet_type(type1, type2):
        """
        Strictly compare bet types - they must be exactly the same
        For example: 12 (match winner) ≠ 12set1 (first set winner)
        """
        return type1 == type2

    arbitrage_opportunities = []
    processed_indices = set()
    groups_found = 0

    for i, match1 in enumerate(matches_list):
        if i in processed_indices:
            continue

        team1_1, team2_1 = match1[1].lower(), match1[2].lower()
        start_time1 = match1[-1]
        bet_type1 = match1[5]
        sport_id1 = match1[4]
        margin1 = match1[6]

        current_group = {
            "matches": [match1],
            "bookmakers": {match1[3]},
            "bet_type": bet_type1,
            "sport_id": sport_id1,
            "margin": margin1
        }
        processed_indices.add(i)

        # Find matching events
        for j, match2 in enumerate(matches_list[i + 1:], start=i + 1):
            if j in processed_indices:
                continue

            # Strict matching criteria
            if (not is_same_bet_type(match2[5], bet_type1) or  # Exact same bet type
                match2[4] != sport_id1 or                       # Same sport
                match2[3] in current_group["bookmakers"] or     # Different bookmaker
                match2[6] != margin1 or                         # Exact same margin
                not same_time(start_time1, match2[-1])):       # Similar time
                continue

            team1_2, team2_2 = match2[1].lower(), match2[2].lower()
            
            # Try exact match first
            if ((team1_1 in team1_2 or team1_2 in team1_1) and 
                (team2_1 in team2_2 or team2_2 in team2_1)):
                current_group["matches"].append(match2)
                current_group["bookmakers"].add(match2[3])
                processed_indices.add(j)
                continue

            # If no exact match, try fuzzy matching
            similarity1 = (fuzz.ratio(team1_1, team1_2) + fuzz.ratio(team2_1, team2_2)) / 2
            similarity2 = (fuzz.ratio(team1_1, team2_2) + fuzz.ratio(team2_1, team1_2)) / 2
            
            if max(similarity1, similarity2) >= similarity_threshold:
                current_group["matches"].append(match2)
                current_group["bookmakers"].add(match2[3])
                processed_indices.add(j)

        # Check for arbitrage if we have enough matches
        if len(current_group["matches"]) >= 2:
            groups_found += 1
            is_three_way = bet_type1 in [2, 3, 4]  # 1X2 markets
            
            print(f"\nFound group {groups_found}:")
            print(f"Teams: {team1_1} vs {team2_1}")
            print(f"Sport ID: {sport_id1}")
            print(f"Bet type ID: {bet_type1}")
            print(f"Margin: {margin1}")
            print(f"Number of matches: {len(current_group['matches'])}")
            
            best_odds = [0, 0, 0] if is_three_way else [0, 0]
            best_bookies = [None, None, None] if is_three_way else [None, None]

            print("Odds in group:")
            for match in current_group["matches"]:
                print(f"Bookmaker {match[3]}: {match[7]}, {match[8]}, {match[9] if is_three_way else ''}")
                
                if is_three_way:
                    odds = [match[7], match[8], match[9]]
                else:
                    odds = [match[7], match[8]]

                for idx, odd in enumerate(odds):
                    if odd > best_odds[idx]:
                        best_odds[idx] = odd
                        best_bookies[idx] = match[3]

            print(f"Best odds found: {best_odds}")
            print(f"From bookmakers: {best_bookies}")

            if is_three_way and all(odd > 0 for odd in best_odds):
                arb_exists, stake1, stake2, stake3, profit = calculate_three_way_arbitrage(*best_odds)
                print(f"3-way arbitrage check: exists={arb_exists}, profit={profit if arb_exists else 0}%")
                if arb_exists and profit > 0:
                    arbitrage_opportunities.append({
                        "type": "3-way",
                        "teams": (match1[1], match1[2]),
                        "time": start_time1,
                        "matches": current_group["matches"],
                        "odds": list(zip(best_odds, best_bookies)),
                        "stakes": (stake1, stake2, stake3),
                        "profit": profit,
                        "bet_type": bet_type1,
                        "sport_id": sport_id1,
                        "margin": margin1
                    })
            elif not is_three_way and all(odd > 0 for odd in best_odds[:2]):  # Only check first two odds for 2-way
                arb_exists, stake1, stake2, profit = calculate_two_way_arbitrage(*best_odds[:2])
                print(f"2-way arbitrage check: exists={arb_exists}, profit={profit if arb_exists else 0}%")
                if arb_exists and profit > 0:
                    arbitrage_opportunities.append({
                        "type": "2-way",
                        "teams": (match1[1], match1[2]),
                        "time": start_time1,
                        "matches": current_group["matches"],
                        "odds": list(zip(best_odds[:2], best_bookies[:2])),
                        "stakes": (stake1, stake2),
                        "profit": profit,
                        "bet_type": bet_type1,
                        "sport_id": sport_id1,
                        "margin": margin1
                    })

    print(f"\nTotal groups found: {groups_found}")
    print(f"Found {len(arbitrage_opportunities)} arbitrage opportunities")
    
    return arbitrage_opportunities

def get_reference_data():
    """Fetch reference data from database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get sports
    cursor.execute("SELECT id, name FROM Sport")
    sports = {row[0]: row[1] for row in cursor.fetchall()}
    
    # Get bookmakers
    cursor.execute("SELECT id, name FROM Bookmaker")
    bookmakers = {row[0]: row[1] for row in cursor.fetchall()}
    
    # Get bet types
    cursor.execute("SELECT id, name FROM BetType")
    bet_types = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    return sports, bookmakers, bet_types

def main():
    while True:  # Infinite loop
        try:
            print("\n" + "="*50)
            print(f"Starting new scan at {datetime.now()}")
            
            # First run async_run
            print("Running async scraping...")
            asyncio.run(run_full_scrape())
            print("Scraping completed")

            # Then process matches for arbitrage
            print("Processing matches for arbitrage...")
            matches = get_all_matches()
            sports, bookmakers, bet_types = get_reference_data()
            
            # Find arbitrage opportunities
            opportunities = find_arbitrage_opportunities(matches)
            
            # Read existing opportunities to avoid duplicates
            existing_opportunities = set()
            try:
                with open('arbitrage_opportunities.txt', 'r', encoding='utf-8') as f:
                    current_opp = {}
                    for line in f:
                        if line.startswith("Teams:"):
                            current_opp['teams'] = line.strip().replace("Teams: ", "")
                        elif line.startswith("Time:"):
                            current_opp['time'] = line.strip().replace("Time: ", "")
                        elif line.startswith("Sport:"):
                            current_opp['sport'] = line.strip().replace("Sport: ", "").split(" (ID:")[0]
                        elif line.startswith("Bet Type:"):
                            current_opp['bet_type'] = line.strip().replace("Bet Type: ", "").split(" (ID:")[0]
                        elif line.startswith("Margin:"):
                            current_opp['margin'] = float(line.strip().replace("Margin: ", ""))
                        elif line.startswith("Best odds:"):
                            current_opp['odds_started'] = True
                            current_opp['odds'] = []
                        elif line.startswith("Outcome ") and 'odds_started' in current_opp:
                            odd = float(line.split(": ")[1].split(" ")[0])
                            current_opp['odds'].append(odd)
                        elif line.startswith("--"):
                            if 'odds_started' in current_opp:
                                key = (
                                    current_opp['teams'],
                                    current_opp['time'],
                                    current_opp['sport'],
                                    current_opp['bet_type'],
                                    current_opp['margin'],
                                    tuple(current_opp['odds'])
                                )
                                existing_opportunities.add(key)
                            current_opp = {}
            except FileNotFoundError:
                pass  # File doesn't exist yet

            # Filter out duplicate opportunities
            new_opportunities = []
            for opp in opportunities:
                key = (
                    f"{opp['teams'][0]} vs {opp['teams'][1]}",
                    opp['time'].strftime("%Y-%m-%d %H:%M:%S"),
                    sports.get(opp['sport_id'], 'Unknown'),
                    bet_types.get(opp['bet_type'], 'Unknown'),
                    float(opp['margin']),
                    tuple(odd for odd, _ in opp['odds'])
                )
                if key not in existing_opportunities:
                    new_opportunities.append(opp)
                    existing_opportunities.add(key)

            # Append only new opportunities to file
            if new_opportunities:
                with open('arbitrage_opportunities.txt', 'a', encoding='utf-8') as f:
                    f.write(f"\n\nScan Time: {datetime.now()}\n")
                    f.write("="*50 + "\n")
                    
                    for opp in new_opportunities:
                        f.write(f"\nArbitrage Opportunity ({opp['type']}):\n")
                        f.write(f"Teams: {opp['teams'][0]} vs {opp['teams'][1]}\n")
                        f.write(f"Time: {opp['time']}\n")
                        f.write(f"Sport: {sports.get(opp['sport_id'], 'Unknown')} (ID: {opp['sport_id']})\n")
                        f.write(f"Bet Type: {bet_types.get(opp['bet_type'], 'Unknown')} (ID: {opp['bet_type']})\n")
                        f.write(f"Margin: {opp['margin']}\n")
                        f.write("Best odds:\n")
                        for i, (odd, bookie) in enumerate(opp['odds'], 1):
                            f.write(f"Outcome {i}: {odd:.2f} ({bookmakers.get(bookie, f'Bookmaker {bookie}')} ID: {bookie})\n")
                        f.write(f"Recommended stakes: {[f'{stake:.2f}%' for stake in opp['stakes']]}\n")
                        f.write(f"Potential profit: {opp['profit']:.2f}%\n")
                        f.write("-" * 50 + "\n")

            print(f"Found {len(opportunities)} arbitrage opportunities")
            print(f"Wrote {len(new_opportunities)} new opportunities to file")
            print("Waiting 60 seconds before next scan...")
            time.sleep(2)  # Wait 60 seconds before next iteration
            
        except Exception as e:
            print(f"Error occurred: {str(e)}")
            print("Waiting 60 seconds before retry...")
            time.sleep(60)  # Wait 60 seconds before retry on error

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram stopped by user")