# Reviewed ZIP merge and executed verification

Executed in this workspace on 6 October 2026. This report covers current merged
source. `INDEPENDENT_REVIEW.md` retains the supplied reviewer's historical report;
its claims are not substituted for current validation. The implementation and this
review used AI assistance in Codex. No authorship, Git history or live-provider
results are invented.

The supplied `DocVerify-Reviewed.zip` was extracted into a temporary directory after
checking paths. Its 129 backend tests were rerun here on Python 3.13 and passed.
Useful fixes were merged against the current source and prior sanitized archive;
private/local configuration and staged work were retained. The original 92 tests
remain; the supplied review adds 37 cases, and this merge adds 18: **147 passed**.
Existing assertions were retained.

Further corrections were needed for manual currency normalization, selective
table-completeness checks, unavailable fresh upload-recovery sessions, delayed
reconciliation of uncertain uploads, durable rollback cleanup, owner-scoped cleanup
status, and review-cache invalidation after changed facts. These are included.

## Each bug and correction

| # | Functions/files | Trigger and previous result | Fix |
| --- | --- | --- | --- |
| 1 | `extraction.number`, `read_fields` | `12,34`, `1.234,56`, `1 2` became invented values after removing separators. | Validate formatting before removing grouping commas. Ambiguous input stays unknown; zero stays zero. |
| 2 | `matching.normalize`, `match_candidates` | SKUs `部品甲` and `部品乙` both became empty; equal descriptions could override their conflict. | NFKC/casefold preserves Unicode letters, digits and combining marks. Identifier conflicts prevent description matching. |
| 3 | `parse_field_value`, `read_fields`, `schemas.Extraction` | Lowercase currency, tax rate 150%, or supplier over 300 characters could contradict the manual-review schema. | Shared validation; currency is stripped/uppercased in both paths. Invalid extracted fields become unknown with source warnings. |
| 4 | `read_line_item` | One description over 500 characters crashed the entire extraction. | Keep valid rows and record an unresolved `invalid_row` source limitation. |
| 5 | `read_line_item`, `check_document_totals` | 201 rows exceeded the review limit and partial rows could falsely imply a subtotal error. | Cap at 200, record omissions, skip full-table sums for unresolved table/page limitations. Invalid metadata alone does not suppress valid arithmetic checks. |
| 6 | `parse_provider_answer`, `answer_question` | HTTP 200 with `content: [null]` or `["bad"]` raised an attribute error. | Validate response/text-block shapes, JSON and citations. Invalid output, timeout and provider failure retain evidence with an understandable fallback. |
| 7 | `api.documents.upload`, `save_upload`, `validate_file`, `rollback_upload` | A later batch write/SQL failure left staged state; cleanup could hide the original error. A lost COMMIT reply could delete a committed PDF. | Roll back uncommitted rows/jobs; remove safe files and queue failed unlink attempts. After COMMIT starts, preserve files immediately, check fresh references, and delay reconciliation of unreferenced files. If the fresh session fails, retain files. The controlled 503 says to refresh before re-uploading. |
| 8 | `process_claim`, `record_processing_failure`, embedding fallbacks, DB/Alembic engines | Exception messages/tracebacks exposed private extracted text or SQL values. | Log useful event names, internal IDs and exception classes only; hide SQL bind parameters and return generic SQLAlchemy errors. Fictional sentinel tests check logs/responses. |
| 9 | `remove_document`, `delete_case`, file-deletion helpers | SQL deletion committed, then PermissionError left a PDF without a retry record. | Commit cleanup tasks with logical deletion; attempt physical removal afterward and retry via worker. Tasks survive case/document removal and never unlink referenced files. Owner-scoped pending status appears in API/UI; additive migration `0003` retains existing records. |
| 10 | `retry_document`, `refresh_case`, comparison scope | Retry displayed old comparisons or rebuilding lost existing reviews. | Refresh on retry and exclude pending/processing/failed snapshots. Cache decisions while involved documents are inactive, restore unchanged material findings, and discard obsolete decisions when facts change. Changed-then-reverted facts reopen. |

