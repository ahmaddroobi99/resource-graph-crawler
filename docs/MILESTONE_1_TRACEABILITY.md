# Milestone 1 Traceability

This matrix reports implementation coverage in this repository. A `PARTIAL` entry is not a release claim; it identifies validation or functionality that remains unverified/incomplete.

| Requirement | Implementation | Test/verification | Status |
| --- | --- | --- | --- |
| M1-R01 Preserve crawler behavior | Existing `crawler/` modules and routes retained; shared API errors normalized | Full suite, including `tests/test_service.py` | PASS |
| M1-R02–R06 Upload, types, validation, original preservation, API route | `service/document_api.py`, `service/document_processing.py`, `service/document_store.py` | API upload, MIME-independent detection, invalid/empty/oversize/corrupt cases; worker source-byte check | PASS |
| M1-R07 CV preprocessing | `service/document_processing.py:preprocess_image` | Synthetic image preprocessing test | PASS |
| M1-R08–R10 Structured OCR, boxes, confidence | `service/document_processing.py:ocr_page`; `document_pages` persistence | OCR output mocked for repeatability; coordinates/confidence shape exercised | PARTIAL: no local Tesseract binding or executable |
| M1-R11 Entity types and replaceable extraction | `service/document_processing.py:extract_entities` | Seven entity types exercised with synthetic resume text | PASS with heuristic limitations |
| M1-R12–R14 Evidence/provenance | OCR block evidence in `service/document_processing.py`; entity storage/API in `service/document_store.py` and `service/document_api.py` | Fixture checks evidence points to source page/block; entity detail API test | PASS |
| M1-R15–R16 Full-text/entity search | `service/document_store.py:search` | Fixture text/entity search, empty query, empty results, pagination contract | PASS |
| M1-R17 Browser workflow | `service/templates/documents.html`, `/documents` in `service/app.py` | Route smoke test; Playwright viewport checks at 1440px and 390px; API flows tested separately | PARTIAL: visual capture unavailable and file-upload browser flow not automated |
| M1-R18 Async status states | `service/document_worker.py`, document status API | Upload returns queued job; worker completion/partial and status polling tests | PASS for implemented local worker paths |
| M1-R19–R20 Errors and sensitive-data handling | Common exception handlers in `service/app.py`; fixed safe processing messages | API validation, auth, search/database failures, and no-path-leak tests | PASS for covered routes |
| M1-R21–R22 Partial results, bounded retry | `service/document_worker.py`, `service/document_store.py:recover_jobs` | Partial-page test, transient-timeout retry, exhausted recovery limit | PASS for simulated failures |
| M1-R23 Diagnostic logging | Request middleware in `service/app.py`; job logging in `service/document_worker.py` | Inspected fields; no dedicated log-capture test | PARTIAL |
| M1-R24 Automated test coverage | `tests/test_document_api.py`, `test_document_store.py`, `test_document_worker.py`, existing suite | `python -m pytest -q`: 41 passed | PASS for implemented coverage |
| M1-R25 Known-content fixture and end-to-end | `tests/fixtures/sample_resume.pdf`; worker/store/search path | Fixture test mocks Tesseract output | PARTIAL: real OCR end-to-end unavailable locally |
| M1-R26 Performance baseline | `docs/ASYNC_DOCUMENT_INTELLIGENCE.md` | CV preprocessing measured on synthetic page | PARTIAL: OCR/total job time and memory not measured |
| M1-R27 Documentation/OpenAPI | `openapi.yaml`, README and docs | PyYAML parsing and route parity test | PASS |

## Error Codes (M1-E01–M1-E14)

The 14 required codes are declared in `openapi.yaml`. The first 12 except `SEARCH_FAILED` are exercised by runtime paths or tests; `SEARCH_FAILED` is covered by an injected search exception. `FORBIDDEN` is available in the shared error schema but no document route currently emits it because document authorization uses one bearer key rather than resource-level roles.

| ID | Code | Implementation/test |
| --- | --- | --- |
| M1-E01 | `INVALID_REQUEST` | API input validation and cursor tests |
| M1-E02 | `UNSUPPORTED_FILE_TYPE` | Unsupported upload test |
| M1-E03 | `FILE_TOO_LARGE` | Upload-size check in `service/document_api.py` |
| M1-E04 | `EMPTY_FILE` | Empty upload test |
| M1-E05 | `CORRUPTED_DOCUMENT` | Corrupt PDF test and worker failure path |
| M1-E06 | `OCR_FAILED` | Per-page worker failure path |
| M1-E07 | `OCR_PARTIAL` | Partial terminal state |
| M1-E08 | `ENTITY_EXTRACTION_FAILED` | Worker entity-stage failure path |
| M1-E09 | `DOCUMENT_NOT_FOUND` | Missing document/entity test |
| M1-E10 | `SEARCH_FAILED` | Injected search-layer exception test |
| M1-E11 | `DATABASE_ERROR` | Injected SQLite exception test |
| M1-E12 | `TIMEOUT` | OCR timeout retry and exhausted recovery paths |
| M1-E13 | `INTERNAL_ERROR` | Unexpected worker/API failure handlers |
| M1-E14 | `EMPTY_QUERY` | Blank search query test |

## Async Tests (TC26–TC32)

| Test | Coverage | Status |
| --- | --- | --- |
| TC26 | Upload returns `201` with document/job before worker execution | PASS with stub worker |
| TC27 | Job reaches completed/partial terminal state | PASS in worker tests |
| TC28 | Status polling returns current job/document state | PASS |
| TC29 | Restart requeues interrupted work or terminalizes exhausted attempts | PASS at SQLite recovery layer; process-kill integration not run |
| TC30 | Transient OCR timeout retries are bounded | PASS for simulated retry; exhausted attempts verified at recovery layer |
| TC31 | Partial page failure retains successful page | PASS |
| TC32 | Repeated idempotency key avoids duplicate document/job | PASS |

TC01–TC25 were referenced by the supplied prompt but not individually specified there; tests are organized by requirement and behavior rather than inventing missing case definitions.

## Runtime Validation Limits

The current environment has PyMuPDF and OpenCV installed, but neither the `pytesseract` Python module nor a Tesseract executable. Docker is also unavailable in this environment. Consequently, real OCR accuracy/duration, Docker image build, and real-process restart/recovery remain environment-dependent checks and must not be represented as verified.
