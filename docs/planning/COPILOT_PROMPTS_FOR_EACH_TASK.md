# Visualping Crawler — Ready-to-Paste Copilot Prompts
### Partitioned by Task + Target Files

**How to use**
1. Create a new empty folder `visualping-crawler`
2. Open it in VS Code / Cursor with Copilot (or any AI coding assistant)
3. First paste the **Master Context Prompt** (once)
4. Then paste the Task prompts **one by one**
5. After each task, do a quick manual test before continuing

---

## Master Context Prompt (paste this ONCE at the beginning of the chat)

```
You are helping a 4th-year CS student implement a clean, modular web crawler for the Visualping take-home challenge.

Target site: http://54.214.7.161/
HTTP Basic Auth (send on EVERY request):
  username: ahmad.droobi2
  password: 2dd4b97903ace571f147

Goal: discover and extract exactly 8 passwords of the form VISUALPING{16 hexadecimal characters}.

Hard rules you must never break:
- Never invent or guess any URL. Only follow resources discovered from responses.
- Every password is reachable from the homepage the way a real browser would.
- Not every link is an <a> tag — also look in <script src>, <img src>, <link href>, JavaScript string literals, etc.
- Passwords that appear ONLY in HTTP response headers are staging placeholders — IGNORE them.
- Stay on the same host (54.214.7.161) only.
- Completeness condition: the frontier queue is empty and every in-scope discovered URL has been visited.
- Ignore the example password VISUALPING{0000deadbeef0000}.

We will build the crawler step-by-step in separate modules. Wait for the next specific prompt before writing the next file.
```

---

## Task 1 — Project Setup & Config
**Target files:**  
`config.py` · `requirements.txt` · `README.md` · folder structure

### Prompt to paste:
```
Create a clean Python project skeleton for a Visualping web crawler challenge.

Create these files:

1. requirements.txt containing:
requests
beautifulsoup4
lxml
urllib3

2. config.py with the following constants:
- BASE_URL = "http://54.214.7.161/"
- USERNAME = "ahmad.droobi2"
- PASSWORD = "2dd4b97903ace571f147"
- PASSWORD_REGEX = r"VISUALPING\{[0-9a-fA-F]{16}\}"
- EXAMPLE_PASSWORD = "VISUALPING{0000deadbeef0000}"  # must be ignored
- MAX_PAGES = 500
- REQUEST_TIMEOUT = 10
- USER_AGENT = "VisualpingCrawler/1.0 (student challenge)"

Also compile the regex with re.compile and export it as COMPILED_PASSWORD_RE.

3. Create empty package folders:
crawler/
processors/
tests/

4. Write a short README.md that explains:
- What the crawler does
- How to install dependencies
- That we will implement it in 10 progressive tasks

Do not write any crawling logic yet. Only the skeleton and config.
```

---

## Task 2 — HTTP Fetcher
**Target file:** `crawler/fetcher.py`

### Prompt to paste:
```
Implement crawler/fetcher.py for the Visualping crawler.

Requirements:
- Use the requests library and the credentials from config.py
- Create a function:

def fetch(url: str) -> requests.Response | None:

Behaviour:
- Always send HTTP Basic Auth using USERNAME and PASSWORD from config
- Set a reasonable User-Agent from config
- Timeout = REQUEST_TIMEOUT from config
- Follow redirects
- On any network error, timeout, or unexpected exception → return None and print a short warning
- On 4xx / 5xx still return the Response object (do not raise)
- Never invent or modify the URL

Also create a small helper:
def get_content_type(response) -> str:
    return response.headers.get("Content-Type", "").lower()

Add type hints and a short docstring.
Do not implement any parsing or password extraction yet.
```

---

## Task 3 — URL Utilities
**Target file:** `crawler/url_utils.py`

