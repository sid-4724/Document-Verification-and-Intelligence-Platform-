> Supplied external review report preserved for provenance. Its execution claims describe the reviewer's environment. Current merged-code results are in docs/MERGE_VERIFICATION.md.

# DocVerify: independent code review and repair

Reviewed input: `docverify-review(2).zip`. Paths below are relative to the `DocVerify` project folder. This report describes the uploaded code and the revised source delivered with it. It is not a claim that every possible defect has been found.

**Verdict:** a useful local portfolio project for procurement-document consistency checking. It is not an ID/certificate authenticity detector and is not ready to accept arbitrary public uploads. The code has real engineering features worth explaining, but several failure paths and number-parsing assumptions needed repair.

## 1. Walkthrough

### What “verify” actually means

The supported inputs are selectable-text PDF purchase orders, quotations and invoices. The application extracts English-labelled fields and supported item tables, then checks numbers and differences. It does not contact an issuer, validate a certificate registry, verify a digital signature, decode a trusted QR code, or decide whether a document was forged. There is no OCR implementation. A marksheet may upload as a PDF, but its fields are not supported by this procurement schema.

Two fabricated PDFs can agree perfectly. A real document can have an unfamiliar layout and need review. Consequently, neither “completed” nor “zero findings” means genuine.

### Actual stack

Python backend with FastAPI, SQLAlchemy and Alembic; PostgreSQL 17 in Compose, SQLite for native development; pdfplumber for PDF text; Pydantic for data validation; Decimal for arithmetic; scikit-learn TF-IDF and logistic regression for document classification. Frontend: Next.js, React and TypeScript. Passwords use Argon2 and authentication uses opaque session cookies. Optional sentence-transformer embeddings and an optional Anthropic answer provider are separate enhancements. There is no custom deep-learning training pipeline or C++ module.

The repository targets Python 3.13 and Node 22+. This review executed Python checks on 3.12.14 with the pinned dependencies available in the review environment. The installed frontend resolved Next.js 16.3.8. A successful test run here does not replace a Python 3.13/PostgreSQL run on your machine.

### The full request flow

1. **Start the services.** `scripts/dev.py` creates only missing samples/model files, applies migrations, then runs the API, worker and frontend. The API receives requests; the worker handles queued extraction. Keeping a worker separate allows the browser to see `pending` while work continues.
2. **Sign in.** `api/accounts.py` stores a password hash, creates a random session token and sends it in an HttpOnly cookie. `auth.current_user` looks up its hash, checks expiry and checks the CSRF token on changes. `api/access.py` verifies the case belongs to that user.
3. **Upload.** `api/documents.upload` checks ownership and the batch count. `file_storage.save_upload` reads 64 KiB chunks, enforces the configured per-file size and saves to a server-generated UUID filename. `validate_file` checks the PDF header; `extraction.validate_pdf` actually opens the PDF and checks its page count/readability. Renaming an image to `.pdf` is insufficient.
4. **Store metadata and queue work.** A `Document` row records the original display name, private storage name and status. A `Job` row points to it. The API commits the case change, document and job together. Filesystem writes are a separate resource, so failures need compensating cleanup; this is not a single transaction across disk and SQL.
5. **Claim a job.** `worker.claim_job` selects an eligible job, increments attempts and assigns a unique lease token. The token prevents an older worker from overwriting a newer attempt. The API and worker must share the same database and PDF directory.
6. **Extract.** `worker.extract_document` calls `extract_pdf`, classification and chunking. `parse_pages` walks each page and line. `read_fields` handles labelled fields; `read_line_item` handles the supported table layouts; `check_fields` adds uncertainty warnings. Unsupported or ambiguous values remain unknown. An image-only PDF fails explicitly with `OCR required`.
7. **Save the extraction.** `save_processing_result` checks the lease again, stores pages/chunks, appends a processing run and updates the latest raw extraction. It retains the first extraction and preserves manual corrections anchored to their own extraction revision. These snapshots serve different purposes; they are not interchangeable copies.
8. **Run deterministic checks.** `case_verification.refresh_case` obtains effective values and calls `verification.verify_documents`. The revised entry point first checks each document, then chooses reference–target pairs, then compares each pair. Arithmetic includes quantity × unit price, known line amounts versus subtotal, subtotal + tax, and an explicit tax rate. Matching prioritizes identifiers, then exact descriptions; fuzzy or conflicting matches require review. Monetary comparisons require a shared currency; quantity comparisons require compatible units. The program does not convert currencies or aggregate invoices.
9. **Show results.** The frontend polls case state and renders findings with source pages. Document processing status and finding review status are separate. A warning can be acknowledged without changing the PDF. A manual correction triggers a new comparison and a before/after audit record. A stale editor receives 409 rather than silently overwriting newer work.
10. **Search and export.** Retrieval ranks case-scoped source chunks. Original-source and reviewed-data scopes are labelled separately. Without an API key it returns evidence only. With a key, it checks returned citation IDs, but does not prove the generated sentences follow from those citations. JSON exports include provenance; CSV escapes spreadsheet-formula prefixes.
11. **Delete.** The revised version commits a file-deletion task with the document/case removal. It then tries physical deletion. Storage failure leaves a task for the worker and a pending-cleanup notice for the user. Removing access immediately and erasing bytes eventually are different events.

