here are concrete acceptance criteria suggestions for each task so the MD is very Copilot-friendly:

Task 1 – Setup
Create project folder with requirements.txt (requests, beautifulsoup4, urllib3, optionally pillow/pytesseract)
config.py with BASE_URL, USERNAME, PASSWORD, PASSWORD_REGEX, USER_AGENT
README with challenge summary + how to run


Task 2 – Fetcher
get(url) → Response object with status, headers, content, text, content_type
Always send Basic Auth
Handle timeouts, 3xx redirects, 4xx/5xx without crashing the crawl

Task 3 – URL utils
normalize(url, base) → absolute URL, strip fragment, optional strip query if needed
is_in_scope(url) → same host only (54.214.7.161)
never invent paths


Task 4 – Data structures
Frontier: collections.deque
visited: set of normalized URLs
passwords: set of matched strings


Task 5 – HTML discovery
Parse with BeautifulSoup
Extract from: a[href], img[src], script[src], link[href], iframe[src], form[action], source[src], any data-* that looks like URL


Task 6 – Text/JS discovery
Regex for quoted paths starting with / or absolute same-host
Also extract from comments and string literals


Task 7 – Password extractor
Apply VISUALPING{[0-9a-fA-F]{16}} to body text
Explicitly DO NOT count matches that appear only in response headers

Task 8 – Crawl engine
BFS loop: while frontier: pop → if not visited → fetch → extract passwords + discover links → enqueue new
Stop condition: frontier empty
Print progress


Task 9 – Optional media
If image/*: optionally run OCR or at least store bytes and search raw for ASCII password pattern
Same for application/pdf if encountered


Task 10 – Output & report
Print exactly the 8 passwords one per line
Print crawl stats: pages fetched, unique URLs, passwords found
Write short “how I know complete” paragraph
Package code for submission (GitHub/Gist)
Also recommend single-file first (main.py) then optionally split modules if time allows — keeps 4th-year + Copilot focused.