Supported extracted numbers are nonnegative, signless dot-decimal values: `0`,
`1234`, `1234.56`, Western `1,234.56`, Indian `1,23,456.78`. A leading ₹/$/€ and
surrounding whitespace are supported. Internal spaces, comma decimals, exponents,
signed values, `.5` and `1.` deliberately remain unknown. Negative credit-note
amounts are unsupported by the current procurement schema. Labels/layouts must
still match the supported parser.

## Changed files and intentional behavior versus refactoring

Behavior changes are the ten fixes, lowercase manual-currency normalization,
generic database errors, and accurate authenticity/physical-cleanup notices.
Duplicate uploads remain separate private records. Original names are display
names; UUID names determine storage. Ownership, CSRF, revision conflicts, source
references, processing/correction history and worker lease protection remain.

- Backend services: `extraction.py`, `matching.py`, `verification.py`, `retrieval.py`,
  `case_verification.py`, `review_state.py`, `presentation.py`, new `file_storage.py`.
- Backend routes/core: `api/documents.py`, `api/cases.py`, `worker.py`, `schemas.py`,
  `models.py`, `db.py`, `main.py`.
- Migration: `alembic/env.py`, new `alembic/versions/0003_file_deletions.py`.
- Tests: new `test_document_edge_cases.py`, `test_robustness_merge.py`,
  `test_cleanup_migration.py`; migration-head assertions in `test_migrations.py`.
- Frontend: `app/page.tsx`, `app/cases/[id]/page.tsx`, `lib/types.ts`.
- README, implementation status, validation report, this report and supplied
  `INDEPENDENT_REVIEW.md`, `READ_THIS_FIRST.md`, `APPLY_CHANGES_PROMPT.md`.
  Evaluation JSON records newly executed measurements.

Refactoring separates `save_upload`/`validate_file`,
`read_fields`/`read_line_item`/`check_fields`,
`extract_document`/`save_processing_result`/`record_processing_failure`,
`check_line_totals`/`check_document_totals`/`compare_document_pair`, and
`parse_provider_answer`. These organize responsibilities; the validation/failure
behavior changes are listed above. No framework replacement or blanket dependency
upgrade was needed.

## Executed results

| Check | Actual result |
| --- | --- |
| Supplied ZIP backend suite in a temporary copy | 129 passed |
| Current suite, isolated SQLite | 147 passed |
| Current suite, separate PostgreSQL `docverify_test` | 147 passed |
| Ruff lint/format | Passed; 57 files formatted |
| TypeScript/formatting of modified frontend files | Passed |
| Native Next production build | Passed |
| Docker production images and Compose services | Built and started; migration `0003` |
| Chromium native app / Docker app | 4 passed each |
| Isolated SQLite existing-record upgrade | Passed in regression suite |
| Restored PostgreSQL backup `0002 → 0003` | Passed; checked account/business values unchanged |
| Original native data | 12 users, 12 sessions, 11 cases, 22 documents, 9 corrections retained with checked values and PDFs |
| Original PostgreSQL data | 23 users, 23 sessions, 22 cases, 43 documents, 16 corrections retained with checked values and PDFs |
| 15 original sample PDFs | Hashes unchanged |
| Requested 100×80 versus 120×85 example | Executed; three differences, no internal arithmetic error |

One upstream Starlette/httpx TestClient deprecation warning remains per backend
suite. Browser runs report a harmless NO_COLOR/FORCE_COLOR environment warning.
No assertions were weakened to hide warnings. Application databases were never
used as destructive pytest targets. No application table reset, volume deletion,
Git commit or staged-work discard occurred.

Tests use generated fictional PDFs for empty, oversized, corrupt, encrypted,
misnamed/traversal-style inputs and image-only blurry/rotated/low-resolution scans.
They cover unknown fields/numbers, Unicode identity, invalid/excess rows, duplicate
uploads and cross-user access. Database/storage faults, lost COMMIT replies,
unavailable fresh sessions, cleanup PermissionError, sensitive exception payloads,
embedding/provider failures and timeout are **simulated**. No paid provider called.

