# How to Run the Visualping Crawler

This guide explains how to run the crawler and how to verify that its output satisfies `VISUALPING_CRAWLER_REQUIREMENTS.md`.

## 1. Open the project

Open a terminal in the project root:

```powershell
cd "C:\Users\ahmad\OneDrive\Desktop\POP"
```

The root must contain `main.py`, `config.py`, `crawler/`, `processors/`, and `tests/`.

## 2. Install dependencies

Create and activate a virtual environment if desired, then install the pinned project dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The crawler requires `requests`, `beautifulsoup4`, and `lxml`. OCR is optional; the crawler still works without Pillow or Tesseract.

## 3. Run the tests

Run pytest through Python so the project root is included on Windows:

```powershell
python -m pytest -v
```

All tests should pass. The tests cover URL normalization and host scope, BFS frontier de-duplication, HTML/text discovery, exact password matching, binary scanning, and the header-only exclusion rule.

## 4. Run the crawler

Run the normal CLI command:

```powershell
python main.py
```

Useful options:

```powershell
python main.py --verbose
python main.py --max-pages 6000
python main.py --max-pages 10000 --workers 16
```

`--max-pages` is a safety limit. It does not add URLs or guess paths; it only prevents an unexpectedly large discovered graph from running forever.
`--workers` controls bounded parallel fetching. Discovery and queueing remain
BFS batches, while requests in one batch run concurrently to reduce network
latency.

## 5. Verify the final output

A successful complete run prints a report similar to this shape:

```text
=== Visualping Crawler Results ===
Passwords found (8):
VISUALPING{16 hexadecimal characters}
...

Stats:
- Pages / resources visited: <number>
- Unique in-scope URLs discovered: <same number>
- Frontier remaining: 0
- Time taken: <number> seconds

Completeness justification:
The frontier is empty and every discovered in-scope URL is in the visited set.
```

The exact password values are discovered at runtime and must not be guessed or hardcoded. Verify the run using all of these checks:

1. `Passwords found (8)` is displayed.
2. Exactly eight lines follow it, each matching `VISUALPING{[0-9a-fA-F]{16}}`.
3. `VISUALPING{0000deadbeef0000}` is absent.
4. `Frontier remaining: 0` is displayed.
5. The number of visited resources equals the number of unique discovered in-scope URLs.
6. `Failed fetches: 0` is displayed.
7. The completeness message says that the frontier is empty and every discovered URL was visited.
8. `passwords.txt` exists in the project root and contains exactly eight non-empty password lines.

A report that says the crawl stopped because `max-pages` was reached is **not** complete, even if it found some passwords. Increase the limit only to continue following URLs that were already discovered by fetched content.

## 6. Validate the saved file

PowerShell checks for the output file:

```powershell
Get-Content .\passwords.txt
(Get-Content .\passwords.txt | Where-Object { $_.Trim() }).Count
```

The second command must return `8`. The file must contain only the eight extracted passwords, one per line.

## Requirement mapping

| Requirement | Implementation |
| --- | --- |
| Basic Auth on every request | `crawler/fetcher.py` |
| Same-host-only crawling | `crawler/url_utils.py` and bounded redirects in `crawler/fetcher.py` |
| No invented URLs | URLs enter the frontier only through fetched response discovery |
| HTML, JS, CSS, data attributes, and comments | `crawler/discovery.py` |
| Exact password pattern | `config.py` and `crawler/extractor.py` |
| Ignore header-only passwords | `extract_passwords_from_response()` reads the body only |
| Binary/image attempt | `processors/image.py` and the engine image route |
| BFS and completeness state | `crawler/frontier.py` and `crawler/engine.py` |
| Final report and saved passwords | `main.py` |
| Unit tests | `tests/` |
| Layered explanation | `ARCHITECTURE.md` |

The password identified in the report as a likely genuine credential leak is the one found near an `ADMIN_PASSWORD` and `FIXME` JavaScript comment. That conclusion is based on the fetched body context, never on response headers alone.
