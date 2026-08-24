# Visualping Crawler Challenge, Requirements & Architecture


  
**Goal:** Build a complete, production-style web crawler that discovers and extracts all 8 hidden passwords of the form `VISUALPING{16_hex_chars}` from the challenge site.

**Target site:** `http://54.214.7.161/`  
**Authentication:** HTTP Basic Auth  
- Username: `ahmad.droobi2`  
- Password: `2dd4b97903ace571f147`  

**Password format (exact):**
```
VISUALPING{[0-9a-fA-F]{16}}
```

**Important rules from the challenge:**
- Every password is reachable from the homepage by following real browser-reachable resources.
- Do **not** guess URLs, use wordlists, or read robots.txt tricks.
- Not everything a browser can reach is an `<a>` tag. Look at **all** resources the server returns (HTML, JS, CSS, images, etc.).
- Passwords found **only** in HTTP response headers are staging placeholders — **ignore them**.
- You must be able to prove the crawl is complete (frontier empty + visited set).

---

## High-Level Architecture

Think of the website as a **directed graph** of resources:

```
URL = node
Reference (href, src, path string, etc.) = edge
```

Your crawler performs a systematic graph traversal (BFS recommended).

### Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  10. CLI + Report (results, stats, completeness proof)      │
└──────────────────────────────▲──────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────┐
│  9. Optional Processors (Image OCR, PDF text, etc.)         │
└──────────────────────────────▲──────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────┐
│  7. Content-Type Router + Password Extractor                │
└──────────────────────────────▲──────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────┐
│  5–6. Discovery (HTML parser + generic text/JS/CSS paths)   │
└──────────────────────────────▲──────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────┐
│  4. Frontier (Queue) + Visited Set + Results Set            │
└──────────────────────────────▲──────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────┐
│  3. URL Utilities (normalize, resolve, scope filter)        │
└──────────────────────────────▲──────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────┐
│  2. HTTP Fetcher (Basic Auth, timeout, redirects, status)   │
└──────────────────────────────▲──────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────┐
│  1. Config + Project Skeleton                               │
└─────────────────────────────────────────────────────────────┘
```

### Horizontal Data Flow (one iteration)

```
SEED URL
   │
   ▼
Frontier ←─── new URLs discovered
   │
   ▼
Visited check ──→ already seen? → skip
   │
   ▼
Fetcher (HTTP + Auth)
   │
   ▼
