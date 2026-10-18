# ML evaluation and validity limits

These measurements were executed locally on the included synthetic data. Machine-readable metric files are under `evaluation/`. No metric estimates real-world accuracy. Model weights are reproducible local outputs, not hand-written predictions or fake analytics.

## Document classification

- 720 synthetic text documents: three classes × six generator families × 40 documents.
- Train: 480 rows from families 0–3. Test: 240 rows from entirely held-out families 4–5.
- Seed: 42. Labels: purchase_order, quotation, invoice.
- Keyword baseline searches initial headings for documented terms.
- ML: unigram/bigram TF-IDF, sublinear term frequency, first-line heading repeated ten times, logistic regression C=1.0, max_iter=1000, random_state=42. Heading weighting is applied identically by a serializable preprocessor in training and inference.
- Test macro-F1: **1.000 for keyword rules and 1.000 for TF-IDF/logistic regression**.

Measured ML confusion matrix, rows=true and columns=predicted, label order purchase_order / quotation / invoice:

| True class | Purchase order | Quotation | Invoice |
| --- | ---: | ---: | ---: |
| Purchase order | 80 | 0 | 0 |
| Quotation | 0 | 80 | 0 |
| Invoice | 0 | 0 | 80 |

Entire template families are separated, but headings and class-specific phrasing repeat across splits. This makes the task easy. The keyword baseline matching the model shows no demonstrated incremental ML benefit on this dataset. The initial unweighted model performed perfectly on generated text but misclassified the richer PDF fixtures; executable demo tests exposed this distribution shift. Heading weighting repaired that particular mismatch. It is an engineering feature change informed by the demo fixtures, not an unbiased improvement measured on an untouched real-world test set.

The application shows both predictions, permits correcting the type, and flags disagreement. A future evaluation needs diverse, independently labelled supplier PDFs, unseen vendors and headings, a validation set for model choices, and a held-out final test set.

## Structured extraction

- 15 labelled synthetic PDFs in three PDF layout families: pipe-delimited rows, positioned column tables, and labelled item cards.
- Every metadata field, expected null, line-item count, and item attribute is checked against `sample_data/manifest.json`. Numeric formatting differences are compared as Decimal values; textual values use exact equality.
- Executed field-level accuracy: **1.000**, with zero fixture errors. Per-field numerators/denominators are in `extraction_metrics.json`.
- Page-two provenance and unique exact-match coordinates are also tested separately by pytest.

This is a parser regression/coverage benchmark over intentionally supported layouts. It is not an independent evaluation of general extraction. Unknown formats, missing labels, additional currencies/locales, and complex tables can lower coverage. Null handling and provenance matter alongside accuracy: the application must refuse to infer unsupported values.

## Keyword retrieval

- Corpus: the same 15 PDFs; evaluation ranks one combined text per PDF. Runtime retrieval ranks approximately 700-character page chunks, so this metric evaluates the ranking baseline, not every aspect of runtime chunking.
- Eight labelled queries: five answerable, three unanswerable. Relevant document sets are explicit in `retrieval_queries.json`.
- Unigram/bigram TF-IDF, sublinear TF, cosine similarity; discard scores ≤0.035. Runtime uses the same keyword scorer.
- **Recall@5 = 0.9095238095; MRR = 1.000.** Recall is the fraction of each query's relevant document set in its top five, averaged over answerable queries. MRR uses the first relevant document's rank across all returned results.
- **Two of three unanswerable queries returned evidence** because they shared words such as supplier/date with unrelated source passages. This is a measured weakness. Relevance and answerability are different; a retrieved date is not evidence of a warranty date.

No-key mode provides evidence and never simulates an answer, including for unanswerable questions. Mocked provider tests check insufficient evidence, schema/citation membership, and failure fallback; they do not measure real model factuality. Similarity scores are labelled as similarity, not confidence.

## Runtime case/page/chunk evaluation (repair iteration)

