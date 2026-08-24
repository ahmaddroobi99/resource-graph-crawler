"""Command-line entry point for the Visualping crawler."""

import argparse
import logging
import time

from config import MAX_PAGES
from crawler.engine import Crawler


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl the Visualping challenge site.")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    started = time.monotonic()
    crawler = Crawler(verbose=args.verbose)
    crawler.run(max_pages=args.max_pages)
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