Read `READ_THIS_FIRST.md` next for a beginner reading order, Python vocabulary and a concrete numerical dry run.

## 2. Crashes and wrong results

The first new suite contained 34 checks: **17 failed and 17 passed against the uploaded version**. Parameterized examples count as separate checks, not separate root causes. The final suite contains 37 new checks plus the original 92. Additional changes below include regression protection for retry freshness and an uncertain commit result.

### Confirmed defects and concrete triggers

| Location in uploaded code | Specific trigger | What you would see | Repair |
| --- | --- | --- | --- |
| `services/extraction.number` | `12,34`, `1.234,56`, `1 2`, or `1,23,4` in a supported item value | No exception. Values become `1234`, `1.23456`, `12`, or `1234`; later arithmetic can be wrong. | Validate supported decimal/grouping syntax before removing commas. Accept ordinary dot-decimal, Western grouping and Indian grouping; leave ambiguous formats unknown. Scientific notation is now deliberately unsupported too. |
| `services/matching.normalize` and `match_candidates` | Left SKU `部品甲`, right SKU `部品乙`, both described as `Cable` | Both identifiers normalize to empty; the original matcher treats the descriptions as an exact match rather than an identifier conflict. Identical Chinese descriptions without SKUs can also fail to match. | Preserve Unicode letters, digits and combining marks using normalization and case folding. This is not transliteration or translation. |
| `services/extraction.parse_pages` field assignment | `Currency: inr`, `Tax rate: 150%`, or a 301-character supplier | Extraction bypasses the schema's assignment checks. Revalidating/saving the result produces currency-pattern, maximum-value or maximum-length validation errors; the correction API can return 422. | Normalize currency case and validate each extracted value through the same schema. Invalid fields become unknown with persistent source warnings. |
| `services/extraction.parse_line` called by `parse_pages` | A supported pipe row with a 501-character description | `ValidationError: String should have at most 500 characters`. The worker retries and can eventually fail the whole document. | Catch that row validation error, retain other valid rows and record an explicit `invalid_row` limitation. |
| `services/extraction.parse_pages` list append | 201 supported rows | Extraction returns 201 rows although the review schema allows 200; a later save returns 422 (`List should have at most 200 items`). | Enforce the bound during extraction and retain a `row_limit` warning. Do not silently claim all rows were read. |
| `services/retrieval.answer_question` | Provider responds HTTP 200 with `{"content":[null]}` or `{"content":["bad"]}` | Uncaught `AttributeError: 'NoneType' object has no attribute 'get'` or the equivalent for `str`; search can return 500. | Validate the response envelope and blocks in `parse_provider_answer`; retain evidence when generation is unusable. |
| `api/documents.upload` | Database operation fails after the file and document row have been staged; test injects `OperationalError` in `refresh_case` | `500 Internal Server Error`; raw database exceptions can contain parameters. | Roll back the batch, remove staged files where possible, return a controlled 503 and log only the error type. |
| `api/documents.upload` | First PDF is saved; opening the second raises `OSError(ENOSPC)` | Generic 500 even though this is a recognizable storage failure. | Return `503 Document storage unavailable; please retry shortly`; verify no document rows or files from the failed batch remain in the tested scenario. |
| `api/documents.upload` cleanup | COMMIT succeeds but the connection/reply fails before the caller sees success | The old unconditional cleanup can delete the PDF even though its database row committed. | After an uncertain commit, check using a fresh session before removing files. Preserve referenced files; if the outcome cannot be checked, defer cleanup. Tell the user to refresh the case before uploading again. The new test simulates a lost reply after a real commit. |
| `worker.process_claim` exception logging | Extraction raises `RuntimeError` containing a fictional name/account marker | The marker appears in the server traceback, even though the API error is sanitized. | Log event, internal document ID and exception class, without exception text/tracebacks. Apply the same policy to optional embedding failures; hide SQL bind parameters. |
| `api/documents.remove_document` and `api/cases.delete_case` | SQL deletion commits, then PDF unlink raises `PermissionError` | Generic 500, but the document is already gone from the database and its bytes remain. A normal retry cannot locate it. | Durable `file_deletions` tasks in migration 0003; immediate attempt followed by worker retries. API and UI distinguish successful access removal from pending physical cleanup. |
| `api/documents.retry_document` and current-result calculation | Reprocess an already compared invoice while its old extraction still exists, especially with explicit reference/targets | Case revision is unchanged and old quantity differences remain presented as current during `pending`. | Refresh the case on retry and exclude pending/processing/failed documents from current checks. Preserve acknowledged reviews for unchanged finding identities so reprocessing does not erase them. |

