# DocVerify implementation status

## Reviewed ZIP merge and robustness iteration

- [x] Compare reviewed archive against the current source and prior sanitized ZIP.
- [x] Verify proposed fixes/tests; merge code without replacing private/local configuration.
- [x] Complete all ten requested robustness fixes and additional failure-path regressions.
- [x] Validate isolated migrations, tests, lint, TypeScript/builds and available browser/PostgreSQL checks.
- [x] Update beginner walkthrough, concrete bug report, dry run and limitations.
- [x] Produce a sanitized updated review ZIP from verified current source.

Claims in the supplied review documents are external review evidence, not this agent's executed validation. Original data and staged work are preserved.

Current results: 147 backend tests pass on isolated SQLite and PostgreSQL; four browser flows pass on each deployment. Native/Docker builds, Ruff, TypeScript and additive 0003 preservation pass. See `docs/MERGE_VERIFICATION.md` for the ten fixes, changed files, commands, dry run and limitations. Earlier result counts below are historical.

## Independent-review repair iteration (complete)

- [x] Reproduce reported regressions with disposable test data.
- [x] Stable row/finding identity; deterministic matching precedence and comparison scope.
- [x] Source limitations, extraction runs, audited revisions, stale-edit conflicts; additive migration.
- [x] Safe frontend document loading and dirty-draft protection.
- [x] Explicit original/reviewed answer context and embedding compatibility metadata.
- [x] Focused route/services/UI refactor; test-database safety and portable verification/CI.
- [x] Runtime case/chunk retrieval evaluation and harder synthetic classification evaluation.
- [x] Code walkthrough, decisions, interview guide, exercises, repair evidence.
- [x] Verify SQLite/PostgreSQL migrations and data preservation, tests, builds, evaluations, and browser flows.


### Verified repair outcomes

- Seven regressions reproduced against the old implementation (7 failed, original 53 passed); all now pass.
- Final backend suite: 92 passed on isolated SQLite and on dedicated PostgreSQL; original assertions retained. One upstream TestClient deprecation warning remains.
- Four browser flows passed on native/Docker: complete journey, delayed A→B identity/save target, dirty draft stay/discard with polling and sign-out protection, stale-tab conflict/reload.
- Ruff/Prettier/TypeScript/native and Docker builds passed; portable verify script executed. Standalone start/login/static assets verified on port 3003.
- Additive migration tested on SQLite and PostgreSQL backup copy; application migrated normally without reset. Prior native and PostgreSQL account/case/document/correction business values and original PDFs preserved.
- Runtime chunk test: Recall@5 0.800, MRR 0.600, gold support coverage 0.750; three unsupported questions retrieved passages, all 24 no-key queries abstained. Harder synthetic classifier macro-F1 0.667; rules 0.100. Historical easy/document-level metrics remain labelled separately.
- Added focused API/services/UI modules, run/review/provenance metadata, comparison selection, external-test safety, CI, and all requested learning/repair documents.
- Final Docker app is available at localhost:3000. Temporary native/standalone validation servers were stopped. Private migration backups are ignored under var/review-baseline; application volumes retained.
- No library version upgrade, commit, author identity, public deployment, or live provider/model quality claim was fabricated. Optional live model/provider checks and remote GitHub CI remain unexecuted.

Existing staged files are being preserved; no commit or replacement scaffold is planned. Earlier results below are historical, not validation of this repair iteration.

- [x] Inspect workspace and instructions (empty workspace; no AGENTS.md).
- [x] Stage 1: Configuration, migrations, accounts, ownership, health checks.
- [x] Stage 2: PDF uploads, persistent jobs, extraction, source viewer.
- [x] Stage 3: Audited corrections, verification, current exports.
- [x] Stage 4: Classification, retrieval, optional grounded provider.
- [x] Stage 5: Responsive frontend, synthetic demos, evaluation, tests, documentation.
- [x] Stage 6: Run checks and browser journey; fix failures.

Architecture: Next.js + FastAPI + PostgreSQL + one database worker. SQLite is an explicit local development/test option. Optional semantic retrieval and LLM generation must degrade visibly to evidence search. No public deployment.

## Historical initial implementation outcomes (6 October 2026)

- SQLite: 53 pytest tests passed.
- Dedicated PostgreSQL test database: 53 tests passed, including ownership, corrections, atomic claiming, stale leases, retry bounds, and demo expectations.
- Ruff lint/format, Prettier formatting, TypeScript, native production build, and Docker production builds passed.
- Chromium essential journey passed on native SQLite (8.4 s) and final Docker/PostgreSQL (6.5 s), including an actual source PDF popup and mobile overflow assertion.
- Docker restart persistence passed for the session, case, original extraction, and original PDF SHA-256 hash.
- Actual synthetic evaluations: keyword/ML classification macro-F1 1.000, extraction exact field accuracy 1.000, TF-IDF Recall@5 0.9095238095 and MRR 1.000. Two unanswerable queries retrieved passages. These are explicitly synthetic, known-layout measurements.
- Final Docker stack is running on localhost:3000. Native test processes were stopped. Application/test/demo files remain on persistent local volumes; no public deployment.

## Remaining optional/repository steps

- Live semantic model quality and live Claude generation are not evaluated: weights/key are absent. Core functionality and visible fallbacks are tested. README contains exact optional setup commands.
- OCR is deliberately deferred; image-only PDFs report “OCR required.” Parser/generalization and production-hardening limitations are documented.
- Git repository initialized on main. Dependency lock files are included. Initial commit awaits user-supplied Git author name/email; no identity was invented. After supplying it, configure repository-local identity and commit the prepared source.

See docs/VALIDATION.md and docs/ML_EVALUATION.md for evidence, commands, and validity limits.
