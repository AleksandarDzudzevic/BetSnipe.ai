"""
ibet365 Ticket Resolver
Fetches betslip details and match results from 365.rs (ibet2.365.rs) API.
No login required - UUID from barcode on betslip.

Usage:
    # Single ticket (UUID from QR/barcode)
    python ibet365_tickets.py --ticket 0b570aac-300d-405d-be68-5cd4abe03526

    # Multiple tickets
    python ibet365_tickets.py --tickets 0b570aac-300d-405d-be68-5cd4abe03526 4452d6a5-0511-42ea-a8ae-b18ba315beac

    # From file (one UUID per line)
    python ibet365_tickets.py --file tickets.txt

    # Save raw JSON output
    python ibet365_tickets.py --ticket 0b570aac-300d-405d-be68-5cd4abe03526 --output results.json --raw

Ticket status codes:
    ITicket.status          : 1 = WON, -1 = LOST, 0 = PENDING
    ticketStatusTipType.status : 1 = hit, -1 = missed
"""

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

import aiohttp


TICKET_API = "https://ibet2.365.rs/ibet/profile/getTicketByUuid"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "sr",
    "Origin": "https://365.rs",
    "Referer": "https://365.rs/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

PARAMS = {
    "mobileVersion": "2.32.10.5",
    "locale": "sr",
}

SPORT_NAMES = {
    "F":   "Fudbal",
    "B":   "Košarka",
    "T":   "Tenis",
    "H":   "Hokej",
    "TT":  "Stoni tenis",
    "BO":  "Boks",
    "VB":  "Odbojka",
    "RU":  "Ragbi",
    "BB":  "Bejzbol",
    "MMA": "MMA",
    "CS":  "CS:GO",
    "LOL": "LoL",
    "DA":  "Dota",
}


async def fetch_ticket(session: aiohttp.ClientSession, uuid: str) -> dict:
    """Fetch a single ticket's details from 365.rs API."""
    url = f"{TICKET_API}/{uuid}.json"
    async with session.get(url, params=PARAMS, headers=HEADERS) as resp:
        if resp.status == 404:
            return {"uuid": uuid, "error": "Ticket not found (check UUID)"}
        if resp.status != 200:
            text = await resp.text()
            return {"uuid": uuid, "error": f"HTTP {resp.status}: {text[:200]}"}
        data = await resp.json(content_type=None)
        ticket = data.get("ITicket", data)
        ticket["_uuid"] = uuid
        return ticket


def format_ts(ts_ms: int | None) -> str:
    """Convert millisecond timestamp to readable datetime."""
    if not ts_ms:
        return "-"
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M")


def overall_status(status: int) -> str:
    """Convert ITicket.status to display string."""
    return {1: "WON", -1: "LOST", 0: "PENDING"}.get(status, f"UNKNOWN({status})")


def tip_status_mark(status: int) -> str:
    return {1: "+", -1: "-", 0: "?"}.get(status, "?")


