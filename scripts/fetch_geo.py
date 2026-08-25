"""Targeted fetch of the Germany-geo-locked page through a proxy / VPN exit.

The challenge server serves ``/status/eu-region/`` only to a Germany source IP
and geolocates the *real* TCP source address (forwarding headers such as
X-Forwarded-For / CF-IPCountry are ignored). So the page is reachable only from
a genuine German exit. This helper sends one authenticated request through the
proxy you supply and prints whether it unlocked and any password it found.

Usage:
    # via a German HTTP proxy
    python scripts/fetch_geo.py --proxy http://de-host:8080

    # via a local SOCKS proxy (WireGuard/OpenVPN + local SOCKS, or `ssh -D`)
    python scripts/fetch_geo.py --proxy socks5h://127.0.0.1:1080

    # or connect a system-wide Germany VPN and run with no proxy:
    python scripts/fetch_geo.py

Note: over plain HTTP the Basic Auth credentials and the recovered password
pass through the proxy operator in cleartext. Use a proxy/VPN you trust.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from config import PASSWORD, PROXY, REQUEST_TIMEOUT, USERNAME, USER_AGENT
from crawler.extractor import extract_encoded_passwords, extract_passwords, extract_passwords_from_bytes

GEO_URL = "http://54.214.7.161/status/eu-region/"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy", default=PROXY,
                        help="http://host:port or socks5h://host:port (default: $VP_PROXY)")
    parser.add_argument("--url", default=GEO_URL, help="URL to fetch (default: the geo page)")
    args = parser.parse_args()

    proxies = {"http": args.proxy, "https": args.proxy} if args.proxy else None
    print(f"Fetching {args.url}")
    print(f"Proxy   : {args.proxy or '(none — direct connection)'}")

    try:
        r = requests.get(args.url, auth=(USERNAME, PASSWORD),
                         headers={"User-Agent": USER_AGENT},
                         timeout=REQUEST_TIMEOUT, allow_redirects=False, proxies=proxies)
    except requests.RequestException as exc:
        print(f"Request failed: {exc}")
        return 2

    print(f"HTTP {r.status_code}")
    country = re.search(r"Your IP is from ([A-Za-z ]+)", r.text)
    if country:
        print(f"Server sees your region as: {country.group(1)}")

    if r.status_code == 403:
        print("Still blocked — the exit IP is not in Germany. Connect a German "
              "VPN/proxy and retry.")
        return 1

    passwords = (extract_passwords(r.text)
                 | extract_encoded_passwords(r.text)
                 | extract_passwords_from_bytes(r.content))
    if passwords:
        print(f"Unlocked. Password(s) found ({len(passwords)}):")
        for pw in sorted(passwords):
            print(f"  {pw}")
        return 0
    print("Unlocked (HTTP 2xx) but no VISUALPING{...} value in the body.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
