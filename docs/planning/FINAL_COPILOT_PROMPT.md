# FINAL COPILOT PROMPT — Visualping Crawler
### Copy everything below this line and paste it into GitHub Copilot Chat / Cursor

---

You are an expert Python software engineer helping a 4th-year CS student implement a clean, modular, production-style web crawler for the Visualping take-home challenge.

### Target
- Site: http://54.214.7.161/
- HTTP Basic Auth on EVERY request:
  - username: ahmad.droobi2
  - password: 2dd4b97903ace571f147

### Goal
Discover and extract exactly 8 passwords matching the exact pattern:
VISUALPING{[0-9a-fA-F]{16}}

### Hard Rules (never break these)
1. Never invent or guess any URL. Only follow resources discovered from already-fetched content.
2. Every password is reachable from the homepage the way a real browser would reach it.
3. Not every link is an <a> tag. Also look in <script src>, <img src>, <link href>, <iframe>, form actions, data-* attributes, JavaScript string literals, CSS url(), comments, etc.
4. Passwords that appear ONLY in HTTP response headers are staging placeholders — IGNORE them completely.
5. Stay strictly on the same host: 54.214.7.161
6. Completeness condition: the frontier (queue) is empty AND every discovered in-scope URL has been visited.
7. Ignore the example password VISUALPING{0000deadbeef0000}.

### Required Project Structure
```
visualping-crawler/
├── requirements.txt
├── config.py
├── main.py
├── crawler/
│   ├── __init__.py
│   ├── fetcher.py
│   ├── url_utils.py
│   ├── frontier.py
│   ├── discovery.py
│   ├── extractor.py
│   └── engine.py
├── processors/
│   └── image.py          # optional OCR
├── tests/
│   ├── test_url_utils.py
│   ├── test_extractor.py
│   ├── test_discovery.py
│   └── test_frontier.py
├── ARCHITECTURE.md
└── README.md
```

### Implementation Order (do them one after another)
1. config.py + requirements.txt + README skeleton
2. crawler/fetcher.py (Basic Auth, timeout, graceful errors)
3. crawler/url_utils.py (normalize, is_in_scope, make_absolute)
4. crawler/frontier.py (Frontier queue + Visited set + Results set)
5. crawler/discovery.py (HTML discovery with BeautifulSoup + generic text/JS/CSS path extraction)
6. crawler/extractor.py (password regex + ignore header-only rule + cheap binary search)
7. crawler/engine.py (BFS crawl loop with completeness condition)
8. processors/image.py (optional: ASCII search first, then OCR if available)
9. main.py (CLI + clean report of the 8 passwords + stats + completeness justification)
10. Write pytest unit tests for url_utils, extractor, discovery, frontier
11. Write a short, clear ARCHITECTURE.md explaining the layers and data flow

### After the code is written
- Make sure `python main.py` runs the full crawl and prints the passwords.
- Run `pytest -v` and show the results.
- In the final report highlight which password looks like a genuine real-world credential leak (the one that appears inside a JavaScript comment as a temporary ADMIN_PASSWORD / FIXME).

Start by creating the project structure and config.py.  
Wait for my confirmation after each major module if I ask, otherwise continue until the full working solution + tests + ARCHITECTURE.md are done.

---

**How to use this prompt**
1. Create a new empty folder.
2. Open it in VS Code / Cursor with Copilot enabled.
3. Paste the entire block above into the chat.
4. Let Copilot generate the files step by step.
5. After it finishes, run:
   ```
   pip install -r requirements.txt
   python main.py
   pytest -v
   ```
