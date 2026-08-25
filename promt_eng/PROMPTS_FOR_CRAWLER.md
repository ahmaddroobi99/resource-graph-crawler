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

---

*End of prompts*
