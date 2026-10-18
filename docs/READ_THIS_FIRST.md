# Understand DocVerify before presenting it

Start with this sentence: **“This app compares supported procurement documents; it does not prove they are genuine.”** A purchase order says what the buyer requested, a quotation says what the supplier offered, and an invoice says what the supplier billed. The app helps a reviewer notice inconsistent quantities, prices and totals.

## A concrete example

Your purchase order contains 100 metres of cable at ₹80/metre: its amount is ₹8000. The invoice contains 120 metres at ₹85/metre: its amount is ₹10200. Both rows can be internally correct because their own multiplication works. They still disagree with each other on quantity and unit price. The subtotal difference is ₹2200.

These are two different checks:

- **Within one document:** does quantity × price equal the stated amount?
- **Between documents:** do matched rows have the same quantity and price?

A price difference could reflect an approved change. An invoice might cover partial delivery. The app reports the difference; it does not decide who is dishonest.

## Read the code in this order

### 1. `backend/app/schemas.py`: what data is allowed?

Read `LineItem` first. It has an item code (`sku`), description, quantity, unit, unit price, amount and optional source. `None` means unknown. It does not mean zero. `Decimal` represents the base-ten numbers used in these rules; binary floating-point is not a good default for exact currency comparisons.

Read `Extraction` next: it groups fields, rows, source locations and warnings. `Field(max_length=500)` is a validation rule, not a database query. `model_dump(mode="json")` converts validated Python data into JSON-friendly values such as decimal strings. Validation does not establish that a supplier's statement is true.

### 2. `backend/app/models.py`: what is saved?

| Table | Plain-language purpose |
| --- | --- |
| `users`, `sessions` | Who signed in and which expiring session identifies them |
| `cases` | A user's group of related documents, comparison settings and result revision |
| `documents` | PDF metadata, processing status, original/latest extraction and manual corrections |
| `jobs` | Documents waiting for work, attempts and lease tokens |
| `pages`, `chunks` | Latest extracted page text and smaller searchable passages |
| `processing_runs` | Retained successful/failed processing attempts and their metadata |
| `corrections` | Before/after review values and explicit source-resolution reasons |
| `findings` | Current differences, arithmetic issues and uncertainty messages |
| `file_deletions` | Stored files that still need physical cleanup after logical deletion |

The PDF bytes are on disk. The database stores their server-generated filename. A foreign key connects records and supports deletion of dependent records. The cleanup table intentionally has no document foreign key: its task must survive the document's removal.

### 3. `backend/app/auth.py` and `api/access.py`: who may do this?

The browser sends an opaque session cookie. The backend hashes that token and looks up the session. It checks expiry, then gets the user. For writes, it also compares a CSRF token. `owned_case` combines the requested case ID with the signed-in user's ID. A random-looking UUID alone is not authorization.

In a route signature, `Depends(current_user)` means “ask FastAPI to run this dependency before my handler.” `Depends(get_db)` gives the handler a database session. These decorators and dependencies are framework conventions, not business logic you need to reinvent.

### 4. `api/documents.py`: upload, read it top to bottom

In `upload`:

1. `owned_case(..., lock=True)` checks ownership and coordinates changes to this case.
2. The batch-count check rejects more than five files.
3. `saved` records paths this request actually created, so failed uploads can clean them up.
4. A new UUID chooses the storage path. The uploaded filename does not choose a directory.
5. `save_upload` reads chunks, counts bytes and writes the file.
6. `validate_file` checks content, then parses enough of the PDF to reject malformed/unreadable input and enforce the page limit.
7. `enqueue_file` creates a document row and its job. `flush` sends pending SQL statements inside the transaction; it is not the same as `commit`.
8. `refresh_case` updates the case revision and current results in that transaction.
9. `commit_started` records whether the outcome could be uncertain if the connection drops.
10. `commit` finishes the SQL transaction. The handler returns document summaries.
11. The exception branch rolls back and performs appropriate disk cleanup. After a lost commit reply it preserves PDFs immediately, checks references using a fresh session, and schedules delayed reconciliation of unreferenced files. If that check is unavailable, it retains files and tells you to refresh before re-uploading. Deleting immediately after an uncertain commit could lose valid data.

Open `services/file_storage.py` and read `save_upload`. The `while True` loop ends when reading returns empty bytes. The limit is checked before writing the new chunk. The `with` statement closes the handle even if an exception occurs.

### 5. `worker.py`: work after the HTTP response

The `main` loop repeatedly calls `run_once`. It briefly sleeps when there is no work. `run_once` retries one due file-deletion task, claims a processing job, then passes it to `process_claim`.

`process_claim` is the main reading entry point: extract, save the result, log a small success event; if something fails, record the failed attempt. The helper functions keep these responsibilities separate.

A **lease** says which worker attempt currently owns the job. A worker may crash and another attempt may take over later. The final write checks the token so the old attempt cannot overwrite newer work. A lease does not stop a process that is stuck inside the PDF parser; that limitation is still documented.

### 6. `services/extraction.py`: text becomes fields

