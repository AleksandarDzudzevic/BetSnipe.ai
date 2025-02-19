import pyodbc
from dotenv import load_dotenv
import os
import pandas as pd

load_dotenv()

def get_db_connection():
    try:
        # For Windows
        conn = pyodbc.connect(
            'DRIVER={SQL Server};'
            'SERVER=195.178.52.110;'
            'DATABASE=ArbitrageBetting;'
            'UID=admin;'
            f'PWD={os.getenv("DB_PASSWORD")};'
        )
    except:
        # For Mac OS
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 18 for SQL Server};'  # Note the different driver name
            'SERVER=195.178.52.110;'
            'DATABASE=ArbitrageBetting;'
            'UID=admin;'
            f'PWD={os.getenv("DB_PASSWORD")};'
            'TrustServerCertificate=yes;'  # Added for SSL/TLS
        )
    return conn

def insert_match(conn, team_home, team_away, bookmaker_id, sport_id, bet_type_id, 
                margin, odd1, odd2, odd3, start_time):
    cursor = conn.cursor()
    cursor.execute("""
        EXEC InsertAllMatches 
        @teamHome=?, @teamAway=?, @bookmaker_id=?, @sport_id=?, @betType_id=?,
        @margin=?, @odd1=?, @odd2=?, @odd3=?, @startTime=?
    """, (team_home, team_away, bookmaker_id, sport_id, bet_type_id, 
          margin, odd1, odd2, odd3, start_time))
    conn.commit()

def batch_insert_matches(conn, matches):
    if not matches:  # Early return if no matches
        print("No matches to insert")
        return

    cursor = conn.cursor()
    cursor.fast_executemany = True

    try:
        # Convert matches list to Pandas DataFrame
        df = pd.DataFrame(matches, columns=[
            'teamHome', 'teamAway', 'bookmaker_id', 'sport_id', 'betType_id',
            'margin', 'odd1', 'odd2', 'odd3', 'startTime'
        ])

        # Convert numpy types to Python native types
        df['teamHome'] = df['teamHome'].astype(str).str.slice(0, 255)
        df['teamAway'] = df['teamAway'].astype(str).str.slice(0, 255)
        df['bookmaker_id'] = df['bookmaker_id'].astype(int)
        df['sport_id'] = df['sport_id'].astype(int)
        df['betType_id'] = df['betType_id'].astype(int)
        df['margin'] = df['margin'].astype(float).round(2)
        df['odd1'] = df['odd1'].astype(float).round(2)
        df['odd2'] = df['odd2'].astype(float).round(2)
        df['odd3'] = df['odd3'].astype(float).round(2)
        df['startTime'] = pd.to_datetime(df['startTime'])

        print(f"Processing {len(df)} matches")  # Debug print

        # Create temp table
        cursor.execute("""
            IF OBJECT_ID('tempdb..#TempMatchTable') IS NOT NULL 
                DROP TABLE #TempMatchTable;
                
            CREATE TABLE #TempMatchTable (
                teamHome varchar(255),
                teamAway varchar(255),
                bookmaker_id int,
                sport_id int,
                betType_id int,
                margin decimal(5,2),
                odd1 decimal(8,2),
                odd2 decimal(8,2),
                odd3 decimal(8,2),
                startTime datetime
            )
        """)

        # Insert records into temp table
        records = df.values.tolist()
        cursor.executemany("""
            INSERT INTO #TempMatchTable 
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, records)
        print("Inserted into temp table")  # Debug print

        # Execute stored procedure
        cursor.execute("""
            DECLARE @MatchList AS MatchTableType;
            INSERT INTO @MatchList 
            SELECT * FROM #TempMatchTable;
            EXEC InsertAllMatches @MatchList = @MatchList;
        """)
        conn.commit()  # Commit the transaction
        print("Stored procedure executed successfully")  # Debug print

    except Exception as e:
        conn.rollback()  # Rollback on error
        print(f"Error in batch_insert_matches: {type(e).__name__}: {str(e)}")
        raise
    finally:
        try:
            cursor.execute("DROP TABLE IF EXISTS #TempMatchTable")
            conn.commit()
        except:
            pass
        cursor.close()

