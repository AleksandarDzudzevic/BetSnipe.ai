"""
Meridian Bet Ticket Resolver
Fetches betslip details and match results from Meridian's API.
No login required - uses anonymous token from meridianbet.rs.

Usage:
    # Single ticket
    python meridian_tickets.py --ticket 20737716953

    # Multiple tickets
    python meridian_tickets.py --tickets 20737716953 20736310298

    # From file (one ticket ID per line)
    python meridian_tickets.py --file tickets.txt

    # Save raw JSON output
    python meridian_tickets.py --ticket 20737716953 --output results.json --raw
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup


TICKET_API = "https://online.meridianbet.com/betshop/api/v2/client-report/ticket"
SITE_URL = "https://meridianbet.rs/sr/kladjenje/fudbal"

COMMON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "sr",
    "Origin": "https://meridianbet.rs",
    "Referer": "https://meridianbet.rs/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}


async def get_anon_token(session: aiohttp.ClientSession) -> str | None:
    """Fetch anonymous token from Meridian main page (same method as scraper)."""
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "User-Agent": COMMON_HEADERS["User-Agent"],
    }
    async with session.get(SITE_URL, headers=headers) as resp:
        if resp.status != 200:
            return None
        text = await resp.text()
        soup = BeautifulSoup(text, "html.parser")
        for script in soup.find_all("script"):
            if script.string and "NEW_TOKEN" in script.string:
                try:
                    json_data = json.loads(script.string)
                    token_data = json.loads(json_data["NEW_TOKEN"])
                    return token_data.get("access_token")
                except (json.JSONDecodeError, KeyError):
                    continue
    return None


async def fetch_ticket(session: aiohttp.ClientSession, ticket_id: str, token: str) -> dict:
    """Fetch a single ticket's details from Meridian API."""
    url = f"{TICKET_API}/{ticket_id}"
    headers = {**COMMON_HEADERS, "Authorization": f"Bearer {token}"}
    async with session.get(url, headers=headers) as resp:
        if resp.status == 401:
            return {"ticket_id": ticket_id, "error": "Token expired or invalid"}
        if resp.status != 200:
            return {"ticket_id": ticket_id, "error": f"HTTP {resp.status}: {await resp.text()}"}
        data = await resp.json()
        return data.get("payload", data)


def format_result(result: dict) -> str:
    """Format match result (formattedResult) into score string."""
    if not result:
        return "-"
    periods = result.get("periods", [])
    final = result.get("finalPeriod", {})
    final_pts = final.get("points", [])

    if not periods:
        if final_pts:
            return f"{final_pts[0]}:{final_pts[1]}"
        return "-"

    period_strs = [f"{p['points'][0]}:{p['points'][1]}" for p in periods if p.get("points")]
    final_str = f"{final_pts[0]}:{final_pts[1]}" if final_pts else ""

    if final_str:
        return f"{final_str} ({', '.join(period_strs)})"
    return ", ".join(period_strs)


def format_timestamp(ts_ms: int | None) -> str:
    """Convert millisecond timestamp to readable datetime."""
    if not ts_ms:
        return "-"
    return datetime.fromtimestamp(ts_ms / 1000, tz=None).strftime("%Y-%m-%d %H:%M")


def format_ticket(data: dict) -> str:
    """Format ticket data into readable output."""
    if "error" in data:
        return f"  ERROR: {data['error']}"

    lines = []

    status = data.get("status", "?")
    status_icon = {"PAID_OUT": "WON", "LOSER": "LOST", "WINNER": "WON", "OPEN": "PENDING"}.get(status, status)

    lines.append(f"  Status:      {status_icon} ({status})")
    lines.append(f"  Type:        {data.get('ticketType', '?')}")
    lines.append(f"  Stake:       {data.get('payin', '?')} RSD")
    lines.append(f"  Total Odds:  {data.get('maximumPrice') or data.get('minimumPrice', '?')}")
    lines.append(f"  Potential:   {data.get('maximumBetwin', '?')} RSD")

    payout = data.get("payout")
    if payout:
        lines.append(f"  Payout:      {payout} RSD")

    lines.append(f"  Placed:      {format_timestamp(data.get('payinTime'))}")
    lines.append("")

    selections = data.get("selections", [])
    if selections:
        lines.append(f"  Selections ({len(selections)}):")
        lines.append(f"  {'─' * 78}")
        for i, sel in enumerate(selections, 1):
            home = sel.get("home", "?")
            away = sel.get("away", "?")
            sel_status = sel.get("status", "?")
            status_mark = {"WINNER": "+", "LOSER": "-", "OPEN": "?", "CANCELLED": "x"}.get(sel_status, "?")

            lines.append(f"  [{status_mark}] {i}. {home} vs {away}")
            lines.append(f"       {sel.get('sportName', '')} | {sel.get('leagueName', '')}")
            lines.append(f"       Start:     {format_timestamp(sel.get('eventStartTime'))}")
            lines.append(f"       Market:    {sel.get('marketName', '?')} ({sel.get('gameTemplateName', '')})")
            lines.append(f"       Pick:      {sel.get('name', '?')} @ {sel.get('price', '?')}")
            lines.append(f"       Result:    {sel_status}")

            score = format_result(sel.get("formattedResult"))
            if score != "-":
                lines.append(f"       Score:     {score}")

            if sel.get("resultTime"):
                lines.append(f"       Resolved:  {format_timestamp(sel.get('resultTime'))}")
            lines.append("")
    else:
        lines.append(f"  [No selections found. Keys: {list(data.keys())}]")

    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(description="Fetch Meridian betslip ticket details (no login required)")

    ticket_group = parser.add_mutually_exclusive_group(required=True)
    ticket_group.add_argument("--ticket", help="Single ticket ID")
    ticket_group.add_argument("--tickets", nargs="+", help="Multiple ticket IDs")
    ticket_group.add_argument("--file", help="File with ticket IDs (one per line)")

    parser.add_argument("--output", help="Save raw JSON results to file")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON instead of formatted output")
    parser.add_argument("--token", help="Manual JWT token (optional, auto-fetched if omitted)")

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
        # Get token
        if args.token:
            token = args.token
        else:
            print("Fetching anonymous token from meridianbet.rs...")
            token = await get_anon_token(session)
            if not token:
                print("ERROR: Could not fetch token from meridianbet.rs")
                sys.exit(1)

        # Fetch tickets
        tasks = [fetch_ticket(session, tid, token) for tid in ticket_ids]
        results = await asyncio.gather(*tasks)

    # Output
    if args.raw:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2, ensure_ascii=False))
    else:
        print(f"\n{'=' * 85}")
        print(f"  MERIDIAN BET TICKET REPORT  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
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