### Prompt to paste:
```
Implement crawler/url_utils.py for the Visualping crawler.

Create these pure functions:

1. def normalize(url: str) -> str:
   - Remove the fragment (#...)
   - Return a clean absolute URL

2. def is_in_scope(url: str) -> bool:
   - Return True only if the host is exactly "54.214.7.161"
   - Reject any external domain

3. def make_absolute(base_url: str, relative: str) -> str | None:
   - Use urllib.parse.urljoin
   - Then normalize
   - If the result is not in scope → return None
   - Otherwise return the absolute URL

4. def clean_url(url: str) -> str:
   - Convenience wrapper: normalize + strip trailing slash inconsistently if needed

Important rules:
- Never invent new paths
- Fragments must be removed so /page and /page#section are treated as the same resource
- Keep query strings (they matter for pagination)

Add type hints and short docstrings. No network calls in this file.
```

---

## Task 4 — Frontier, Visited, Results
**Target file:** `crawler/frontier.py`

### Prompt to paste:
```
Implement crawler/frontier.py for the Visualping crawler.

Create three simple data structures:

1. class Frontier:
   - Use collections.deque internally
   - Methods: add(url), get() -> str | None, __len__, is_empty
   - add() must not insert a URL that is already in the frontier or already visited
   - Accept a visited set reference so it can check uniqueness

2. class Visited:
   - Simple set of normalized URLs
   - Methods: add(url), __contains__, __len__

3. class Results:
   - set of discovered passwords
   - Methods: add(password), get_all() -> list[str], __len__
   - Automatically ignore the EXAMPLE_PASSWORD from config

All classes should have clear docstrings. Keep the implementation simple and thread-unsafe (single-threaded crawler is enough).
```

---

## Task 5 — HTML Discovery
**Target file:** `crawler/discovery.py` (first part)

### Prompt to paste:
```
In crawler/discovery.py implement the HTML discovery function.

Function signature:
def extract_from_html(html: str, base_url: str) -> set[str]:

Requirements:
- Use BeautifulSoup with the "lxml" parser
- Extract URLs from at least these tags/attributes:
  - a[href]
  - img[src]
  - script[src]
  - link[href]
  - iframe[src]
  - form[action]
  - source[src]
  - any data-* attribute that looks like a path

- For every found reference:
  - Call make_absolute(base_url, ref) from url_utils
  - If the result is not None, add it to the returned set

- Also look inside <style> tags for CSS url(...) values

Return a set of absolute in-scope URLs.
Do not extract passwords yet. Only discovery of links/resources.
```

---

## Task 6 — Generic Text / JS / CSS Discovery
**Target file:** `crawler/discovery.py` (continue)

### Prompt to paste:
```
Extend crawler/discovery.py with a second function for non-HTML resources.

Function:
def extract_paths_from_text(text: str, base_url: str) -> set[str]:

Goal: discover paths that are hidden inside JavaScript, CSS or plain text
(for example the MENU array inside main.js).

Implementation ideas:
- Use several regexes to find quoted strings that look like paths:
  - "/something/"
  - '/static/js/foo.js'
  - path: "/docs/..."
- Also catch relative paths that start with ./ or ../
- For every match, call make_absolute(base_url, match)
- Keep only results that are in scope

Also create a convenience function:
def discover_resources(content: str, base_url: str, content_type: str) -> set[str]:
  - if "html" in content_type → call extract_from_html
  - else → call extract_paths_from_text

This is critical for the challenge because many links are injected by JavaScript.
```

---

## Task 7 — Password Extractor + Content-Type Router
**Target file:** `crawler/extractor.py`

### Prompt to paste:
```
Implement crawler/extractor.py.

1. Password extraction:
def extract_passwords(text: str) -> set[str]:
   - Use COMPILED_PASSWORD_RE from config
   - Return a set of matches
   - Explicitly discard EXAMPLE_PASSWORD
   - Also discard any match that looks malformed

2. Header rule (very important):
def extract_passwords_from_response(response) -> set[str]:
   - Extract from response.text (body) only
   - DO NOT count passwords that appear only in response.headers
   - (The challenge states header passwords are staging placeholders)

3. Optional cheap binary search:
def extract_passwords_from_bytes(data: bytes) -> set[str]:
   - Try to decode as utf-8 / latin-1 with errors="ignore"
   - Then run the same regex
   - Useful for images that contain the password as plain text

Keep the module pure (no network calls).
```

