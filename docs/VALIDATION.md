# Executed validation

## Current reviewed-ZIP merge — 6 October 2026

The supplied ZIP's 129 tests were independently executed. The current merged suite
passes **147 tests** on temporary SQLite and dedicated PostgreSQL. Ruff lint/format,
TypeScript, modified-frontend formatting, native and Docker production builds pass.
Four Chromium flows pass on native SQLite and four on Docker/PostgreSQL. One
upstream Starlette/httpx warning remains in each backend suite.

The additive `0002 → 0003` migration passes against isolated existing SQLite records
and a restored disposable PostgreSQL backup. Checked native/PostgreSQL account and
business values, original stored PDFs and all 15 sample-PDF hashes remain intact.
No application test-table reset or volume deletion occurred. The exact preservation
counts, bug report, simulated failures, executed dry run and commands are in
`MERGE_VERIFICATION.md`. Evaluations were rerun and retain their documented limits.
Live embeddings, a paid provider, public deployment and remote CI were not executed.

Earlier sections below retain historical results rather than describing this merge.

## Historical initial implementation (before independent-review repairs)

Executed in this workspace on 6 October 2026 (client timezone Asia/Kolkata). All sample documents and validation accounts are synthetic. Commands below were actually run; optional live model/provider results are not claimed.

| Check | Recorded outcome |
| --- | --- |
| Native SQLite pytest suite | 53 passed |
| Separate PostgreSQL pytest suite inside Docker | 53 passed |
| Ruff lint and format | Passed |
| Frontend TypeScript | Passed |
| Next.js production build, native and Docker | Passed |
| Docker Compose PostgreSQL/API/worker/frontend | Built and started locally |
| Chromium browser journey on native app | 1 passed in 8.4 seconds |
| Chromium browser journey on final Docker/PostgreSQL | 1 passed in 6.5 seconds |
| Restart persistence through Docker frontend | Session, case, extraction, and original PDF hash survived restart |
| Synthetic classification evaluation | Both baselines macro-F1 1.000 on 240 held-out generated texts |
| Synthetic extraction evaluation | Accuracy 1.000 on 15 known-layout PDFs; no fixture errors |
| Keyword retrieval evaluation | Recall@5 0.9095238095; MRR 1.000; two unanswerable queries returned passages |

The suite emitted one upstream Starlette deprecation warning about its httpx TestClient integration. Assertions pass; this is recorded instead of hidden.

The browser flow covers registration and login/logout, case creation, uploads, completed processing, INR 2,200 discrepancy, audited correction, refreshed findings, real PDF byte response and page-fragment popup, no-key evidence retrieval, CSV download, current JSON export, and mobile overflow. Tests use Chromium's full headless channel for the built-in PDF viewer, rather than the minimal headless shell.

## PostgreSQL suite reproduction

Create a separate disposable test database inside the local running Compose database:

```bash
docker compose exec -T db createdb -U docverify docverify_test
docker compose exec -T \
  -e TEST_DATABASE_URL=postgresql+psycopg://docverify:docverify_local@db:5432/docverify_test \
  backend python -m pytest -q
```

If the database already exists, skip `createdb`. Substitute your configured password in the test URL. The test fixture drops/recreates its target tables; do not point it at the application database. `conftest.py` defaults to an isolated temporary SQLite database when `TEST_DATABASE_URL` is absent.

## Issues caught and resolved

- The initial synthetic full-text classifier misclassified richer sample PDFs despite a perfect generated-text score. Heading weighting was applied consistently in training and inference; demo expectations now pass.
- Next.js's development indicator covered the sidebar Sign out button. It is disabled through the documented setting.
- A React effect could clear save feedback after updated document props arrived. The notice now resets only when switching documents.
- The minimal Chromium headless shell did not show source PDF popups. Full Chromium headless is configured and the popup is tested.
- Docker's CLI/credential helper were outside PATH on this Mac. The README gives the application-path setup.
- Docker and native servers originally competed for port 3000. Compose supports `WEB_PORT`, paired with `APP_ORIGIN`.

## Optional checks not executed live

Sentence Transformers weights were not downloaded and no real semantic quality evaluation was run. The visible unavailable-model fallback is tested. A real Claude key was not supplied, so no paid/live provider calls or live generation quality numbers were produced. Mocked tests verify grounding/citation boundaries and provider outage fallback. Scanned-PDF OCR is deliberately outside the core and is detected explicitly.


## Independent-review repair iteration — 6 October 2026

These results are newly executed against repaired source, rather than inherited from the initial 53-test validation.

- Reproduction: the 53 original tests passed while seven added independent-review regressions failed. All seven are now repaired without removing their assertions.
- Final SQLite suite: **92 passed**, one upstream Starlette/httpx deprecation warning.
- Final dedicated PostgreSQL suite: **92 passed**, the same upstream warning. It required a dedicated `docverify_test` target and `DOCVERIFY_ALLOW_EXTERNAL_TEST_DB=1`.
- Ruff lint/format, Prettier, TypeScript and native/Docker production builds passed.
- `scripts/verify.py` executed generation, training, tests, lint/format, TypeScript, production build and both evaluation levels. The later unknown-unit regressions were also executed with the entire backend suite.
- Four Chromium flows passed on native SQLite and Docker/PostgreSQL: the original journey, delayed A→B load/save identity, dirty drafts/polling/stay-discard, and stale-tab conflict/reload. The final dirty-flow also checks that sign-out can be cancelled without deleting the session.
- Standalone `PORT=3003 npm start` launched the generated server; the login page and compiled static asset returned 200. This checks the frontend start contract, not a separate full backend deployment on that port.
- Additive `0001 → 0002` upgrades were checked in isolated SQLite and in a restored disposable PostgreSQL backup copy. The application database also reached 0002 through normal Compose startup.
- Native preservation: all earlier account/case/document/audit IDs, effective business values and storage names remained; all 15 original sample PDF hashes were unchanged.
- PostgreSQL preservation against the pre-upgrade private backup: all prior 3 users, 3 sessions, 2 cases, 3 documents and 1 correction retained their account/business values; the original PDF files remained. The synthetic persistence session/case/extraction values/PDF hash continued to work after migration/rebuild.
- No application table reset, volume deletion, public deployment, Git commit or invented author identity occurred. Existing staged work was preserved.

Actual new quality measurements: runtime case/page/chunk Recall@5 **0.800**, MRR **0.600**, support-passage coverage **0.750**; three of nine unsupported questions still retrieved evidence, and no-key mode abstained on all 24 test queries. The unchanged classifier's harder synthetic challenge macro-F1 is **0.6666666667**, keyword macro-F1 **0.100**. The easy synthetic and whole-PDF metrics remain separately labelled. See ML_EVALUATION.md and metric JSON for definitions/limits.

A mutable Docker base tag initially hit a registry DNS failure. Pinning the previously validated cached image digests resolved the build; no blanket dependency upgrade was performed. Live embedding/provider quality remains unexecuted because weights/key are absent. GitHub CI is authored, not claimed run remotely.

### Safe current PostgreSQL command

```bash
docker compose exec -T \
  -e TEST_DATABASE_URL=postgresql+psycopg://docverify:docverify_local@db:5432/docverify_test \
  -e DOCVERIFY_ALLOW_EXTERNAL_TEST_DB=1 \
  backend python -m pytest -q
```

The older historical command above omitted the new opt-in and is retained only as historical evidence; use this current command. Substitute your configured password without pointing at the application database. Default tests create a temporary SQLite target.
