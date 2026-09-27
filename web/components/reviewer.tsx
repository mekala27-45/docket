"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronRight,
  CircleCheck,
  FileText,
  Focus,
  Keyboard,
  Layers,
  LoaderCircle,
  Minus,
  Plus,
  RotateCcw,
  ShieldCheck,
  X,
} from "lucide-react";
import { asset, FIELD_COLORS, label, money, pct } from "@/lib/types";
import type { DocumentItem, LineItem } from "@/lib/types";
import { Status } from "./workbench";

interface Props {
  documents: DocumentItem[];
  evaluation: Record<string, unknown>;
  connected: boolean;
  onSave: (
    doc: DocumentItem,
    fields: Record<string, string>,
    items: LineItem[],
    decision: "accept" | "reject",
    reason: string,
  ) => Promise<void>;
}
interface Calibration {
  field: string;
  backend: string;
  bins: { confidence: number; accuracy: number; count: number }[];
}

export function calibrationSentence(
  name: string,
  confidence: number,
  evaluation: Record<string, unknown>,
): string {
  const entries = (evaluation.calibration || []) as Calibration[];
  const entry =
    entries.find((e) => e.field === name && e.backend === "rules") ||
    entries.find((e) => e.field === name);
  const bins = (entry?.bins || []).filter((b) => b.count > 0);
  const bin = bins.sort(
    (a, b) =>
      Math.abs(a.confidence - confidence) - Math.abs(b.confidence - confidence),
  )[0];
  return bin
    ? `Of 100 fields in this confidence band, about ${Math.round(bin.accuracy * 100)} were correct in held-out evaluation (n=${bin.count}).`
    : "No held-out calibration bin is available for this field; treat its confidence as unverified.";
}
export function Reviewer({ documents, evaluation, connected, onSave }: Props) {
  const [id, setId] = useState("");
  useEffect(() => {
    setId(
      new URLSearchParams(window.location.search).get("id") ||
        documents[0]?.id ||
        "",
    );
  }, [documents]);
  const doc = documents.find((d) => d.id === id);
  const [values, setValues] = useState<Record<string, string>>({});
  const [items, setItems] = useState<LineItem[]>([]);
  const [active, setActive] = useState("vendor");
  const [trace, setTrace] = useState<string | null>(null);
  const [overlays, setOverlays] = useState(true);
  const [zoom, setZoom] = useState(100);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [tab, setTab] = useState("fields");
  const [saved, setSaved] = useState(false);
  const [help, setHelp] = useState(false);
  const inputs = useRef<Record<string, HTMLInputElement | null>>({});
  useEffect(() => {
    if (!doc) return;
    setValues(
      Object.fromEntries(
        Object.entries(doc.extraction.fields).map(([k, f]) => [
          k,
          String(f.value ?? ""),
        ]),
      ),
    );
    setItems(doc.extraction.line_items || doc.line_items || []);
    setSaved(doc.status === "accepted" || doc.status === "rejected");
  }, [doc]);
  const next = documents.find(
    (d) => d.status === "needs_review" && d.id !== id,
  );
  const save = async (decision: "accept" | "reject") => {
    if (!doc || busy) return;
    setBusy(true);
    setError("");
    try {
      await onSave(doc, values, items, decision, reason);
      setSaved(true);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "The review could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        void save("accept");
        return;
      }
      if ((e.target as HTMLElement).matches("input,textarea,select")) return;
      if (e.key === "t") setTrace((t) => (t ? null : active));
      if (e.key === "b") setOverlays((b) => !b);
      if (e.key === "?") setHelp((h) => !h);
      if (e.key === "n" && next)
        window.location.href = `/docket/review/?id=${encodeURIComponent(next.id)}`;
      if (/^[1-9]$/.test(e.key) && doc) {
        const key = Object.keys(doc.extraction.fields)[Number(e.key) - 1];
        if (key) {
          setActive(key);
          inputs.current[key]?.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  });
  if (!id) return <div className="skeleton table-skeleton" />;
  if (!doc)
    return (
      <div className="empty-state panel">
        <FileText size={32} />
        <h1>Document not found.</h1>
        <p>
          This identifier is not in the current queue. Connect its API or choose
          a recorded document.
        </p>
        <Link className="button primary" href="/">
          Back to inbox
        </Link>
      </div>
    );
  const fields = Object.entries(doc.extraction.fields);
  const failed = doc.rules.filter((r) => r.status === "fail");
  return (
    <>
      <div className="review-heading">
        <div>
          <Link className="back-link" href="/">
            <ArrowLeft size={14} />
            Back to inbox
          </Link>
          <h1>
            {doc.number || doc.id}
            <Status status={doc.status} />
          </h1>
          <p>
            {doc.vendor} <span>·</span> {label(doc.type)} <span>·</span>{" "}
            {doc.source}
          </p>
        </div>
        <div className="heading-actions">
          <button
            className="button"
            aria-label="Keyboard shortcuts"
            onClick={() => setHelp((h) => !h)}
          >
            <Keyboard size={16} />
            <span className="desktop-only">Shortcuts</span>
          </button>
          {next && (
            <Link
              className="button"
              href={`/review/?id=${encodeURIComponent(next.id)}`}
            >
              Next document <ArrowRight size={15} />
            </Link>
          )}
        </div>
      </div>
      {help && (
        <div className="keyboard-help panel">
          <strong>Keyboard shortcuts</strong>
          <span>
            <kbd>Ctrl</kbd> + <kbd>Enter</kbd> accept
          </span>
          <span>
            <kbd>1</kbd> - <kbd>9</kbd> jump to field
          </span>
          <span>
            <kbd>T</kbd> trace
          </span>
          <span>
            <kbd>B</kbd> boxes
          </span>
          <span>
            <kbd>N</kbd> next document
          </span>
          <button
            className="icon-button"
            aria-label="Close shortcuts"
            onClick={() => setHelp(false)}
          >
            <X size={15} />
          </button>
        </div>
      )}
      <div className="review-layout">
        <section
          className="viewer-panel panel"
          aria-label="Document image and evidence"
        >
          <div className="viewer-toolbar">
            <span>
              <FileText size={15} />
              <strong>Original document</strong>
              <span className="page-count">1 / 1</span>
            </span>
            <div>
              <button
                className={`icon-button ${overlays ? "selected" : ""}`}
                aria-label="Toggle field overlays"
                aria-pressed={overlays}
                onClick={() => setOverlays(!overlays)}
              >
                <Layers size={16} />
              </button>
              <span className="toolbar-divider" />
              <button
                className="icon-button"
                aria-label="Zoom out"
                onClick={() => setZoom(Math.max(60, zoom - 20))}
              >
                <Minus size={15} />
              </button>
              <span className="zoom-label">{zoom}%</span>
              <button
                className="icon-button"
                aria-label="Zoom in"
                onClick={() => setZoom(Math.min(180, zoom + 20))}
              >
                <Plus size={15} />
              </button>
              <button
                className="icon-button"
                aria-label="Reset zoom"
                onClick={() => setZoom(100)}
              >
                <Focus size={16} />
              </button>
            </div>
          </div>
          <div className="paper-area">
            <div
              className="document-paper"
              style={{
                width: `${zoom}%`,
                maxWidth: zoom > 100 ? "none" : undefined,
              }}
            >
              {doc.image ? (
                <img
                  className="source-image"
                  src={asset(doc.image)}
                  alt={`Generated ${label(doc.type).toLowerCase()} ${doc.number} from ${doc.vendor}`}
                />
              ) : (
                <div className="no-document-image">
                  <FileText size={40} />
                  <p>No image supplied by this API.</p>
                </div>
              )}
              {overlays &&
                fields
                  .filter(([, f]) => f.box)
                  .map(([name, field]) => {
                    const box = field.box!;
                    return (
                      <button
                        key={name}
                        aria-label={`Show ${label(name)} evidence`}
                        className={`field-box ${active === name ? "active" : ""}`}
                        style={
                          {
                            left: `${box[0] * 100}%`,
                            top: `${box[1] * 100}%`,
                            width: `${box[2] * 100}%`,
                            height: `${box[3] * 100}%`,
                            borderColor: FIELD_COLORS[name] || "#5E8A1A",
                            "--box-color": FIELD_COLORS[name] || "#5E8A1A",
                          } as React.CSSProperties
                        }
                        onClick={() => {
                          setActive(name);
                          setTab("fields");
                          inputs.current[name]?.focus();
                        }}
                      >
                        <span>{label(name)}</span>
                      </button>
                    );
                  })}
            </div>
          </div>
          <div className="viewer-footer">
            <ShieldCheck size={14} />
            <span>
              Demonstration document · click a field box to inspect its value
            </span>
          </div>
        </section>
        <section
          className="review-fields panel"
          aria-label="Review extracted fields"
        >
          <div className="review-panel-heading">
            <div>
              <h2>Check the details</h2>
              <p>Read the page. Follow the evidence.</p>
            </div>
            <span className="backend-label">{doc.extraction.backend}</span>
          </div>
          <div
            className="review-tabs"
            role="tablist"
            aria-label="Review panels"
          >
            {[
              ["fields", "Fields", fields.length],
              ["items", "Line items", items.length],
              ["rules", "Validation", failed.length],
            ].map(([key, title, count]) => (
              <button
                key={key}
                role="tab"
                aria-selected={tab === key}
                className={tab === key ? "active" : ""}
                onClick={() => setTab(String(key))}
              >
                {title}
                <span
                  className={
                    key === "rules" && failed.length ? "warning-count" : ""
                  }
                >
                  {count}
                </span>
              </button>
            ))}
          </div>
          <div className="review-panel-content">
            {tab === "fields" && (
              <div className="field-list">
                {fields.map(([name, field], index) => (
                  <div
                    key={name}
                    className={`field-editor ${active === name ? "active" : ""}`}
                    style={
                      {
                        "--field-color": FIELD_COLORS[name] || "#5E8A1A",
                      } as React.CSSProperties
                    }
                  >
                    <div className="field-label-row">
                      <label htmlFor={`field-${name}`}>
                        <span className="field-color" />
                        {label(name)}
                      </label>
                      <span
                        className={`field-confidence ${(field.confidence ?? 1) < 0.8 ? "low" : ""}`}
                      >
                        {field.reviewed
                          ? "Reviewed"
                          : pct(field.confidence ?? 0)}
                        <span>
                          {field.reviewed ? "by a human" : "confidence"}
                        </span>
                      </span>
                    </div>
                    <input
                      id={`field-${name}`}
                      ref={(el) => {
                        inputs.current[name] = el;
                      }}
                      value={values[name] ?? ""}
                      onFocus={() => setActive(name)}
                      onChange={(e) => {
                        setValues({ ...values, [name]: e.target.value });
                        setSaved(false);
                      }}
                      aria-describedby={`calibration-${name}`}
                    />
                    <div className="field-meta">
                      <button
                        className="trace-link"
                        onClick={() => {
                          setTrace(trace === name ? null : name);
                          setActive(name);
                        }}
                      >
                        <ChevronRight
                          className={trace === name ? "rotate" : ""}
                          size={13}
                        />
                        Why this value?
                      </button>
                      <kbd>{index + 1}</kbd>
                    </div>
                    <p
                      className="calibration-sentence"
                      id={`calibration-${name}`}
                    >
                      {field.calibration_sentence ||
                        calibrationSentence(
                          name,
                          field.confidence ?? 0,
                          evaluation,
                        )}
                    </p>
                    {trace === name && (
                      <div
                        className="trace-content"
                        aria-label={`${label(name)} extraction trace`}
                      >
                        <span className="eyebrow">EXTRACTION TRACE</span>
                        {field.trace?.length ? (
                          <ol>
                            {field.trace.map((step, i) => (
                              <li key={i}>
                                <strong>{step.step}</strong>
                                <p>{step.detail}</p>
                              </li>
                            ))}
                          </ol>
                        ) : (
                          <p>
                            The selected backend supplied this value without a
                            detailed trace.
                          </p>
                        )}
                        <div className="trace-source">
                          <span>OCR engine</span>
                          <code>{doc.extraction.ocr_engine}</code>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {tab === "items" && (
              <>
                <div className="section-note">
                  <FileText size={16} />
                  <p>
                    Correct each extracted row against the document. Totals
                    below are computed from these editable rows.
                  </p>
                </div>
                <div className="item-editors">
                  {items.map((item, i) => (
                    <div className="item-editor" key={i}>
                      <div className="item-heading">
                        <span className="eyebrow">LINE {i + 1}</span>
                        <button
                          className="icon-button"
                          aria-label={`Remove line ${i + 1}`}
                          onClick={() => {
                            setItems(items.filter((_, j) => j !== i));
                            setSaved(false);
                          }}
                        >
                          <X size={14} />
                        </button>
                      </div>
                      <label className="form-label">
                        Description
                        <input
                          value={item.description}
                          onChange={(e) => {
                            setItems(
                              items.map((r, j) =>
                                j === i
                                  ? { ...r, description: e.target.value }
                                  : r,
                              ),
                            );
                            setSaved(false);
                          }}
                        />
                      </label>
                      <div className="item-numbers">
                        {(["quantity", "unit_price", "amount"] as const).map(
                          (key) => (
                            <label className="form-label" key={key}>
                              {label(key)}
                              <input
                                type="number"
                                step="0.01"
                                value={item[key]}
                                onChange={(e) => {
                                  setItems(
                                    items.map((r, j) =>
                                      j === i
                                        ? {
                                            ...r,
                                            [key]: Number(e.target.value),
                                          }
                                        : r,
                                    ),
                                  );
                                  setSaved(false);
                                }}
                              />
                            </label>
                          ),
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                <button
                  className="button full-width"
                  onClick={() => {
                    setItems([
                      ...items,
                      {
                        description: "",
                        quantity: 1,
                        unit_price: 0,
                        amount: 0,
                      },
                    ]);
                    setSaved(false);
                  }}
                >
                  <Plus size={14} />
                  Add line item
                </button>
                <div className="line-total">
                  <span>Line item sum</span>
                  <strong>
                    {money(
                      items.reduce((s, i) => s + i.amount, 0),
                      doc.currency,
                    )}
                  </strong>
                </div>
              </>
            )}
            {tab === "rules" && (
              <>
                <div
                  className={`validation-summary ${failed.length ? "warning" : "success"}`}
                >
                  <ShieldCheck size={22} />
                  <div>
                    <strong>
                      {failed.length
                        ? `${failed.length} checks need your attention`
                        : "All applicable rules passed"}
                    </strong>
                    <p>
                      Rule results reflect the original recorded extraction.
                      Local corrections do not rerun the pipeline.
                    </p>
                  </div>
                </div>
                <div className="rule-results">
                  {doc.rules.map((rule) => (
                    <div key={rule.id} className="rule-result">
                      <span className={`rule-result-icon ${rule.status}`}>
                        {rule.status === "pass" ? (
                          <Check size={16} />
                        ) : rule.status === "fail" ? (
                          <X size={16} />
                        ) : (
                          <Minus size={16} />
                        )}
                      </span>
                      <div>
                        <strong>{rule.name}</strong>
                        <p>{rule.message}</p>
                      </div>
                      <Status status={rule.status} />
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
          <div className="review-actions">
            <label className="form-label">
              Review note <span>(optional)</span>
              <input
                placeholder="What did you check or correct?"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            {saved && (
              <div className="saved-note" role="status">
                <CircleCheck size={14} />
                Review saved {connected ? "by API" : "in this browser"}
              </div>
            )}
            <div className="review-action-buttons">
              <button
                className="button reject-button"
                disabled={busy}
                onClick={() => void save("reject")}
              >
                <X size={15} />
                Reject
              </button>
              <button
                className="button primary"
                disabled={busy}
                onClick={() => void save("accept")}
              >
                {busy ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <Check size={16} />
                )}
                Accept document <kbd>⌃ ↵</kbd>
              </button>
            </div>
            <p className="practice-note">
              {connected
                ? "The API confirms the saved review before the queue changes."
                : "Local practice only. Your review stays in this browser."}
            </p>
          </div>
        </section>
      </div>
    </>
  );
}