`extract_pdf` obtains selectable text page by page. It does not recognize words in photographs. An image-only document therefore fails with an explicit OCR message.

`parse_pages` creates a result, loops through pages and lines, calls `read_fields` and `read_line_item`, then calls `check_fields`. This is the same basic traversal idea as nested loops over a vector of strings in C++.

`number` validates formatting before removing grouping commas. Try explaining these three outcomes without running them:

| Input | Result | Reason |
| --- | --- | --- |
| `1,23,456.78` | `Decimal("123456.78")` | Supported Indian grouping with dot decimal |
| `12,34` | `None` | Ambiguous/unsupported grouping; do not invent the value 1234 |
| `0` | `Decimal("0")` | A known zero is valid and different from an unknown value |

A source reference records the document, page and text snippet. A bounding box is saved only when the text match is unique. A manual value has different provenance from text actually extracted from the PDF.

### 7. `services/verification.py`: understand the entry point line by line

The main function is intentionally short:

```python
findings = []
for document in documents:
    check_document(document, tolerance, findings)
pairs = check_comparison_scope(documents, selection, findings)
for reference, target in pairs:
    compare_document_pair(reference, target, tolerance, findings)
return findings
```

- The empty list will collect issues; the function does not start by assuming a document is genuine.
- The first loop checks individual documents. Pending/failed documents do not contribute current extracted facts.
- `tolerance` allows configured rounding differences for monetary checks.
- `check_comparison_scope` chooses a reference and individual targets, and can add a warning when the selection is incomplete.
- The second loop compares each selected pair. It does not compare every target against every other target.
- The returned list contains structured findings; a separate service saves them to the database.

Read `check_line_totals`, then `check_document_totals`. A row is checked only when the necessary values are known. A complete-table subtotal check is withheld if source limitations mean the table may be incomplete. Read `matching.match_candidates` before `check_matched_row`: matching identity must precede comparing numbers.

`add_finding` attaches source references and builds a stable ID from material facts. Reordering a row should not reset its review status; changing the actual quantity should create a materially different finding. The tests exercise both cases.

### 8. `services/corrections.py`: human changes and stale tabs

The request carries a revision. If it is older than the server's revision, the API returns 409. Otherwise the service validates row identities and source references, saves the correction, appends before/after history and recomputes results. It does not edit the PDF.

Source limitations are separate from ordinary field warnings. Typing a total into a form does not suddenly make an unreadable page readable. Resolving a source limitation requires an explicit reason. The owner can perform this action; there is no independent administrator approval process.

### 9. `services/retrieval.py`: the optional ML/NLP part

TF-IDF represents words as numbers and ranks passages for a query. Classification separately predicts document type using a locally trained synthetic TF-IDF/logistic model. Neither process decides whether the content is authentic.

The optional embedding model can improve ranking, but missing/incompatible weights fall back to keywords. The optional answer provider receives selected evidence. `parse_provider_answer` checks its response structure; citation validation ensures IDs belong to the supplied set. Valid IDs alone cannot establish that every generated claim is supported.

### 10. Frontend: follow one action

`frontend/lib/api.ts` sends a request, adds the CSRF header for changes and turns API errors into messages. `app/cases/[id]/page.tsx` has the upload/retry/delete/save actions. `use-case-workspace.ts` loads and polls the case, tracks the selected document and guards unsaved changes. Components render documents, findings, the editor and evidence.

`useState` holds a value for the current UI. Calling its setter requests another render. `useEffect` starts work such as polling and cleans it up. `useRef` holds a value across renders without triggering one. `AbortController` cancels an outdated request. The selection checks also prevent a slower response for document A from appearing while document B is selected.

## Python vocabulary you should be able to explain

| Python | Familiar idea |
| --- | --- |
| `list` | An ordered collection, similar to a C++ vector |
| `dict` | Key/value lookup, similar in use to an unordered map |
| `None` | Missing/unknown value; not zero or an empty string |
| `for value in values` | Iterate through a collection |
| `with ...` | Acquire a resource and reliably clean it up, similar in purpose to RAII |
| `try / except` | Handle a specific failure path |
| `raise` | Signal an exception to the caller |
| `@router.post(...)` | Register the function as an HTTP route |
| `**mapping` | Supply named values from a dictionary |
| `-> list[dict]` | A type hint describing the return value |
| `flush / commit / rollback` | Send statements inside a transaction / finish it / abandon uncommitted changes |

## Questions to rehearse with the code open

1. Why can two matching PDFs still be fake?
2. Why is an unknown quantity not zero?
3. Why use Decimal for the monetary rules?
4. What survives when a worker crashes?
5. Why check ownership in the backend even if the UI hides other cases?
6. Why can a failed HTTP response follow a successful database commit?
7. Why does deleting a case need a cleanup task?
8. What happens if the provider returns nonsense or times out?
9. What does your model's synthetic F1 score fail to measure?
10. Which code and tests would you change to add OCR without claiming authenticity?

If you cannot trace one of these, use the local Codex prompt to learn that section. Do not memorize a description that the code cannot support.
