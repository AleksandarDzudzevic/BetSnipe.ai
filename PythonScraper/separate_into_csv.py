from database_utils import get_db_connection
import csv
import os


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
       # 6: "1xbet",  # if this exists in your data
        7: "superbet",
        8: "merkur",
    }
    return bookmakers.get(bookmaker_id, "unknown")


def should_exclude_match(team1, team2):
    """Check if match should be excluded based on team names"""
    match_string = f"{team1} {team2}"
    excluded_terms = ["U20", "U21", "U22", "U23", "U24", "(ž)", "(Ž)", "(Reserves)"]
    return any(term in match_string for term in excluded_terms)


def separate_into_csv():
    # Create directory for CSV files if it doesn't exist
    if not os.path.exists("matches_csv"):
        os.makedirs("matches_csv")

    # Connect to database and fetch all matches
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM AllMatches")

    # Create dictionary to store file handlers and row counts
    file_handlers = {}
    csv_writers = {}
    row_counts = {}  # New dictionary to track rows per file
    total_rows = 0  # Counter for total rows

    try:
        # Process each row
        for row in cursor:
            team1 = row[1]  # team1
            team2 = row[2]  # team2

            # Skip youth, women's and reserve matches
            if should_exclude_match(team1, team2):
                continue

            bookmaker_id = row[3]
            sport_id = row[4]

            # Get names
            bookmaker_name = get_bookmaker_name(bookmaker_id)
            sport_name = get_sport_name(sport_id)

            # Skip if unknown bookmaker or sport
            if bookmaker_name == "unknown" or sport_name == "unknown":
                continue

            # Create filename
            filename = f"matches_csv/{bookmaker_name}_{sport_name}_matches.csv"

            # If we haven't opened this file yet
            if filename not in file_handlers:
                file_handlers[filename] = open(
                    filename, "w", newline="", encoding="utf-8"
                )
                csv_writers[filename] = csv.writer(file_handlers[filename])
                row_counts[filename] = 0  # Initialize row count for new file
                # Write header
                csv_writers[filename].writerow(
                    [
                        "team1",
                        "team2",
                        "bookmaker_id",
                        "sport_id",
                        "bet_type_id",
                        "margin",
                        "odd1",
                        "odd2",
                        "odd3",
                        "timestamp",
                    ]
                )

            # Write the row to appropriate file
            csv_writers[filename].writerow(
                [
                    row[1],  # team1
                    row[2],  # team2
                    row[3],  # bookmaker_id
                    row[4],  # sport_id
                    row[5],  # bet_type_id
                    row[6],  # margin
                    row[7],  # odd1
                    row[8],  # odd2
                    row[9],  # odd3
                    row[10],  # timestamp
                ]
            )

            row_counts[filename] += 1  # Increment row count for this file
            total_rows += 1  # Increment total row count

    finally:
        # Close all file handlers
        for handler in file_handlers.values():
            handler.close()

        # Close database connection
        cursor.close()
        conn.close()

        # Print summary
        print("\nSummary of CSV files created:")
        print("=" * 50)
        for filename, count in row_counts.items():
            print(f"{filename}: {count} rows")
        print("=" * 50)
        print(f"Total rows written: {total_rows}")


def main():
    print("Starting to separate matches into CSV files...")
    separate_into_csv()
    print("Finished separating matches into CSV files!")


if __name__ == "__main__":
    main()
