import csv
import os
import pandas as pd
from datetime import datetime
import time
from rapidfuzz import fuzz
import numpy as np
from arbitrage_storage import store_arbitrage
from telegram_utils import send_to_telegram
import asyncio


def get_sport_name(sport_id):
    sports = {
        1: "football",
        2: "basketball",
        3: "tennis",
        4: "hockey",
        5: "table",  # table tennis
    }
    return sports.get(sport_id, "unknown")


def get_bookmaker_name(bookmaker_id):
    bookmakers = {
        1: "mozzart",
        2: "meridianbet",
        3: "maxbet",
        4: "admiral",
        5: "soccerbet",
        #6: "1xbet",
        7: "superbet",
        8: "merkur",
        10: "topbet"
    }
    return bookmakers.get(bookmaker_id, "unknown")


def calculate_two_way_arbitrage(odds1, odds2):
    """Calculate if arbitrage exists between two odds and return stake distribution"""
    try:
        odds1, odds2 = float(odds1), float(odds2)
        prob1 = 1 / odds1
        prob2 = 1 / odds2
        total_prob = prob1 + prob2

        if total_prob < 1:
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

        if total_prob < 1:
            stake1 = (1 / total_prob) * prob1 * 100
            stake2 = (1 / total_prob) * prob2 * 100
            stake3 = (1 / total_prob) * prob3 * 100
            profit_percentage = ((1 / total_prob) - 1) * 100
            return True, stake1, stake2, stake3, profit_percentage
        return False, 0, 0, 0, 0
    except (ValueError, ZeroDivisionError):
        return False, 0, 0, 0, 0


def load_sport_matches(sport_name):
    """Load all CSV files for a specific sport into a single DataFrame"""
    matches_data = []
    csv_dir = "matches_csv"

    for filename in os.listdir(csv_dir):
        if filename.endswith(f"_{sport_name}_matches.csv"):
            file_path = os.path.join(csv_dir, filename)
            df = pd.read_csv(file_path)
            matches_data.append(df)

    if matches_data:
        return pd.concat(matches_data, ignore_index=True)
    return None


async def process_arbitrage(arbitrage_data):
    """Process single arbitrage opportunity"""
    # Extract required data
    teams = f"{arbitrage_data['teams'][0]} vs {arbitrage_data['teams'][1]}"
    match_time = arbitrage_data['time']
    sport_id = arbitrage_data['sport_id']
    bet_type = arbitrage_data['bet_type']
    margin = arbitrage_data['margin']
    best_odds = [odd for odd, _ in arbitrage_data['odds']]
    profit = arbitrage_data['profit']
    
    # Only process if profit is above 1.5%
    if profit > 1.5:
        # Try to store arbitrage
        if store_arbitrage(teams, match_time, sport_id, bet_type, margin, best_odds, profit):
            # If successfully stored (meaning it's new), send to Telegram
            await send_to_telegram(arbitrage_data)
            print(f"New arbitrage found and sent: {teams} with {profit:.2f}% profit")
    else:
        print(f"Skipping low profit arbitrage: {teams} with {profit:.2f}% profit")


