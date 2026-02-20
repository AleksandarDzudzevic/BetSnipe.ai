"""
Admiral Bet Ticket Resolver
Fetches betslip details and match results from Admiral Bet's API.

Usage:
    # Single ticket
    python admiral_tickets.py --ticket 1200171532081

    # Multiple tickets
    python admiral_tickets.py --tickets 1200171532081 1200171532082

    # From file (one ticket ID per line)
    python admiral_tickets.py --file tickets.txt

    # Save raw JSON output
    python admiral_tickets.py --ticket 1200171532081 --output results.json --raw

    # Use custom token (if default stops working)
    python admiral_tickets.py --ticket 1200171532081 --token YOUR_TOKEN
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import aiohttp


TICKET_API = "https://sport-webapi.admiralbet.rs/api/Platform/ticket"

# Public ticket-check token (not user-specific, works for any ticket)
DEFAULT_TOKEN = "743a83407e8991fda06a7ac34bcae2cab1d9c96a58b7eb782b769feed175b5f14d8d2062280d9de2d894d1071f01701ac6687e51cfbfa68bbc6f3f469be3bf72"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}


async def fetch_ticket(session: aiohttp.ClientSession, ticket_id: str, token: str) -> dict:
    """Fetch a single ticket's details from Admiral API."""
    url = f"{TICKET_API}/{ticket_id}/"
    params = {"language": "sr", "token": token}
    async with session.get(url, params=params, headers=HEADERS) as resp:
        if resp.status != 200:
            text = await resp.text()
            return {"ticketNumber": ticket_id, "error": f"HTTP {resp.status}: {text[:200]}"}
        data = await resp.json()
        if isinstance(data, dict) and data.get("code") == 1:
            return {"ticketNumber": ticket_id, "error": data.get("message", "Invalid token")}
        return data


STATUS_MAP = {
    "AKTIVAN": "PENDING",
    "DOBITAK": "WON",
    "GUBITAK": "LOST",
    "ISPLACEN": "PAID_OUT",
    "STORNIRAN": "CANCELLED",
}

EVENT_STATUS_MAP = {
    "Pending": "PENDING",
    "Won": "WON",
    "Lost": "LOST",
    "Cancelled": "CANCELLED",
    "Dobitak": "WON",
    "Gubitak": "LOST",
}


def format_ticket(data: dict) -> str:
    """Format ticket data into readable output."""
    if "error" in data:
        return f"  ERROR: {data['error']}"

    lines = []

    status_raw = data.get("status", {})
    status_name = status_raw.get("name", "?") if isinstance(status_raw, dict) else str(status_raw)
    status_display = STATUS_MAP.get(status_name, status_name)

    lines.append(f"  Status:      {status_display} ({status_name})")
    lines.append(f"  Type:        {data.get('type', '?')} / {data.get('system', '?')}")
    lines.append(f"  Stake:       {data.get('stake', '?')} {data.get('currency', 'RSD')}")
    lines.append(f"  Total Odds:  {data.get('quota', '?')}")
    lines.append(f"  Potential:   {data.get('possibleMaxWin', '?')} {data.get('currency', 'RSD')}")

    payout = data.get("possiblePayout")
    if payout and status_display in ("WON", "PAID_OUT"):
        lines.append(f"  Payout:      {payout} {data.get('currency', 'RSD')}")

    lines.append(f"  Placed:      {data.get('createdOn', '?')}")
    lines.append(f"  Combos:      {data.get('numberOfCombinations', 1)}")

    bonus = data.get("bonus", 0)
    if bonus:
        lines.append(f"  Bonus:       {bonus} {data.get('currency', 'RSD')}")
    lines.append("")

    events = data.get("events", [])
    if events:
        lines.append(f"  Selections ({len(events)}):")
        lines.append(f"  {'─' * 78}")
        for i, evt in enumerate(events, 1):
            evt_status = evt.get("status", {})
            evt_status_name = evt_status.get("name", "?") if isinstance(evt_status, dict) else str(evt_status)
            evt_status_display = EVENT_STATUS_MAP.get(evt_status_name, evt_status_name)
            status_mark = {"WON": "+", "LOST": "-", "PENDING": "?", "CANCELLED": "x"}.get(evt_status_display, "?")

            is_live = "LIVE" if evt.get("isLive") else "PRE"
            result = evt.get("result", "") or "-"
            sbv = evt.get("sbv")
            market = evt.get("betType", "?")
            if sbv is not None:
                market = f"{market} ({sbv})"

            lines.append(f"  [{status_mark}] {i}. {evt.get('name', '?')}  [{is_live}]")
            lines.append(f"       {evt.get('sport', '')} | {evt.get('region', '')} | {evt.get('competition', '')}")
            lines.append(f"       Time:      {evt.get('time', '?')}")
            lines.append(f"       Market:    {market}")
            lines.append(f"       Pick:      {evt.get('outcome', '?')} @ {evt.get('odd', '?')}")
            lines.append(f"       Result:    {evt_status_display}")
            if result != "-":
                lines.append(f"       Score:     {result}")
            lines.append("")
    else:
        lines.append(f"  [No events found. Keys: {list(data.keys())}]")

    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(description="Fetch Admiral Bet ticket details")

    ticket_group = parser.add_mutually_exclusive_group(required=True)
    ticket_group.add_argument("--ticket", help="Single ticket ID")
    ticket_group.add_argument("--tickets", nargs="+", help="Multiple ticket IDs")
    ticket_group.add_argument("--file", help="File with ticket IDs (one per line)")

    parser.add_argument("--output", help="Save raw JSON results to file")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON instead of formatted output")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="API token (default: public ticket-check token)")

    args = parser.parse_args()

    # Collect ticket IDs
    if args.ticket:
        ticket_ids = [args.ticket]
    elif args.tickets:
        ticket_ids = args.tickets
    else:
        ticket_ids = Path(args.file).read_text().strip().splitlines()
        ticket_ids = [t.strip() for t in ticket_ids if t.strip()]

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_ticket(session, tid, args.token) for tid in ticket_ids]
        results = await asyncio.gather(*tasks)

    # Output
    if args.raw:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2, ensure_ascii=False))
    else:
        print(f"\n{'=' * 85}")
        print(f"  ADMIRAL BET TICKET REPORT  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'=' * 85}")
        for ticket_id, data in zip(ticket_ids, results):
            print(f"\n{'─' * 85}")
            print(f"  TICKET: {ticket_id}")
            print(f"{'─' * 85}")
            print(format_ticket(data))
        print(f"{'=' * 85}\n")

    # Save to file
    if args.output:
        output_data = results if len(results) > 1 else results[0]
        Path(args.output).write_text(json.dumps(output_data, indent=2, ensure_ascii=False))
        print(f"Results saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
