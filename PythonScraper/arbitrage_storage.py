import hashlib
from database_utils import get_db_connection
from datetime import datetime
import numpy as np

def generate_arbitrage_hash(match_time, bet_type, margin, best_odds, profit):
    """
    Generate a unique hash for an arbitrage opportunity based on key parameters
    
    Args:
        match_time (str): Time of the match
        bet_type (int): Type of bet
        margin (float): Margin value
        best_odds (list): List of best odds
        profit (float): Profit percentage
    
    Returns:
        str: MD5 hash of the combined parameters
    """
    # Convert numpy types to Python native types
    bet_type = int(bet_type) if isinstance(bet_type, np.integer) else bet_type
    margin = float(margin) if isinstance(margin, np.floating) else margin
    profit = float(profit) if isinstance(profit, np.floating) else profit
    
    # Sort odds to ensure consistent hash regardless of order
    sorted_odds = sorted([str(float(odd)) for odd in best_odds])
    
    # Combine key elements to create a unique identifier
    unique_string = (
        f"{match_time}"
        f"{bet_type}"
        f"{margin:.2f}"
        f"{','.join(sorted_odds)}"
        f"{profit:.2f}"
    )
    
    # Generate MD5 hash
    return hashlib.md5(unique_string.encode()).hexdigest()

def store_arbitrage(teams, match_time, sport_id, bet_type, margin, best_odds, profit):
    """
    Store arbitrage opportunity in database if it's unique
    
    Args:
        teams (str): Team names
        match_time (str): Time of the match
        sport_id (int): Sport ID
        bet_type (int): Type of bet
        margin (float): Margin value
        best_odds (list): List of best odds
        profit (float): Profit percentage
    
    Returns:
        bool: True if stored successfully (new arbitrage), False if already exists
    """
    try:
        # Convert numpy types to Python native types
        sport_id = int(sport_id) if isinstance(sport_id, np.integer) else sport_id
        bet_type = int(bet_type) if isinstance(bet_type, np.integer) else bet_type
        margin = float(margin) if isinstance(margin, np.floating) else margin
        profit = float(profit) if isinstance(profit, np.floating) else profit
        best_odds = [float(odd) for odd in best_odds]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Generate hash
        arb_hash = generate_arbitrage_hash(match_time, bet_type, margin, best_odds, profit)
        
        # Check if this hash exists in the last 24 hours
        cursor.execute("""
            SELECT 1 
            FROM SentArbitrage 
            WHERE arb_hash = ? 
            AND sent_at > DATEADD(hour, -24, GETDATE())
        """, (arb_hash,))
        
        if cursor.fetchone():
            return False  # Already exists
            
        # Insert new arbitrage
        cursor.execute("""
            INSERT INTO SentArbitrage 
            (teams, match_time, sport_id, bet_type, margin, best_odds, profit, arb_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(teams),
            str(match_time),
            sport_id,
            bet_type,
            margin,
            ','.join(map(str, best_odds)),
            profit,
            arb_hash
        ))
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"Error storing arbitrage: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close() 