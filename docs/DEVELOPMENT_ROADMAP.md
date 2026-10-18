# Development roadmap

The current iteration deliberately completes selectable-text extraction, private cases, human review, deterministic checks, evidence search, and exports before adding more frameworks.

## Extraction and OCR

Add opt-in OCR with page rendering, rotation detection, and clear per-field uncertainty. Evaluate image-only and mixed PDFs separately. Preserve OCR word coordinates and distinguish OCR from source text. Extend table parsing to merged cells, multi-page continuation, discounts/shipping, localized decimals and dates, and richer SKU extraction. Benchmark unsupported supplier layouts instead of adding fixtures only after parser changes.

## Data and ML

Build a consented, anonymized dataset with independent field/source labels and vendor-separated train/validation/test sets. Include unknown document classes and shifted headings. Compare keyword rules, TF-IDF, embedding classifiers, and document-layout models. Measure field coverage, accuracy on extracted values, null precision, and provenance correctness. Run semantic retrieval against the same labelled queries and expand the query set with paraphrases and hard unanswerable cases.

Keep an untouched final test set. The synthetic classification score is a pipeline demonstration; it should not become a résumé claim of general procurement accuracy.

## Review and verification

Add explicit match review to approve ambiguous pairings, correction diffs per field, and richer audit exports. Support deliberate unit conversions with recorded factors and currency rates only when supplied explicitly. Expand tax rules based on document-provided information, without inferring a jurisdiction. Consider withholding confirmed missing-item findings when any relevant page/table is incomplete.

## Retrieval and grounded answers

Add query-dependent answerability tests and generation evaluation on labelled supported/unsupported questions. Validate sentence-level entailment and numerical statements against deterministic results. Provide corrected-value context separately from original quotations, retaining provenance and revision. Consider hybrid lexical/semantic retrieval and reranking once baseline measurements justify them.

## Operations and security

Add worker heartbeats, deliberate review/rebase merge tools beyond the implemented optimistic revisions, job telemetry, structured JSON logging for every service, cleanup of expired sessions and orphan files, and transactional file reconciliation. Automate recurring backups and restores beyond the migration-validation backups, keep migration CI on PostgreSQL, resource limits for PDF processing, file-scanning/isolation, distributed login throttling, password reset, optional MFA, deployment-specific secure cookie/CSP headers, and tested HTTPS reverse-proxy behavior. Validate container/resource limits and align lease duration with worst-case processing time.

For deployment scale, move original files to private object storage with authorized short-lived retrieval and add external job/vector services only if workload measurements require them. Public deployment is outside this iteration.
