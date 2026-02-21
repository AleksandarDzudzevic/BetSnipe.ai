"""
Mozzart Bet Ticket Resolver
Fetches betslip details from Mozzart's public ticket status API.
No login required — just the ticket ID (tid) from the URL or betslip.

The public URL format: https://www.mozzartbet.com/sr/status-tiketa-sport/{tid}

Usage:
    # Single ticket
    python mozzart_tickets.py --ticket 1137024173628661

    # Multiple tickets
    python mozzart_tickets.py --tickets 1137024173628661 1137024173628662

    # From file (one tid per line)
    python mozzart_tickets.py --file tickets.txt

    # Save raw JSON output
    python mozzart_tickets.py --ticket 1137024173628661 --output results.json --raw

Ticket status (ticketStatus):
    ACTIVE   = not yet resolved
    WON      = ticket won
    LOST     = ticket lost
    CANCELED = voided

Selection status (winStatus per row):
    ACTIVE   = pending
    WON      = hit
    LOST     = missed
    CANCELED = void
"""

import argparse
import asyncio
import json
import random
import time
from datetime import datetime
from pathlib import Path

import aiohttp


TICKET_API = "https://www.mozzartbet.com/my-bet-ticket-public"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.mozzartbet.com",
    "Referer": "https://www.mozzartbet.com/sr/status-tiketa-sport/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

SPORT_NAMES = {
    1: "Fudbal",
    2: "Košarka",
    3: "Tenis",
    4: "Hokej",
    5: "Stoni tenis",
    6: "Odbojka",
    7: "Rukomet",
}

TICKET_STATUS_DISPLAY = {
    "WON": "WON",
    "LOST": "LOST",
    "ACTIVE": "PENDING",
    "CANCELED": "CANCELLED",
}

WIN_STATUS_MARK = {
    "WON": "+",
    "LOST": "-",
    "ACTIVE": "?",
    "CANCELED": "x",
}


def _unique_id() -> str:
    return f"{int(time.time() * 1000)}-{random.randint(0, 0xFFFFFFFF):08x}"


def format_ts(ts_ms: int | None) -> str:
    if not ts_ms:
        return "-"
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M")


