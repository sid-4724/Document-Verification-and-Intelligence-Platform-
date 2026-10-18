# DocVerify — Document Intelligence and Verification Platform

A local portfolio application for private cases containing purchase orders, quotations and invoices. It extracts supported selectable-text PDF fields, shows their original pages, preserves processing/review history, and checks discrepancies using Decimal rules. This implementation and its review repairs were developed with AI assistance in Codex; the code and executed evidence are documented for learning and interviews.

Unknown values stay null. Extraction uncertainty, document differences and internal arithmetic errors are separate outcomes. A normal field save cannot clear an unreadable-page warning. One reference is compared to individual targets; invoice aggregation is unsupported.

**Verification means supported field and arithmetic consistency checks. It does not establish whether a document is genuine.** No OCR, issuer registry, QR authenticity check or digital-signature verification is implemented. Read `docs/MERGE_VERIFICATION.md` for current fixes and executed results, `docs/INDEPENDENT_REVIEW.md` for the supplied external review, and `docs/READ_THIS_FIRST.md` for the beginner walkthrough.

The independent review added conservative number parsing, Unicode-aware matching, safe provider failures, private error logging, durable file-deletion retries and clearer runtime functions. Run migrations through **0003** before starting the revised API and worker. Native startup below applies them automatically. Existing PDFs and accounts are retained. Deleted files are normally removed immediately; if storage fails, the UI reports pending cleanup and the worker retries it every minute. This is eventual removal, not an immediate erasure guarantee.

The merged implementation exposes owner-scoped cleanup status on the dashboard and case page. After an uncertain upload commit, files are preserved while a fresh session checks references; unreferenced files are reconciled after a delay. Refresh before re-uploading after the corresponding 503. If recovery cannot reach the database, preserved orphan files may need operational reconciliation. Retrying hides inactive snapshots while preserving reviews of unchanged material findings.

## Start with Docker / PostgreSQL

Prerequisite: Docker Engine/Desktop with Compose v2. From the repository root:

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

If `.env` already exists, retain it rather than copying over your configuration. Open **http://localhost:3000**, register your own account (password 10+ characters), and create a case. No provider credentials are required and there are no default public accounts.

Docker startup applies additive Alembic migrations before the API starts. The earlier `0002` migration preserves records, original PDF storage names, business values and old audits. Legacy overwritten history cannot be recovered: only the existing retained snapshot is backfilled, with unknown processing time/old correction bases clearly labelled. Legacy reviewed records may need an explicit audited source-history review. Do not start an older backend against the upgraded review schema.

PostgreSQL and the backend are internal; only the frontend binds to localhost. Named volumes preserve database, PDFs and optional model caches. Container base images are pinned to validated digests; library versions remain in the existing lock files.

```bash
docker compose logs -f backend worker
docker compose restart
docker compose stop
```

Stopping preserves data. Do not use `down -v` for ordinary development because it deletes volumes. For another port, set `WEB_PORT=3001` and `APP_ORIGIN=http://localhost:3001` together. macOS users whose Docker CLI is outside PATH can use:

```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
docker --context desktop-linux compose up --build -d
```

## Start natively / SQLite

Prerequisites: Python **3.13**, Node **22+**, npm. These are portable setup commands, not a claim about preinstalled dependencies:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
npm --prefix frontend ci
.venv/bin/python scripts/dev.py
```

The runner keeps local data in `var/`, generates only missing fictional PDFs, trains a missing classifier, applies migrations, and starts FastAPI (8000), one worker and Next.js (3000). Ctrl+C stops its child processes. Environment variables override the runner's SQLite/storage defaults. It never resets a database.

If Docker already uses port 3000, keep it running and use an explicitly different native frontend:

```bash
.venv/bin/python scripts/dev.py --web-port 3002
```

Open http://localhost:3002. `--api-port 8002` is available if the API port is also occupied. The runner derives the proxy target and browser origin from these ports unless you explicitly configured them.

Manual component commands (separate terminals, root working directory):

```bash
.venv/bin/alembic -c backend/alembic.ini upgrade head
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
PYTHONPATH=backend .venv/bin/python -m app.worker
npm --prefix frontend run dev
```

For manual native startup with a Docker-style `.env`, first set `DATABASE_URL=sqlite:///./var/docverify.db`, `STORAGE_DIR=var/uploads`, `BACKEND_URL=http://127.0.0.1:8000` and the actual `APP_ORIGIN`.

Production frontend startup uses the generated standalone server, consistent with the build:

```bash
npm --prefix frontend run build
npm --prefix frontend start
```

The start script copies `.next/static` (and optional `public`) into the standalone directory and runs `server.js`. `PORT` and `DOCVERIFY_BIND_HOST` can configure local binding. `BACKEND_URL` is baked into rewrites at build time, so configure it before building. Docker performs the equivalent static copy and launches `server.js` directly.

## Demo and review workflow

