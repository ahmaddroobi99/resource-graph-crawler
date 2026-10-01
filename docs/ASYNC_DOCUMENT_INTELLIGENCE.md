# Async Document Intelligence MVP

## Scope

The document workflow is additive to the existing resource-graph crawler. It processes only documents deliberately submitted to this service. It does not identify people from faces, search for people across the web, map social connections, rank candidates, or make hiring decisions.

The supported deployment is one local or Docker service instance with persistent local storage. Vercel continues to serve the existing crawler API; document endpoints return `DOCUMENT_API_DISABLED` there because serverless filesystems and request lifetimes cannot support the required durable worker. This implementation uses one in-process worker and SQLite, not a distributed queue.

## Run Locally

Install the Python dependencies and a system Tesseract executable. Tesseract must be available on `PATH` on Windows; Docker installs `tesseract-ocr` in the image.

```powershell
python -m pip install -r requirements-documents.txt
$env:RGC_DOCUMENT_API_KEY = "replace-with-a-long-random-key"
uvicorn service.app:app --reload --port 8000
```

Open `http://127.0.0.1:8000/documents`. Enter the bearer key in the page; it is kept in memory and is not saved to browser storage. The workbench supports upload, processing polling, page OCR, entity evidence, and search. The contract is available at `http://127.0.0.1:8000/openapi.yaml` and through FastAPI's `/docs`.

For Docker, configure `.env` with `RGC_DOCUMENT_API_KEY` and run:

```powershell
docker compose up --build
```

Docker Compose mounts the `document_data` volume at `/app/data`; keep this volume when replacing the container. Back it up as sensitive data. Do not expose this API publicly without TLS, a strong key, restricted network access, and a retention/deletion policy appropriate for the uploaded documents.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `RGC_DOCUMENT_API_KEY` | unset | Required bearer key; falls back to `RGC_API_KEY`. If neither is set, document endpoints return 503. |
| `RGC_DOCUMENT_DB_PATH` | `data/documents.sqlite3` | SQLite database path. |
| `RGC_DOCUMENT_UPLOAD_DIR` | `data/uploads` | Persistent directory containing original, unmodified uploads. |
| `RGC_DOCUMENT_MAX_UPLOAD_SIZE_BYTES` | `20971520` | Maximum request file size (20 MiB). |
| `RGC_DOCUMENT_MAX_PAGES` | `100` | Maximum PDF pages. |
| `RGC_DOCUMENT_MAX_PIXELS` | `50000000` | Maximum image pixel count. |
| `RGC_DOCUMENT_MAX_OCR_SECONDS` | `30` | Per-page Tesseract timeout. |
| `RGC_DOCUMENT_MAX_PROCESSING_SECONDS` | `600` | Total job processing budget. |
| `RGC_DOCUMENT_MAX_ATTEMPTS` | `3` | Maximum attempts, including attempts recovered after a restart. |
| `RGC_DOCUMENT_RETRY_BASE_MILLISECONDS` | `500` | Exponential retry backoff base for transient OCR timeouts. |
| `RGC_DOCUMENT_WORKER_POLL_MILLISECONDS` | `500` | Worker queue poll interval. |

The server identifies media type from file contents, not the filename or submitted MIME type. Empty, unsupported, malformed, oversized, and over-limit files receive structured 4xx responses. Filenames are reduced to a printable basename; stored files use generated names.

## Processing

```text
multipart upload
  -> signature and integrity validation
  -> atomic persistence of original bytes + SQLite document/job records
  -> 201 response with document ID and queued job ID
  -> background PDF page rendering or image loading
  -> resize, grayscale, median denoise, CLAHE contrast enhancement, deskew
  -> Tesseract block OCR with source confidence and bounding boxes
  -> evidence-backed rule-based entity extraction
  -> persist page results, entities, errors; search through SQLite
```

PDFs are rendered page-by-page. Images use one page. OCR bounding boxes use non-negative pixel coordinates from the top-left of the **preprocessed page raster**; each page response includes that raster's width and height. Confidence is returned only when Tesseract supplies it; otherwise it is `null`. Original bytes are not modified.

