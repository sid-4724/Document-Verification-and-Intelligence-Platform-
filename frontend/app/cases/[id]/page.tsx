"use client";
import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  UploadCloud,
  FileText,
  Download,
  Trash2,
  RotateCcw,
  ExternalLink,
  Search,
  AlertTriangle,
  CheckCircle2,
  Pencil,
  ArrowRight,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { DocumentEditor } from "@/components/document-editor";
import { CaseDocuments } from "@/components/case-documents";
import { FindingsPanel } from "@/components/findings-panel";
import { EvidencePanel } from "@/components/evidence-panel";
import { ComparisonSettings } from "@/components/comparison-settings";
import { useCaseWorkspace } from "@/lib/use-case-workspace";
import { api, pretty, sourceUrl } from "@/lib/api";
import type { Finding } from "@/lib/types";
function CaseWorkspace({
  workspace,
}: {
  workspace: ReturnType<typeof useCaseWorkspace>;
}) {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const {
    record,
    findings,
    error,
    setError,
    selected,
    document,
    documentLoading,
    load,
  } = workspace;
  const [page, setPage] = useState(1);
  const [tab, setTab] = useState("findings");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState("");
  async function upload(files: FileList | File[]) {
    if (!files.length) return;
    setBusy(true);
    setError("");
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));
    try {
      await api(`/cases/${id}/documents`, { method: "POST", body: form });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove(docId: string) {
    if (!confirm("Remove this document and its extraction from the case?"))
      return;
    try {
      const result = await api<{ storage_cleanup_pending: boolean }>(
        `/documents/${docId}`,
        { method: "DELETE" },
      );
      setNotice(
        result.storage_cleanup_pending
          ? "Document access removed. Physical cleanup was queued; current pending tasks are shown above."
          : "Document and stored PDF removed.",
      );
      if (selected === docId) {
        workspace.selectDocument("");
      }
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function retry(docId: string) {
    try {
      await api(`/documents/${docId}/retry`, { method: "POST" });
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function rename(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    try {
      await api(`/cases/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: data.get("name"),
          tolerance: data.get("tolerance"),
        }),
      });
      setEditing(false);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function deleteCase() {
    if (!confirm("Delete this case and all its documents?")) return;
    try {
      const result = await api<{ storage_cleanup_pending: boolean }>(
        `/cases/${id}`,
        { method: "DELETE" },
      );
      if (result.storage_cleanup_pending) {
        alert(
          "Case removed. Some stored PDFs could not be removed yet; automatic cleanup will retry.",
        );
      }
      router.push("/");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function review(finding: Finding, value: string) {
    try {
      await api(`/cases/${id}/findings/${finding.id}`, {
        method: "PATCH",
        body: JSON.stringify({ review_status: value }),
      });
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const open = (docId: string, sourcePage = 1) => {
    workspace.selectDocument(docId, () => {
      setPage(sourcePage);
      setTab("review");
    });
  };
  if (!record || record.id !== id)
    return (
      <div className="empty panel">
        {error || "Loading case…"}
        <Link className="text-link" href="/">
          Back to cases
        </Link>
      </div>
    );
  return (
    <>
      <Link className="back-link" href="/">
        <ArrowLeft size={15} /> All cases
      </Link>
      <div className="page-heading">
        <div>
          <div className="eyebrow">CASE WORKSPACE</div>
          <h1>{record.name}</h1>
          <p>
            {record.document_count} documents{" "}
            <span className="separator">/</span> {record.finding_count} findings{" "}
            <span className="separator">/</span> Rounding tolerance:{" "}
            {record.tolerance}
          </p>
        </div>
        <div className="heading-actions">
          <button className="button" onClick={() => setEditing(!editing)}>
            <Pencil size={14} /> Case settings
          </button>
          <a className="button" href={`/api/cases/${id}/export.json`} download>
            <Download size={15} /> JSON
          </a>
          <a className="button" href={`/api/cases/${id}/findings.csv`} download>
            <Download size={15} /> Export CSV
          </a>
        </div>
      </div>
      <div className="warning-banner" role="status">
        Readiness: {record.readiness.readable_count}/{record.document_count}{" "}
        documents have readable extractions;{" "}
        {record.readiness.status_counts.failed} failed;{" "}
        {record.readiness.unresolved_count} have unresolved review warnings.{" "}
        {record.comparison.note} Zero findings alone does not establish complete
        checks. These checks do not prove document authenticity.
      </div>
      {record.cleanup_pending_count > 0 && (
        <div className="warning-banner">
          {record.cleanup_pending_count} logically removed PDFs await physical
          cleanup. Access is removed; the worker retries deletion.
        </div>
      )}
      {workspace.pendingSelection && (
        <div className="dialog-backdrop">
          <section
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="discard-title"
            className="discard-dialog"
            onKeyDown={(event) => {
              if (event.key === "Escape") workspace.stay();
            }}
          >
            <h3 id="discard-title">Unsaved changes</h3>
            <p>
              Keep editing this draft, or discard it before continuing. Saved
              reviews remain in the audit history.
            </p>
            <div className="heading-actions">
              <button
                className="button primary"
                autoFocus
                onClick={workspace.stay}
              >
                Keep editing
              </button>
              <button
                className="button danger-text"
                onClick={workspace.discardAndContinue}
              >
                Discard changes
              </button>
            </div>
          </section>
        </div>
      )}
      {editing && (
        <form className="inline-form panel" onSubmit={rename}>
          <label>
            Case name
            <input
              name="name"
              defaultValue={record.name}
              required
              maxLength={160}
            />
          </label>
          <label>
            Rounding tolerance
            <input
              type="number"
              min="0"
              max="100"
              step="any"
              name="tolerance"
              defaultValue={record.tolerance}
              required
            />
          </label>
          <button className="button primary">Save settings</button>
          <button
            type="button"
            className="button danger-text"
            onClick={() =>
              workspace.protectDraft(() => {
                void deleteCase();
              })
            }
          >
            <Trash2 size={15} /> Delete case
          </button>
        </form>
      )}
      {notice && (
        <div role="status" className="warning-banner">
          {notice}
        </div>
      )}
      {error && (
        <div role="alert" className="error-banner">
          {error}
          <button
            aria-label="Dismiss error"
            className="icon-button"
            onClick={() => setError("")}
          >
            ×
          </button>
        </div>
      )}
      <CaseDocuments
        record={record}
        selected={selected}
        busy={busy}
        upload={upload}
        open={open}
        retry={(identifier) =>
          new Promise<void>((resolve) =>
            workspace.protectDraft(() => {
              void retry(identifier).finally(resolve);
            }),
          )
        }
        remove={(identifier) =>
          new Promise<void>((resolve) =>
            workspace.protectDraft(() => {
              void remove(identifier).finally(resolve);
            }),
          )
        }
      />
      <ComparisonSettings record={record} onSaved={load} />
      <div className="tabs" role="tablist" aria-label="Case views">
        {[
          { id: "findings", label: "Verification", count: findings.length },
          { id: "review", label: "Document review" },
          { id: "search", label: "Evidence search" },
        ].map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? "active" : ""}
            onClick={() => workspace.protectDraft(() => setTab(t.id))}
          >
            {t.label}
            {t.count !== undefined && <span className="count">{t.count}</span>}
          </button>
        ))}
      </div>
      {tab === "findings" && (
        <FindingsPanel
          record={record}
          findings={findings}
          open={open}
          review={review}
        />
      )}
      {tab === "review" &&
        (document && document.id === selected ? (
          <DocumentEditor
            key={document.id}
            document={document}
            initialPage={page}
            onSaved={workspace.saved}
            onDirtyChange={workspace.setDocumentDirty}
            onReload={workspace.reloadSelected}
            serverRevision={
              record.documents.find((item) => item.id === selected)?.revision ??
              document.revision
            }
          />
        ) : (
          <div className="empty panel">
            <FileText size={28} />
            <h3>
              {documentLoading
                ? "Loading selected document…"
                : "Select a document"}
            </h3>
            <p>
              Choose a PDF above or open a finding’s source to review the
              extraction next to the original.
            </p>
          </div>
        ))}
      {tab === "search" && (
        <EvidencePanel caseId={id} revision={record.revision} open={open} />
      )}
    </>
  );
}
export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const workspace = useCaseWorkspace(id);
  return (
    <Shell onBeforeLogout={workspace.protectDraft}>
      <CaseWorkspace workspace={workspace} />
    </Shell>
  );
}
