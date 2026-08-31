# resource-graph-crawler

Production service for a same-host **resource-graph crawler**.

Fetched URLs are nodes. References discovered in HTML, scripts, CSS, comments,
and binary payloads are edges. The original CLI still solves the Visualping
challenge. This release adds a production HTTP control plane, Docker image,
CI, and a public deployment.

## What shipped

- FastAPI control plane with health, readiness, target probe, and bounded crawl
- Production console UI at `/`
- OpenAPI at `/docs`
- Docker + Compose for long-running / full crawls
- GitHub Actions unit tests
- Environment-based configuration

## Live service

After deploy, the production URL is the Vercel project `resource-graph-crawler`.

| Path | Purpose |
| --- | --- |
| `/` | Operations console |
| `/health` | Liveness |
| `/ready` | Target readiness (503 if challenge host is down) |
| `/docs` | Interactive API |
| `POST /api/v1/crawl` | Bounded crawl (capped for serverless) |
| `GET /api/v1/probe` | Single authenticated fetch of the seed URL |

The public API is **intentionally capped** (`RGC_API_MAX_PAGES`, default 12).
A complete 2,000-page BFS does not belong on a serverless timeout. Use Docker
or the CLI for a full run.

## Local API

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn service.app:app --reload --port 8000
```

Then open http://127.0.0.1:8000

## CLI (original crawler)

```bash
python main.py --verbose --max-pages 2000 --workers 8
```

## Docker (production process)

```bash
cp .env.example .env
docker compose up --build
```

Healthcheck hits `/health`. Map host `8000` to the container.

## Configuration

See `.env.example`. Important variables:

- `RGC_BASE_URL` / `RGC_ALLOWED_HOST` — crawl seed and host allow-list
- `RGC_USERNAME` / `RGC_PASSWORD` — HTTP Basic Auth
- `RGC_API_KEY` — if set, `POST /api/v1/crawl` requires `Authorization: Bearer` token
- `VP_PROXY` — optional HTTP/SOCKS exit for geo-locked pages

Challenge defaults remain for local compatibility. Do not treat committed
defaults as a secret store.

## Tests

```bash
python -m pytest -q
```

## Architecture

`fetcher` is the only network layer. `url_utils` enforces host scope.
`frontier` owns BFS + dedupe. `discovery` extracts references.
`extractor` matches exact body passwords and never inspects headers.
`engine` orchestrates bounded parallel BFS. `service.app` is the production
HTTP facade.

The challenge target (`54.214.7.161`) may be offline. The service stays up and
reports `degraded` from `/ready` plus a structured probe error from crawl jobs.
