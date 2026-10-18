"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  Plus,
  ArrowUpRight,
  FolderOpen,
  Files,
  LoaderCircle,
  Search,
  FlaskConical,
  ShieldCheck,
} from "lucide-react";
import { Shell, useUser } from "@/components/shell";
import { api } from "@/lib/api";
import type { Case } from "@/lib/types";
function Dashboard() {
  const user = useUser();
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newCase, setNewCase] = useState(false);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("");
  const [cleanupPending, setCleanupPending] = useState(0);
  const load = useCallback(async () => {
    try {
      const [latest, cleanup] = await Promise.all([
        api<Case[]>("/cases"),
        api<{ pending_count: number }>("/storage-cleanup"),
      ]);
      setCases(latest);
      setCleanupPending(cleanup.pending_count);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [load]);
  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    const data = new FormData(e.currentTarget);
    try {
      await api("/cases", {
        method: "POST",
        body: JSON.stringify({ name: data.get("name") }),
      });
      setNewCase(false);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function demo() {
    setBusy(true);
    setError("");
    try {
      await api("/demo", { method: "POST" });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const visible = cases.filter((c) =>
    c.name.toLowerCase().includes(filter.toLowerCase()),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">WORKSPACE OVERVIEW</div>
          <h1>
            Your cases<span className="heading-dot">.</span>
          </h1>
          <p>
            Keep related documents together. Let the details tell the story.
          </p>
        </div>
        <button className="button primary" onClick={() => setNewCase(!newCase)}>
          <Plus size={17} /> New case
        </button>
      </div>
      {error && (
        <div role="alert" className="error-banner">
          {error}
        </div>
      )}
      {cleanupPending > 0 && (
        <div className="warning-banner">
          {cleanupPending} private PDFs are logically removed but await physical
          cleanup. The worker retries; this count refreshes automatically.
        </div>
      )}
      {newCase && (
        <form className="inline-form panel" onSubmit={create}>
          <label>
            Case name
            <input
              name="name"
              required
              maxLength={160}
              autoFocus
              placeholder="e.g. Copper cable procurement"
            />
          </label>
          <button className="button primary" disabled={busy}>
            Create case
          </button>
          <button
            type="button"
            className="button"
            onClick={() => setNewCase(false)}
          >
            Cancel
          </button>
        </form>
      )}
      <div className="metrics">
        <div className="metric">
          <span>
            Total cases <FolderOpen />
          </span>
          <strong>{loading ? "—" : cases.length}</strong>
          <small>Organized in your workspace</small>
        </div>
        <div className="metric">
          <span>
            Documents <Files />
          </span>
          <strong>
            {loading ? "—" : cases.reduce((s, c) => s + c.document_count, 0)}
          </strong>
          <small>Original PDFs, accessible through your account</small>
        </div>
        <div className="metric">
          <span>
            In processing <LoaderCircle />
          </span>
          <strong>
            {loading ? "—" : cases.reduce((s, c) => s + c.processing_count, 0)}
          </strong>
          <small>Queued or being extracted</small>
        </div>
      </div>
      <div className="section-heading">
        <h2>
          Case library <span className="count">{cases.length}</span>
        </h2>
        <label className="search-input">
          <Search size={16} />
          <input
            aria-label="Search cases"
            placeholder="Find a case…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </label>
      </div>
      {loading ? (
        <div className="empty panel">Loading your cases…</div>
      ) : !visible.length ? (
        <div className="empty panel">
          <div className="empty-icon">
            <FolderOpen size={28} />
          </div>
          <h3>{filter ? "No cases found" : "Start with a case"}</h3>
          <p>
            {filter
              ? "Try a different case name."
              : "Create a case, then upload the purchase order, quotation, and invoice you want to compare."}
          </p>
          {!filter && (
            <button className="button primary" onClick={() => setNewCase(true)}>
              <Plus size={16} /> Create your first case
            </button>
          )}
        </div>
      ) : (
        <div className="case-grid">
          {visible.map((c) => (
            <Link className="case-card" key={c.id} href={`/cases/${c.id}`}>
              <div className="case-card-top">
                <span className="folder-icon">
                  <FolderOpen size={20} />
                </span>
                <ArrowUpRight size={19} />
              </div>
              <h3>{c.name}</h3>
              <p>
                {c.document_count}{" "}
                {c.document_count === 1 ? "document" : "documents"}{" "}
                <span>·</span> {c.finding_count} findings
              </p>
              <div className="case-card-bottom">
                <span
                  className={`badge ${c.processing_count ? "processing" : c.finding_count ? "needs_review" : "completed"}`}
                >
                  {c.processing_count
                    ? "Processing"
                    : c.finding_count
                      ? "Review findings"
                      : c.document_count
                        ? "Ready"
                        : "Empty case"}
                </span>
                <time>
                  {new Date(c.created_at * 1000).toLocaleDateString(undefined, {
                    month: "short",
                    day: "numeric",
                  })}
                </time>
              </div>
            </Link>
          ))}
        </div>
      )}
      {user?.demo_mode && (
        <div className="demo-banner">
          <span className="demo-icon">
            <FlaskConical />
          </span>
          <div>
            <h3>Explore the details with sample cases</h3>
            <p>
              Load seven fictional scenarios: matching documents, discrepancies,
              arithmetic errors, and uncertainty.
            </p>
          </div>
          <button className="button" onClick={demo} disabled={busy}>
            <FlaskConical size={16} /> {busy ? "Loading…" : "Load sample cases"}
          </button>
        </div>
      )}
      <div className="evidence-note">
        <ShieldCheck size={16} /> Differences are separate from extraction
        uncertainty. Missing information never becomes a confirmed mismatch.
      </div>
    </>
  );
}
export default function Home() {
  return (
    <Shell>
      <Dashboard />
    </Shell>
  );
}
