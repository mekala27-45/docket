"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowDownUp,
  ArrowRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleCheck,
  CircleHelp,
  Database,
  Download,
  FileCheck2,
  FileText,
  FlaskConical,
  Inbox,
  LayoutGrid,
  LoaderCircle,
  Menu,
  Moon,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Upload,
  X,
} from "lucide-react";
import type { Bundle, Connection, DocumentItem, PageName } from "@/lib/types";
import { BASE, asset, label, lowest, money, pct } from "@/lib/types";
import { Reviewer } from "./reviewer";
import { Evaluation, Explore, Lab, Models, Report, Rules } from "./sections";

const nav = [
  { id: "inbox", name: "Inbox", icon: Inbox },
  { id: "evaluation", name: "Evaluation", icon: LayoutGrid },
  { id: "lab", name: "Degradation lab", icon: FlaskConical },
  { id: "rules", name: "Business rules", icon: ShieldCheck },
  { id: "models", name: "Models", icon: Database },
  { id: "explore", name: "Explore data", icon: Search },
  { id: "report", name: "Report", icon: BookOpen },
];
const LOCAL_KEY = "docket:practice:v1";
let sessionConnection: Connection | null = null;
const STATEMENT =
  "Demonstration documents only. Generated invoices and public receipt data; no customer transactions. Practice reviews stay in this browser.";

function metricValue(raw: unknown): string {
  if (typeof raw === "number") return pct(raw);
  const m = raw as { value?: number | null } | undefined;
  return typeof m?.value === "number" ? pct(m.value) : "Not measured";
}
function interval(raw: unknown): string {
  const m = raw as { ci?: number[]; reason?: string } | undefined;
  return m?.ci?.length === 2 && m.ci.every((v) => typeof v === "number")
    ? `95% CI ${pct(m.ci[0])} to ${pct(m.ci[1])}`
    : m?.reason || "See evaluation methodology";
}
export function Status({ status }: { status: string }) {
  const good =
    status === "auto_approved" || status === "accepted" || status === "pass";
  return (
    <span
      className={`status ${good ? "good" : status === "rejected" || status === "fail" ? "bad" : "warn"}`}
    >
      {good ? <CheckCheck size={12} /> : <span className="status-dot" />}
      {label(status === "auto_approved" ? "auto_approved" : status)}
    </span>
  );
}

