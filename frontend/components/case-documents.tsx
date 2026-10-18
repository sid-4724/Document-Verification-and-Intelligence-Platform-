"use client";
import { useState } from "react";
import {
  UploadCloud,
  FileText,
  RotateCcw,
  ExternalLink,
  Trash2,
} from "lucide-react";
import { pretty, sourceUrl } from "@/lib/api";
import type { Case } from "@/lib/types";
export function CaseDocuments({
  record,
  selected,
  busy,
  upload,
  open,
  retry,
  remove,
}: {
  record: Case;
  selected: string;
  busy: boolean;
  upload: (files: FileList | File[]) => Promise<void>;
  open: (id: string, page?: number) => void;
  retry: (id: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
}) {
  const [dragging, setDragging] = useState(false);
  return (
    <>
      {" "}
      <section
        className={`upload-area ${dragging ? "dragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void upload(e.dataTransfer.files);
        }}
      >
        <span className="upload-icon">
          <UploadCloud size={25} />
        </span>
        <div>
          <h3>{busy ? "Working…" : "Add documents to this case"}</h3>
          <p>
            Selectable-text PDFs · up to 10 MB and 30 pages each · 5 files at a
            time
          </p>
        </div>
        <label className={`button ${busy ? "disabled" : "primary"}`}>
          {" "}
          <UploadCloud size={16} /> Upload PDFs
          <input
            className="sr-only"
            aria-label="Upload PDFs"
            type="file"
            accept="application/pdf,.pdf"
            multiple
            disabled={busy}
            onChange={(e) => {
              if (e.target.files) void upload(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
      </section>
      <div className="document-list">
        {record.documents.map((doc) => (
          <div
            className={`document-row ${selected === doc.id ? "selected" : ""}`}
            key={doc.id}
          >
            <span className="document-icon">
              <FileText size={19} />
            </span>
            <button className="document-name" onClick={() => open(doc.id)}>
              <strong>{doc.filename}</strong>
              <span>
                {pretty(doc.document_type)}
                {doc.error && ` · ${doc.error}`}
              </span>
            </button>
            <span className={`badge ${doc.status}`}>{pretty(doc.status)}</span>
            <div className="document-actions">
              {["failed", "completed", "needs_review"].includes(doc.status) && (
                <button
                  className="icon-button"
                  onClick={() => retry(doc.id)}
                  title={
                    doc.status === "failed"
                      ? "Retry processing"
                      : "Reprocess original PDF (preserves corrections)"
                  }
                  aria-label={`Retry ${doc.filename}`}
                >
                  <RotateCcw size={15} />
                </button>
              )}
              <a
                className="icon-button"
                href={sourceUrl(doc.id)}
                target="_blank"
                rel="noreferrer"
                aria-label={`Open ${doc.filename}`}
              >
                <ExternalLink size={15} />
              </a>
              <button
                className="icon-button danger-text"
                onClick={() => remove(doc.id)}
                aria-label={`Remove ${doc.filename}`}
              >
                <Trash2 size={15} />
              </button>
            </div>
          </div>
        ))}
        {!record.documents.length && (
          <p className="document-empty">
            Your case is ready. Upload related documents to start reviewing.
          </p>
        )}
      </div>
    </>
  );
}
