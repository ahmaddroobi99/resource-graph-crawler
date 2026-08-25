# 10 Long Prompts Used to Generate the Visualping Crawler

These are the detailed, progressive prompts that were used (or could realistically have been used) to build the entire modular crawler from scratch.

---

## Prompt 1 – Architecture First

```
I need to build a web crawler for a take-home challenge. 

Target: http://54.214.7.161/
HTTP Basic Auth on every request (username: ahmad.droobi2, password: 2dd4b97903ace571f147)

Goal: find all passwords of the exact form VISUALPING{16 hexadecimal characters}.

Hard rules:
- Never invent or guess any URL
- Only follow resources that are discoverable from content the server actually returns
- Stay on the same host only
- Passwords that appear ONLY in HTTP response headers must be ignored
- I must be able to prove the crawl is complete

Please design a clean, modular architecture first (before writing any code). 
I want clear layers: config, URL utilities, fetcher, frontier/visited/results, discovery, extractor, engine, and a CLI entry point.
Explain the data flow and how completeness will be proven.
```

---

## Prompt 2 – Config + URL Utilities

```
Implement the foundation of the crawler.

1. config.py should contain:
   - BASE_URL, USERNAME, PASSWORD
   - compiled password regex
   - the example password that must be ignored
   - MAX_PAGES, REQUEST_TIMEOUT, USER_AGENT
   - a frozenset of tracking/pagination parameters that should be stripped during normalization (utm_*, ref, v, hl, page, etc.)

2. url_utils.py should provide:
   - normalize(url) → strip fragment + tracking params, return clean absolute URL
   - is_in_scope(url) → True only for host 54.214.7.161
   - make_absolute(base, ref) → resolve relative links and return None if out of scope

Write production-quality code with type hints and short docstrings. Do not invent any crawling logic yet.
```

---

## Prompt 3 – Frontier / Visited / Results

```
Implement the three core data structures for a BFS crawler:

- Frontier: uses a deque, never adds a URL that is already pending or already visited
- Visited: simple set of normalized URLs
- Results: set of discovered passwords that automatically ignores the example password

All URLs must be normalized before being stored. 
Keep the implementation simple and single-threaded for now.
Add clear docstrings and a couple of small usage examples in comments.
```

---

## Prompt 4 – Authenticated Fetcher

```
Write crawler/fetcher.py.

Requirements:
- Always send HTTP Basic Auth
- Support an optional proxy (http or socks5h) so I can later reach a geo-restricted page
- Follow redirects but reject any redirect that leaves the allowed host
- Return the full requests.Response on success, or None on network errors
- Never raise – the crawl must continue
- Include a get_content_type helper

Also add a configure_proxy() function so the engine can switch proxies at runtime.
```

---

## Prompt 5 – Discovery Layer

```
Implement discovery.py with two main functions:

1. extract_from_html(html, base_url)
   - Use BeautifulSoup
   - Extract from a[href], img[src], script[src], link[href], iframe[src], form[action], source[src]
   - Also extract from any data-* attribute that looks like a path
   - Extract CSS url() values from style attributes and <style> tags

2. extract_paths_from_text(text, base_url)
   - Find quoted strings that look like paths (especially useful for JavaScript MENU arrays)
   - Also catch CSS url() values

Then provide a convenience function discover_resources(content, base_url, content_type) that chooses the right strategy.

All returned URLs must already be absolute and in-scope.
```

---

## Prompt 6 – Password Extractor (the important one)

```
The challenge says passwords are “not always stored the way you’d first expect”.

Implement a robust extractor.py that can find passwords in:

1. Plain text (normal regex)
2. JavaScript character-code arrays such as [86, 73, 83, 85, …] that are later turned into a string with String.fromCharCode
3. Base64-encoded blobs
4. Raw response bytes under multiple encodings (utf-8, utf-16-le, utf-16-be, latin-1) so we catch EXIF UserComment and similar metadata

Also enforce the rule that passwords appearing only in HTTP headers are ignored.

Write clear helper functions and make sure the example password is never returned.
```

---

## Prompt 7 – Core BFS Engine

```
Write the main crawl engine (crawler/engine.py).

It should:
- Seed the frontier with the homepage
- Run a classic BFS loop (optionally with a small thread pool)
- For every response:
  - always run the multi-encoding byte scan
  - if image/* → call the optional image processor
  - otherwise decode text, run plain + encoded extractors, and discover new links
- Maintain discovered / visited / failed sets
- Expose a get_stats() method that returns the completeness condition:

  frontier.empty and not failed and discovered.issubset(visited)

Keep the code readable and well-commented.
```

---

## Prompt 8 – Optional Image / OCR Processor

```
Create processors/image.py.

It must be completely optional – if Pillow or pytesseract are missing the crawler still works.

Strategy:
1. First do a cheap byte scan (multi-encoding) on the raw image
2. If nothing found and Tesseract is available, run OCR
3. Use a restricted character whitelist so “l” vs “1” mistakes are reduced
4. Optionally retry at 2× scale

Return a set of passwords. Never raise.
```

---

## Prompt 9 – CLI + Completeness Report

```
Write main.py – the final entry point.

It should:
- Accept --max-pages, --verbose, and --proxy arguments
- Run the crawler
- Print a clean report containing:
  - all discovered passwords (one per line)
  - pages visited / unique URLs / frontier remaining
  - the exact completeness justification
- Write the passwords to passwords.txt
- Mention which password looks like a real credential leak (the one near ADMIN_PASSWORD / FIXME)

Make the output submission-ready.
```

---

## Prompt 10 – Tests + Final Polish