def format_ticket(data: dict) -> str:
    """Format ticket data into readable output."""
    if "error" in data:
        return f"  ERROR: {data['error']}"

    lines = []

    status = data.get("status", 0)
    status_display = overall_status(status)

    pay_in = data.get("payIn", 0)
    win = data.get("win", 0)
    possible_win = data.get("maxTotalWin", data.get("minTotalWin", 0))
    total_odd = data.get("maxTotalOdd", data.get("minTotalOdd", "?"))
    caption = data.get("caption", "?")

    lines.append(f"  Status:      {status_display}")
    lines.append(f"  Code:        {data.get('code', data.get('_uuid', '?'))}")
    lines.append(f"  Type:        {caption}")
    lines.append(f"  Stake:       {pay_in} RSD")
    lines.append(f"  Total Odds:  {total_odd}")
    lines.append(f"  Potential:   {possible_win} RSD")

    if win and win > 0:
        lines.append(f"  Won:         {win} RSD")

    lines.append(f"  Placed:      {format_ts(data.get('creationDate'))}")
    if data.get("payoutTime"):
        lines.append(f"  Paid out:    {format_ts(data.get('payoutTime'))}")

    combos = data.get("numOfCombinations", 1)
    if combos and combos > 1:
        lines.append(f"  Combos:      {combos}")

    lines.append("")

    # Selections — nested under ticketStatusSystem → ticketStatusMatch → ticketStatusTipType
    all_matches = []
    for system in data.get("ticketStatusSystem", []):
        for match in system.get("ticketStatusMatch", []):
            all_matches.append(match)

    if all_matches:
        lines.append(f"  Selections ({len(all_matches)}):")
        lines.append(f"  {'─' * 78}")

        for i, match in enumerate(all_matches, 1):
            home = match.get("home", "?")
            away = match.get("away", "?")
            score = match.get("results") or match.get("fullTimeResult") or "-"
            sport_code = match.get("sport", "")
            sport_name = SPORT_NAMES.get(sport_code, sport_code)
            kick_off = format_ts(match.get("kickOffTime"))
            deleted = " [DELETED]" if match.get("deleted") else ""

            # Each match may have multiple tips (parlays)
            for tip in match.get("ticketStatusTipType", []):
                tip_stat = tip.get("status", 0)
                mark = tip_status_mark(tip_stat)
                tip_display = overall_status(tip_stat)

                pick = tip.get("caption", "?")
                market = tip.get("groupName", tip.get("tipType", "?"))
                odd = tip.get("odd", "?")
                special = tip.get("specialDisplay") or tip.get("special")
                if special:
                    market = f"{market} ({special})"
                live_tag = " [LIVE]" if tip.get("live") else ""

                lines.append(f"  [{mark}] {i}. {home} vs {away}{deleted}{live_tag}")
                lines.append(f"       Sport:     {sport_name}")
                lines.append(f"       Kick-off:  {kick_off}")
                lines.append(f"       Market:    {market}")
                lines.append(f"       Pick:      {pick} @ {odd}")
                lines.append(f"       Result:    {tip_display}")
                if score != "-":
                    lines.append(f"       Score:     {score}")
                lines.append("")
    else:
        lines.append(f"  [No selections found. Keys: {list(data.keys())}]")

    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(
        description="Fetch 365.rs (ibet2) betslip ticket details (no login required)"
    )

    ticket_group = parser.add_mutually_exclusive_group(required=True)
    ticket_group.add_argument("--ticket", help="Single ticket UUID (from QR/barcode on betslip)")
    ticket_group.add_argument("--tickets", nargs="+", help="Multiple ticket UUIDs")
    ticket_group.add_argument("--file", help="File with ticket UUIDs (one per line)")

    parser.add_argument("--output", help="Save raw JSON results to file")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON instead of formatted output")

    args = parser.parse_args()

    # Collect UUIDs
    if args.ticket:
        ticket_ids = [args.ticket]
    elif args.tickets:
        ticket_ids = args.tickets
    else:
        ticket_ids = Path(args.file).read_text().strip().splitlines()
        ticket_ids = [t.strip() for t in ticket_ids if t.strip()]

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_ticket(session, uid) for uid in ticket_ids]
        results = await asyncio.gather(*tasks)

    # Output
    if args.raw:
        print(json.dumps(
            results if len(results) > 1 else results[0],
            indent=2,
            ensure_ascii=False
        ))
    else:
        print(f"\n{'=' * 85}")
        print(f"  365.RS (iBet2) TICKET REPORT  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'=' * 85}")
        for uid, data in zip(ticket_ids, results):
            ticket_code = data.get("code", uid) if isinstance(data, dict) else uid
            print(f"\n{'─' * 85}")
            print(f"  TICKET: {ticket_code}  (UUID: {uid})")
            print(f"{'─' * 85}")
            print(format_ticket(data))
        print(f"{'=' * 85}\n")

    # Save to file
    if args.output:
        output_data = results if len(results) > 1 else results[0]
        Path(args.output).write_text(
            json.dumps(output_data, indent=2, ensure_ascii=False)
        )
        print(f"Results saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