One further safety correction accompanies row-limit handling: a partial table is not proof that a subtotal is wrong. `check_document_totals` now skips the complete-table sum check while source limitations remain unresolved. Known individual-row arithmetic can still be checked. A new test covers 201 rows with a subtotal of 201: extracting 200 rows must not accuse the source of a subtotal error.

### Every requested document-platform case

| Case | Observed behavior / test coverage |
| --- | --- |
| Empty file | HTTP 400: `File content is not a PDF`; no retained row/file in the test. |
| Huge file | Existing regression lowers the configured limit to 1 MiB and sends more than that: HTTP 413. The same code uses 10 MiB by default. This does not establish a global request or account quota. |
| Corrupted file | `%PDF-1.7 corrupted` passes the header check but fails actual parsing: HTTP 400, `Invalid, encrypted, or unreadable PDF`. |
| Wrong extension/type | An image with a `.pdf` name is rejected. A real PDF named `../../outside.txt` is accepted by content and stored under a UUID. This acceptance is intentional. |
| Password-protected PDF | A generated encrypted PDF is rejected with the readable 400 error above; no password is requested or logged. |
| Blurry, rotated or low-resolution scan | Generated image-only PDFs are accepted as PDF files, then finish in `failed` with `OCR required: this PDF has no usable selectable text`. No OCR recovery or rotation correction is claimed. |
| Empty/wrong OCR output | There is no OCR service to mock. Empty selectable text is covered. Incorrect hidden text already embedded in a PDF can still be extracted as written; the application cannot establish its truth. |
| Missing/partial fields | Unknown values remain null and lead to review warnings, rather than invented zeroes. Existing and new tests cover missing identifiers, quantity, amount and unsupported tables. |
| Special/non-English names | Direct parser tests preserve `José & Sons / शर्मा` and `李明`; matching tests cover Unicode codes and combining marks. These are text-level tests, not evidence that all PDF fonts, scripts or non-English labels work. |
| Same document twice | Two uploads create two independent document IDs/files. There is no deduplication guarantee and no inference that identical bytes prove genuineness. |
| Two users, same bytes | Each receives their own record; cross-user file access returns 404. Existing tests also exercise the other user-scoped routes. |
| Database failure during upload | A real transaction with an injected database exception is rolled back, including metadata, job and file cleanup. The lost-commit-reply test separately checks the ambiguous-success case. No live PostgreSQL server was disconnected during this review. |
| Storage failure during upload | A simulated full disk while opening the second output file verifies batch rollback. This is controlled fault injection, not a physical disk-fill experiment. |
| Verification/service timeout | Deterministic verification is local; there is no external authenticity service. A simulated HTTP read timeout in the optional answer provider returns evidence-only fallback. The request uses a 30-second HTTP timeout. |
| Parser hangs | File/page limits do not impose a CPU or wall-clock deadline. No actual hanging-PDF exploit was reproduced. Process isolation and a hard parser deadline remain a deployment requirement. A lease timeout is not the same as terminating a stuck parser. |

