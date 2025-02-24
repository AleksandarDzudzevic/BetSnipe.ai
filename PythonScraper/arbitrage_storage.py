import hashlib
from database_utils import get_db_connection
from datetime import datetime
import numpy as np

class ArbitrageTracker:
    def __init__(self):
        self.active_arbitrages = {}
        self.load_active_arbitrages()

    def generate_match_hash(self, match_time, bet_type, margin, teams):
        """Generate a hash that identifies the same match (without odds)"""
        if isinstance(match_time, datetime):
            match_time = match_time.strftime('%Y-%m-%d %H:%M:%S')
        
        hash_string = f"{match_time}_{bet_type}_{margin}_{teams}"
        return hashlib.md5(hash_string.encode()).hexdigest()

    def generate_full_hash(self, match_time, bet_type, margin, teams, odds):
        """Generate a unique hash including odds"""
        if isinstance(match_time, datetime):
            match_time = match_time.strftime('%Y-%m-%d %H:%M:%S')
        
        odds_str = ','.join(str(round(odd, 2)) for odd in odds)
        hash_string = f"{match_time}_{bet_type}_{margin}_{teams}_{odds_str}"
        return hashlib.md5(hash_string.encode()).hexdigest()

    def store_arbitrage(self, teams, match_time, sport_id, bet_type, margin, best_odds, profit):
        """Store arbitrage in database if it doesn't exist"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Generate both hashes
            match_hash = self.generate_match_hash(match_time, bet_type, margin, teams)
            full_hash = self.generate_full_hash(match_time, bet_type, margin, teams, best_odds)
            
            # Check if this exact arbitrage exists
            cursor.execute("""
                SELECT id FROM dbo.SentArbitrage 
                WHERE arb_hash = ? AND expired = 0
            """, (full_hash,))
            
            if cursor.fetchone() is None:
                # Store new arbitrage
                cursor.execute("""
                    INSERT INTO dbo.SentArbitrage (teams, match_time, sport_id, bet_type, margin, best_odds, profit, arb_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    teams,
                    match_time,
                    sport_id,
                    bet_type,
                    margin,
                    ','.join(str(odd) for odd in best_odds),
                    profit,
                    full_hash
                ))
                conn.commit()
                
                # Store in active arbitrages using match_hash as key
                self.active_arbitrages[match_hash] = {
                    'teams': teams,
                    'match_time': match_time,
                    'bet_type': bet_type,
                    'margin': margin,
                    'original_odds': best_odds,
                    'full_hash': full_hash  # Store the full hash for reference
                }
                
                return full_hash
                
            return None
            
        except Exception as e:
            print(f"Error storing arbitrage: {e}")
            return None
        finally:
            if 'conn' in locals():
                conn.close()

    def check_expired_arbitrages(self, current_opportunities):
        current_arbs = {}
        new_opportunities = []
        expired_hashes = set()
        
        # Build current arbitrage info
        for opp in current_opportunities:
            teams = f"{opp['teams'][0]} vs {opp['teams'][1]}"
            # Generate both hashes
            match_hash = self.generate_match_hash(
                opp['time'],
                opp['bet_type'],
                opp['margin'],
                teams
            )
            
            current_arbs[match_hash] = {
                'profit': opp['profit'],
                'odds': [odd for odd, _ in opp['odds']],
                'full_data': opp,
                'teams': teams
            }
        
        # Check all active arbitrages
        for match_hash, stored_arb in list(self.active_arbitrages.items()):
            # Generate full_hash if it doesn't exist (backwards compatibility)
            if 'full_hash' not in stored_arb:
                stored_arb['full_hash'] = self.generate_full_hash(
                    stored_arb['match_time'],
                    stored_arb['bet_type'],
                    stored_arb['margin'],
                    stored_arb['teams'],
                    stored_arb['original_odds']
                )
            
            if match_hash in current_arbs:
                current_arb = current_arbs[match_hash]
                current_odds = current_arb['odds']
                stored_odds = stored_arb['original_odds']
                
                # Check if odds changed significantly (more than 1% difference)
                odds_changed = any(abs(c - s) > 0.01 for c, s in zip(current_odds, stored_odds))
                
                if odds_changed:
                    print(f"Odds changed for {stored_arb['teams']}: {stored_odds} -> {current_odds}")
                    # Mark as expired in database
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE dbo.SentArbitrage
                            SET expired = 1
                            WHERE arb_hash = ?
                        """, (stored_arb['full_hash'],))
                        conn.commit()
                        conn.close()
                    except Exception as e:
                        print(f"Error marking arbitrage as expired in DB: {e}")
                    
                    expired_hashes.add(stored_arb['full_hash'])
                    del self.active_arbitrages[match_hash]
                    
                    # If still profitable, add as new opportunity
                    if current_arb['profit'] > 1.5:
                        print(f"Adding new opportunity with profit {current_arb['profit']}%")
                        new_opportunities.append(current_arb['full_data'])
            else:
                # Arbitrage no longer exists
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE dbo.SentArbitrage
                        SET expired = 1
                        WHERE arb_hash = ?
                    """, (stored_arb['full_hash'],))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"Error marking arbitrage as expired in DB: {e}")
                
                expired_hashes.add(stored_arb['full_hash'])
                del self.active_arbitrages[match_hash]
        
        # Add completely new opportunities that weren't in active_arbitrages
        for match_hash, current_arb in current_arbs.items():
            if (match_hash not in self.active_arbitrages and 
                current_arb['profit'] > 1.5):
                print(f"Found completely new arbitrage with profit {current_arb['profit']}%")
                new_opportunities.append(current_arb['full_data'])
        
        return expired_hashes, new_opportunities

    def load_active_arbitrages(self):
        """Load active arbitrages from database at startup"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get all non-expired arbitrages from last 24 hours
            cursor.execute("""
                SELECT teams, match_time, bet_type, margin, best_odds, arb_hash
                FROM dbo.SentArbitrage
                WHERE expired = 0
                AND sent_at > DATEADD(hour, -24, GETDATE())
            """)
            
            for row in cursor.fetchall():
                teams = row[0]
                match_time = row[1]
                bet_type = row[2]
                margin = row[3]
                best_odds = [float(x) for x in row[4].split(',')]
                full_hash = row[5]
                
                # Generate match hash
                match_hash = self.generate_match_hash(
                    match_time,
                    bet_type,
                    margin,
                    teams
                )
                
                # Store in active_arbitrages
                self.active_arbitrages[match_hash] = {
                    'teams': teams,
                    'match_time': match_time,
                    'bet_type': bet_type,
                    'margin': margin,
                    'original_odds': best_odds,
                    'full_hash': full_hash
                }
                
            print(f"Loaded {len(self.active_arbitrages)} active arbitrages from database")
            
        except Exception as e:
            print(f"Error loading active arbitrages: {e}")
        finally:
            if 'conn' in locals():
                conn.close()

    def mark_arbitrage_expired(self, arb_hash):
        """Mark arbitrage as expired in database"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE SentArbitrage
                SET expired = 1
                WHERE arb_hash = ?
            """, (arb_hash,))
            
            conn.commit()
        except Exception as e:
            print(f"Error marking arbitrage as expired: {e}")
        finally:
            if 'conn' in locals():
                conn.close() 