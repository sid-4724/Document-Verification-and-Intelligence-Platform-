"use client";
import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ArrowRight,
  FileText,
} from "lucide-react";
import { pretty } from "@/lib/api";
import type { Case, Finding } from "@/lib/types";
export function FindingsPanel({
  record,
  findings,
  open,
  review,
}: {
  record: Case;
  findings: Finding[];
  open: (id: string, page?: number) => void;
  review: (finding: Finding, status: string) => Promise<void>;
}) {
  const [severity, setSeverity] = useState("all");
  const [reviewFilter, setReviewFilter] = useState("all");
  const visibleFindings = findings.filter(
    (finding) =>
      (severity === "all" || finding.severity === severity) &&
      (reviewFilter === "all" || finding.review_status === reviewFilter),
  );
  return (
    <section>
      <div className="section-heading">
        <div>
          <h2>What needs your attention</h2>
          <p className="helper">
            Confirmed differences, arithmetic checks, and uncertain extraction
            are shown separately.
          </p>
        </div>
        <div className="filters">
          <select
            aria-label="Filter severity"
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
          >
            {["all", "error", "warning", "review"].map((v) => (
              <option key={v} value={v}>
                {v === "all" ? "All severities" : pretty(v)}
              </option>
            ))}
          </select>
          <select
            aria-label="Filter review status"
            value={reviewFilter}
            onChange={(e) => setReviewFilter(e.target.value)}
          >
            {["all", "open", "acknowledged", "resolved"].map((v) => (
              <option key={v} value={v}>
                {v === "all" ? "All statuses" : v}
              </option>
            ))}
          </select>
        </div>
      </div>
      {record.processing_count > 0 && (
        <div className="warning-banner">
          {record.processing_count} documents are still processing. Findings
          will refresh as extraction completes.
        </div>
      )}
      {!visibleFindings.length ? (
        <div className="empty panel">
          <div className="empty-icon">
            <CheckCircle2 size={27} />
          </div>
          <h3>
            {record.processing_count
              ? "Review is on its way"
              : "No findings to show"}
          </h3>
          <p>
            {record.documents.length
              ? "No findings match the current filter. Only supported fields are checked."
              : "Upload documents to extract fields and compare them."}
          </p>
        </div>
      ) : (
        <div className="findings-list">
          {visibleFindings.map((f) => (
            <article
              className={`finding ${f.severity}`}
              key={f.id}
              data-testid={`finding-${f.kind}`}
            >
              <div className="finding-symbol">
                <AlertTriangle size={18} />
              </div>
              <div className="finding-body">
                <div className="finding-title">
                  <h3>{pretty(f.kind)}</h3>
                  <span className={`badge ${f.severity}`}>
                    {f.severity === "review"
                      ? "Needs human review"
                      : f.severity}
                  </span>
                </div>
                <p>{f.explanation}</p>
                <p className="helper">
                  Rule: {pretty(f.rule)} ·{" "}
                  {f.document_ids
                    .map(
                      (identifier) =>
                        record.documents.find(
                          (document) => document.id === identifier,
                        )?.filename ?? identifier,
                    )
                    .join(" → ")}
                </p>
                {(f.expected !== null || f.observed !== null) && (
                  <div className="comparison">
                    <span>
                      <small>
                        {f.document_ids.length === 1
                          ? "Calculated / required"
                          : "Reference value"}
                      </small>
                      <strong>{f.expected ?? "Unknown"}</strong>
                    </span>
                    <ArrowRight size={15} />
                    <span>
                      <small>
                        {f.document_ids.length === 1
                          ? "Stated in document"
                          : "Target value"}
                      </small>
                      <strong>{f.observed ?? "Unknown"}</strong>
                    </span>
                  </div>
                )}
                <div className="finding-sources">
                  {f.sources.map((s, i) => (
                    <button
                      key={i}
                      className="source-chip"
                      onClick={() => open(s.document_id, s.page)}
                    >
                      <FileText size={12} />{" "}
                      {record.documents.find((d) => d.id === s.document_id)
                        ?.filename || "Source"}{" "}
                      · p. {s.page}
                    </button>
                  ))}
                </div>
              </div>
              <select
                aria-label={`Review ${f.kind} ${f.id}`}
                className="finding-review"
                value={f.review_status}
                onChange={(e) => review(f, e.target.value)}
              >
                {["open", "acknowledged", "resolved"].map((v) => (
                  <option value={v} key={v}>
                    {v}
                  </option>
                ))}
              </select>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