def find_arbitrage_opportunities(sport_name, similarity_threshold=75, time_window=7200):
    """Find arbitrage opportunities within a specific sport"""
    df = load_sport_matches(sport_name)
    if df is None:
        print(f"No matches found for {sport_name}")
        return []

    print(f"Processing {len(df)} matches for {sport_name}")

    # Convert timestamp to datetime and sort
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")

    # Pre-process team names
    df["team1_lower"] = df["team1"].str.lower()
    df["team2_lower"] = df["team2"].str.lower()

    # Convert to numpy arrays for faster processing
    timestamps = df["timestamp"].values.astype(np.int64) // 10**9
    team1s = df["team1_lower"].values
    team2s = df["team2_lower"].values
    margins = df["margin"].values
    bet_types = df["bet_type_id"].values
    bookmakers = df["bookmaker_id"].values

    arbitrage_opportunities = []
    processed_indices = set()

    # Create numpy arrays for odds
    odds1 = df["odd1"].values
    odds2 = df["odd2"].values
    odds3 = df["odd3"].values if "odd3" in df.columns else np.zeros(len(df))

    # Process each bet type separately
    for bet_type in np.unique(bet_types):
        bet_mask = bet_types == bet_type
        bet_indices = np.where(bet_mask)[0]

        for i, idx in enumerate(bet_indices):
            if idx in processed_indices:
                continue

            # Time window filter using vectorized operations
            time_diffs = np.abs(timestamps[bet_indices] - timestamps[idx])
            time_mask = time_diffs <= time_window
            margin_mask = margins[bet_indices] == margins[idx]
            valid_mask = time_mask & margin_mask
            potential_indices = bet_indices[valid_mask]

            if len(potential_indices) < 2:
                continue

            # Improved team name matching
            team1_current = team1s[idx]
            team2_current = team2s[idx]

            def calc_similarity(s1, s2):
                if s1 == s2:
                    return 100

                # Clean strings for comparison
                s1_clean = s1.replace(".", "").strip()
                s2_clean = s2.replace(".", "").strip()

                # Check for substring matches
                if s1_clean in s2_clean or s2_clean in s1_clean:
                    return 90

                # For regular teams, use fuzzy matching
                return fuzz.ratio(s1_clean, s2_clean)

            # Vectorized similarity calculation with both team orders
            similarities1 = np.array(
                [
                    max(
                        min(
                            calc_similarity(team1_current, team1s[i]),
                            calc_similarity(team2_current, team2s[i]),
                        ),
                        min(
                            calc_similarity(team1_current, team2s[i]),
                            calc_similarity(team2_current, team1s[i]),
                        ),
                    )
                    for i in potential_indices
                ]
            )

            match_mask = similarities1 >= similarity_threshold
            matched_indices = potential_indices[match_mask]

            if len(matched_indices) < 2:
                continue

            # Check for unique bookmakers
            if len(np.unique(bookmakers[matched_indices])) < 2:
                continue

            # Calculate best odds
            is_three_way = bet_type in [2, 3, 4, 12]

            if is_three_way:
                best_odds = [
                    np.max(odds1[matched_indices]),
                    np.max(odds2[matched_indices]),
                    np.max(odds3[matched_indices]),
                ]
                best_bookies = [
                    bookmakers[matched_indices[np.argmax(odds1[matched_indices])]],
                    bookmakers[matched_indices[np.argmax(odds2[matched_indices])]],
                    bookmakers[matched_indices[np.argmax(odds3[matched_indices])]],
                ]
            else:
                best_odds = [
                    np.max(odds1[matched_indices]),
                    np.max(odds2[matched_indices]),
                ]
                best_bookies = [
                    bookmakers[matched_indices[np.argmax(odds1[matched_indices])]],
                    bookmakers[matched_indices[np.argmax(odds2[matched_indices])]],
                ]

            # Calculate arbitrage
            if is_three_way and all(o > 0 for o in best_odds):
                arb_exists, *results = calculate_three_way_arbitrage(*best_odds)
                if arb_exists and results[-1] > 0:
                    arbitrage_opportunities.append(
                        {
                            "type": "3-way",
                            "teams": (df.iloc[idx]["team1"], df.iloc[idx]["team2"]),
                            "time": df.iloc[idx]["timestamp"],
                            "matches": df.iloc[matched_indices].to_dict("records"),
                            "odds": list(zip(best_odds, best_bookies)),
                            "stakes": results[:-1],
                            "profit": results[-1],
                            "bet_type": bet_type,
                            "sport_id": df.iloc[idx]["sport_id"],
                            "margin": df.iloc[idx]["margin"],
                        }
                    )
            elif not is_three_way and all(o > 0 for o in best_odds):
                arb_exists, *results = calculate_two_way_arbitrage(*best_odds)
                if arb_exists and results[-1] > 0:
                    arbitrage_opportunities.append(
                        {
                            "type": "2-way",
                            "teams": (df.iloc[idx]["team1"], df.iloc[idx]["team2"]),
                            "time": df.iloc[idx]["timestamp"],
                            "matches": df.iloc[matched_indices].to_dict("records"),
                            "odds": list(zip(best_odds, best_bookies)),
                            "stakes": results[:-1],
                            "profit": results[-1],
                            "bet_type": bet_type,
                            "sport_id": df.iloc[idx]["sport_id"],
                            "margin": df.iloc[idx]["margin"],
                        }
                    )

            processed_indices.update(matched_indices)

    # Process each opportunity
    for arb in arbitrage_opportunities:
        asyncio.run(process_arbitrage(arb))

    return arbitrage_opportunities


def main():
    start_time = time.time()
    all_opportunities = []
    # Process each sport separately
    for sport_id in range(1, 6):
        sport_name = get_sport_name(sport_id)
        print(f"\nProcessing {sport_name} matches...")
        opportunities = find_arbitrage_opportunities(sport_name)
        all_opportunities.extend(opportunities)
        print(
            f"Found {len(opportunities)} arbitrage opportunities in {sport_name}"
        )

    elapsed_time = time.time() - start_time
    print(f"\nTotal opportunities found: {len(all_opportunities)}")
    print(f"Time taken: {elapsed_time:.2f} seconds")


if __name__ == "__main__":
    main()