async def fetch_ticket(session: aiohttp.ClientSession, tid: str) -> dict | list:
    """Fetch a single ticket from Mozzart's public API."""
    headers = {**HEADERS, "X-Unique-Id": _unique_id()}
    try:
        async with session.post(
            TICKET_API,
            json={"tid": tid},
            headers=headers,
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                return {"tid": tid, "error": f"HTTP {resp.status}: {text[:200]}"}
            data = await resp.json(content_type=None)
            # API returns a list; grab first element
            if isinstance(data, list):
                if not data:
                    return {"tid": tid, "error": "Ticket not found"}
                ticket = data[0]
                ticket["_queried_tid"] = tid
                return ticket
            return data
    except Exception as e:
        return {"tid": tid, "error": str(e)}


def format_ticket(ticket: dict) -> str:
    if "error" in ticket:
        return f"  ERROR: {ticket['error']}"

    lines = []

    status = ticket.get("ticketStatus", "?")
    status_display = TICKET_STATUS_DISPLAY.get(status, status)

    tid = ticket.get("tid", ticket.get("_queried_tid", "?"))
    amount = ticket.get("amount", 0)
    potential = ticket.get("potentialPayment", ticket.get("maxPotentialPayment", 0))
    total_odd = ticket.get("totalOdd", "?")
    if isinstance(total_odd, float):
        total_odd = round(total_odd, 2)
    rows = ticket.get("numberOfRows", 0)
    combos = ticket.get("combinationNumber", 1)
    paid_in = format_ts(ticket.get("payInTime"))
    single = ticket.get("single", False)
    ticket_type = "Single" if single else f"Accumulator {rows}/{rows}"
    if combos > 1:
        ticket_type = f"System ({combos} combos)"

    lines.append(f"  Status:      {status_display}")
    lines.append(f"  Ticket ID:   {tid}")
    lines.append(f"  Type:        {ticket_type}")
    lines.append(f"  Stake:       {amount} RSD")
    lines.append(f"  Total Odds:  {total_odd}")
    lines.append(f"  Potential:   {potential} RSD")

    if status == "WON":
        payout = ticket.get("paymentAmount", potential)
        lines.append(f"  Won:         {payout} RSD")

    cashout = ticket.get("cashOutPayout", 0)
    if cashout:
        lines.append(f"  Cash-out:    {cashout} RSD")

    bonus = ticket.get("bonus", 0)
    if bonus:
        lines.append(f"  Bonus:       {bonus} RSD")

    lines.append(f"  Placed:      {paid_in}")
    lines.append("")

    bet_rows = sorted(
        ticket.get("betRowDetails", []),
        key=lambda r: r.get("rowNumber", 0)
    )

    if bet_rows:
        lines.append(f"  Selections ({len(bet_rows)}):")
        lines.append(f"  {'─' * 78}")

        for row in bet_rows:
            win_stat = row.get("winStatus", "ACTIVE")
            mark = WIN_STATUS_MARK.get(win_stat, "?")
            stat_display = TICKET_STATUS_DISPLAY.get(win_stat, win_stat)

            match_name = row.get("rowRepresentation", "?")
            league = row.get("rowAdditionalInfo", "")
            start = format_ts(row.get("eventStartTime"))
            bet_desc = row.get("betRepresentation", "?")
            pick_short = row.get("betRepresentationShortName", "")
            odd = row.get("odd", "?")
            score = (row.get("betEventResult") or "").strip()
            event_status = row.get("eventStatus", "")
            sport_id = row.get("sportId")
            sport = SPORT_NAMES.get(sport_id, f"Sport {sport_id}" if sport_id else "")
            is_live = row.get("payInEventStatus") == "LIVE"
            live_tag = " [LIVE]" if is_live else ""

            lines.append(f"  [{mark}] {match_name}{live_tag}")
            info_parts = [p for p in [sport, league] if p]
            if info_parts:
                lines.append(f"       {' | '.join(info_parts)}")
            lines.append(f"       Kick-off:  {start}")
            lines.append(f"       Pick:      {pick_short}  —  {bet_desc}")
            lines.append(f"       Odd:       {odd}")
            lines.append(f"       Result:    {stat_display}")
            if score:
                lines.append(f"       Score:     {score}")
            if event_status and event_status not in ("NOT_STARTED", "FINISHED"):
                lines.append(f"       State:     {event_status}")
            lines.append("")
    else:
        lines.append("  [No selections found]")

    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(
        description="Fetch Mozzart Bet ticket details (no login required)"
    )

    ticket_group = parser.add_mutually_exclusive_group(required=True)
    ticket_group.add_argument("--ticket", help="Single ticket ID (tid)")
    ticket_group.add_argument("--tickets", nargs="+", help="Multiple ticket IDs")
    ticket_group.add_argument("--file", help="File with ticket IDs (one per line)")

    parser.add_argument("--output", help="Save raw JSON results to file")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON instead of formatted output")

    args = parser.parse_args()

    if args.ticket:
        ticket_ids = [args.ticket]
    elif args.tickets:
        ticket_ids = args.tickets
    else:
        ticket_ids = Path(args.file).read_text().strip().splitlines()
        ticket_ids = [t.strip() for t in ticket_ids if t.strip()]

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_ticket(session, tid) for tid in ticket_ids]
        results = await asyncio.gather(*tasks)

    if args.raw:
        print(json.dumps(
            list(results) if len(results) > 1 else results[0],
            indent=2, ensure_ascii=False
        ))
    else:
        print(f"\n{'=' * 85}")
        print(f"  MOZZART BET TICKET REPORT  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'=' * 85}")
        for tid, data in zip(ticket_ids, results):
            print(f"\n{'─' * 85}")
            print(f"  TICKET: {tid}")
            print(f"{'─' * 85}")
            print(format_ticket(data))
        print(f"{'=' * 85}\n")

    if args.output:
        output_data = list(results) if len(results) > 1 else results[0]
        Path(args.output).write_text(
            json.dumps(output_data, indent=2, ensure_ascii=False)
        )
        print(f"Results saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
