"""
Telegram notification utilities for BetSnipe.ai v2.0

Sends arbitrage alerts to Telegram.
"""

import asyncio
import logging
import os
from typing import Optional, Dict, Any, TYPE_CHECKING

from telegram import Bot
from telegram.error import TelegramError

if TYPE_CHECKING:
    from core.arbitrage import ArbitrageOpportunity

logger = logging.getLogger(__name__)

# Sport emojis
SPORT_EMOJIS = {
    1: "⚽",  # Football
    2: "🏀",  # Basketball
    3: "🎾",  # Tennis
    4: "🏒",  # Hockey
    5: "🏓",  # Table Tennis
}

# Sport names
SPORT_NAMES = {
    1: "Football",
    2: "Basketball",
    3: "Tennis",
    4: "Hockey",
    5: "Table Tennis",
}


class TelegramNotifier:
    """Handles Telegram notifications for arbitrage alerts."""

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self._bot: Optional[Bot] = None

    @property
    def bot(self) -> Bot:
        if self._bot is None:
            if not self.token:
                raise ValueError("TELEGRAM_BOT_TOKEN not set")
            self._bot = Bot(token=self.token)
        return self._bot

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def format_arbitrage_message(self, opp: "ArbitrageOpportunity") -> str:
        """Format arbitrage opportunity for Telegram notification."""
        sport_emoji = SPORT_EMOJIS.get(opp.sport_id, "🎯")
        sport_name = SPORT_NAMES.get(opp.sport_id, "Sport")
        arb_type = "2-way" if opp.is_two_way else "3-way"

        lines = [
            f"🎯 *ARBITRAGE ALERT* ({arb_type})",
            f"",
            f"{sport_emoji} *{sport_name}*",
            f"🏟️ *{opp.team1}* vs *{opp.team2}*",
            f"⏰ {opp.start_time.strftime('%Y-%m-%d %H:%M') if opp.start_time else 'TBD'}",
            f"",
            f"📊 *Bet Type:* {opp.bet_type_name}",
        ]

        if opp.margin > 0:
            lines.append(f"📏 *Margin:* {opp.margin}")

        lines.extend([
            f"💰 *Profit:* {opp.profit_percentage:.2f}%",
            f"",
            f"*Best Odds:*",
        ])

        for i, odd in enumerate(opp.best_odds):
            outcome = odd['outcome']
            if outcome == 1:
                outcome_label = "1 (Home)"
            elif outcome == 2:
                outcome_label = "2 (Away)"
            elif outcome == 'X':
                outcome_label = "X (Draw)"
            else:
                outcome_label = str(outcome)

            emoji = "1️⃣" if i == 0 else "2️⃣" if i == 1 else "3️⃣"
            lines.append(
                f"{emoji} {outcome_label}: *{odd['odd']:.2f}* @ {odd['bookmaker_name']}"
            )

        lines.extend([
            f"",
            f"*Optimal Stakes (100 units):*",
        ])

        for i, (stake, odd) in enumerate(zip(opp.stakes, opp.best_odds)):
            outcome = odd['outcome']
            if outcome == 1:
                outcome_label = "Home"
            elif outcome == 2:
                outcome_label = "Away"
            elif outcome == 'X':
                outcome_label = "Draw"
            else:
                outcome_label = str(outcome)

            lines.append(f"   {outcome_label}: {stake:.2f} units")

        return '\n'.join(lines)

    async def send_arbitrage_alert(self, opp: "ArbitrageOpportunity") -> bool:
        """
        Send arbitrage opportunity alert to Telegram.

        Args:
            opp: ArbitrageOpportunity to send

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.warning("Telegram not configured, skipping notification")
            return False

        try:
            message = self.format_arbitrage_message(opp)

            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown'
            )

            logger.info(
                f"Sent Telegram alert: {opp.team1} vs {opp.team2} "
                f"({opp.profit_percentage:.2f}%)"
            )
            return True

        except TelegramError as e:
            logger.error(f"Telegram error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False

    async def send_message(self, text: str, parse_mode: str = 'Markdown') -> bool:
        """Send a custom message to Telegram."""
        if not self.is_configured:
            return False

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode
            )
            return True
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False


# Global notifier instance
_notifier: Optional[TelegramNotifier] = None


def get_telegram_notifier() -> TelegramNotifier:
    """Get or create the global Telegram notifier instance."""
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier


async def send_arbitrage_alert(opp: "ArbitrageOpportunity") -> bool:
    """Convenience function to send arbitrage alert."""
    return await get_telegram_notifier().send_arbitrage_alert(opp)
