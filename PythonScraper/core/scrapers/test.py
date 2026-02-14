#!/usr/bin/env python3
"""
Scraper test bench for BetSnipe.ai

Usage:
    python -m core.scrapers.test
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

import aiohttp
from aiohttp import ClientTimeout

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger('aiohttp').setLevel(logging.WARNING)

# ---------- CONFIG ----------
TEST_EVENT_ID = 18260775
BASE_API = "https://online.meridianbet.com/betshop/api"
SITE_URL = "https://meridianbet.rs"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "sr",
    "Origin": SITE_URL,
    "Referer": f"{SITE_URL}/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
}


async def try_get_token_from_html(session: aiohttp.ClientSession) -> str | None:
    """Method 1: Get token from the HTML page (existing approach)."""
    logger.info("--- Method 1: Token from HTML page ---")
    url = f"{SITE_URL}/sr/kladjenje/fudbal"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "User-Agent": HEADERS["User-Agent"],
    }

    try:
        async with session.get(url, headers=headers) as resp:
            logger.info(f"  HTML page status: {resp.status}")
            text = await resp.text()
            logger.info(f"  HTML size: {len(text)} bytes")

            # Search for token patterns in the page
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, "html.parser")

            for script in soup.find_all("script"):
                if not script.string:
                    continue

                # Try NEW_TOKEN pattern (old approach)
                if "NEW_TOKEN" in script.string:
                    logger.info("  Found NEW_TOKEN in script tag!")
                    try:
                        data = json.loads(script.string)
                        if "NEW_TOKEN" in data:
                            token_data = json.loads(data["NEW_TOKEN"])
                            if "access_token" in token_data:
                                token = token_data["access_token"]
                                logger.info(f"  Token: {token[:50]}...")
                                return token
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"  Failed to parse NEW_TOKEN: {e}")

                # Search for any JWT-like string
                if "eyJ" in script.string:
                    import re
                    tokens = re.findall(r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', script.string)
                    if tokens:
                        logger.info(f"  Found {len(tokens)} JWT(s) in script tags")
                        for i, t in enumerate(tokens):
                            logger.info(f"    JWT {i+1}: {t[:60]}...")
                        return tokens[0]

            logger.warning("  No token found in HTML")
            return None

    except Exception as e:
        logger.error(f"  Error: {e}")
        return None


async def try_get_token_from_oauth(session: aiohttp.ClientSession) -> str | None:
    """Method 2: Try common OAuth/token endpoints."""
    logger.info("--- Method 2: OAuth token endpoint ---")

    # Common token endpoints to try
    endpoints = [
        f"{BASE_API}/oauth/token",
        f"{BASE_API}/v1/auth/token",
        f"{BASE_API}/auth/token",
        "https://online.meridianbet.com/oauth/token",
        "https://online.meridianbet.com/auth/token",
        f"{BASE_API}/v1/token",
    ]

    # Common payloads for anonymous/guest tokens
    payloads = [
        {"grant_type": "client_credentials", "client_id": "web-serbia"},
        {"grant_type": "client_credentials", "client_id": "web-serbia", "platform": "WEB_DESKTOP"},
    ]

    for url in endpoints:
        for payload in payloads:
            try:
                async with session.post(url, json=payload, headers=HEADERS) as resp:
                    status = resp.status
                    body = await resp.text()
                    logger.info(f"  POST {url} -> {status}")
                    if status == 200:
                        data = json.loads(body)
                        token = data.get("access_token") or data.get("token")
                        if token:
                            logger.info(f"  Got token: {token[:50]}...")
                            return token
                        logger.info(f"  Response: {body[:200]}")
                    elif status != 404:
                        logger.info(f"  Response: {body[:200]}")
            except Exception as e:
                logger.debug(f"  {url} failed: {e}")

    # Also try GET requests
    for url in endpoints:
        try:
            async with session.get(url, headers=HEADERS) as resp:
                status = resp.status
                if status == 200:
                    body = await resp.text()
                    logger.info(f"  GET {url} -> {status}: {body[:200]}")
                    data = json.loads(body)
                    token = data.get("access_token") or data.get("token")
                    if token:
                        return token
        except Exception:
            pass

    logger.warning("  No OAuth endpoint found")
    return None


async def try_no_auth(session: aiohttp.ClientSession) -> bool:
    """Method 3: Check if endpoints work without auth."""
    logger.info("--- Method 3: Test without auth ---")

    # Test leagues endpoint (might not need auth)
    urls = [
        (f"{BASE_API}/v1/standard/sport/58/leagues?page=0&time=ALL&groupIndices=0,0,0", "Leagues (football)"),
        (f"{BASE_API}/v2/events/{TEST_EVENT_ID}", "Single event"),
        (f"{BASE_API}/v2/events/{TEST_EVENT_ID}/markets", "Event markets"),
    ]

    for url, name in urls:
        try:
            async with session.get(url, headers=HEADERS) as resp:
                status = resp.status
                body = await resp.text()
                logger.info(f"  {name}: {status} ({len(body)} bytes)")
                if status == 200:
                    logger.info(f"    Works without auth!")
                    data = json.loads(body)
                    logger.info(f"    Keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                    return True
                else:
                    logger.info(f"    Response: {body[:150]}")
        except Exception as e:
            logger.error(f"  {name}: {e}")

    return False


async def fetch_event(session: aiohttp.ClientSession, token: str):
    """Fetch the test event with auth token."""
    logger.info(f"--- Fetching event {TEST_EVENT_ID} ---")

    auth_headers = {**HEADERS, "Authorization": f"Bearer {token}"}

    # Fetch event details
    url = f"{BASE_API}/v2/events/{TEST_EVENT_ID}"
    start = time.time()
    async with session.get(url, headers=auth_headers) as resp:
        elapsed = time.time() - start
        logger.info(f"  Event: {resp.status} ({elapsed:.2f}s)")

        if resp.status == 200:
            data = await resp.json()
            print_event(data)
            return data
        else:
            body = await resp.text()
            logger.error(f"  Failed: {body[:300]}")
            return None


async def fetch_event_markets(session: aiohttp.ClientSession, token: str):
    """Fetch markets/odds for the test event."""
    logger.info(f"--- Fetching markets for {TEST_EVENT_ID} ---")

    auth_headers = {**HEADERS, "Authorization": f"Bearer {token}"}

    url = f"{BASE_API}/v2/events/{TEST_EVENT_ID}/markets"
    start = time.time()
    async with session.get(url, headers=auth_headers) as resp:
        elapsed = time.time() - start
        logger.info(f"  Markets: {resp.status} ({elapsed:.2f}s)")

        if resp.status == 200:
            data = await resp.json()
            print_markets(data)
            return data
        else:
            body = await resp.text()
            logger.error(f"  Failed: {body[:300]}")
            return None


def print_event(data: dict):
    """Pretty print event data."""
    print()
    print("=" * 60)
    print("  EVENT DATA")
    print("=" * 60)
    # Print full JSON indented for inspection
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str)[:3000])
    if len(json.dumps(data)) > 3000:
        print(f"  ... (truncated, full size: {len(json.dumps(data))} bytes)")
    print()


def print_markets(data: dict):
    """Pretty print markets data."""
    print()
    print("=" * 60)
    print("  MARKETS DATA")
    print("=" * 60)

    payload = data.get("payload", data) if isinstance(data, dict) else data

    if isinstance(payload, list):
        print(f"  Total market groups: {len(payload)}")
        print()
        for group in payload:
            market_name = group.get("marketName", "?")
            markets = group.get("markets", [])
            print(f"  [{market_name}] ({len(markets)} markets)")
            for market in markets[:3]:
                selections = market.get("selections", [])
                handicap = market.get("handicap", "")
                over_under = market.get("overUnder", "")
                prefix = ""
                if handicap:
                    prefix = f" HC={handicap}"
                if over_under:
                    prefix = f" O/U={over_under}"
                sel_str = " | ".join(
                    f"{s.get('name', '?')}={s.get('price', '?')}"
                    for s in selections
                )
                print(f"    {prefix} {sel_str}")
            if len(markets) > 3:
                print(f"    ... +{len(markets) - 3} more")
        print()
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str)[:3000])
    print()


async def main():
    print()
    print("=" * 60)
    print("  MERIDIAN SCRAPER TEST")
    print(f"  Event ID: {TEST_EVENT_ID}")
    print("=" * 60)
    print()

    timeout = ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Step 1: Try to get a token
        token = None

        # Try no-auth first (fastest if it works)
        no_auth_works = await try_no_auth(session)

        if not no_auth_works:
            # Try HTML scraping
            token = await try_get_token_from_html(session)

            # Try OAuth endpoints
            if not token:
                token = await try_get_token_from_oauth(session)

            if not token:
                print()
                print("  FAILED: Could not obtain auth token.")
                print("  Paste a token manually below (from browser DevTools):")
                print()
                token = input("  Bearer token: ").strip()
                if not token:
                    print("  No token provided. Exiting.")
                    return

            # Decode token to check expiry
            try:
                import base64
                payload_b64 = token.split('.')[1]
                # Add padding
                payload_b64 += '=' * (4 - len(payload_b64) % 4)
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                exp = payload.get('exp', 0)
                created = payload.get('created_at', 0)
                logger.info(f"  Token client_id: {payload.get('client_id')}")
                logger.info(f"  Token expires: {exp} (in {exp - time.time():.0f}s)")
            except Exception as e:
                logger.debug(f"  Could not decode token: {e}")

            # Step 2: Fetch the event
            await fetch_event(session, token)

            # Step 3: Fetch markets
            await fetch_event_markets(session, token)

        else:
            logger.info("Endpoints work without auth - fetching directly")
            await fetch_event(session, "")
            await fetch_event_markets(session, "")

    print("=" * 60)
    print("  DONE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
