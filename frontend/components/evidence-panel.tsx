"use client";
import { useState } from "react";
import { ArrowRight, ExternalLink, Search } from "lucide-react";
import { api, sourceUrl } from "@/lib/api";
import type { SearchResult } from "@/lib/types";

export function EvidencePanel({
  caseId,
  revision,
  open,
}: {
  caseId: string;
  revision: number;
  open: (id: string, page?: number) => void;
}) {
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<"original" | "reviewed">("original");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const stale = !!result && result.revision !== revision;
  async function search(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setResult(
        await api<SearchResult>(`/cases/${caseId}/search`, {
          method: "POST",
          body: JSON.stringify({ query, scope }),
        }),
      );
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="search-panel panel">
      <div className="panel-heading">
        <h3>
          <Search size={18} /> Ask your documents
        </h3>
        <span className="badge neutral">Selected case only</span>
      </div>
      <div className="search-inner">
        <p className="helper">
          Original passages quote the PDF. Current reviewed values are separate
          records with their audit revisions. Answer generation requires an
          optional server-side provider key.
        </p>
        <label>
          Answer scope
          <select
            aria-label="Answer scope"
            value={scope}
            onChange={(event) =>
              setScope(event.target.value as "original" | "reviewed")
            }
          >
            <option value="original">Original PDF source</option>
            <option value="reviewed">Current reviewed data</option>
          </select>
        </label>
        <form className="query-form" onSubmit={search}>
          <input
            aria-label="Document question"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            required
            minLength={2}
            maxLength={1000}
            placeholder="What quantity of copper cable was invoiced?"
          />
          <button className="button primary" disabled={busy}>
            <Search size={16} /> {busy ? "Searching…" : "Search evidence"}
          </button>
        </form>
        {error && (
          <div role="alert" className="error-banner">
            {error}
          </div>
        )}
        {result && (
          <>
            <div className="retrieval-status">
              <strong>{result.generation_status}</strong>
              <p>{result.retrieval_status}</p>
              <p>{result.correction_notice}</p>
              <p>
                Scope:{" "}
                {result.scope === "original"
                  ? "original source"
                  : "current reviewed values"}{" "}
                · case revision {result.revision}
              </p>
            </div>
            {stale && (
              <div className="warning-banner">
                Case data changed after this search. Search again to refresh the
                answer and verification snapshot.
              </div>
            )}
            {result.answer && !stale && (
              <div className="answer">
                <h4>Answer</h4>
                <p>{result.answer}</p>
                {result.cited_source_ids.map((sourceId) => {
                  const passage = result.evidence.find(
                    (item) => item.id === sourceId,
                  );
                  const reviewed = result.reviewed_records.find(
                    (item) => item.id === sourceId,
                  );
                  if (passage)
                    return (
                      <a
                        className="source-chip"
                        key={sourceId}
                        href={sourceUrl(passage.document_id, passage.page)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Original PDF: {passage.filename} · p. {passage.page}
                        <ExternalLink size={12} />
                      </a>
                    );
                  if (reviewed)
                    return (
                      <button
                        key={sourceId}
                        className="source-chip"
                        onClick={() => open(reviewed.document_id)}
                      >
                        Reviewed record: {reviewed.filename} · revision{" "}
                        {reviewed.provenance.document_revision}
                      </button>
                    );
                  return null;
                })}
              </div>
            )}
            <h4>Retrieved evidence ({result.evidence.length})</h4>
            {!result.evidence.length && (
              <p className="empty-inline">
                No supporting original passages found. This does not establish
                an answer.
              </p>
            )}
            {result.evidence.map((passage) => (
              <article className="evidence-card" key={passage.id}>
                <div>
                  <a
                    className="text-link"
                    href={sourceUrl(passage.document_id, passage.page)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {passage.filename} · page {passage.page}
                    <ExternalLink size={13} />
                  </a>
                  <small>
                    Retrieval score {passage.score} · similarity, not confidence
                  </small>
                </div>
                <pre>{passage.text}</pre>
                <button
                  className="text-link"
                  onClick={() => open(passage.document_id, passage.page)}
                >
                  Review this source <ArrowRight size={13} />
                </button>
              </article>
            ))}
            {result.scope === "reviewed" && (
              <details className="audit-details">
                <summary>
                  Current structured records ({result.reviewed_records.length})
                </summary>
                {result.reviewed_records.map((record) => (
                  <article key={record.id}>
                    <h4>
                      {record.filename} · review revision{" "}
                      {record.provenance.document_revision}
                    </h4>
                    <p>
                      {record.values_origin === "human_review"
                        ? "Human-reviewed values; not quoted PDF text"
                        : "Latest unreviewed extraction"}{" "}
                      · extraction basis{" "}
                      {record.provenance.extraction_revision ??
                        "unknown legacy run"}
                    </p>
                    <pre>{JSON.stringify(record.values, null, 2)}</pre>
                    <p>
                      Audit:{" "}
                      {record.provenance.correction_id ?? "No human correction"}
                    </p>
                  </article>
                ))}
              </details>
            )}
            {!!result.verification.length && (
              <details className="audit-details">
                <summary>
                  Deterministic verification snapshot (
                  {result.verification.length})
                </summary>
                {result.verification.map((finding) => (
                  <p key={finding.id}>{finding.explanation}</p>
                ))}
              </details>
            )}
          </>
        )}
      </div>
    </section>
  );
}