## 3. Security and privacy

| Area | Finding |
| --- | --- |
| File type validation | Positive: checks header and parser behavior, not only MIME/extension. This is not malware scanning, PDF sanitization or protection against every parser exploit. |
| Path traversal | Positive for the tested upload path: user filenames are display metadata; storage uses server UUIDs. The traversal filename test cannot choose the stored path. |
| SQL injection | Reviewed route queries use SQLAlchemy parameters. Health checks use static SQL. No user-controlled SQL string concatenation was found in these paths. This is a source review, not a full penetration test. |
| Secrets | No live provider credential was found in the reviewed configuration. `.env.example` contains an obvious database-password placeholder, not a safe production password. Runtime `.env` files must stay out of shared ZIPs/Git. |
| Authentication | Password hashing, expiring session cookies, token hashes, CSRF and origin checks are implemented. In-process login throttling is only a local mitigation. HTTPS and secure cookies must be configured for any remote deployment. |
| Authorization | Case ownership is checked before document content, results, edits and exports. Existing cross-user route tests and the new duplicate-upload test pass. There is no separate administrator role; “manual review” means the owning user's review. |
| Storage exposure | PDFs are served through an authenticated endpoint, not a public static directory. The application does not encrypt PDFs or extracted database fields at rest. Host/disk/database backup security remains external to the app. |
| Sensitive logs | Fixed confirmed worker traceback leakage and optional embedding exception logging. SQL parameters are hidden. This does not audit reverse-proxy logs, hosting logs, OS crash dumps or third-party services. |
| Sensitive stored data | Pages, extracted fields and before/after reviews intentionally persist in the database. Access control does not make them encrypted, anonymous or tamper-evident. |
| Optional provider | Enabling a provider key sends retrieved passages and, for reviewed scope, effective records to that provider. It is off by default. Do not treat the no-key privacy behavior as the behavior after enabling it. |
| Size/resource limits | Per-PDF 10 MiB, 30 pages, 5 files per upload by default. Multipart handling occurs before route-level copying; the frontend proxy has a separate 55 MB setting. No account quota, global disk budget, decompression bound or hard parser runtime limit is implemented. |
| Deletion | The new durable queue repairs ordinary storage failure. File bytes may remain while cleanup retries. Failed upload cleanup can also leave private orphan files if permissions or the database prevent confirming the outcome; log events identify this condition. No automatic orphan sweeper is claimed. |

## 4. Other changes needed

### Must fix

**Before an interview/demo:** describe the system as procurement-document consistency checking. Use the repaired parsing, error handling, log policy and retry/deletion behavior; run migration 0003; verify your local environment. Do not claim OCR, fraud detection, issuer validation, encryption or real-world model accuracy. Keep the synthetic-data label visible.

**Before public deployment or real sensitive documents:** isolate PDF parsing with resource limits and a hard deadline; impose upload/account/storage quotas at the request boundary; configure HTTPS and secure cookies; define retention and backup deletion; provide encrypted storage/backups if that is a requirement; add operational monitoring for stuck processing and failed cleanup; test the actual PostgreSQL deployment and restore process. These are remaining requirements, not features silently added by this patch.

If your required product is ID/certificate authenticity verification, the missing trusted source is a fundamental scope gap. Define the issuing authority and verification mechanism first. OCR only reads fields; hashing only compares bytes; manual approval only records a person's decision. None alone establishes authenticity.

### Nice to have for this local portfolio scope