Entity types are `PERSON`, `ORGANIZATION`, `LOCATION`, `DATE`, `EMAIL`, `URL`, and `SKILL`. Extraction is deterministic and rule-based: email/URL/date and a small skills vocabulary use patterns; person extraction looks for a likely name heading; organization and location extraction use labeled text. It is not a validated named-entity model. Confidence is therefore `null`, and every entity includes its supporting OCR block as evidence. Treat extracted entities as leads for human review, not as verified qualifications or hiring recommendations.

## Async and Recovery

`POST /api/v1/documents` validates and persists the upload, creates a queued job, then returns without awaiting OCR. Job states are `QUEUED`, `PROCESSING`, `COMPLETED`, `PARTIAL`, and `FAILED`; every accepted job is either processed or recovered at service startup. SQLite stores job state and intermediate page output. On restart, queued and interrupted jobs are requeued unless their attempt budget is exhausted, in which case they terminate with `TIMEOUT`.

Transient Tesseract timeouts receive bounded exponential retries. Permanent validation errors are rejected before job creation and are not retried. Successful pages remain available if another page or the entity stage fails. Processing work and source bytes are idempotently overwritten by page number and stable block/entity IDs. The current worker is single-process; do not run multiple API replicas against the same database/upload directory.

The UI polls status with a bounded, increasing interval. Progress is nullable when the worker cannot calculate a truthful percentage. An idempotency key replay with the same bytes, filename, and metadata returns the existing document/job (`200`); reuse with a different payload returns `409`.

## API Contract

All document routes require `Authorization: Bearer <RGC_DOCUMENT_API_KEY>`:

| Method and path | Purpose |
| --- | --- |
| `POST /api/v1/documents` | Upload a PDF/PNG/JPEG and enqueue processing. |
| `GET /api/v1/documents/{document_id}` | Metadata and document status. |
| `GET /api/v1/documents/{document_id}/status` | Job, stage, truthful progress, page counts, and failed pages. |
| `GET /api/v1/documents/{document_id}/pages` | Paginated OCR text/blocks/evidence coordinates. |
| `GET /api/v1/documents/{document_id}/entities` | Paginated extracted entities and provenance. |
| `GET /api/v1/entities/{entity_id}` | One entity and its evidence. |
| `GET /api/v1/documents/{document_id}/errors` | Paginated safe processing errors. |
| `GET /api/v1/search?q=...` | Full-text/entity substring search. Empty matches return `200`; a blank query returns `400`. |

List/search routes use `limit` (default 20, maximum 100) and opaque `cursor` values. API errors use `{ "error": { "code": "...", "message": "...", "details": {} }}`. The checked-in source of truth is [`../openapi.yaml`](../openapi.yaml); `GET /openapi.yaml` serves it.

## Tests and Performance

Run the suite with `python -m pytest -q`. `tests/fixtures/sample_resume.pdf` is synthetic and contains only fictional names, contact details, company, location, skills, date, and URL. Worker integration tests mock the OCR engine for repeatability, then exercise persistence, entity evidence, search, partial failure, retry, and source immutability.

Measured on this development machine: preprocessing a synthetic 1600 x 1000 RGB image (4.8 MB raw pixels, one page) took a median 64.76 ms and minimum 43.34 ms over five runs. This is only the OpenCV preprocessing stage, not compressed upload size, OCR, or total job time. The environment has PyMuPDF/OpenCV installed but lacks both the Python Tesseract binding and native OCR executable; no OCR duration or accuracy is claimed. Install `requirements-documents.txt` plus the system engine to measure those values on representative documents before production use.

## Known Limitations

- SQLite plus one in-process worker is for a single local/Docker instance, not horizontally scaled production.
- There is no document delete/retention API yet; operators must protect and manage the data volume.
- Authentication is a shared bearer key, not per-user identity or document-level authorization.
- Entity extraction is heuristic, language-limited, and not an assessment of candidate suitability.
- The browser UI does not persist the API key, and browser/API traffic should remain on a trusted local network or use TLS behind an authenticated reverse proxy.
- OCR quality depends on Tesseract, scan quality, and language configuration; no accuracy guarantee is made.