Content-Type classification
   │
   ├── text/html      → HTML Discovery + Password Extract
   ├── text/js / css  → Generic path Discovery + Password Extract
   ├── image/*        → (optional) OCR → Password Extract
   └── other          → try decode as text → Password Extract
   │
   ▼
Results set (passwords) + Frontier (new URLs)
```

**Completeness condition:**  
`frontier is empty` **AND** every discovered in-scope URL is in the `visited` set.

---

## 10 Sequential Tasks

Implement the tasks **in order**. Each task builds on the previous one and should be independently testable. After finishing a task, run a small test before moving on.

### Task 1 — Project Setup & Configuration

**Goal:** Create a clean Python project that a 4th-year student (or Copilot) can open and understand immediately.

**Deliverables:**
- `requirements.txt` with:
  ```
  requests
  beautifulsoup4
  lxml
  # optional later:
  # pillow
  # pytesseract
  ```
- `config.py` containing:
  - Base URL
  - Username / password
  - Password regex pattern (compiled)
  - Max pages safety limit (e.g. 500)
  - Request timeout
  - User-Agent string
- `README.md` skeleton explaining what the crawler does
- Project structure:
  ```
  visualping_crawler/
  ├── main.py
  ├── config.py
  ├── crawler/
  │   ├── __init__.py
  │   ├── fetcher.py
  │   ├── url_utils.py
  │   ├── frontier.py
  │   ├── discovery.py
  │   ├── extractor.py
  │   └── engine.py
  ├── processors/          # optional, Task 9
  │   └── image.py
  ├── tests/
  └── README.md
  ```

**Acceptance criteria:**
- `python -c "from config import ..."` works
- README clearly states the challenge goal and the 10-task plan

---

### Task 2 — HTTP Fetcher with Basic Auth

**Goal:** One reliable place that talks to the network.

**Implement `crawler/fetcher.py`:**
- Function `fetch(url: str) -> Response | None`
- Always sends HTTP Basic Auth
- Handles timeouts, connection errors, and non-2xx statuses gracefully
- Follows redirects (but stays in scope — see Task 3)
- Returns the full response object (status, headers, content, text, content-type)
- Logs (or returns) useful debug info

**Acceptance criteria:**
- Successfully fetches `http://54.214.7.161/` and prints status 200 + content-type
- Correctly authenticates (no 401)
- Does not crash on 403 / 404

---

### Task 3 — URL Utilities & Scope Control

**Goal:** Never crawl the whole internet and never treat the same page as two different URLs.

**Implement `crawler/url_utils.py`:**
- `normalize(url: str) -> str`
  - Resolve relative URLs against a base
  - Strip URL fragments (`#...`)
  - Optionally strip common tracking query params if you want stricter deduplication
- `is_in_scope(url: str) -> bool`
  - Only allow host `54.214.7.161`
- `make_absolute(base: str, ref: str) -> str | None`

**Acceptance criteria:**
- `"/docs/"` relative to homepage becomes `http://54.214.7.161/docs/`
- `"../about#section"` is normalized correctly
- External domains are rejected
- Fragments are removed so `/page` and `/page#foo` are treated as the same resource

---

### Task 4 — Frontier, Visited Set, Results Set

**Goal:** The three core data structures of any real crawler.

**Implement `crawler/frontier.py` (or put inside engine):**
- `Frontier` class using a queue (BFS recommended)
  - `add(url)`
  - `get()` → next URL or None
  - `empty` property
- `Visited` set (hash set of normalized URLs)
- `Results` set (the discovered passwords)

**Acceptance criteria:**
- Adding the same URL twice does not create duplicates in the frontier
- Once a URL is marked visited it is never fetched again
- Passwords are stored in a set (automatic de-duplication)

---

### Task 5 — HTML Resource Discovery

**Goal:** Extract every possible reference a browser could follow from HTML.

**Implement `crawler/discovery.py` → `extract_from_html(html: str, base_url: str) -> set[str]`**

Extract at least:
- `<a href="...">`
- `<img src="...">`
- `<script src="...">`
- `<link href="...">`
- `<iframe src="...">`
- `<form action="...">`
- Any `data-*` attributes that contain paths (bonus)
- CSS `url(...)` if present inside `<style>`

Use BeautifulSoup (preferred) or careful regex.

**Acceptance criteria:**
- From the homepage HTML you discover at least the main nav links + `/static/css/style.css` + `/static/js/main.js`
- Relative links are turned into absolute in-scope URLs

---

### Task 6 — Generic Text / JavaScript / CSS Discovery

**Goal:** Catch resources that are **not** in classic HTML tags (the key insight of this challenge).

**Extend discovery:**
- `extract_paths_from_text(text: str, base_url: str) -> set[str]`
- Look for quoted strings that look like paths: `"/something/"`, `'/static/js/foo.js'`, etc.
- Especially useful inside `.js` files (the homepage’s `main.js` dynamically injects extra navigation links this way).

**Acceptance criteria:**
- From `/static/js/main.js` you discover the extra MENU paths such as `/docs/upstream-sample-channel/`, `/notes/archive-region/`, etc.
- No false-positive external domains are added

---

### Task 7 — Content-Type Router + Password Extractor

**Goal:** Decide what to do with each response and reliably pull out passwords.

**Implement `crawler/extractor.py`:**
- Compiled regex: `VISUALPING\{[0-9a-fA-F]{16}\}`
- Function `extract_passwords(text: str) -> set[str]`
- Ignore the example password `VISUALPING{0000deadbeef0000}` (it is only a format illustration)
- **Critical rule:** If a password appears *only* in response headers, discard it (per challenge instructions)
- Also try a cheap ASCII search on raw response bytes for the string `VISUALPING{` (useful for images or binary resources before full OCR)

**Router logic (inside engine):**
```
if content-type contains "html":
    discover HTML links + extract passwords from body
elif content-type contains "javascript" or "css" or "json" or "text":
    discover path strings + extract passwords from body
elif content-type starts with "image/":
    (optional) send to image processor
else:
    try decode as text and extract
```

**Acceptance criteria:**
- Correctly finds `VISUALPING{349a583fba34c301}` inside `/static/js/analytics.js`
- Never reports a header-only password as a real result

---

### Task 8 — Core Crawl Engine (BFS Loop)

**Goal:** Tie everything together into a working crawler.

**Implement `crawler/engine.py`:**
```
seed = base_url
frontier.add(seed)

while not frontier.empty:
    url = frontier.get()
    if url in visited: continue
    visited.add(url)

    response = fetcher.fetch(url)
    if response is None: continue

    # classify by content-type
    # extract passwords → results
    # extract new URLs → frontier (after normalize + scope check)
```

Add a safety `max_pages` limit so a bug cannot run forever.

**Acceptance criteria:**
- Running the engine from the homepage eventually stops
- You can print: number of pages visited, number of passwords found, remaining frontier size
- You can articulate the completeness condition: “Frontier is empty and every discovered in-scope URL has been visited.”

---

### Task 9 — Optional Advanced Processors (Images / OCR)

**Goal:** Handle the possibility that a password lives inside an image (the challenge hints that resources are not always text).

**Implement `processors/image.py` (optional but impressive):**
- Download image bytes
- First try a cheap ASCII/byte search for the string `VISUALPING{` (many images simply embed the text)
- If needed, use Pillow + pytesseract (or easyocr) to run OCR
- Feed any recovered text into the same password extractor

**Also consider:**
- Any PDF resources (use `pypdf` or `pdfminer` if they appear)

**Acceptance criteria:**
- If an image contains a readable `VISUALPING{...}` string, it is recovered
- The processor is cleanly optional — the core crawler still works without OCR libraries installed

---

### Task 10 — CLI, Final Report & Completeness Story

**Goal:** Produce something you can actually submit.

**Implement `main.py`:**
- Parse any CLI flags you want (e.g. `--max-pages`, `--verbose`)
- Run the full crawl
- Print a clean report:
  ```
  === Visualping Crawler Results ===
  Passwords found (N):
  VISUALPING{...}
  VISUALPING{...}
  ...

  Stats:
  - Pages / resources visited: X
  - Unique in-scope URLs discovered: Y
  - Frontier remaining: 0
  - Time taken: Z seconds

  Completeness justification:
  The crawl terminated because the frontier was empty.
  Every URL that was ever discovered and was in scope
  was present in the visited set. Therefore no reachable
  resource was left unexamined.
  ```
- Write the eight passwords (one per line) to a file `passwords.txt`
- Update the README with:
  - How to run
  - Architecture summary
  - How you know the crawl is complete
  - Any interesting findings (e.g. the admin password left in a JS comment)

**Acceptance criteria:**
- One command produces the final answer
- You can answer the form questions:
  1. All eight passwords
  2. Link to your code
  3. Approach + completeness reasoning
  4. (Optional) AI session log
  5. Which password looks like a real credential leak and why  
     (strong candidate: the one that appears inside a JavaScript comment framed as a temporary hardcoded `ADMIN_PASSWORD` / `FIXME(ops)` — classic real-world credential leak pattern)

---

## Recommended Implementation Order for Copilot / Student

1. Do Task 1 completely (folder + config + README).
2. Implement and unit-test Task 2 (fetcher) in isolation.
3. Implement and unit-test Task 3 (URL utils).
4. Implement Task 4 (data structures).
5. Implement Task 5 + 6 (discovery) and test on the homepage + `main.js`.
6. Implement Task 7 (extractor) and verify it finds the known password in `analytics.js`.
7. Wire everything in Task 8 and run a limited crawl (`max_pages=50`).
8. Only then add Task 9 if you still have missing passwords.
9. Polish with Task 10 and write a clear completeness story.

---

## Testing Strategy (important for a 4th-year student)

- Write small unit tests for:
  - URL normalization
  - Password regex
  - HTML link extraction on a tiny fixture HTML string
  - Scope filter
- After the core loop works, run the real site with a low `max_pages` first, inspect the frontier, then raise the limit.
- Keep a `DEBUG` flag that prints every newly discovered URL and every password as soon as it is found.

---

## Final Mental Model (one sentence)

A crawler is a program that systematically traverses a graph of discoverable resources, maintaining a frontier of pending resources and a visited set, fetching each resource within a defined scope, parsing its content to discover additional resources, and processing the returned data until the frontier is exhausted.

That is exactly what this challenge is testing — and exactly the skill set that maps to the larger Human Data Platforms / document-intelligence engineering role.

---

**Good luck. Build it layer by layer, test each layer, and the eight passwords will appear.**
