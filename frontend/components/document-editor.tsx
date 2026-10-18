"use client";
import { useEffect, useState } from "react";
import {
  Save,
  Plus,
  Trash2,
  ExternalLink,
  FileText,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { api, ApiError, pretty, sourceUrl } from "@/lib/api";
import type { DocumentDetail, Extraction, Item } from "@/lib/types";
const fields = [
  "document_number",
  "order_reference",
  "supplier",
  "customer",
  "currency",
  "date",
  "subtotal",
  "tax",
  "tax_rate",
  "total",
] as const;
export function DocumentEditor({
  document,
  initialPage,
  onSaved,
  onDirtyChange,
  onReload,
  serverRevision,
}: {
  document: DocumentDetail;
  initialPage: number;
  onSaved: (documentId: string) => Promise<void>;
  onDirtyChange: (documentId: string, dirty: boolean) => void;
  onReload: () => void;
  serverRevision: number;
}) {
  const [draft, setDraft] = useState<Extraction | null>(document.data);
  const [baseline, setBaseline] = useState<Extraction | null>(document.data);
  const [conflict, setConflict] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  useEffect(() => {
    onDirtyChange(document.id, dirty);
  }, [dirty, onDirtyChange]);
  const [page, setPage] = useState(initialPage);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    // A background refresh may update the source, but cannot discard local edits.
    if (
      !dirty &&
      document.data &&
      (!baseline || document.revision >= baseline.revision)
    ) {
      setDraft(document.data);
      setBaseline(document.data);
      setError("");
    }
  }, [document.id, document.data]);
  useEffect(() => {
    setNotice("");
  }, [document.id]);
  useEffect(() => {
    setPage(initialPage);
  }, [initialPage, document.id]);
  function itemChange(index: number, key: keyof Item, value: string) {
    if (!draft) return;
    setDraft({
      ...draft,
      line_items: draft.line_items.map((item, i) =>
        i === index ? { ...item, [key]: value === "" ? null : value } : item,
      ),
    });
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!draft) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<{ document_revision: number; data: Extraction }>(
        `/documents/${document.id}/correction`,
        {
          method: "PUT",
          body: JSON.stringify(draft),
        },
      );
      // The acknowledgement includes server-assigned IDs before the editor becomes editable.
      const savedDraft = result.data;
      setDraft(savedDraft);
      setBaseline(savedDraft);
      onDirtyChange(document.id, false);
      setConflict(false);
      await onSaved(document.id);
      setNotice("Review saved. Verification and exports are up to date.");
    } catch (e) {
      setError((e as Error).message);
      setConflict(e instanceof ApiError && e.status === 409);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="review-split">
      <section className="pdf-panel">
        <div className="panel-heading">
          <h3>
            <FileText size={17} /> Original source
          </h3>
          <a
            className="text-link"
            href={sourceUrl(document.id, page)}
            target="_blank"
            rel="noreferrer"
          >
            Open PDF <ExternalLink size={13} />
          </a>
        </div>
        <div className="pdf-controls">
          <button
            aria-label="Previous page"
            className="icon-button"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            <ChevronLeft size={16} />
          </button>
          <span>
            Page {page} of {Math.max(document.pages.length, 1)}
          </span>
          <button
            aria-label="Next page"
            className="icon-button"
            disabled={page >= document.pages.length}
            onClick={() => setPage(page + 1)}
          >
            <ChevronRight size={16} />
          </button>
        </div>
        <iframe
          key={`${document.id}-${page}`}
          title={`Original PDF: ${document.filename}, page ${page}`}
          src={`${sourceUrl(document.id, page)}&toolbar=0`}
          className="pdf-frame"
        />
        <details className="source-text">
          <summary>Accessible extracted text · page {page}</summary>
          <pre>
            {document.pages.find((p) => p.number === page)?.text ||
              "No usable text on this page."}
          </pre>
        </details>
      </section>
      <section className="editor-panel">
        <div className="panel-heading">
          <h3>Extracted fields</h3>
          <span className="badge neutral">
            {dirty ? "Unsaved changes" : `Review revision ${document.revision}`}
          </span>
        </div>
        {!draft ? (
          <div className="empty">
            <p>{document.error || "Fields will appear after processing."}</p>
          </div>
        ) : (
          <form onSubmit={save} className="editor-form">
            <p className="helper">
              {document.filename} · {document.effective_basis} · extraction
              basis {draft.extraction_revision ?? "unknown legacy run"}; latest
              raw run {document.raw_revision}.
            </p>
            {serverRevision > draft.revision && (
              <div className="warning-banner">
                Newer values exist on the server. Your draft is preserved.
                Reload before saving another review.
              </div>
            )}
            {(conflict || serverRevision > draft.revision) && (
              <button type="button" className="button" onClick={onReload}>
                Reload latest values
              </button>
            )}
            {!!draft.source_warnings?.length && (
              <details className="audit-details">
                <summary>
                  Source limitations require a separate manual review
                </summary>
                {draft.source_warnings.map((warning) => (
                  <div key={warning.id}>
                    <p>{warning.message}</p>
                    <button
                      type="button"
                      className="text-link"
                      disabled={busy || dirty}
                      title={
                        dirty
                          ? "Save or discard field edits first"
                          : "Record a manual review of this source limitation"
                      }
                      onClick={async () => {
                        const reason = prompt(
                          "Explain how you manually reviewed this source page/table. This records an audit action; it does not add OCR text. Minimum 15 characters.",
                        );
                        if (!reason) return;
                        setBusy(true);
                        setError("");
                        try {
                          await api(
                            `/documents/${document.id}/source-limitations/${warning.id}/resolve`,
                            {
                              method: "POST",
                              body: JSON.stringify({
                                revision: draft.revision,
                                reason,
                              }),
                            },
                          );
                          await onSaved(document.id);
                        } catch (failure) {
                          setError((failure as Error).message);
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      Record manual source review
                    </button>
                  </div>
                ))}
              </details>
            )}

            <p className="helper">
              {draft.confidence_label}. Blank values stay unknown.
            </p>
            {draft.warnings.length > 0 && (
              <div className="warning-banner">
                {draft.warnings.map((w) => (
                  <p key={w}>{w}</p>
                ))}
              </div>
            )}
            <label>
              Document type
              <select
                value={draft.document_type}
                onChange={(e) =>
                  setDraft({ ...draft, document_type: e.target.value })
                }
              >
                {["purchase_order", "quotation", "invoice", "unknown"].map(
                  (t) => (
                    <option value={t} key={t}>
                      {pretty(t)}
                    </option>
                  ),
                )}
              </select>
            </label>
            <div className="field-grid">
              {fields.map((field) => (
                <label key={field}>
                  {pretty(field)}
                  <input
                    aria-label={pretty(field)}
                    value={draft[field] ?? ""}
                    type={
                      ["subtotal", "tax", "tax_rate", "total"].includes(field)
                        ? "number"
                        : "text"
                    }
                    min="0"
                    step="any"
                    maxLength={field === "currency" ? 3 : 300}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        [field]:
                          e.target.value === ""
                            ? null
                            : field === "currency"
                              ? e.target.value.toUpperCase()
                              : e.target.value,
                      })
                    }
                  />
                  {draft.sources[field] && (
                    <a
                      href={sourceUrl(document.id, draft.sources[field].page)}
                      target="_blank"
                      rel="noreferrer"
                      className="field-source"
                    >
                      Original field source · p. {draft.sources[field].page}
                    </a>
                  )}
                </label>
              ))}
            </div>
            <div className="section-heading compact">
              <h4>Line items</h4>
              <button
                type="button"
                className="text-link"
                onClick={() =>
                  setDraft({
                    ...draft,
                    line_items: [
                      ...draft.line_items,
                      {
                        id: null,
                        sku: null,
                        description: "",
                        quantity: null,
                        unit: null,
                        unit_price: null,
                        amount: null,
                        source: null,
                      },
                    ],
                  })
                }
              >
                <Plus size={14} /> Add item
              </button>
            </div>
            {draft.line_items.map((item, index) => (
              <fieldset className="item-editor" key={item.id ?? `new-${index}`}>
                <legend>
                  Item {index + 1}
                  {item.source && (
                    <a
                      href={sourceUrl(document.id, item.source.page)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {" "}
                      · Original row p. {item.source.page} · run{" "}
                      {item.source.extraction_revision ?? "legacy unknown"}
                    </a>
                  )}
                </legend>
                <div className="item-main">
                  <label>
                    Description
                    <input
                      aria-label={`Description ${index + 1}`}
                      required
                      value={item.description}
                      onChange={(e) =>
                        itemChange(index, "description", e.target.value)
                      }
                    />
                  </label>
                  <button
                    type="button"
                    className="icon-button danger-text"
                    aria-label={`Remove item ${index + 1}`}
                    onClick={() =>
                      setDraft({
                        ...draft,
                        line_items: draft.line_items.filter(
                          (_, i) => i !== index,
                        ),
                      })
                    }
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
                <div className="line-fields">
                  {(
                    ["sku", "quantity", "unit", "unit_price", "amount"] as const
                  ).map((field) => (
                    <label key={field}>
                      {pretty(field)}
                      <input
                        aria-label={`${pretty(field).replace(/^./, (c) => c.toUpperCase())} ${index + 1}`}
                        value={item[field] ?? ""}
                        type={
                          ["quantity", "unit_price", "amount"].includes(field)
                            ? "number"
                            : "text"
                        }
                        min="0"
                        step="any"
                        onChange={(e) =>
                          itemChange(index, field, e.target.value)
                        }
                      />
                    </label>
                  ))}
                </div>
                {!item.source && (
                  <p className="helper">
                    Added during human review; no original source coordinates.
                  </p>
                )}
              </fieldset>
            ))}
            {error && (
              <div className="error-banner" role="alert">
                {error}
              </div>
            )}
            {notice && (
              <div
                className="success-banner"
                role="status"
                data-testid="review-save-status"
              >
                {notice}
              </div>
            )}
            <button
              className="button primary wide"
              disabled={
                busy ||
                ["pending", "processing", "failed"].includes(document.status)
              }
            >
              <Save size={16} /> {busy ? "Saving…" : "Save review & verify"}
            </button>
            {document.classification && (
              <details className="audit-details">
                <summary>Classification methods</summary>
                <p>
                  Keyword rules:{" "}
                  {pretty(document.classification.keyword_prediction)}
                </p>
                <p>
                  ML:{" "}
                  {document.classification.model_prediction
                    ? pretty(document.classification.model_prediction)
                    : "Unavailable"}
                </p>
                <p>{document.classification.model_status}</p>
              </details>
            )}
            <details className="audit-details">
              <summary>
                First retained extraction & audit trail (
                {document.corrections.length})
              </summary>
              <p>
                The first retained extraction is immutable; legacy data cannot
                recover earlier overwritten runs. Each save records before/after
                values and the reviewer.
              </p>
              <pre>{JSON.stringify(document.original, null, 2)}</pre>
              {document.corrections.map((c) => (
                <div key={c.id}>
                  <strong>
                    {new Date(c.created_at * 1000).toLocaleString()}
                  </strong>
                  <p>Reviewer: {c.user_id}</p>
                  <p>
                    {pretty(c.action)} · review revision{" "}
                    {c.document_revision ?? "legacy unknown"} · extraction{" "}
                    {c.extraction_revision ?? "legacy unknown"}
                    {c.resolution && ` · ${c.resolution.reason}`}
                  </p>
                  <details>
                    <summary>Before and after</summary>
                    <pre>
                      {JSON.stringify(
                        { before: c.before, after: c.after },
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                </div>
              ))}
            </details>
            <details className="audit-details">
              <summary>
                Latest raw extraction & processing runs (
                {document.processing_runs.length})
              </summary>
              <p>
                New raw results never silently merge into earlier human
                corrections.
              </p>
              <pre>{JSON.stringify(document.latest_raw, null, 2)}</pre>
              {document.processing_runs.map((run) => (
                <details key={run.id}>
                  <summary>
                    Run {run.revision} ·{" "}
                    {run.created_at
                      ? new Date(run.created_at * 1000).toLocaleString()
                      : "Legacy timestamp unavailable"}
                  </summary>
                  <pre>{JSON.stringify(run.metadata, null, 2)}</pre>
                  <pre>{JSON.stringify(run.extraction, null, 2)}</pre>
                </details>
              ))}
            </details>
          </form>
        )}
      </section>
    </div>
  );
}
