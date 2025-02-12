import pyodbc
from dotenv import load_dotenv
import os

load_dotenv()

def get_db_connection():
    conn = pyodbc.connect(
        'DRIVER={SQL Server};'
        'SERVER=195.178.52.110;'
        'DATABASE=ArbitrageBetting;'
        'UID=admin;'
        f'PWD={os.getenv("DB_PASSWORD")};'
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