With `DEMO_MODE=true`, explicitly click **Load sample cases**. It creates seven fictional cases only for the current user. It never auto-populates accounts.

1. Open “04 · Quantity + price (INR 2,200)”. Its unique purchase order becomes the automatic reference; the invoice is its target. Use Comparison selection to choose explicitly when the case is ambiguous.
2. Inspect 100 → 120 quantity, 80 → 85 unit price, and INR 2,200 subtotal difference. Each card names its rule/documents and opens the source page.
3. Open the invoice. Change quantity to 100, unit price to 80, line amount/subtotal/total to 8000, then Save review & verify. Current reviewed findings disappear while the original PDF remains unchanged.
4. Inspect first retained extraction, latest raw runs and before/after audit. Add two identical source-null rows: both retain distinct identities. Field edits preserve row IDs and provenance.
5. A new processing run does not silently merge into old corrections. A stale tab receives 409 without losing its draft. Switching documents/off the review offers Keep editing or Discard changes.
6. Search Original PDF source for quoted passages or Current reviewed data for separately labelled effective records. Numerical checks use the selected scope: original raw values can still differ even after the human-reviewed values match. No key means evidence-only mode, never a simulated answer.
7. Export JSON with effective/first/latest raw data and CSV with current reviewed findings. CSV escapes potential spreadsheet formulas.

Case readiness reports failed, unreadable and unresolved documents. **Zero findings alone never means every document was successfully checked.** Several invoices are individual targets with an explicit unsupported-aggregation warning; the app does not infer partial fulfilment totals.

| Case | Expected supported checks |
| --- | --- |
| Matching | No discrepancy for supported complete fields |
| Quantity | Quantity/subtotal deltas |
| Unit price | Unit-price/subtotal deltas |
| Both | Quantity/price and INR 2,200 subtotal delta |
| Arithmetic + missing item | Incorrect multiplication, missing connector, subtotal delta |
| Incomplete + ambiguous | Unknown identifier/quantity and duplicate-match review |
| Incompatible | Currency/unit review; incompatible comparisons skipped |

`sample_data/manifest.json` provides labels; `sample_quotation.pdf` demonstrates the third class. The fixtures use three layouts and fictional companies. Existing sample PDFs are not overwritten by generation. Runtime evaluation uses separate multi-page fictional files under `evaluation/runtime_samples/`.

## Verify and evaluate

After installing dependencies:

```bash
.venv/bin/python scripts/verify.py
```

This runs generation/training, the backend suite, Ruff checks, TypeScript, production build and both historical/runtime evaluations. To add browser checks with a running app and Chromium installed, use `--browser`. `--skip-build` is available when deliberately skipping a build; it is not a full verification claim.

Individual commands remain supported:

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
npm --prefix frontend run typecheck
npm --prefix frontend run build
PYTHONPATH=backend .venv/bin/python scripts/generate_samples.py
PYTHONPATH=backend .venv/bin/python scripts/train_classifier.py
PYTHONPATH=backend .venv/bin/python scripts/evaluate.py
```

Browser checks, from another terminal:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

Set `E2E_BASE_URL=http://localhost:3002` for the alternate native port. Full Chromium headless supports the PDF popup. Four flows cover the main journey, delayed A→B response/save identity, dirty-draft choices with polling, and stale-tab conflicts. Traces/screenshots are ignored runtime outputs.

Default pytest uses temporary SQLite. External destructive tests require a dedicated target and explicit opt-in; the fixture refuses application identity/database name, including host aliases. **Never choose the application database.** For local Compose:

```bash
docker compose exec -T db createdb -U docverify docverify_test
docker compose exec -T \
  -e TEST_DATABASE_URL=postgresql+psycopg://docverify:docverify_local@db:5432/docverify_test \
  -e DOCVERIFY_ALLOW_EXTERNAL_TEST_DB=1 \
  backend python -m pytest -q
```

Skip `createdb` if the test database already exists and substitute your configured database password. The fixture clears only its validated disposable target. A separate migration test upgrades an old-schema temporary database and checks preserved values and honest legacy metadata. CI under `.github/workflows/verify.yml` runs these meaningful checks; remote execution is not implied by local validation.

Actual measured quality, all synthetic:

- Easy classification test: rules and TF-IDF/logistic macro-F1 1.000; repeated headings/phrases limit validity.
- Separately authored unfamiliar-heading/unknown-class challenge: model macro-F1 0.667, rules 0.100; no challenge tuning.
- Supported-layout extraction fixture accuracy: 1.000 on 15 PDFs; this is regression coverage, not general supplier accuracy.
- Historical whole-PDF retrieval baseline: Recall@5 0.910, MRR 1.000.
- Runtime case/page/chunk held-out test: Recall@5 0.800, MRR 0.600, gold support-passage coverage 0.750. Three unsupported questions retrieved evidence; all 24 queries abstained in no-key mode.