`evaluate_runtime.py` generates ten separate two-page fictional PDFs in five cases. Metadata and item evidence occupy different pages; shared administrative text creates multiple ~700-character chunks. Gold relevance labels use document ID, page, and a required passage fragment to derive actual runtime chunk IDs. The evaluator asserts that labels point to real chunks.

Two validation cases contain 16 queries; three held-out test cases contain 24. Each case includes direct questions, one paraphrase, an ambiguous price question, and three unsupported questions. The generator definitions and labels were fixed before executing the test. Threshold candidates 0.035, 0.02, 0.06, 0.1, and 0.16 were scored only on validation, with a declared support-coverage/unsupported-hit/recall objective and stable ties. The selected threshold is **0.035**. `Settings` reads the recorded validation configuration by default; explicit environment values override it. Test outcomes were not used to alter the model or threshold.

Measured held-out results in `runtime_retrieval_metrics.json`:

| Measurement | Result |
| --- | ---: |
| Case-scoped chunk Recall@5 | 0.800 |
| MRR (within returned top five chunks) | 0.600 |
| Gold support-passage coverage, answerable queries | 0.750 |
| Unsupported questions that nevertheless retrieved evidence | 3 of 9 |
| Ambiguous questions requiring clarification | 3 |
| No-key abstentions | 24 of 24 |

Support coverage checks manually labelled required passages, not generated-answer entailment. No-key mode abstains on answerable questions too, so that abstention count is behavior evidence, not evidence of an effective answer model. Ambiguous queries are reported separately; the product cannot silently treat “the price” as a single cross-document value. These small synthetic cases do not establish real-world retrieval quality. The earlier Recall@5 0.9095 / MRR 1.0 numbers above rank whole PDFs and must not be substituted for these runtime results.

## Separately generated classification challenge

The unchanged trained model is evaluated on an independently authored synthetic challenge: unfamiliar non-class headings, business-intent text, and delivery acknowledgments labelled unknown. It includes 16 validation examples and 48 test examples. No parameter/feature change was tuned on this challenge.

Measured challenge macro-F1: **0.6666666667 for the trained model**, **0.100 for keyword rules**, over four labels including unknown. The model was trained on three classes and cannot emit unknown. Challenge confusion matrices are in `classification_challenge_metrics.json`; the original easy-test F1 1.0 remains labelled separately. Intent phrases still repeat, and some overlap training vocabulary, so neither challenge nor baseline proves broad document recognition. No permitted real dataset was supplied/used.

## Optional semantic retrieval and generation

Sentence Transformers supports normalized MiniLM embeddings, per-case stored chunk vectors, cosine-style dot-product ranking, and keyword fallback. Stored vectors now carry model identifier, resolved weight revision/local hash, dimension, normalization, and chunking version. Incompatible or unlabelled legacy vectors are never compared to new queries. Model load/inference failures are handled visibly. The core environment does not include downloaded weights, so **no live semantic quality numbers are claimed**. Optional dependencies are isolated from the core lock. A mock vector test can verify mechanics but cannot establish model quality.

Claude Messages is the sole optional answer provider. Without a configured key, the full extraction/review/verification/search/export product works. No live provider response or provider evaluation is claimed. Citation membership does not guarantee the answer is entailed by its passages; human review remains necessary. Numerical comparisons come from deterministic findings, not newly invented arithmetic.

## Reproduction

```bash
PYTHONPATH=backend .venv/bin/python scripts/generate_samples.py
PYTHONPATH=backend .venv/bin/python scripts/train_classifier.py
PYTHONPATH=backend .venv/bin/python scripts/evaluate.py
```

The scripts print measured results and write metrics. Test/demo expectations assert meaningful outcomes instead of snapshotting implementation details. An honest portfolio description is: “I implemented and evaluated a reproducible synthetic document-classification and retrieval pipeline, and measured a conservative parser on labelled supported layouts.”
