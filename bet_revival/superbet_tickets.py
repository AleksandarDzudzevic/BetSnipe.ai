"""
Superbet Ticket Resolver
Fetches betslip details and match results from Superbet's API.
No login or token required.

Usage:
    # Single ticket
    python superbet_tickets.py --ticket 890D-QJ1HHB

    # Multiple tickets
    python superbet_tickets.py --tickets 890D-QJ1HHB 890D-ABC123

    # From file (one ticket ID per line)
    python superbet_tickets.py --file tickets.txt

    # Save raw JSON output
    python superbet_tickets.py --ticket 890D-QJ1HHB --output results.json --raw
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import aiohttp


TICKET_API = "https://prod-superbet-betting.freetls.fastly.net/tickets/presentation-api/v3/SB_RS/ticket"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}


async def fetch_ticket(session: aiohttp.ClientSession, ticket_id: str) -> dict:
    """Fetch a single ticket's details from Superbet API."""
    url = f"{TICKET_API}/{ticket_id}"
    async with session.get(url, headers=HEADERS) as resp:
        if resp.status == 404:
            return {"ticketId": ticket_id, "error": "Ticket not found"}
        if resp.status != 200:
            text = await resp.text()
            return {"ticketId": ticket_id, "error": f"HTTP {resp.status}: {text[:200]}"}
        return await resp.json()


STATUS_MAP = {
    "won": "WON",
    "lost": "LOST",
    "open": "PENDING",
    "cashout": "CASHED_OUT",
    "cancelled": "CANCELLED",
    "void": "VOID",
}


def format_dt(iso_str: str | None) -> str:
    """Format ISO datetime string."""
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return str(iso_str)


def format_ticket(data: dict) -> str:
    """Format ticket data into readable output."""
    if "error" in data:
        return f"  ERROR: {data['error']}"

    lines = []

    status = data.get("status", "?")
    status_display = STATUS_MAP.get(status, status.upper())

    payment = data.get("payment", {})
    win = data.get("win", {})

    lines.append(f"  Status:      {status_display}")
    lines.append(f"  Source:      {data.get('source', '?')}")
    lines.append(f"  Stake:       {payment.get('stake', '?')} RSD")
    lines.append(f"  Total Odds:  {data.get('coefficient', '?')}")
    lines.append(f"  Potential:   {win.get('potentialPayoff', win.get('potentialTotalWinnings', '?'))} RSD")

    actual_win = win.get("totalWinnings", 0)
    if actual_win and actual_win > 0:
        lines.append(f"  Winnings:    {actual_win} RSD")
        payoff = win.get("payoff", 0)
        if payoff:
            lines.append(f"  Payout:      {payoff} RSD")

    lines.append(f"  Placed:      {format_dt(data.get('dateReceived'))}")

    if data.get("system"):
        lines.append(f"  System:      {data['system']}")

    bonus = data.get("bonus")
    if bonus:
        lines.append(f"  Bonus:       {bonus}")
    lines.append("")

    events = data.get("events", [])
    if events:
        lines.append(f"  Selections ({len(events)}):")
        lines.append(f"  {'─' * 78}")
        for i, evt in enumerate(events, 1):
            evt_status = evt.get("status", "?")
            status_mark = {"won": "+", "lost": "-", "open": "?", "void": "x", "cancelled": "x"}.get(evt_status, "?")

            names = evt.get("name", [])
            match_name = " vs ".join(names) if isinstance(names, list) else str(names)

            odd = evt.get("odd", {})
            market = evt.get("market", {})
            coeff = evt.get("coefficient") or odd.get("coefficient", "?")
            odd_status = odd.get("oddStatus", evt_status.upper())

            lines.append(f"  [{status_mark}] {i}. {match_name}")
            lines.append(f"       Time:      {format_dt(evt.get('date'))}")
            lines.append(f"       Market:    {market.get('name', '?')}")
            lines.append(f"       Pick:      {odd.get('name', '?')} @ {coeff}")
            lines.append(f"       Result:    {odd_status}")

            sv = odd.get("specialValue")
            if sv is not None:
                lines.append(f"       Line:      {sv}")
            lines.append("")
    else:
        lines.append(f"  [No events found. Keys: {list(data.keys())}]")

    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(description="Fetch Superbet ticket details (no login required)")

    ticket_group = parser.add_mutually_exclusive_group(required=True)
    ticket_group.add_argument("--ticket", help="Single ticket ID (e.g. 890D-QJ1HHB)")
    ticket_group.add_argument("--tickets", nargs="+", help="Multiple ticket IDs")
    ticket_group.add_argument("--file", help="File with ticket IDs (one per line)")

    parser.add_argument("--output", help="Save raw JSON results to file")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON instead of formatted output")

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
        tasks = [fetch_ticket(session, tid) for tid in ticket_ids]
        results = await asyncio.gather(*tasks)

    # Output
    if args.raw:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2, ensure_ascii=False))
    else:
        print(f"\n{'=' * 85}")
        print(f"  SUPERBET TICKET REPORT  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
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