export function Workbench({ page }: { page: PageName }) {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [loadError, setLoadError] = useState("");
  const [settings, setSettings] = useState(false);
  const [upload, setUpload] = useState(false);
  const [connection, setConnection] = useState<Connection | null>(
    sessionConnection,
  );
  const [connected, setConnected] = useState(Boolean(sessionConnection));
  const [toast, setToast] = useState("");
  const [dark, setDark] = useState(false);
  const [mobile, setMobile] = useState(false);
  const notify = useCallback((message: string) => {
    setToast(message);
  }, []);

  useEffect(() => {
    const savedTheme = localStorage.getItem("docket:theme") === "dark";
    setDark(savedTheme);
    document.documentElement.dataset.theme = savedTheme ? "dark" : "light";
    fetch(`${BASE}/data/demo.json`)
      .then((r) => {
        if (!r.ok) throw new Error("Could not load the recorded documents.");
        return r.json();
      })
      .then((data: Bundle) => {
        setBundle(data);
        let practice: Record<string, DocumentItem> = {};
        try {
          practice = JSON.parse(localStorage.getItem(LOCAL_KEY) || "{}");
        } catch {
          localStorage.removeItem(LOCAL_KEY);
        }
        setDocs(data.documents.map((d) => practice[d.id] || d));
        if (sessionConnection) {
          const live = sessionConnection;
          fetch(`${live.url}/v1/queue`, {
            headers: live.token
              ? { Authorization: `Bearer ${live.token}` }
              : {},
          })
            .then((r) => {
              if (!r.ok) throw new Error("API unavailable");
              return r.json();
            })
            .then((body) => {
              const queue = Array.isArray(body)
                ? body
                : body.documents || body.items;
              if (!Array.isArray(queue)) throw new Error("Invalid queue");
              setDocs(queue);
              setConnected(true);
            })
            .catch(() => {
              setConnected(false);
              setConnection(null);
              sessionConnection = null;
              setToast(
                "The API is unavailable. Showing the recorded demo; reviews are browser-local.",
              );
            });
        }
      })
      .catch((e) =>
        setLoadError(
          e instanceof Error ? e.message : "Unable to load documents.",
        ),
      );
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 6500);
    return () => clearTimeout(timer);
  }, [toast]);

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    localStorage.setItem("docket:theme", next ? "dark" : "light");
    document.documentElement.dataset.theme = next ? "dark" : "light";
  };
  const saveReview = async (
    doc: DocumentItem,
    fields: Record<string, string>,
    items: DocumentItem["line_items"],
    decision: "accept" | "reject",
    reason: string,
  ) => {
    let serverDocument: DocumentItem | undefined;
    if (connection && connected) {
      const response = await fetch(
        `${connection.url}/v1/review/${encodeURIComponent(doc.id)}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${connection.token}`,
          },
          body: JSON.stringify({ fields, line_items: items, decision, reason }),
        },
      );
      if (!response.ok)
        throw new Error(`Review was not saved (HTTP ${response.status}).`);
      const payload = await response.json();
      serverDocument =
        payload.document ||
        (payload.id && payload.extraction ? payload : undefined);
    }
    const reviewedFields = Object.fromEntries(
      Object.entries(doc.extraction.fields).map(([name, field]) => [
        name,
        fields[name] !== undefined && fields[name] !== String(field.value ?? "")
          ? {
              ...field,
              value: fields[name].trim() === "" ? null : fields[name],
              confidence: null,
              reviewed: true,
              model_confidence: field.confidence ?? field.model_confidence,
              calibration_sentence:
                "Human-corrected value. Original model confidence does not measure this revision.",
            }
          : field,
      ]),
    );
    const updated: DocumentItem = serverDocument || {
      ...doc,
      ...Object.fromEntries(
        Object.entries(fields).filter(([key]) =>
          [
            "vendor",
            "number",
            "date",
            "due_date",
            "currency",
            "po_number",
          ].includes(key),
        ),
      ),
      ...Object.fromEntries(
        Object.entries(fields)
          .filter(
            ([key, value]) =>
              ["total", "subtotal", "tax"].includes(key) &&
              (value.trim() === "" || Number.isFinite(Number(value))),
          )
          .map(([key, value]) => [
            key,
            value.trim() === "" ? null : Number(value),
          ]),
      ),
      status: decision === "accept" ? "accepted" : "rejected",
      risk: 0,
      line_items: items,
      extraction: {
        ...doc.extraction,
        line_items: items,
        fields: reviewedFields,
      },
    };
    setDocs((current) => current.map((d) => (d.id === doc.id ? updated : d)));
    if (!connected) {
      const existing = JSON.parse(localStorage.getItem(LOCAL_KEY) || "{}");
      localStorage.setItem(
        LOCAL_KEY,
        JSON.stringify({ ...existing, [doc.id]: updated }),
      );
    }
    notify(
      connected
        ? "Review saved by the connected API."
        : "Practice review saved in this browser. Published evaluation is unchanged.",
    );
  };
  const reset = () => {
    localStorage.removeItem(LOCAL_KEY);
    if (bundle) setDocs(bundle.documents);
    notify("Practice reviews cleared. The recorded queue is restored.");
  };
  const active = nav.find((n) => n.id === page)?.name || "Document review";
  const waiting = docs.filter((d) => d.status === "needs_review").length;
  const op = bundle?.evaluation.operating_point as
    Record<string, unknown> | undefined;

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobile ? "mobile-open" : ""}`}>
        <Link href="/" className="brand" aria-label="Docket inbox">
          <span className="brand-mark">
            <FileText size={25} strokeWidth={1.65} />
          </span>
          <span>
            docket<span className="brand-dot">.</span>
          </span>
        </Link>
        <div className="workspace">
          <span className="workspace-icon">N</span>
          <div>
            <strong>Northstar AP</strong>
            <small>Demonstration workspace</small>
          </div>
          <ChevronDown size={14} />
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Main navigation">
          {nav.map((item) => (
            <Link
              key={item.id}
              href={item.id === "inbox" ? "/" : `/${item.id}/`}
              className={`nav-item ${page === item.id || (page === "review" && item.id === "inbox") ? "active" : ""}`}
              onClick={() => setMobile(false)}
            >
              <item.icon size={18} />
              <span>{item.name}</span>
              {item.id === "inbox" && (
                <span className="nav-count">{waiting || "0"}</span>
              )}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="recorded-card">
            <span className="eyebrow">
              <span className="live-dot" /> RECORDED DEMO
            </span>
            <strong>Every field has a paper trail.</strong>
            <p>Explore the documents, check the evidence, and try a review.</p>
            <Link href="/evaluation/">
              See how it is measured <ArrowRight size={13} />
            </Link>
          </div>
          <button className="nav-item" onClick={() => setSettings(true)}>
            <Settings2 size={18} />
            <span>Connection & settings</span>
          </button>
          <div className="sidebar-profile">
            <span className="avatar">AP</span>
            <div>
              <strong>Review workspace</strong>
              <small>
                {connected ? "Connected API" : "Browser-local practice"}
              </small>
            </div>
            <button
              className="icon-button"
              aria-label={
                dark ? "Switch to light theme" : "Switch to dark theme"
              }
              onClick={toggleTheme}
            >
              {dark ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </div>
      </aside>
      {mobile && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      )}
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobile(true)}
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{active}</strong>
          </div>
          <div className="topbar-actions">
            <span className="connection-status">
              <span className="live-dot" />
              {connected ? "API connected" : "Recorded session"}
            </span>
            <span className="topbar-divider" />
            <button
              aria-label="About this demo"
              className="icon-button"
              onClick={() =>
                notify(
                  "This is a recorded evaluation with fictional generated invoices and public CORD receipts. Reviews are browser-local unless you connect an API.",
                )
              }
            >
              <CircleHelp size={18} />
            </button>
            <span className="avatar small">AP</span>
          </div>
        </header>
        <main id="main-content">
          {!bundle && !loadError ? (
            <Loading />
          ) : loadError ? (
            <div className="empty-state panel">
              <FileText size={32} />
              <h1>The recorded queue could not load.</h1>
              <p>{loadError}</p>
              <button
                className="button primary"
                onClick={() => location.reload()}
              >
                Try again
              </button>
            </div>
          ) : (
            bundle && (
              <>
                {page === "inbox" && (
                  <InboxPage
                    docs={docs}
                    evaluation={bundle.evaluation}
                    op={op}
                    onUpload={() => setUpload(true)}
                  />
                )}
                {page === "review" && (
                  <Reviewer
                    documents={docs}
                    evaluation={bundle.evaluation}
                    onSave={saveReview}
                    connected={connected}
                  />
                )}
                {page === "evaluation" && (
                  <Evaluation evaluation={bundle.evaluation} />
                )}
                {page === "lab" && (
                  <Lab documents={docs} evaluation={bundle.evaluation} />
                )}
                {page === "rules" && (
                  <Rules documents={docs} evaluation={bundle.evaluation} />
                )}
                {page === "models" && <Models evaluation={bundle.evaluation} />}
                {page === "explore" && <Explore documents={docs} />}
                {page === "report" && (
                  <Report evaluation={bundle.evaluation} documents={docs} />
                )}
              </>
            )
          )}
        </main>
        <footer className="app-footer">
          <div>
            <ShieldCheck size={14} />
            <span>{STATEMENT}</span>
          </div>
          <a
            href="https://github.com/mekala27-45/docket"
            target="_blank"
            rel="noreferrer"
          >
            View source <ArrowRight size={12} />
          </a>
        </footer>
      </div>
      {toast && (
        <div role="status" className="toast">
          <CircleCheck size={18} />
          <span>{toast}</span>
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setToast("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {settings && (
        <SettingsModal
          connection={connection}
          onClose={() => setSettings(false)}
          onReset={reset}
          onConnect={async (c) => {
            const response = await fetch(`${c.url}/v1/queue`, {
              headers: c.token ? { Authorization: `Bearer ${c.token}` } : {},
            });
            if (!response.ok)
              throw new Error(`The API returned HTTP ${response.status}.`);
            const body = await response.json();
            const queue = Array.isArray(body)
              ? body
              : body.documents || body.items;
            if (!Array.isArray(queue))
              throw new Error("The API did not return a queue.");
            setDocs(queue);
            sessionConnection = c;
            setConnection(c);
            setConnected(true);
            setSettings(false);
            notify(
              "Connected to the API. Reviews will be submitted to this service.",
            );
          }}
          onDisconnect={() => {
            sessionConnection = null;
            setConnection(null);
            setConnected(false);
            if (bundle) setDocs(bundle.documents);
            setSettings(false);
          }}
        />
      )}
      {upload && (
        <UploadModal
          connection={connected ? connection : null}
          onClose={() => setUpload(false)}
          onSettings={() => {
            setUpload(false);
            setSettings(true);
          }}
          onUploaded={(doc) => {
            setDocs((d) => [doc, ...d]);
            setUpload(false);
            notify("Document processed by the connected API.");
          }}
        />
      )}
    </div>
  );
}

function InboxPage({
  docs,
  evaluation,
  op,
  onUpload,
}: {
  docs: DocumentItem[];
  evaluation: Record<string, unknown>;
  op?: Record<string, unknown>;
  onUpload: () => void;
}) {
  const [tab, setTab] = useState("needs_review");
  const [search, setSearch] = useState("");
  const [type, setType] = useState("all");
  const [sort, setSort] = useState("risk");
  const [source, setSource] = useState("generated");
  const [pageIndex, setPageIndex] = useState(0);
  const PAGE_SIZE = 8;
  useEffect(() => setPageIndex(0), [tab, search, type, sort, source]);
  const [selected, setSelected] = useState<string[]>([]);
  const waiting = docs.filter((d) => d.status === "needs_review");
  const approved = docs.filter(
    (d) => d.status === "auto_approved" || d.status === "accepted",
  );
  const filtered = useMemo(
    () =>
      docs
        .filter(
          (d) =>
            (tab === "all" ||
              (tab === "approved"
                ? ["auto_approved", "accepted"].includes(d.status)
                : d.status === tab)) &&
            (type === "all" || d.type === type) &&
            (source === "all" ||
              (source === "generated"
                ? !d.source?.includes("cord")
                : d.source?.includes("cord"))) &&
            `${d.vendor} ${d.number} ${d.id} ${d.total}`
              .toLowerCase()
              .includes(search.toLowerCase()),
        )
        .sort((a, b) =>
          sort === "vendor"
            ? a.vendor.localeCompare(b.vendor)
            : sort === "confidence"
              ? lowest(a) - lowest(b)
              : a.currency.localeCompare(b.currency) ||
                (b.risk ?? b.total ?? 0) - (a.risk ?? a.total ?? 0),
        ),
    [docs, tab, type, search, sort, source],
  );
  const paged = filtered.slice(
    pageIndex * PAGE_SIZE,
    (pageIndex + 1) * PAGE_SIZE,
  );
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const next = waiting.find((d) => !d.source?.includes("cord")) || waiting[0];
  const failedCount = waiting.filter((d) =>
    d.rules.some((r) => r.status === "fail"),
  ).length;
  function exportRows() {
    const exportDocs = selected.length
      ? docs.filter((d) => selected.includes(d.id))
      : filtered;
    const csv = [
      "document,vendor,type,total,currency,status",
      ...exportDocs.map((d) =>
        [
          d.number,
          d.vendor,
          d.type,
          d.extraction.fields.total?.value == null ? "" : d.total,
          d.currency,
          d.status,
        ]
          .map((v) => `"${String(v).replaceAll('"', '""')}"`)
          .join(","),
      ),
    ].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "docket-queue.csv";
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            ACCOUNTS PAYABLE / DOCUMENT INTELLIGENCE
          </div>
          <h1>
            Your document inbox<span className="heading-dot">.</span>
          </h1>
          <p>
            A clear view of what came in, what checks out, and what needs you.
          </p>
        </div>
        <div className="heading-actions">
          <button className="button" onClick={onUpload}>
            <Upload size={16} />
            Upload document
          </button>
          {next && (
            <Link
              className="button primary"
              href={`/review/?id=${encodeURIComponent(next.id)}`}
            >
              Review next <ArrowRight size={16} />
            </Link>
          )}
        </div>
      </div>
      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-label">
            Needs a human{" "}
            <span className="stat-icon amber">
              <Inbox size={16} />
            </span>
          </div>
          <div className="stat-value">
            {waiting.length}
            <span className="stat-unit">documents</span>
          </div>
          <div className="stat-caption">
            <span className="tiny-dot amber-bg" />
            {failedCount} with a failed business rule
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">
            Amount in review{" "}
            <span className="stat-icon gray">
              <FileText size={16} />
            </span>
          </div>
          <div className="stat-value amount">
            {money(
              waiting
                .filter((d) => d.currency === "USD")
                .reduce((sum, d) => sum + (d.total ?? 0), 0),
            )}
          </div>
          <div className="stat-caption">Known USD totals · current queue</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">
            Test review rate{" "}
            <span className="stat-icon purple">
              <SlidersHorizontal size={16} />
            </span>
          </div>
          <div
            className={`stat-value ${metricValue(op?.review_rate) === "Not measured" ? "unmeasured" : ""}`}
          >
            {metricValue(op?.review_rate)}
          </div>
          <div className="stat-caption">{interval(op?.review_rate)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">
            Auto-approval error{" "}
            <span className="stat-icon green">
              <ShieldCheck size={16} />
            </span>
          </div>
          <div
            className={`stat-value ${metricValue(op?.auto_approval_error) === "Not measured" ? "unmeasured" : ""}`}
          >
            {metricValue(op?.auto_approval_error)}
          </div>
          <div className="stat-caption">
            {interval(op?.auto_approval_error)}
          </div>
        </div>
      </div>
      <div className="evidence-strip">
        <span className="evidence-icon">
          <Sparkles size={16} />
        </span>
        <span>
          <strong>The evidence comes with the answer.</strong> Every extracted
          field links to its place on the page and the rules behind it.
        </span>
        <Link href="/evaluation/">
          View evaluation <ArrowRight size={14} />
        </Link>
      </div>
      <section className="panel queue-panel" aria-label="Document queue">
        <div className="queue-tabs">
          <div role="tablist" aria-label="Document status">
            {[
              ["needs_review", "Needs review", waiting.length],
              ["approved", "Approved", approved.length],
              ["all", "All documents", docs.length],
            ].map(([id, title, count]) => (
              <button
                role="tab"
                aria-selected={tab === id}
                key={id}
                className={tab === id ? "active" : ""}
                onClick={() => {
                  setTab(String(id));
                  setSelected([]);
                }}
              >
                {title}
                <span>{count}</span>
              </button>
            ))}
          </div>
          <button className="button subtle small-button" onClick={exportRows}>
            <Download size={14} />
            Export{selected.length > 0 ? ` (${selected.length})` : ""}
          </button>
        </div>
        <div className="filter-bar">
          <label className="search-field">
            <Search size={16} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search vendor, document, or amount..."
              aria-label="Search documents"
            />
            {search && (
              <button
                className="icon-button"
                aria-label="Clear search"
                onClick={() => setSearch("")}
              >
                <X size={14} />
              </button>
            )}
            <kbd>/</kbd>
          </label>
          <div className="filter-controls">
            <label className="select-control source-control">
              <Database size={14} />
              <select
                aria-label="Document source"
                value={source}
                onChange={(e) => setSource(e.target.value)}
              >
                <option value="generated">Generated documents</option>
                <option value="cord">CORD receipts</option>
                <option value="all">All sources</option>
              </select>
              <ChevronDown size={12} />
            </label>
            <label className="select-control">
              <FileText size={14} />
              <select
                aria-label="Document type"
                value={type}
                onChange={(e) => setType(e.target.value)}
              >
                <option value="all">All types</option>
                <option value="invoice">Invoices</option>
                <option value="purchase_order">Purchase orders</option>
                <option value="receipt">Receipts</option>
              </select>
              <ChevronDown size={12} />
            </label>
            <label className="select-control">
              <ArrowDownUp size={14} />
              <select
                aria-label="Sort documents"
                value={sort}
                onChange={(e) => setSort(e.target.value)}
              >
                <option value="risk">Currency, then risk</option>
                <option value="confidence">Lowest confidence</option>
                <option value="vendor">Vendor A to Z</option>
              </select>
              <ChevronDown size={12} />
            </label>
          </div>
        </div>
        <div className="table-scroll">
          <table className="queue-table">
            <thead>
              <tr>
                <th className="check-cell">
                  <input
                    type="checkbox"
                    aria-label="Select all documents"
                    checked={
                      filtered.length > 0 &&
                      filtered.every((d) => selected.includes(d.id))
                    }
                    onChange={(e) =>
                      setSelected(
                        e.target.checked ? filtered.map((d) => d.id) : [],
                      )
                    }
                  />
                </th>
                <th>DOCUMENT</th>
                <th>VENDOR</th>
                <th className="align-right">TOTAL</th>
                <th>
                  CONFIDENCE <CircleHelp size={11} />
                </th>
                <th>VALIDATION</th>
                <th
                  className="align-right"
                  title="Total × (1 − lowest required-field confidence), in native currency. Zero does not mean business rules passed."
                >
                  PRIORITY AMOUNT <ArrowDown size={11} />
                </th>
                <th />
              </tr>
            </thead>
            <tbody>
              {paged.map((doc) => {
                const failed = doc.rules.filter((r) => r.status === "fail");
                const confidence = lowest(doc);
                return (
                  <tr key={doc.id}>
                    <td className="check-cell">
                      <input
                        type="checkbox"
                        aria-label={`Select ${doc.number}`}
                        checked={selected.includes(doc.id)}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? [...selected, doc.id]
                              : selected.filter((id) => id !== doc.id),
                          )
                        }
                      />
                    </td>
                    <td>
                      <Link
                        className="document-cell"
                        href={`/review/?id=${encodeURIComponent(doc.id)}`}
                      >
                        <span className="document-thumb">
                          {doc.image ? (
                            <img src={asset(doc.image)} alt="" />
                          ) : (
                            <FileText size={21} />
                          )}
                          <span className="doc-type-tag">
                            {doc.type === "purchase_order"
                              ? "PO"
                              : doc.type === "receipt"
                                ? "REC"
                                : "INV"}
                          </span>
                        </span>
                        <span>
                          <strong className="mono">
                            {doc.number || doc.id}
                          </strong>
                          <small>
                            {label(doc.type)} <span>·</span>{" "}
                            {doc.date || "Date missing"}
                          </small>
                        </span>
                      </Link>
                    </td>
                    <td>
                      <span className="vendor-name">
                        {doc.vendor || "Vendor not extracted"}
                      </span>
                      <small className="cell-secondary">
                        {doc.source?.includes("cord")
                          ? "CORD public receipt"
                          : "Generated document"}
                      </small>
                    </td>
                    <td className="align-right">
                      <span className="table-amount">
                        {doc.extraction.fields.total?.value == null
                          ? "Not extracted"
                          : money(doc.total, doc.currency)}
                      </span>
                      <small className="cell-secondary">{doc.currency}</small>
                    </td>
                    <td>
                      <div
                        className={`confidence-inline ${confidence < 0.8 ? "low" : ""}`}
                      >
                        <span className="confidence-meter">
                          <span style={{ width: `${confidence * 100}%` }} />
                        </span>
                        <strong>
                          {doc.status === "accepted" ||
                          doc.status === "rejected"
                            ? "Reviewed"
                            : pct(confidence)}
                        </strong>
                      </div>
                      <small className="cell-secondary confidence-note">
                        Required fields ·{" "}
                        <Link href="/evaluation/#calibration">
                          calibration ↗
                        </Link>
                      </small>
                    </td>
                    <td>
                      {failed.length ? (
                        <span className="rule-pill">
                          <span className="tiny-dot amber-bg" />
                          {failed.length}{" "}
                          {failed.length === 1 ? "rule" : "rules"} flagged
                        </span>
                      ) : (
                        <span className="rule-pass">
                          <CircleCheck size={13} />
                          All checks passed
                        </span>
                      )}
                      <small className="cell-secondary validation-secondary">
                        {failed[0]?.name ||
                          (doc.status === "needs_review"
                            ? "Confidence below threshold"
                            : label(doc.status))}
                      </small>
                    </td>
                    <td className="align-right">
                      <span
                        className={`table-amount ${failed.length ? "risk-amount" : ""}`}
                      >
                        {money(
                          doc.risk ??
                            (doc.status === "needs_review" ? doc.total : 0),
                          doc.currency,
                        )}
                      </span>
                    </td>
                    <td>
                      <Link
                        href={`/review/?id=${encodeURIComponent(doc.id)}`}
                        className="row-link"
                        aria-label={`Review ${doc.number}`}
                      >
                        <ChevronRight size={17} />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!filtered.length && (
          <div className="empty-state">
            <Search size={30} />
            <h3>
              {search
                ? "No documents match your search."
                : "You are all caught up here."}
            </h3>
            <p>
              {search
                ? "Try another vendor, identifier, or amount."
                : "Switch to all documents to explore the recorded queue."}
            </p>
            <button
              className="button"
              onClick={() => {
                setSearch("");
                setType("all");
                setSource("all");
                setTab("all");
              }}
            >
              Show all documents
            </button>
          </div>
        )}
        <div className="table-footer">
          <span>
            Showing{" "}
            <strong>
              {paged.length ? pageIndex * PAGE_SIZE + 1 : 0} to{" "}
              {Math.min((pageIndex + 1) * PAGE_SIZE, filtered.length)}
            </strong>{" "}
            of {filtered.length} matching documents
            {selected.length > 0 && ` · ${selected.length} selected`}
          </span>
          <div className="pagination">
            <button
              className="icon-button"
              aria-label="Previous page"
              disabled={pageIndex === 0}
              onClick={() => setPageIndex((p) => p - 1)}
            >
              <ChevronRight size={15} style={{ transform: "rotate(180deg)" }} />
            </button>
            <span>
              {pageIndex + 1} / {pageCount}
            </span>
            <button
              className="icon-button"
              aria-label="Next page"
              disabled={pageIndex >= pageCount - 1}
              onClick={() => setPageIndex((p) => p + 1)}
            >
              <ChevronRight size={15} />
            </button>
          </div>
        </div>
      </section>
      <div className="below-queue">
        <div>
          <ShieldCheck size={16} />
          <p>
            <strong>Built for a second look.</strong> Approval requires every
            required field to clear the threshold and every business rule to
            pass.
          </p>
        </div>
        <Link href="/rules/">
          Understand the rules <ArrowRight size={13} />
        </Link>
      </div>
      <div className="data-caption">
        Evaluation recorded{" "}
        {typeof evaluation.generated_at === "string"
          ? new Date(evaluation.generated_at).toLocaleDateString("en-US", {
              month: "long",
              day: "numeric",
              year: "numeric",
            })
          : "in the committed manifest"}{" "}
        · Operating point chosen on validation, reported on test. Priority
        amount is total × (1 − lowest required-field confidence), in native
        currency; zero does not mean business rules passed.{" "}
        <Link href="/evaluation/">View population and methods</Link>
      </div>
    </>
  );
}

