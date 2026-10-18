# Code walkthrough

The application and this repair iteration were developed with AI assistance in Codex. This guide explains the code that exists; it is not a claim of a separate manual coding history. Read the functions, run their tests, and describe decisions you understand.

## Map of the main paths

| User action | Browser code | Backend entry / service | Stored records |
| --- | --- | --- | --- |
| Sign in | `components/auth-form.tsx:submit`, `lib/api.ts:api` | `api/accounts.py:login`, `auth.py:start_session` | users, sessions |
| Open private case | `use-case-workspace.ts:load` | `api/cases.py:get_case`, `api/access.py:owned_case`, `presentation.py:case_summary` | cases/documents/findings |
| Upload | `CaseWorkspace.upload`, `case-documents.tsx` | `api/documents.py:upload`, `enqueue_file` | documents, jobs; PDF volume |
| Process a job | status polling in the loading hook | `worker.py:claim_job`, `process_claim`; `extraction.py:extract_pdf` | processing_runs, pages, chunks, document snapshots |
| Review fields | `document-editor.tsx:save` | `api/documents.py:correct_document`, `corrections.py:save_correction` | corrected JSON, corrections, revisions, findings |
| Review source limitation | editor's manual-source action | `resolve_limitation`, `resolve_source_limitation` | resolution and before/after audit |
| Select comparisons | `comparison-settings.tsx:save` | `api/cases.py:configure_comparison`, `comparison.py:comparison_scope` | case comparison JSON and refreshed findings |
| Verify | `findings-panel.tsx` displays results | `verification.py:verify_documents`, `matching.py:match_candidates`; `case_verification.py:refresh_case` persists | findings |
| Search | `evidence-panel.tsx:search` | `api/evidence.py:search`, `retrieval.py:retrieve`, optional `answer_question` | reads selected-case chunks/current reviews |
| Export | case header download links | `api/exports.py`, `services/exports.py:structured_export`, `findings_csv` | reads current effective snapshots and findings |

Paths in the browser column are relative to `frontend/`; Python paths are relative to `backend/app/`.

## Trace one upload

1. The upload input supplies files to `CaseWorkspace.upload`. It builds a multipart `FormData` and sends `/api/cases/{id}/documents` through `api()`.
2. Next.js rewrites `/api/*` to FastAPI. The session cookie stays HttpOnly; `api()` adds the CSRF header obtained by `Shell` from `/auth/me`.
3. `current_user` validates the session and mutation token. `owned_case` checks that this user owns the case and locks it for the write.
4. `upload` streams each file to a generated UUID filename, checks size/signature, and calls `validate_pdf`. Failure rolls back rows and removes only newly written files. Successful uploads add a `Document` and one `Job` each.
5. `claim_job` uses PostgreSQL row locks plus a conditional update to claim an eligible job. The lease token is its right to complete that attempt. The worker reads the immutable uploaded PDF outside a long database transaction.
6. `extract_pdf` extracts selectable text with pdfplumber, calls `parse_pages`, and retains source snippets/pages and unique exact-match coordinates. Textless PDFs fail with OCR required. Textless pages inside otherwise readable PDFs become structural source limitations.
7. `classify` runs keyword rules and the locally trained TF-IDF/logistic model. `make_chunks` builds page-local passages and optionally labelled embeddings. Missing optional models do not break extraction.
8. The worker locks the case, verifies the lease, records a `ProcessingRun`, and updates latest raw extraction. It sets `original` only when no retained extraction exists. Raw row IDs are stable when an old source anchor maps uniquely; ambiguous new mappings receive new run-bound IDs.
9. `effective_data` chooses current corrections when present, retaining their original run basis. It combines field warnings with unresolved source limitations. `refresh_case` calls pure verification and persists findings at the new case revision.
10. The loading hook polls summaries. Opening a document cancels the previous request and checks response identity. The editor appears only when its document ID equals the selection.

## Trace one correction

1. `DocumentEditor` keeps a draft and a baseline. Changes make it dirty. Polling cannot replace a dirty draft. A selection/navigation change offers Keep editing or Discard changes.
2. `save` sends the document's current review revision, extraction basis, persistent row IDs, and values. It uses the displayed document ID, not a separately remembered file name.
3. `save_correction` verifies the extraction basis and each existing row's source. New rows receive a UUID once. Duplicate client IDs are rejected; two identical values with distinct IDs remain distinct rows.
4. `check_revision` performs an update with both document ID and expected revision. A stale request affects zero rows and returns 409 with a useful explanation. The draft remains in the browser until the user decides to reload.
5. The service stores corrected values and a complete before/after audit with user, time, document revision, and extraction revision. It rebuilds missing-field warnings but retains source limitations. A separate reasoned source-review action is required to resolve an OCR/table limitation.
6. `refresh_case` computes current results in the same transaction. Finding identity contains rule, document pair, row IDs, and material values. Unchanged findings retain review status; changed facts produce an open finding.
7. The successful save returns canonical values and newly assigned row IDs before allowing another edit, then refreshes the selected document and case results. Exports and reviewed-data provider context use these effective values. The original PDF, first retained extraction, and earlier processing runs remain available.

## Read rules before ML

Start with `matching.py` and `verification.py`. Understand identifier conflicts, exact-description precedence, unknown versus zero, units/currencies, and Decimal tolerance. Then read classification/retrieval. The trained classifier assigns types; it does not perform the arithmetic checks. The optional pretrained embedder ranks passages. The optional external Claude API writes an answer; it does not run the worker or mutate documents.

Tests that trace these paths: `test_api_worker.py`, `test_review_regressions.py`, `test_history_matching_scope.py`, `test_migrations.py`, `test_embedding_compatibility.py`, and `frontend/tests/review-regressions.spec.ts`.
