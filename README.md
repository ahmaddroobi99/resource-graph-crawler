# Visualping Crawler

An authenticated, breadth-first web crawler for the Visualping take-home challenge. It starts at
`http://54.214.7.161/`, follows only same-host resources discovered from fetched content (no URL
guessing), and extracts every password of the exact form `VISUALPING{[0-9a-fA-F]{16}}` — from HTML,
JavaScript, image pixels, image metadata, and a Germany-geo-locked page. When the frontier drains,
it prints a **provable** completeness statement.

> Recovered values are written to `passwords.txt`, which is **git-ignored**. One resource,
> `/status/eu-region/`, is only served to a German source IP; proxy / SOCKS / Tor support is built in
> (see [Quick Start](#quick-start) and [scripts/fetch_geo.py](scripts/fetch_geo.py)).

---

## Features

| Capability | Where | Notes |
|---|---|---|
| HTTP Basic Auth on every request | `crawler/fetcher.py` | Credentials sent on all fetches; bounded redirects; retry with backoff |
| Same-host scope + tracking-param stripping | `crawler/url_utils.py` | Drops `utm_*`, `ref`, `v`, `hl`, `page`, … so the frontier stays finite |
| BFS state (Frontier / Visited / Results) | `crawler/frontier.py` | Deduplicated FIFO queue; example password excluded from results |
| Resource discovery | `crawler/discovery.py` | `<a> <img> <script> <link> <iframe> <form> <source> <video> <audio>`, `data-*`, inline & block CSS `url()`, quoted paths in JS/CSS |
| Plain-text extraction | `crawler/extractor.py` | Exact regex; ignores the documented example value |
| Encoded extraction | `crawler/extractor.py` | JS char-code arrays → `String.fromCharCode`; Base64 blobs |
| Multi-encoding byte scan | `crawler/extractor.py` | UTF-8 / UTF-16-LE / UTF-16-BE / Latin-1 — catches UTF-16 EXIF metadata |
| Image processing (optional) | `processors/image.py` | Byte scan first, then Tesseract OCR for pixel-rendered text |
| Header-only passwords ignored | by design | Only response **bodies** are inspected; header values are staging placeholders |
| Proxy / SOCKS / Tor support | `crawler/fetcher.py`, `main.py` | Reach the German geo-page via a real DE exit IP |
| Genuine-leak detection | `crawler/engine.py` | Flags passwords sitting in `ADMIN_PASSWORD` / `FIXME` context |
| Provable completeness | `crawler/engine.py` | Frontier empty ∧ no failures ∧ every discovered URL visited |
| Unit tests | `tests/` | 17 tests across url_utils, extractor, discovery, frontier |

---

## Project structure

```
POP/
├── main.py                 # CLI: run crawl, print report, write passwords.txt
├── config.py               # BASE_URL, auth, regex, tracking params, proxy
├── crawler/
│   ├── __init__.py
│   ├── engine.py           # BFS orchestration + completeness predicate
│   ├── fetcher.py          # authenticated HTTP, redirects, retries, proxy
│   ├── frontier.py         # Frontier (queue) · Visited (set) · Results (set)
│   ├── url_utils.py        # normalize · is_in_scope · make_absolute
│   ├── discovery.py        # browser-reachable reference extraction
│   └── extractor.py        # text / char-code / base64 / multi-encoding byte scan
├── processors/
│   ├── __init__.py
│   └── image.py            # optional byte scan + Tesseract OCR
├── scripts/
│   └── fetch_geo.py        # one-shot fetch of the German geo-page via proxy/Tor
├── tests/
│   ├── test_url_utils.py
│   ├── test_extractor.py
│   ├── test_discovery.py
│   └── test_frontier.py
├── docs/
│   └── SOLUTION.md         # detailed solution walkthrough + diagrams
├── requirements.txt
├── .gitignore
├── passwords.txt           # git-ignored crawl output
└── README.md
```

---

## Quick Start

```bash
pip install -r requirements.txt

# Full crawl → prints report, writes passwords.txt
python main.py

# Verbose progress (per-page counters)
python main.py --verbose

# Run the test suite
pytest -v
```

**Optional OCR** (for passwords rendered as image pixels). Needs the Tesseract engine plus the Python
packages in `requirements.txt`:

```bash
winget install UB-Mannheim.TesseractOCR    # Windows
python main.py                             # OCR is auto-detected; crawl runs fine without it
```

**German geo-page** (`/status/eu-region/`). The server geolocates the real TCP source IP and ignores
forwarding headers, so a genuine German exit is required. Free, reproducible route via a Tor node
forced to Germany:

```bash
# torrc:  SocksPort 9050 | ExitNodes {de} | StrictNodes 1 | GeoIPFile <tor>/geoip | GeoIPv6File <tor>/geoip6
tor -f torrc                                            # wait for "Bootstrapped 100%"
python scripts/fetch_geo.py --proxy socks5h://127.0.0.1:9050
# or route the whole crawl through it:
python main.py --proxy socks5h://127.0.0.1:9050
```

CLI flags: `--max-pages N` (default 2000), `--workers N` (parallel fetches), `--proxy URL`, `--verbose`.

---

## Architecture

Five small layers compose into one BFS loop:

```
main.py ─► engine.Crawler ─► frontier.get()
                                  │
                                  ▼
                          fetcher.fetch(url)         (Basic-Auth, redirects, proxy)
                                  │  response
                 ┌────────────────┼────────────────────────────┐
                 ▼                                               ▼
        image/* ─► processors.image                 non-image ─► decode text
        (byte scan → OCR)                            │
                 │                                   ├─ extractor.extract_passwords          (plain / comment / data-attr)
                 │                                   ├─ extractor.extract_encoded_passwords  (char-code array / base64)
                 │                                   ├─ extractor.extract_passwords_from_bytes (UTF-16 / Latin-1)
                 ▼                                   └─ discovery.discover_resources ─► url_utils.normalize
           Results.update  ◄─────────────────────────────────────────┘        │
                                                       in-scope & unseen? ─► frontier.add
```

**Data flow:** a URL leaves the frontier, is fetched with Basic Auth, and its body is run through every
extraction strategy in parallel while discovery mines it for new references. In-scope, normalized,
unseen references go back onto the frontier. The loop ends when the frontier is empty.

See [docs/SOLUTION.md](docs/SOLUTION.md) for full sequence diagrams, the BFS graph, and the
extraction decision tree.

---

## Completeness condition

The crawl reports itself complete only when the exact predicate in `crawler/engine.py` holds:

```python
"complete": (self.frontier.empty and not self.failed and
             self.discovered.issubset(self.visited.as_set())),
```

In words: **the frontier is empty, no fetch failed, and every discovered in-scope URL is in the
visited set.** Because `url_utils.normalize` strips tracking/pagination parameters, the otherwise
unbounded `/report/?page=N` feed collapses to a single node — which is what makes an empty frontier
reachable and the completeness claim meaningful rather than a timeout.

---

## How the passwords are found

The site hides each password with a different technique; a single regex is not enough. Recovered
values land in the git-ignored `passwords.txt` — the table lists the **method and location**, not the
secrets.

| Method | Source | Detail |
|---|---|---|
| Plain-text regex | `/static/js/analytics.js` | In a `// FIXME(ops)` **`ADMIN_PASSWORD`** comment — flagged as the genuine credential leak |
| Plain-text regex | `/notes/diff-socket-socket/` | Inside an HTML `<!-- ... -->` comment |
| Plain-text regex | `/wiki/detect-embed/` | Inside a `data-*` attribute |
| Char-code decode | `/static/js/theme-switcher.js` | `[86, 73, 83, …]` → `String.fromCharCode`, then regex |
| OCR | `/static/img/whiteboard-scan.png` | Text rendered as pixels → Tesseract |
| Multi-encoding byte scan | `/static/img/field-visit.jpg` | EXIF `UserComment` stored as UTF-16 |
| Geo + proxy/Tor | `/status/eu-region/` | Unlocked only from a German exit IP |

**Deeper metadata (JPEG COM segments).** The JPEGs also carry a bare 16-hex string in a JPEG `COM`
comment segment — no `VISUALPING{}` wrapper, so a strict regex skips it. These are recovered by manual
segment parsing and discussed (with the decoy analysis) in [docs/SOLUTION.md](docs/SOLUTION.md#9-the-8th-password--jpeg-com-comment-segments-debugging-deeper).

---

## Testing

```bash
pytest -v
```

17 unit tests cover the critical, pure-logic modules:

| Test file | Covers |
|---|---|
| `tests/test_url_utils.py` | normalization, tracking-param stripping, scope checks, absolute resolution |
| `tests/test_extractor.py` | plain regex, example-value exclusion, char-code arrays, base64, multi-encoding bytes |
| `tests/test_discovery.py` | HTML/attribute/CSS reference extraction |
| `tests/test_frontier.py` | queue dedup, visited semantics, results dedup |

The crawl itself is deterministic given the site; network-dependent behavior is isolated in
`fetcher.py` and exercised by running `python main.py`.

---

## Submission notes (Google form)

- **Passwords:** the values written to `passwords.txt` after a run (git-ignored, not committed).
- **Code link:** this repository.
- **Approach & completeness:** summarized above and detailed in [docs/SOLUTION.md](docs/SOLUTION.md) —
  BFS over browser-reachable resources, tracking-param stripping for a finite frontier, five
  complementary extractors, and the `frontier-empty ∧ discovered ⊆ visited` proof.
- **Genuine credential leak:** the `ADMIN_PASSWORD` value in `analytics.js` (`FIXME(ops)` context) —
  a hard-coded admin credential shipped in client-side JS, i.e. an accidental commit rather than a
  puzzle. The crawler flags it automatically via `Crawler.credential_leaks`.

---

## Notable design decisions

1. **Tracking-parameter stripping makes completeness provable.** Dropping `utm_*`, `ref`, `v`, `page`,
   … collapses infinite duplicate URLs so the frontier can actually drain to empty.
2. **Five complementary extractors, not one regex.** Plain text, char-code arrays, Base64, multi-encoding
   byte scan, and OCR — because the passwords are deliberately *not* stored the way you'd first expect.
3. **Optional layers never crash the core.** Missing Tesseract/OCR or an unreadable image degrades
   gracefully; the text crawl always completes.
4. **First-class proxy support.** The server geolocates the real client IP and ignores
   `X-Forwarded-For`, so header spoofing cannot work — a genuine German exit (proxy/Tor) is the only way
   in, and the fetcher supports it on every request.
5. **Body-only extraction.** Header-only password values are treated as staging placeholders and never
   collected, per the challenge rules.
```
