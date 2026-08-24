# Visualping Crawler — Password Findings Report

**Target:** `http://54.214.7.161/` (HTTP Basic Auth, user `ahmad.droobi2`)
**Password format:** `VISUALPING{<16 hex chars>}`
**Crawl result:** frontier empty, 541 in-scope resources visited = discovered, 0 failed fetches → **provably complete**.
**Passwords recovered: 6** (the brief advertises 8 — see [Why 6 and not 8](#why-6-and-not-8)).

---

## Passwords found

| # | Password | Where it lives (link) | How it was hidden | How the crawler recovers it |
|---|----------|-----------------------|-------------------|-----------------------------|
| 1 | `VISUALPING{349a583fba34c301}` | [/static/js/analytics.js](http://54.214.7.161/static/js/analytics.js) | JavaScript comment — a hardcoded `ADMIN_PASSWORD` next to a `FIXME(ops)` "remove before prod" note | Plain body regex; flagged as the genuine credential leak by the `ADMIN_PASSWORD`/`FIXME` context check |
| 2 | `VISUALPING{2dd5105a3fad0ef3}` | [/notes/diff-socket-socket/](http://54.214.7.161/notes/diff-socket-socket/) | HTML comment: `<!-- provisioning backup – do not publish: … -->` | Plain body regex (comments are part of the response text) |
| 3 | `VISUALPING{73c8f3073fdc5f74}` | [/wiki/detect-embed/](http://54.214.7.161/wiki/detect-embed/) | Custom HTML attribute: `<body data-vp-archive="VISUALPING{…}">` | Plain body regex |
| 4 | `VISUALPING{fb725e1f3d6728b1}` | [/static/js/theme-switcher.js](http://54.214.7.161/static/js/theme-switcher.js) | A `_beacon` array of character codes fed to `String.fromCharCode` — no literal string in the source | `extract_encoded_passwords()` decodes the char-code array, then applies the regex |
| 5 | `VISUALPING{db7e533a9cef7f72}` | [/static/img/field-visit.jpg](http://54.214.7.161/static/img/field-visit.jpg) | EXIF **UserComment** metadata, encoded as **UTF-16** | Multi-encoding raw-byte scan (UTF-8/UTF-16/latin-1) |
| 6 | `VISUALPING{e1c2e40cf01c17cc}` | [/static/img/whiteboard-scan.png](http://54.214.7.161/static/img/whiteboard-scan.png) | Rendered as **pixels** (text drawn on a whiteboard image) — no text in the file bytes | OCR (Tesseract) with a hex character whitelist |

### How each page is reached from the homepage

- **JS files** (`analytics.js`, `theme-switcher.js`) — referenced from `<script src>` tags and, for the dynamic nav, from string paths inside `main.js`.
- **Images** (`field-visit.jpg`, `whiteboard-scan.png`) — referenced from `<img src>` on content pages.
- **Content pages** (`notes/diff-socket-socket/`, `wiki/detect-embed/`) — reached by BFS through the sites internal "related / further reading" links starting at the homepage.

All six are reachable from the homepage without guessing URLs — exactly as the challenge requires.

---

## Decoys (correctly **not** reported)

The site plants several near-misses to catch a naive extractor. None of these are valid answers:

| Value | Location | Why it is excluded |
|-------|----------|--------------------|
| `VISUALPING{64d26185a2f94e34}` | `X-Provisioning-Note` **response header** on [/products/filter-gateway](http://54.214.7.161/products/filter-gateway) | Challenge rule: passwords appearing only in HTTP headers are staging placeholders — ignore them. The extractor never reads headers. |
| `5a6b01d97bfffdc3` | JPEG `COM` comment in `field-visit.jpg` | Bare hex, **no `VISUALPING{}` wrapper** → not the required format |
| `622ee9dfa76d54a6` | JPEG `COM` comment in `office-plants.jpg` | Bare hex, no wrapper |
| `e19cd3432599af6f` | JPEG `COM` comment in `team-offsite.jpg` | Bare hex, no wrapper |
| `VISUALPING{0000deadbeef0000}` | Homepage, as the format example | Explicitly the documented example, not one of the eight |

Other images (`chart-overview.png`, `diagram-1.png`, `diagram-2.png`, `pattern.png`, `office-plants.jpg`, `team-offsite.jpg`) are decorative gradients — verified to contain no password via byte scan, PNG-chunk inspection, raw-pixel/LSB analysis, and OCR.

---

## The trap that had to be defeated first

Before any of this was reachable, the crawl had to **terminate**. The site generates an effectively infinite URL space:

- **Tracking parameters** (`?utm_source=`, `?ref=`, `?v=`, `?hl=`) appended to otherwise-identical pages.
- An **unbounded `/report/?page=N` feed** ("generated on demand"): every page links to the next, forever, and contains **no passwords** (verified through page 200 and deep sampling to 10,000,000).

The fix normalizes these away (`TRACKING_PARAMS` in `config.py`, applied in `url_utils.normalize()`). Verified on the live site that no query parameter ever changes page content except report pagination — so stripping them is lossless. The frontier then drains to empty and completeness can be proven.

---

## Why 6 and not 8

The brief states there are eight passwords; an exhaustive search recovered six. The following were all checked with negative results for the remaining two:

- All **541** reachable resources decoded as: direct regex, Base64, Base32, char-code arrays, ROT13, gzip/zlib, hex pairs, HTML entities, percent-encoding, UTF-16, tag-stripping, whitespace-removal, and concatenation.
- All **8 images**: EXIF, JPEG `COM`, PNG `tEXt/zTXt/iTXt/eXIf` chunks, decompressed raw pixels, LSB steganography, and OCR on every image.
- All **response headers**, and content negotiation via **User-Agent** (Chrome/Googlebot/empty) and **Accept** headers.
- The **report feed** (pages 1–200 + deep) and conventional paths (`favicon.ico`, `sitemap.xml`, `robots.txt`).

No further `VISUALPING{…}` value — in any encoding — exists in the content the server currently serves for these credentials. The likely explanations: the live instance was partially rotated since the brief was written, or the remaining two use a vector absent from the current content. If the intended location/technique for the last two is known, it can be targeted directly.

---

## Reproduce

```powershell
python -m pip install -r requirements.txt
python main.py            # writes passwords.txt and prints the report above
python -m pytest -q       # 17 tests
```

OCR (password #6) additionally needs the Tesseract engine, e.g. `winget install UB-Mannheim.TesseractOCR`. Without it the crawler still runs and returns the other five.