```
Write a solid pytest suite that covers:

- URL normalization and tracking-parameter stripping
- Scope enforcement
- HTML and text discovery
- All extraction strategies (plain, char-code array, Base64, UTF-16 bytes)
- Frontier deduplication
- Results ignoring the example password
- Header-only passwords being ignored

Also give me a short professional README section that explains the architecture and how completeness is proven, so I can paste it into the submission form.
```

## Prompt 11 – Tracking Parameters & Finite Frontier

```
The frontier never becomes empty because the site keeps generating new URLs with query parameters like ?page=2, ?utm_source=internal, ?ref=nav, ?v=3, ?hl=en.

Update url_utils.normalize() so that a carefully chosen set of tracking and pagination parameters are stripped during normalization. 

After the change:
- /report/?page=1 and /report/?page=99 must both become /report/
- /docs/?utm_source=sidebar&ref=related must become /docs/
- Meaningful parameters (e.g. ?q=searchterm) must still be preserved

Also write a unit test that proves the collapsing behaviour.
Explain why this change is essential for the completeness proof.
```

---

## Prompt 12 – Multi-Encoding Byte Scanner

```
Some passwords are stored in image metadata (EXIF UserComment) as UTF-16. A normal UTF-8 decode misses them completely.

Extend extractor.py with a function extract_passwords_from_bytes(data: bytes) that tries at least these encodings in order:

- utf-8
- utf-16-le
- utf-16-be
- latin-1

Run the same password regex on each successful decode and return the union of matches (still ignoring the example password).

Add a unit test that feeds a UTF-16-LE encoded password and asserts it is recovered.
```

---

## Prompt 13 – JavaScript Char-Code Array Decoder

```
In /static/js/theme-switcher.js the password is hidden as:

var _beacon = [86, 73, 83, 85, 65, 76, 80, 73, 78, 71, 123, ...];

Implement extract_encoded_passwords(text) that:

1. Finds arrays of decimal numbers with a regex
2. Converts each number with chr()
3. Joins them into a string
4. Runs the normal password regex on the result

Also support Base64 tokens as a second strategy inside the same function.
Make sure ordinary short arrays such as [1,2,3,4,5,6,7,8] do not produce false positives.
```

---

## Prompt 14 – Optional OCR Path

```
Create processors/image.py.

Requirements:
- Completely optional – if Pillow or pytesseract are missing the rest of the crawler must still work
- First perform the multi-encoding byte scan (in case the password is in metadata)
- Only if nothing is found and Tesseract is available, run OCR
- Use a restricted character whitelist: VISUALPING{}0123456789abcdefABCDEF
- Use --psm 7 (treat as a single text line)
- Optionally retry the OCR at 2× resolution
- Never raise an exception

Export a HAS_OCR boolean so the engine can decide whether to call this processor.
```

---

## Prompt 15 – Geo-Restricted Page Support

```
One page (/status/eu-region/) returns 403 unless the request comes from a German IP. The server geolocates the real TCP source address and ignores X-Forwarded-For / CF-IPCountry headers.

1. Add optional proxy support to fetcher.py (both HTTP and socks5h)
2. Add a --proxy argument to main.py
3. Write a small helper script scripts/fetch_geo.py that fetches only the geo page through the supplied proxy and prints any password it finds

Document in a comment that a real German exit (Tor, commercial VPN, etc.) is required.
```

---

## Prompt 16 – Completeness Predicate & Reporting

```
In the Crawler class implement get_stats() that returns a dictionary containing at least:

- pages_visited
- pages_fetched
- unique_urls_discovered
- passwords_found
- frontier_remaining
- failed_fetches
- complete (boolean)

The complete flag must be True only when:
  frontier is empty
  AND there are no failed fetches
  AND every discovered URL is present in the visited set

Update main.py so that the final report prints this completeness justification in clear English.
```

---

## Prompt 17 – Credential-Leak Detection

```
One of the passwords appears next to the text “ADMIN_PASSWORD” and “FIXME(ops)” inside a JavaScript comment. This is the one that looks like a real-world credential leak.

Add a small helper inside the engine that, whenever a password is found, examines a window of surrounding text. If it sees “admin_password” or “fixme”, record that password in a credential_leaks set.

At the end of the run, print which password(s) were flagged as potential real leaks so I can answer the form question accurately.
```

---

## Prompt 18 – Full Pytest Suite

```
Write a comprehensive pytest suite (tests/test_*.py) that covers:

- URL normalization + tracking parameter stripping
- Scope enforcement (external hosts rejected)
- HTML discovery (tags, data-*, CSS url())
- Text/JS path discovery
- Plain password extraction + example password ignored
- Char-code array decoding
- Base64 decoding
- UTF-16 byte scan
- Header-only passwords ignored
- Frontier deduplication
- Results set behaviour

Each test should be independent and use small fixtures. Aim for clear assertion messages.
```

---

## Prompt 19 – Submission-Ready CLI & passwords.txt

```
Polish main.py so that a single command produces everything needed for the Google Form:

- Sorted list of passwords printed one per line
- passwords.txt written with the same list
- Statistics (pages visited, frontier remaining, etc.)
- Explicit completeness paragraph
- Indication of which password looks like a genuine credential leak

Accept --max-pages, --verbose and --proxy.
Make the output clean enough that I can copy-paste directly into the form.
```

---

## Prompt 20 – Final Architecture & README Section

```
Write a concise but complete “Architecture & Completeness” section that I can drop into the README and also reuse in the Google Form “Approach / notes” field.

It must explain:
- the BFS + frontier + visited design
- why tracking parameters are stripped
- the five extraction strategies
- how the German geo page was handled
- the exact completeness predicate used

Keep the tone professional and suitable for a hiring review.
```

---

