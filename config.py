"""Configuration for the Visualping crawler challenge."""

import os
import re


BASE_URL = "http://54.214.7.161/"
ALLOWED_HOST = "54.214.7.161"
USERNAME = "ahmad.droobi2"
PASSWORD = "2dd4b97903ace571f147"
PASSWORD_REGEX = r"VISUALPING\{[0-9a-fA-F]{16}\}"
COMPILED_PASSWORD_RE = re.compile(PASSWORD_REGEX)
EXAMPLE_PASSWORD = "VISUALPING{0000deadbeef0000}"
MAX_PAGES = 2000
REQUEST_TIMEOUT = 10
USER_AGENT = "VisualpingCrawler/1.0 (student challenge)"

# Optional outbound proxy for geo-restricted resources. One page,
# ``/status/eu-region/``, is only served to a Germany source IP; the server
# geolocates the real TCP source address and ignores forwarding headers
# (X-Forwarded-For, CF-IPCountry, etc.), so the only way in is to originate the
# request from a genuine German exit. Point this at a German HTTP/SOCKS proxy or
# VPN exit to reach it. Set via ``--proxy`` or the ``VP_PROXY`` environment
# variable. Examples:
#   http://user:pass@de-host:8080
#   socks5h://127.0.0.1:1080   (requires ``pip install requests[socks]``)
# ``socks5h`` (vs ``socks5``) resolves DNS through the proxy, which is usually
# what you want for a VPN exit. Leave as None to fetch directly.
PROXY = os.environ.get("VP_PROXY") or None

# Query parameters that never identify a distinct resource on this site.
# The challenge sprinkles analytics/campaign tags (``utm_*``, ``ref``),
# cache-busting versions (``v``, ``hl``) and an unbounded ``page`` cursor for the
# "generated on demand" monitoring feed onto otherwise-identical URLs. Left in,
# these mint endless new URLs and the frontier never drains. Dropping them during
# normalization collapses those duplicates so BFS can reach an empty frontier and
# prove completeness (see docs/VISUALPING_CRAWLER_REQUIREMENTS.md, Task 3).
TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "v", "hl", "sid", "session", "gclid", "fbclid", "_", "page",
})
