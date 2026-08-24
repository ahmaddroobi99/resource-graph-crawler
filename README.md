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
