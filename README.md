# Visualping Crawler

This project crawls `http://54.214.7.161/` with HTTP Basic Auth, follows only
same-host resources discovered in fetched content, and extracts passwords
matching `VISUALPING{16 hexadecimal characters}`. Header-only matches and the
documented example value are ignored.

## Run

```text
pip install -r requirements.txt
python main.py
pytest -v
```

The crawler reports its results, visited/discovered resource counts, and the
frontier-based completeness condition. It also writes the discovered values to
`passwords.txt`.

For detailed Windows setup instructions and a requirement-by-requirement
output checklist, see [docs/HOW_TO_RUN.md](docs/HOW_TO_RUN.md).

## Architecture

`fetcher` handles authenticated HTTP, `url_utils` enforces scope and URL
normalization, `frontier` provides BFS state, `discovery` extracts browser-
reachable references, and `extractor` handles text and binary password
matching. `engine` composes those layers; `main.py` is the reporting CLI.




=== passwords.txt now (7 total) ===
     1	VISUALPING{2dd5105a3fad0ef3}
     2	VISUALPING{349a583fba34c301}
     3	VISUALPING{5488187886a5755a}
     4	VISUALPING{73c8f3073fdc5f74}
     5	VISUALPING{db7e533a9cef7f72}
     6	VISUALPING{e1c2e40cf01c17cc}
     7	VISUALPING{fb725e1f3d6728b1}
Done — the German-geo password is recovered and saved. Here's where things stand:

How it was solved: The proxy failed because the server geolocates the real TCP source IP (it literally told us "Your IP is from Canada"). No header spoofing worked. The fix was a genuine German exit — I installed Tor Browser (winget), ran its bundled tor.exe headless with ExitNodes {de} StrictNodes 1 (plus the geoip files it needs), which gave a German exit IP (91.132.144.59). Through that, /status/eu-region/ returned 200 and revealed the flag.

Current tally: 7 of 8 passwords now in passwords.txt:

VISUALPING{2dd5105a3fad0ef3}
VISUALPING{349a583fba34c301} ← flagged as genuine credential leak (ADMIN_PASSWORD context)
VISUALPING{5488187886a5755a} ← the German geo-locked one, just recovered
VISUALPING{73c8f3073fdc5f74}
VISUALPING{db7e533a9cef7f72}
VISUALPING{e1c2e40cf01c17cc}
VISUALPING{fb725e1f3d6728b1}
Still missing 1 (challenge wants 8). The crawl was provably complete (frontier empty, 541 URLs), so the 8th is likely hidden in a non-obvious spot the extractors didn't catch — e.g. inside an image (OCR), a different encoding, or another geo/conditional page.

Want me to hunt the 8th? Good next steps: (a) run the image/OCR processor over discovered images, (b) re-crawl through the Tor DE exit in case other pages vary by region, or (c) check for other geo variants (e.g. a US-only or other-region page).

Note: Tor is still running in the background on port 9050 — say the word and I'll stop it.