- Case-scoped duplicate detection with a content hash and a warning. Avoid revealing that another user has uploaded the same bytes.
- Optional OCR with explicit confidence/uncertainty, rotation handling and a labelled evaluation set. Keep extraction quality separate from authenticity.
- Paginated case/history views and indexed retrieval. TF-IDF currently recomputes over case text; row matching compares candidate pairs. This is acceptable for small demos, not a measured throughput claim.
- Broader operational audit events for upload, download, deletion and finding-status changes. Current correction/processing history is useful, but not a complete immutable security audit. The new finding-review map preserves status, not a who/when event history.
- Explicit review of provider data sharing, answer-support evaluation and prompt-injection tests before enabling generated answers for sensitive cases.
- Browser tests for the new pending-deletion notice; PostgreSQL concurrency/failure tests; realistic multilingual-font/layout fixtures; cancellation and hard-deadline tests when isolation exists.

### Status model

Document statuses are `pending`, `processing`, `completed`, `needs_review`, `failed`. `completed` means processing completed without the relevant unresolved extraction warnings; numerical findings may still exist. `failed` is a processing failure, not a declaration of forgery. Finding reviews are `open`, `acknowledged`, `resolved`. There is no issuer-backed `verified/rejected` authenticity state. Renaming these statuses to “genuine/fake” would be misleading.

## 5. Interview-friendly rewrite and behavior changes

The revised source is included, not just a suggestion to rewrite it. The main flow now has named boundaries:

- Upload: `save_upload`, `validate_file`, `enqueue_file`, `rollback_upload`.
- Extraction: `parse_field_value`, `read_fields`, `read_line_item`, `check_fields`, `parse_pages`.
- Worker: `extract_document`, `save_processing_result`, `record_processing_failure`, `process_claim`.
- Verification: `check_document_fields`, `check_line_totals`, `check_document_totals`, `check_matched_row`, `check_extra_rows`, `compare_document_pair`, `check_comparison_scope`, `verify_documents`.
- Provider boundary: `parse_provider_answer` before citation validation.

These functions expose the existing sequence. SQLAlchemy models, revision checks and lease fencing remain because removing them for cosmetic simplicity would lose useful behavior. Comments explain reasons such as ambiguous commas, Unicode combining marks, lost commit replies and durable cleanup. Two pre-existing test import-order lint errors were also fixed.

### Complete intentional behavior-change list

1. Ambiguous numeric formatting and scientific notation now become unknown; supported ordinary/Indian/Western formats still parse.
2. Unicode matching preserves meaningful non-ASCII characters and combining marks.
3. Lowercase currency becomes uppercase. Out-of-schema extracted fields become unknown with source limitations instead of invalid persisted values.
4. An invalid row no longer crashes the whole extraction; the source limitation records the omission. Extraction retains at most 200 supported rows and reports truncation.
5. Complete-table subtotal checks are withheld while source limitations remain; individual known-row checks remain available.
6. Malformed provider envelopes return evidence-only fallback instead of uncaught attribute errors. Existing timeout/citation validation behavior is retained.
7. Recognized storage/database upload failures receive controlled 503 responses; cleanup errors do not replace the primary error.
8. A lost commit reply no longer triggers unconditional deletion of potentially committed PDFs. Unconfirmed cleanup is deferred and the user is told to refresh first.
9. Worker/embedding logs omit exception payloads and tracebacks; SQL bind parameters are hidden. Log formatting uses event text and exception class.
10. Document/case deletion commits a retryable file task. A 200 response means logical removal; `storage_cleanup_pending` distinguishes unfinished physical removal. The UI reports this, and the worker retries due tasks.
11. Retrying refreshes case revision/results and excludes pending/processing/failed snapshots from current checks. Reviews for unchanged findings survive that temporary absence through a case-level status map.
12. Parser version is now `labelled-layouts-v3`. Migration 0003 adds the cleanup table and finding-review map without resetting existing accounts/PDFs. Downgrade refuses to discard outstanding deletion tasks.
13. The UI explicitly states that consistency checks do not prove authenticity, and replaces the broad “securely stored” wording with an account-access description.