Threshold selection uses validation only, not the test. Read `docs/ML_EVALUATION.md` and metric JSON files for definitions/limits; runtime support coverage does not measure model-answer factuality.

Restart check:

```bash
.venv/bin/python scripts/verify_persistence.py seed
docker compose restart
.venv/bin/python scripts/verify_persistence.py check
```

The ignored state file contains a synthetic account session and a PDF hash. For native mode, restart the runner between phases; use `--url` for another frontend port.

## Configuration

| Setting | Purpose |
| --- | --- |
| DATABASE_URL / STORAGE_DIR | Shared API/worker database and persistent PDF directory |
| POSTGRES_PASSWORD | Local Compose database password; change the local default if needed |
| APP_ORIGIN / WEB_PORT | Exact browser origin and frontend port; localhost differs from 127.0.0.1 |
| COOKIE_SECURE | True for HTTPS, false for local HTTP |
| DEMO_MODE | Enables explicit fictional-case loading |
| MAX_FILE_MB / MAX_PAGES | Per-PDF limits, default 10 MB / 30 pages; five PDFs per request |
| JOB_MAX_ATTEMPTS / JOB_LEASE_SECONDS | Automatic attempt bound and stale lease, default 3 / 300 s |
| ANTHROPIC_API_KEY / ANTHROPIC_MODEL | Optional backend-only answer provider; blank key keeps evidence-only mode |
| SEMANTIC_ENABLED / EMBEDDING_MODEL | Optional pretrained ranking, disabled by default |
| EMBEDDING_LOCAL_ONLY / EMBEDDING_REVISION | Local-only loading by default and optional pinned weight revision |
| KEYWORD_MIN_SCORE / SEMANTIC_MIN_SCORE | Retrieval cutoffs; lexical default/validation choice 0.035, semantic default 0.3 |
| BACKEND_URL | Server proxy destination; build-time in production, never a browser API key |

Optional semantic setup, native:

```bash
.venv/bin/python -m pip install -r backend/requirements-semantic.txt
SEMANTIC_ENABLED=true EMBEDDING_LOCAL_ONLY=false .venv/bin/python scripts/dev.py
```

Cache weights first, then use local-only loading. Restart API/worker after configuration changes and reprocess documents to index compatible vectors. For Docker, build backend/worker with `--build-arg INSTALL_SEMANTIC=true`, configure the same settings, and restart. Missing models/inference/configuration mismatch falls back visibly to keywords. Legacy vectors without model metadata are never compared as compatible.

No live semantic/provider quality was evaluated without weights/key. Reviewed records are separately labelled, citation IDs are checked, and unsupported answers are refused; prompt/citation checks do not prove every model sentence is entailed or immune to injection.

## Limits and troubleshooting

- OCR is deferred. Scanned PDFs fail explicitly; mixed-page/table limitations survive field saves until a reasoned manual source-review action is recorded. Manual review does not create OCR text.
- Parsing supports labelled English metadata and three table styles. Localized dates/decimals, arbitrary supplier layouts, merged tables, discounts/shipping and handwriting need an extension/review. Dates remain source strings.
- Numbers support nonnegative signless dot decimals and valid Western/Indian grouping: `1234.56`, `1,234.56`, `1,23,456.78`. Ambiguous separators/spaces, exponent notation, signed credit-note amounts, `.5` and `1.` stay unknown. Extraction retains at most 200 supported rows and records omissions as source limitations.
- Matching is conservative. Unit aliases are names, not numeric conversions; currencies are not converted. Fuzzy candidates and conflicting/duplicate identifiers need review. Invoice aggregation and automatic correction rebase are unsupported.
- Pending jobs require a worker sharing database/storage. Inspect worker logs. Leases/retries are bounded; there is no heartbeat, job-isolation sandbox or production throughput claim.
- A 409 means newer review/run state exists. The draft remains; reload deliberately and review again. Origin/CSRF failures require the configured hostname and a refreshed session token.
- Case readiness distinguishes incomplete processing/review from zero findings. Exact PDF coordinates are preserved only for unique matches; no overlay is drawn.
- Auth throttling is in-process. Password reset, distributed rate limiting, full operational backups/restore automation, processing isolation and independently verified answer entailment remain future work.
- PDFs and database contents have no application-level encryption at rest. File/batch/page limits do not provide aggregate account/storage quotas. A worker lease does not enforce a hard PDF-processing timeout. Physical cleanup needs functioning worker/storage/database and is not immediate guaranteed erasure.

Learning material: `docs/CODE_WALKTHROUGH.md`, `DESIGN_DECISIONS.md`, `INTERVIEW_GUIDE.md`, `LEARNING_EXERCISES.md`, `REVIEW_FIXES.md`, `ARCHITECTURE.md`, and `VALIDATION.md`. `IMPLEMENTATION_STATUS.md` separates this repair iteration from historical results. No Git commit or author identity is invented.
