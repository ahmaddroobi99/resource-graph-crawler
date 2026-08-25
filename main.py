"""Command-line entry point for the Visualping crawler."""

import argparse
import logging
import time

from config import MAX_PAGES, PROXY
from crawler.engine import Crawler
from crawler.fetcher import configure_proxy


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl the Visualping challenge site.")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--proxy", default=PROXY,
        help="Route requests through a proxy / German VPN exit so the geo-locked "
             "/status/eu-region/ page is reachable, e.g. "
             "http://de-host:8080 or socks5h://127.0.0.1:1080",
    )
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.proxy:
        configure_proxy(args.proxy)

    started = time.monotonic()
    crawler = Crawler(verbose=args.verbose)
    crawler.run(max_pages=args.max_pages, workers=args.workers)
    elapsed = time.monotonic() - started
    passwords = crawler.results.get_all()
    with open("passwords.txt", "w", encoding="utf-8") as output:
        output.write("\n".join(passwords))
        if passwords:
            output.write("\n")

    stats = crawler.get_stats()
    print("=== Visualping Crawler Results ===")
    print(f"Passwords found ({len(passwords)}):")
    for password in passwords:
        print(password)
    print("\nStats:")
    print(f"- Pages / resources visited: {stats['pages_visited']}")
    print(f"- Unique in-scope URLs discovered: {stats['unique_urls_discovered']}")
    print(f"- Frontier remaining: {stats['frontier_remaining']}")
    print(f"- Failed fetches: {stats['failed_fetches']}")
    print(f"- Time taken: {elapsed:.2f} seconds")
    print("\nCompleteness justification:")
    if stats["complete"]:
        print("The frontier is empty and every discovered in-scope URL is in the visited set.")
    else:
        print("The crawl stopped before completeness was proven, likely because max-pages was reached.")
    if crawler.credential_leaks:
        print("\nLikely genuine credential leak (ADMIN_PASSWORD/FIXME context):")
        for password in sorted(crawler.credential_leaks):
            print(password)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