Refactoring the verification/worker functions does not intentionally alter supported arithmetic, tolerance, reference selection, stable finding identities, correction provenance or access control. The original 92 tests still pass. Historical extractions are not rewritten: deliberately reprocess originals if you want the new parser, and review any existing corrections anchored to an earlier run.

## 6. Test it and explain it

### Results independently executed for this revision

| Check | Result |
| --- | --- |
| Uploaded version's existing backend suite | 92 passed |
| First new edge-case suite on uploaded version | 17 failed, 17 passed; established the initial gaps |
| Revised full backend suite | 129 passed; one upstream Starlette/httpx TestClient deprecation warning |
| Ruff lint and formatting | Passed after fixes |
| Frontend TypeScript | Passed |
| Frontend production build | Passed |
| Synthetic extraction evaluation | 1.000 on the supported fixture fields; no fixture errors |
| Runtime retrieval held-out synthetic evaluation | Recall@5 0.800, MRR 0.600, support-passage coverage 0.750; 3 unsupported queries retrieved evidence |
| Harder synthetic classification challenge | Model macro-F1 0.667, keyword baseline 0.100 |
| Live provider / optional embedding weights | Not evaluated; provider failure tests use mocks |
| Browser interaction tests | Not executed in this review: Chromium was unavailable |
| PostgreSQL / Docker / target Python 3.13 | Not executed in this review; unavailable locally |

Earlier repository documents contain historical execution claims. They are not substituted for independent verification of this revision. No “100% fraud accuracy” or real-world accuracy follows from these synthetic results.

### Start on macOS/Linux, from the project root

Use Python 3.13 and Node 22+ as specified by the repository. If you already have a working `.venv`, keep it; do not overwrite your environment file or database.

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
npm --prefix frontend ci
.venv/bin/python scripts/dev.py
```

Open `http://localhost:3000`. The native runner supplies SQLite defaults and applies migrations. Exported environment variables take precedence. If port 3000 is occupied, use `scripts/dev.py --web-port 3002`. For an existing separately managed deployment, stop its API/worker, back up its database and PDFs, then apply `alembic -c backend/alembic.ini upgrade head` using the correct deployment environment before restarting both processes. Do not reset tables or delete volumes.

### Run the checks

```bash
.venv/bin/python -m pytest backend/tests/test_document_edge_cases.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check backend scripts
.venv/bin/python -m ruff format --check backend scripts
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Default pytest uses a disposable temporary SQLite database. Do not point destructive tests at your application database. The repository's external-database guard and opt-in rules remain intact.

The broader existing command `.venv/bin/python scripts/verify.py` also generates samples, trains the synthetic classifier and runs evaluations. It does not imply that Docker, PostgreSQL or browser tests were executed. `--browser` requires a running app and a separately installed Chromium.

### Small experiments to understand before an interview

1. Upload `sample_data/both_po.pdf` and `both_invoice.pdf`. Explain 100 × 80 = 8000 versus 120 × 85 = 10200, and why the subtotal delta is 2200. This is a consistency difference, not proof of fraud.
2. Change a known quantity to null in a review. Explain why the program asks for review instead of substituting zero.
3. Run `pytest ... -k ambiguous_amount` and explain why deleting commas before understanding their meaning is unsafe.
4. Run `pytest ... -k non_english` and explain why ASCII-only cleanup made two distinct identifiers equal.
5. Run `pytest ... -k storage_delete_failure` and trace the task from SQL commit to failed unlink to worker retry.
6. Run `pytest ... -k lost_commit_reply` and explain why a failed response does not always mean a failed commit.
7. Open two review tabs, save in one, then save the stale draft. Explain the 409 and why this protects somebody else's newer work.

For the abbreviated pytest commands above, replace `...` with `backend/tests/test_document_edge_cases.py`.

An honest project description: “I built an AI-assisted procurement-document review application. It extracts supported PDF fields, runs deterministic consistency checks, preserves corrections and provenance, and offers case-scoped evidence search. I can explain its failure handling and the limits of its synthetic evaluation.” Do not imply that styling changes make AI assistance disappear; understanding the code and its tradeoffs is the credible part.
