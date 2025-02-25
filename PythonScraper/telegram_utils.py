from telegram.ext import Application
import asyncio
import os
from dotenv import load_dotenv

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

async def send_to_telegram(arbitrage_data):
    """Send arbitrage opportunity to Telegram group"""
    app = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()
    
    # Get proper names from IDs
    sport_name = SPORTS.get(arbitrage_data['sport_id'], f"Sport ID: {arbitrage_data['sport_id']}")
    bet_type_name = BET_TYPES.get(arbitrage_data['bet_type'], f"Bet Type: {arbitrage_data['bet_type']}")
    
    # Format message
    message = (
        f"🎯 New Arbitrage Opportunity! ({arbitrage_data['type']})\n\n"
        f"{sport_name}\n"
        f"🏟️ Teams: {arbitrage_data['teams'][0]} vs {arbitrage_data['teams'][1]}\n"
        f"⏰ Time: {arbitrage_data['time']}\n"
        f"🎲 Bet Type: {bet_type_name}\n"
        f"📊 Margin: {arbitrage_data['margin']}\n\n"
        f"💰 Best odds:\n"
    )
    
    # Add best odds with emojis
    for i, (odd, bookie_id) in enumerate(arbitrage_data['odds'], 1):
        emoji = "1️⃣" if i == 1 else "2️⃣" if i == 2 else "3️⃣"
        bookie_name = BOOKMAKERS.get(bookie_id, f"Bookmaker ID: {bookie_id}")
        message += f"{emoji} Outcome {i}: {odd} ({bookie_name})\n"
    
    # Add stakes
    message += f"\n💸 Recommended stakes:\n"
    stakes = [f"   Stake {i+1}: {stake:.2f}%" for i, stake in enumerate(arbitrage_data['stakes'])]
    message += "\n".join(stakes)
    
    # Add profit
    message += f"\n📈 Potential profit: {arbitrage_data['profit']:.2f}%\n"
    
    # Add all available odds
    message += f"\n📋 All available odds:\n"
    for match in arbitrage_data['matches']:
        bookie_name = BOOKMAKERS.get(match['bookmaker_id'], f"Bookmaker {match['bookmaker_id']}")
        odds = []
        if 'odd1' in match: odds.append(str(match['odd1']))
        if 'odd2' in match: odds.append(str(match['odd2']))
        if 'odd3' in match and match['odd3'] != 'N/A': odds.append(str(match['odd3']))
        message += f"   {bookie_name}: {' - '.join(odds)}\n"
    
    try:
        await app.bot.send_message(
            chat_id=int(os.getenv('TELEGRAM_CHAT_ID')),
            text=message
        )
        print(f"Sent arbitrage alert for {arbitrage_data['teams'][0]} vs {arbitrage_data['teams'][1]}")
    except Exception as e:
        print(f"Error sending telegram message: {e}") 