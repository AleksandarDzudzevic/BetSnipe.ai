from telegram.ext import Application
import asyncio
import os
from dotenv import load_dotenv
from database_utils import get_db_connection

load_dotenv()

# Mapping dictionaries
BOOKMAKERS = {
    1: "Mozzart",
    2: "Meridianbet",
    3: "Maxbet",
    4: "Admiral",
    5: "Soccerbet",
    6: "1xBet",
    7: "Superbet",
    8: "Merkur"
}

SPORTS = {
    1: "⚽ Football",
    2: "🏀 Basketball",
    3: "🎾 Tennis",
    4: "🏒 Hockey",
    5: "🏓 Table Tennis"
}

BET_TYPES = {
    1: "12",
    2: "1X2",
    3: "1X2F",
    4: "1X2S",
    5: "TG",
    6: "TGF",
    7: "TGS",
    8: "GGNG",
    9: "H",
    10: "OU",
    11: "12set1"
}

class TelegramHandler:
    def __init__(self):
        self.message_ids = {}
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = int(os.getenv('TELEGRAM_CHAT_ID'))
        self.load_message_ids()  # Load message IDs on startup

    def load_message_ids(self):
        """Load message IDs and original messages from database"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get active messages with all their data
            cursor.execute("""
                SELECT sa.arb_hash, sa.message_id, m.teamHome, m.teamAway, m.startTime, sa.bet_type, 
                       sa.margin, sa.best_odds, sa.profit, s.name as sport_name,
                       bt.name as bet_type_name, m.bookmaker_id, m.odd1, m.odd2, m.odd3
                FROM dbo.SentArbitrage sa
                JOIN dbo.Sport s ON sa.sport_id = s.id
                JOIN dbo.BetType bt ON sa.bet_type = bt.id
                JOIN dbo.AllMatches m ON CONCAT(m.teamHome, ' vs ', m.teamAway) = sa.teams 
                    AND m.startTime = sa.match_time
                WHERE sa.sent_at > DATEADD(hour, -24, GETDATE())
            """)  # Removed the message_id IS NOT NULL condition
            
            for row in cursor.fetchall():
                arb_hash, message_id = row[0], row[1]
                if message_id:  # Only store if message_id exists
                    teams = f"{row[2]} vs {row[3]}"
                    match_time = row[4]
                    odds = [float(x) for x in row[7].split(',')]
                    
                    # Reconstruct the original message
                    original_text = (
                        f"🎯 New Arbitrage Opportunity! (2-way)\n\n"
                        f"🏀 {row[9]}\n"  # sport_name
                        f"🏟️ Teams: {teams}\n"
                        f"⏰ Time: {match_time}\n"
                        f"🎲 Bet Type: {row[10]}\n"  # bet_type_name
                        f"📊 Margin: {row[6]}\n\n"  # margin
                        f"💰 Best odds:\n"
                        f"1️⃣ Outcome 1: {odds[0]}\n"
                        f"2️⃣ Outcome 2: {odds[1]}\n\n"
                        f"💸 Recommended stakes:\n"
                        f"   Stake 1: {100/(1 + odds[0]/odds[1]):.2f}%\n"
                        f"   Stake 2: {100/(1 + odds[1]/odds[0]):.2f}%\n"
                        f"📈 Potential profit: {row[8]:.2f}%\n"  # profit
                    )
                    
                    self.message_ids[arb_hash] = {
                        'message_id': message_id,
                        'original_text': original_text
                    }
            
            print(f"Loaded {len(self.message_ids)} message IDs")
            
        except Exception as e:
            print(f"Error loading message IDs: {e}")
            print(f"Detailed error: {str(e)}")
        finally:
            if 'conn' in locals():
                conn.close()

    async def send_arbitrage(self, arbitrage_data, arb_hash):
        """Send new arbitrage message and store its ID"""
        app = Application.builder().token(self.bot_token).build()
        
        # Format the message
        message = (
            f"🎯 New Arbitrage Opportunity! (2-way)\n\n"
            f"🏀 Basketball\n"
            f"🏟️ Teams: {arbitrage_data['teams'][0]} vs {arbitrage_data['teams'][1]}\n"
            f"⏰ Time: {arbitrage_data['time']}\n"
            f"🎲 Bet Type: {arbitrage_data['bet_type']}\n"
            f"📊 Margin: {arbitrage_data['margin']}\n\n"
            f"💰 Best odds:\n"
            f"1️⃣ Outcome 1: {arbitrage_data['odds'][0][0]} ({arbitrage_data['odds'][0][1]})\n"
            f"2️⃣ Outcome 2: {arbitrage_data['odds'][1][0]} ({arbitrage_data['odds'][1][1]})\n\n"
            f"💸 Recommended stakes:\n"
            f"   Stake 1: {arbitrage_data['stakes'][0]:.2f}%\n"
            f"   Stake 2: {arbitrage_data['stakes'][1]:.2f}%\n"
            f"📈 Potential profit: {arbitrage_data['profit']:.2f}%\n\n"
            f"📋 All available odds:\n"
        )
        
        # Add all bookmaker odds from the odds array
        bookies = set(bookie for _, bookie in arbitrage_data['odds'])
        for bookie in bookies:
            odds = [odd for odd, b in arbitrage_data['odds'] if b == bookie]
            message += f"   {bookie}: {' - '.join(map(str, odds))} - 0.0\n"
        
        try:
            sent_message = await app.bot.send_message(
                chat_id=self.chat_id,
                text=message
            )
            
            # Store both message ID and original text in memory
            self.message_ids[arb_hash] = {
                'message_id': sent_message.message_id,
                'original_text': message
            }
            
            # Store message_id in database
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE SentArbitrage
                SET message_id = ?
                WHERE arb_hash = ?
            """, (sent_message.message_id, arb_hash))
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error sending telegram message: {e}")

    async def mark_expired(self, arb_hash):
        """Mark arbitrage as expired in Telegram message"""
        if arb_hash not in self.message_ids:
            print(f"Message ID not found for hash {arb_hash}")
            return
        
        message_data = self.message_ids[arb_hash]
        original_text = message_data['original_text']
        message_id = message_data['message_id']
        
        # Add expired notice at the top
        expired_text = "⚠️ EXPIRED/CHANGED ⚠️\n\n" + original_text
        
        app = Application.builder().token(self.bot_token).build()
        try:
            await app.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=message_id,
                text=expired_text
            )
            print(f"Successfully marked message {message_id} as expired")
        except Exception as e:
            print(f"Error editing telegram message: {e}")

# Create global instance
telegram_handler = TelegramHandler() 