function Loading() {
  return (
    <div aria-label="Loading documents" className="loading-page">
      <div className="skeleton heading-skeleton" />
      <div className="skeleton subtitle-skeleton" />
      <div className="stat-grid">
        {[0, 1, 2, 3].map((n) => (
          <div className="skeleton stat-skeleton" key={n} />
        ))}
      </div>
      <div className="skeleton table-skeleton" />
    </div>
  );
}

function Modal({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: string;
  subtitle: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className="modal panel"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-heading">
          <div>
            <h2>{title}</h2>
            <p>{subtitle}</p>
          </div>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
function SettingsModal({
  connection,
  onClose,
  onConnect,
  onDisconnect,
  onReset,
}: {
  connection: Connection | null;
  onClose: () => void;
  onConnect: (c: Connection) => Promise<void>;
  onDisconnect: () => void;
  onReset: () => void;
}) {
  const [url, setUrl] = useState(connection?.url || "");
  const [token, setToken] = useState(connection?.token || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Modal
      title="Connection & settings"
      subtitle="The recorded demo works without an account or service."
      onClose={onClose}
    >
      <div className="info-note">
        <Database size={18} />
        <p>
          Connect your own Docket API for server-backed uploads and reviews. The
          URL and token stay in memory for this session.
        </p>
      </div>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setError("");
          setBusy(true);
          try {
            const clean = new URL(url);
            if (
              clean.protocol !== "https:" &&
              clean.hostname !== "localhost" &&
              clean.hostname !== "127.0.0.1"
            )
              throw new Error("Use HTTPS, or localhost for local development.");
            await onConnect({ url: url.replace(/\/$/, ""), token });
          } catch (e) {
            setError(e instanceof Error ? e.message : "Connection failed.");
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="form-label">
          API URL
          <input
            type="url"
            placeholder="https://your-docket-api.example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
          />
        </label>
        <label className="form-label">
          Write token
          <input
            type="password"
            placeholder="Bearer token for uploads and reviews"
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
        </label>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="modal-actions">
          {connection && (
            <button className="button" type="button" onClick={onDisconnect}>
              Disconnect
            </button>
          )}
          <button className="button primary" disabled={busy}>
            {busy ? (
              <LoaderCircle className="spin" size={15} />
            ) : (
              <Plus size={15} />
            )}
            Connect API
          </button>
        </div>
      </form>
      <div className="settings-reset">
        <div>
          <strong>Reset practice reviews</strong>
          <p>
            Restore the recorded queue and remove corrections stored in this
            browser.
          </p>
        </div>
        <button className="button small-button" onClick={onReset}>
          Reset
        </button>
      </div>
    </Modal>
  );
}
function UploadModal({
  connection,
  onClose,
  onSettings,
  onUploaded,
}: {
  connection: Connection | null;
  onClose: () => void;
  onSettings: () => void;
  onUploaded: (d: DocumentItem) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Modal
      title="Upload a document"
      subtitle="Send a document to your connected processing service."
      onClose={onClose}
    >
      {!connection ? (
        <>
          <div className="upload-zone">
            <Upload size={32} />
            <h3>Connect an API to process uploads</h3>
            <p>
              The public demo uses recorded documents. Your own files are
              processed only by the API you choose.
            </p>
          </div>
          <div className="modal-actions">
            <button className="button" onClick={onClose}>
              Back to inbox
            </button>
            <button className="button primary" onClick={onSettings}>
              Connection settings <ArrowRight size={15} />
            </button>
          </div>
        </>
      ) : (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (!file) return;
            setBusy(true);
            setError("");
            try {
              if (!connection.token)
                throw new Error(
                  "A write token is required. Set it in connection settings.",
                );
              if (file.size > 10 * 1024 * 1024)
                throw new Error("Choose a file smaller than 10 MB.");
              const form = new FormData();
              form.append("file", file);
              const response = await fetch(`${connection.url}/v1/documents`, {
                method: "POST",
                headers: { Authorization: `Bearer ${connection.token}` },
                body: form,
              });
              if (!response.ok)
                throw new Error(`Upload failed (HTTP ${response.status}).`);
              const body = await response.json();
              onUploaded(body.document || body);
            } catch (e) {
              setError(e instanceof Error ? e.message : "Upload failed.");
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="upload-zone">
            <Upload size={30} />
            <strong>{file?.name || "Choose an invoice or receipt"}</strong>
            <span>PNG, JPEG, or PDF · up to 10 MB</span>
            <input
              type="file"
              accept="image/png,image/jpeg,application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </label>
          <p className="fine-print">
            Your file will be sent to {connection.url}. Verify your
            service&apos;s redaction and retention policy before uploading.
          </p>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="modal-actions">
            <button className="button primary" disabled={!file || busy}>
              {busy ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <Upload size={15} />
              )}
              Process document
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}