Evaluations rerun: known-layout synthetic extraction accuracy 1.000; whole-PDF
keyword Recall@5 0.909524/MRR 1.000; runtime passage Recall@5 0.800/MRR 0.600/support
coverage 0.750. Three unsupported runtime questions still retrieved evidence;
no-key mode abstained on all 24 queries. Harder synthetic classification challenge
macro-F1 remains 0.666667. These fixture results do not establish real-world
quality. Live embeddings/provider, public deployment and remote CI were not tested.

## Exact run and upgrade commands

From the existing project root, native startup applies additive migrations and
starts API, worker and frontend:

```bash
.venv/bin/python scripts/dev.py
```

Open `http://localhost:3000`. When Docker is using that port:

```bash
.venv/bin/python scripts/dev.py --web-port 3002
```

Migration only, using the same default native SQLite target:

```bash
DATABASE_URL="sqlite:///$(pwd)/var/docverify.db" PYTHONPATH=backend \
  .venv/bin/python -m alembic -c backend/alembic.ini upgrade head
```

For this project's Docker/PostgreSQL deployment, retain existing `.env`:

```bash
docker compose up --build -d
docker compose ps
```

Compose migrates the existing database before API startup. Explicit command with
the service's configured database:

```bash
docker compose exec -T backend alembic -c backend/alembic.ini upgrade head
```

Do not use `down -v` or reset tables. In a fresh archive extraction, copy
`.env.example` to `.env` only if none exists, replace the password placeholder,
then start Compose. See README for dependency installation and macOS Docker PATH.

Required local checks:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check backend scripts
.venv/bin/python -m ruff format --check backend scripts
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

## Beginner walkthrough and executed dry run

Upload → ownership/content/size checks → private UUID-named PDF on disk → document
and job committed together → worker claims a lease → selectable text becomes
validated fields, rows and page references → Decimal arithmetic and selected-pair
checks → current findings and uncertainty in UI. Manual corrections append history
without changing PDF bytes. Search ranks stored passages; optional answer generation
is a separate, fallible step. Read `READ_THIS_FIRST.md` to follow each function.

For the same SKU, units and INR currency:

| Value | Purchase order | Invoice | Observed minus expected |
| --- | --- | --- | --- |
| Quantity | 100 | 120 | +20 |
| Unit price | 80 | 85 | +5 |
| Subtotal | 8000 | 10200 | +2200 |

Both multiplications are correct. The executed verifier returns
`quantity_difference`, `unit_price_difference`, `subtotal_difference`, each with
both page-1 sources. It does not label the invoice fake or decide whether an
approved commercial change explains the difference.

## Remaining limitations

- No OCR, issuer lookup, certificate/QR/signature authenticity checks or fraud
  detection. Completed processing and zero findings do not mean genuine.
- Storage is access-controlled, without application-level encryption of PDFs or
  database data at rest. Encrypted disks/volumes are separate infrastructure.
- File/batch/page limits exist; aggregate account/storage quotas and a hard
  streaming limit for the entire multipart request are not implemented.
- Leases/retries do not impose a hard wall-clock PDF-processing timeout, isolate a
  stuck parser, provide a heartbeat or establish public-upload safety.
- Physical deletion is eventual and needs working database/storage/worker. If both
  rollback unlink and queue writing fail, or uncertain-upload fresh checks fail,
  preserved orphan files need operational reconciliation. Delayed reference checks
  reduce COMMIT races; disk and SQL are not one distributed atomic transaction.
  Storage snapshots/backups may retain prior copies.
- English-labelled layouts, numeric formats and row limits are limited. Unit/currency
  conversion, invoice aggregation, negative credit notes and automatic correction
  rebasing are unsupported. Citation validation does not prove answer entailment;
  retrieval can surface irrelevant passages.
