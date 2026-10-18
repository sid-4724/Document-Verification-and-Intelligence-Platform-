export type User = {
  id: string;
  email: string;
  csrf: string;
  demo_mode: boolean;
};
export type Source = {
  document_id: string;
  page: number;
  snippet: string;
  bbox: number[] | null;
  extraction_revision?: number | null;
};
export type SourceLimitation = {
  id: string;
  kind: string;
  message: string;
  page: number | null;
};
export type Item = {
  id: string | null;
  sku: string | null;
  description: string;
  quantity: string | null;
  unit: string | null;
  unit_price: string | null;
  amount: string | null;
  source: Source | null;
};
export type Extraction = {
  revision: number;
  extraction_revision: number | null;
  document_type: string;
  document_number: string | null;
  order_reference: string | null;
  supplier: string | null;
  customer: string | null;
  currency: string | null;
  date: string | null;
  subtotal: string | null;
  tax: string | null;
  tax_rate: string | null;
  total: string | null;
  line_items: Item[];
  sources: Record<string, Source>;
  warnings: string[];
  source_warnings: SourceLimitation[];
  confidence_label: string;
};
export type DocumentSummary = {
  revision: number;
  raw_revision: number;
  review_extraction_revision: number | null;
  warning_count: number;
  id: string;
  filename: string;
  status: string;
  error: string | null;
  document_type: string;
  created_at: number;
};
export type DocumentDetail = DocumentSummary & {
  latest_raw: Extraction | null;
  effective_basis: string;
  processing_runs: {
    id: string;
    revision: number | null;
    status: string;
    error: string | null;
    created_at: number | null;
    metadata: Record<string, unknown>;
    extraction: Extraction;
    pages: { number: number; text: string }[];
  }[];
  resolved_limitations: {
    id: string;
    reason: string;
    user_id: string;
    created_at: number;
  }[];
  original: Extraction | null;
  data: Extraction | null;
  pages: { number: number; text: string }[];
  classification: {
    keyword_prediction: string;
    model_prediction: string | null;
    model_status: string;
    disagreement: boolean;
  } | null;
  corrections: {
    id: string;
    user_id: string;
    created_at: number;
    before: Extraction;
    after: Extraction;
    extraction_revision: number | null;
    document_revision: number | null;
    action: string;
    resolution: { reason: string } | null;
  }[];
};
export type Case = {
  cleanup_pending_count: number;
  comparison: {
    mode: string;
    reference_document_id: string | null;
    target_document_ids: string[];
    ready: boolean;
    note: string;
    multiple_invoices: boolean;
  };
  readiness: {
    status_counts: Record<string, number>;
    readable_count: number;
    unresolved_count: number;
    all_documents_checked: boolean;
    comparison_ready: boolean;
  };
  id: string;
  name: string;
  tolerance: string;
  created_at: number;
  document_count: number;
  processing_count: number;
  finding_count: number;
  documents: DocumentSummary[];
  revision: number;
  verified_revision: number;
  stale: boolean;
};
export type Finding = {
  rule: string;
  identity: Record<string, unknown>;
  id: string;
  kind: string;
  severity: string;
  explanation: string;
  expected: string | null;
  observed: string | null;
  sources: Source[];
  document_ids: string[];
  review_status: string;
};
export type Evidence = {
  id: string;
  document_id: string;
  filename: string;
  page: number;
  text: string;
  score: number;
};
export type SearchResult = {
  scope: "original" | "reviewed";
  revision: number;
  reviewed_records: ReviewedRecord[];
  evidence: Evidence[];
  answer: string | null;
  cited_source_ids: string[];
  retrieval_status: string;
  generation_status: string;
  verification: Finding[];
  correction_notice: string;
};
export type ReviewedRecord = {
  id: string;
  document_id: string;
  filename: string;
  source_type: "reviewed_record";
  values_origin: string;
  values: Extraction;
  provenance: {
    document_revision: number;
    extraction_revision: number | null;
    latest_raw_revision: number;
    correction_id: string | null;
    reviewer_id: string | null;
    corrected_at: number | null;
  };
  notice: string;
};
