"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "./api";
import type { Case, DocumentDetail, Finding } from "./types";

/** Poll case summaries; fence document loads so only the current selection can render. */
export function useCaseWorkspace(caseId: string) {
  const router = useRouter();
  const [record, setRecord] = useState<Case | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState("");
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [documentLoading, setDocumentLoading] = useState(false);
  const [dirty, setDirty] = useState(false);
  const selection = useRef("");
  const [loadVersion, setLoadVersion] = useState(0);
  const [pendingSelection, setPendingSelection] = useState<(() => void) | null>(
    null,
  );
  const caseRequest = useRef(0);
  const caseIdentity = useRef(caseId);
  caseIdentity.current = caseId;
  useEffect(() => {
    selection.current = "";
    setSelected("");
    setDocument(null);
    setDirty(false);
    setRecord(null);
    setFindings([]);
    setError("");
  }, [caseId]);
  const load = useCallback(async () => {
    if (caseIdentity.current !== caseId) return;
    const request = ++caseRequest.current;
    try {
      const [latestCase, latestFindings] = await Promise.all([
        api<Case>(`/cases/${caseId}`),
        api<Finding[]>(`/cases/${caseId}/findings`),
      ]);
      if (request === caseRequest.current && caseIdentity.current === caseId) {
        setRecord(latestCase);
        setFindings(latestFindings);
      }
    } catch (failure) {
      if (request === caseRequest.current && caseIdentity.current === caseId)
        setError((failure as Error).message);
    }
  }, [caseId]);
  useEffect(() => {
    void load();
    const timer = setInterval(load, 2500);
    return () => {
      ++caseRequest.current;
      clearInterval(timer);
    };
  }, [load]);
  const selectedStatus = record?.documents.find(
    (item) => item.id === selected,
  )?.status;
  useEffect(() => {
    if (!selected) {
      setDocument(null);
      setDocumentLoading(false);
      return;
    }
    const controller = new AbortController();
    let active = true;
    setDocumentLoading(true);
    api<DocumentDetail>(`/documents/${selected}`, { signal: controller.signal })
      .then((data) => {
        if (active && selection.current === data.id) setDocument(data);
      })
      .catch((failure) => {
        if (active && failure.name !== "AbortError") setError(failure.message);
      })
      .finally(() => {
        if (active) setDocumentLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [selected, selectedStatus, loadVersion]);
  const performSelection = useCallback((identifier: string) => {
    if (identifier !== selection.current) {
      setDocument(null);
      setDirty(false);
    }
    selection.current = identifier;
    setSelected(identifier);
  }, []);
  const setDocumentDirty = useCallback((identifier: string, value: boolean) => {
    if (selection.current === identifier) setDirty(value);
  }, []);
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const navigation = (event: MouseEvent) => {
      if (
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      )
        return;
      const anchor = (event.target as Element).closest?.("a");
      if (
        !anchor ||
        anchor.target === "_blank" ||
        anchor.hasAttribute("download")
      )
        return;
      const destination = new URL(anchor.href, window.location.href);
      if (
        destination.origin !== window.location.origin ||
        destination.pathname.startsWith("/api/") ||
        destination.href === window.location.href
      )
        return;
      event.preventDefault();
      event.stopPropagation();
      setPendingSelection(
        () => () =>
          router.push(
            destination.pathname + destination.search + destination.hash,
          ),
      );
    };
    window.addEventListener("beforeunload", beforeUnload);
    window.document.addEventListener("click", navigation, true);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      window.document.removeEventListener("click", navigation, true);
    };
  }, [dirty]);
  const protectDraft = (action: () => void) => {
    if (dirty) {
      setPendingSelection(() => action);
      return;
    }
    action();
  };
  const selectDocument = (identifier: string, after?: () => void) => {
    const action = () => {
      performSelection(identifier);
      after?.();
    };
    if (identifier !== selected) protectDraft(action);
    else action();
  };
  const saved = async (identifier: string) => {
    await load();
    if (selection.current === identifier) {
      setDirty(false);
      setLoadVersion((value) => value + 1);
    }
  };
  const reloadSelected = () =>
    protectDraft(() => {
      setDirty(false);
      setDocument(null);
      setLoadVersion((value) => value + 1);
    });
  const discardAndContinue = () => {
    const action = pendingSelection;
    setPendingSelection(null);
    setDirty(false);
    action?.();
  };
  return {
    record,
    findings,
    error,
    setError,
    selected,
    document,
    documentLoading,
    dirty,
    setDirty,
    setDocumentDirty,
    load,
    saved,
    selectDocument,
    reloadSelected,
    protectDraft,
    pendingSelection: !!pendingSelection,
    discardAndContinue,
    stay: () => setPendingSelection(null),
  };
}
