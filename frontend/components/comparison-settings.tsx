"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import type { Case } from "@/lib/types";

export function ComparisonSettings({
  record,
  onSaved,
}: {
  record: Case;
  onSaved: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [reference, setReference] = useState(
    record.comparison.reference_document_id ?? "",
  );
  const [targets, setTargets] = useState(record.comparison.target_document_ids);
  const [baseRevision, setBaseRevision] = useState(record.revision);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  function begin() {
    setReference(record.comparison.reference_document_id ?? "");
    setTargets(record.comparison.target_document_ids);
    setBaseRevision(record.revision);
    setEditing(true);
    setError("");
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(`/cases/${record.id}/comparison`, {
        method: "PUT",
        body: JSON.stringify({
          revision: baseRevision,
          reference_document_id: reference || null,
          target_document_ids: targets.filter(
            (identifier) => identifier !== reference,
          ),
        }),
      });
      await onSaved();
      setEditing(false);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel comparison-settings">
      <div className="panel-heading">
        <h3>Comparison selection</h3>
        <button
          className="text-link"
          onClick={editing ? () => setEditing(false) : begin}
        >
          {editing ? "Cancel" : "Choose reference & targets"}
        </button>
      </div>
      <div className="search-inner">
        <p className="helper">
          Reference:{" "}
          {record.documents.find(
            (document) =>
              document.id === record.comparison.reference_document_id,
          )?.filename ?? "Not selected"}{" "}
          · {record.comparison.target_document_ids.length} individual targets ·{" "}
          {record.comparison.mode.replaceAll("_", " ")}. Invoices are never
          aggregated or compared with each other.
        </p>
        {editing && (
          <form onSubmit={save}>
            <label>
              Reference document
              <select
                aria-label="Reference document"
                value={reference}
                onChange={(event) => {
                  setReference(event.target.value);
                  setTargets(
                    targets.filter(
                      (identifier) => identifier !== event.target.value,
                    ),
                  );
                }}
              >
                <option value="">No reference selected</option>
                {record.documents.map((document) => (
                  <option key={document.id} value={document.id}>
                    {document.filename}
                  </option>
                ))}
              </select>
            </label>
            <fieldset className="target-selection">
              <legend>Comparison targets</legend>
              {record.documents
                .filter((document) => document.id !== reference)
                .map((document) => (
                  <label key={document.id}>
                    <input
                      type="checkbox"
                      checked={targets.includes(document.id)}
                      onChange={(event) =>
                        setTargets(
                          event.target.checked
                            ? [...targets, document.id]
                            : targets.filter(
                                (identifier) => identifier !== document.id,
                              ),
                        )
                      }
                    />
                    {document.filename}
                  </label>
                ))}
            </fieldset>
            {error && (
              <div className="error-banner" role="alert">
                {error}
                <button type="button" className="text-link" onClick={begin}>
                  Reload selection
                </button>
              </div>
            )}
            <button className="button primary" disabled={busy}>
              {busy ? "Saving…" : "Save comparison"}
            </button>
          </form>
        )}
      </div>
    </section>
  );
}