---

## Task 8 — Core Crawl Engine
**Target file:** `crawler/engine.py`

### Prompt to paste:
```
Implement the main crawl engine in crawler/engine.py.

Create a class Crawler:

def __init__(self):
   - Create Frontier, Visited, Results
   - Seed the frontier with config.BASE_URL

def run(self, max_pages: int | None = None) -> Results:
   - While frontier is not empty and under max_pages limit:
     1. Get next URL from frontier
     2. If already visited → skip
     3. Mark as visited
     4. response = fetch(url)
     5. If response is None → continue
     6. content_type = get_content_type(response)
     7. Extract passwords from the body (never from headers only)
     8. Discover new resources using discovery.discover_resources
     9. Add every new in-scope URL to the frontier
   - Return the Results object

Also implement:
def get_stats(self) -> dict:
   - pages_visited, passwords_found, frontier_remaining, etc.

Print a short progress line every 10 pages so the user can see it working.
This is the heart of the crawler.
```

---

## Task 9 — Optional Image / Media Processor
**Target file:** `processors/image.py`

### Prompt to paste:
```
Implement an optional image processor in processors/image.py.

Function:
def process_image(url: str, content: bytes) -> set[str]:

Strategy (cheap → expensive):
1. First try extract_passwords_from_bytes(content)  # many images simply embed the ASCII string
2. If nothing found and Pillow + pytesseract are available:
   - Open the image with Pillow
   - Run pytesseract.image_to_string
   - Extract passwords from the OCR text
3. If libraries are missing, just return the empty set (do not crash)

Also export a flag HAS_OCR = True/False so the engine can decide whether to call this processor.

Keep it completely optional — the core crawler must work even if OCR libraries are not installed.
```

---

## Task 10 — CLI + Final Report
**Target file:** `main.py` + polish README

### Prompt to paste:
```
Create the final entry point main.py for the Visualping crawler.

Requirements:
- Use argparse with options:
  --max-pages (default 300)
  --verbose
- Instantiate the Crawler and call run()
- After the crawl finishes, print a clean report:

=== Visualping Crawler Results ===
Passwords found (N):
VISUALPING{...}
VISUALPING{...}
...

Stats:
- Pages visited: X
- Unique URLs discovered: Y
- Frontier remaining: 0
- Time taken: Z.s

Completeness justification:
The crawl terminated because the frontier was empty.
Every URL that was discovered and was in scope was present
in the visited set. Therefore no reachable resource was left unexamined.

- Also write the passwords (one per line) into passwords.txt
- Update the README with:
  - How to run: python main.py
  - Short architecture summary
  - How we know the crawl is complete
  - Note about the “real credential leak” password (the one that appears in a JS comment as ADMIN_PASSWORD / FIXME)

Make the output submission-ready.
```

---

## How to use this pack

1. Start a new empty folder.
2. Open the folder in VS Code / Cursor with Copilot enabled.
3. Paste **Task 1** prompt → let Copilot create the skeleton.
4. Test that `python -c "import config"` works.
5. Paste **Task 2** prompt → test the fetcher alone.
6. Continue one task at a time.
7. After Task 8 you already have a working crawler that can find most (or all) passwords.
8. Task 9 and 10 are polish.

**Pro tip for Copilot:**  
After each task, write a tiny test in the chat, for example:

> “Write a 5-line test that calls extract_from_html on a small HTML snippet and prints the discovered links.”

This keeps Copilot honest and prevents it from drifting.

---

Good luck. Follow the order and the eight passwords will appear.
