"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Check,
  ChevronRight,
  Code2,
  Download,
  FileText,
  FlaskConical,
  Info,
  Play,
  Printer,
  RotateCcw,
  ShieldCheck,
  Table2,
} from "lucide-react";
import {
  BASE,
  asset,
  label,
  money,
  pct,
  displayedConfidence,
  priorityAmount,
} from "@/lib/types";
import type { DocumentItem } from "@/lib/types";
import { Status } from "./workbench";
import {
  DegradationOverview,
  DegradationChart,
  RuleBenchmark,
  ObservedMetric,
  RoutingBreakdown,
  RetrainEvidence,
  type RetrainRun,
  type RoutingPopulation,
  orderedLevels,
  type SweepRow,
  type SweepFloor,
  type RuleScore,
  type Measurement,
  type DegradationParameter,
} from "./benchmark";

type Manifest = Record<string, unknown>;
type Measured = Measurement;
interface EvalRow {
  source: string;
  backend: string;
  ocr_engine: string;
  split: string;
  n: number;
  field_f1: Measured;
  exact_match: Measured;
  document_success: Measured;
  line_item_f1: Measured;
}
interface RatePoint {
  threshold: number;
  review_rate: number;
  error_rate: number | null;
  cost: number;
}
interface Operating {
  threshold: number;
  chosen_on: string;
  reported_on: string;
  review_cost: number;
  error_cost: number;
  review_rate: Measured;
  auto_approval_error: Measured;
  n: number;
  auto_approved: number;
  curve: RatePoint[];
  by_source?: RoutingPopulation[];
  unlabeled_test_documents?: number;
  unlabeled_validation_documents?: number;
  unlabeled_auto_approved?: number;
}
interface Cal {
  field: string;
  backend: string;
  population?: string;
  independent_documents?: number;
  scope?: string;
  n: number;
  ece_before: number;
  ece_after: number;
  bins: {
    confidence: number;
    accuracy: number;
    count: number;
    ci?: [number, number];
    interval_method?: string;
  }[];
}
type Degradation = SweepRow;

function metric(m: Measured | undefined) {
  return <ObservedMetric measurement={m} denominator />;
}

function numeric(v: unknown): number | null {
  if (typeof v === "number") return v;
  if (v && typeof v === "object" && "value" in v)
    return typeof v.value === "number" ? v.value : null;
  return null;
}
function asText(v: unknown): string {
  return v == null
    ? "Not measured"
    : typeof v === "object"
      ? JSON.stringify(v)
      : String(v);
}
function download(name: string, data: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
function PageHeading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>
          {title}
          <span className="heading-dot">.</span>
        </h1>
        <p>{description}</p>
      </div>
      {children && <div className="heading-actions">{children}</div>}
    </div>
  );
}
function Pushback() {
  return (
    <aside className="pushback panel">
      <span className="eyebrow">WHAT THE AP MANAGER WOULD PUSH BACK ON</span>
      <h3>“But your invoices are not our invoices.”</h3>
      <p>
        That is the right objection. Generated documents have limited layouts,
        and public Indonesian receipts differ from an enterprise invoice queue.
        These results establish a reproducible baseline. They do not establish
        production accuracy, and the operating point depends on the stated cost
        of a wrong approval.
      </p>
    </aside>
  );
}

export function Evaluation({ evaluation }: { evaluation: Manifest }) {
  const rows = (evaluation.extraction || []) as EvalRow[];
  const op = evaluation.operating_point as Operating | undefined;
  const [source, setSource] = useState("all");
  const sources = Array.from(new Set(rows.map((r) => r.source)));
  const filtered = rows.filter((r) => source === "all" || r.source === source);
  const paired = Array.from(
    new Set(filtered.map((r) => `${r.source}|${r.backend}`)),
  ).map((key) => {
    const [src, backend] = key.split("|");
    return {
      source: src,
      backend,
      gold: filtered.find(
        (r) =>
          r.source === src &&
          r.backend === backend &&
          r.ocr_engine.includes("gold"),
      ),
      real: filtered.find(
        (r) =>
          r.source === src &&
          r.backend === backend &&
          !r.ocr_engine.includes("gold"),
      ),
    };
  });
  const calibration = (evaluation.calibration || []) as Cal[];
  const [calField, setCalField] = useState("");
  const selectedCal =
    calibration.find(
      (c) => `${c.backend}:${c.population || "all"}:${c.field}` === calField,
    ) || calibration[0];
  const classification = evaluation.classification as
    | {
        labels: string[];
        confusion_matrix: number[][];
        accuracy: Measured | number;
        n: number;
      }
    | undefined;
  const retrain = evaluation.retrain as RetrainRun | undefined;
  return (
    <>
      <PageHeading
        eyebrow="MEASUREMENT / HELD-OUT EVALUATION"
        title="Know what you can trust"
        description="Separate the OCR from the extraction. Keep the uncertainty in view."
      >
        <button
          className="button"
          onClick={() => download("docket-evaluation.json", evaluation)}
        >
          <Download size={16} />
          Download results
        </button>
        <Link className="button primary" href="/report/">
          Read the report <ArrowRight size={15} />
        </Link>
      </PageHeading>
      <div className="info-note">
        <Info size={18} />
        <p>
          All figures below are read from the committed evaluation manifest.
          Operating thresholds are chosen on validation and reported on test.
          Intervals are 95%; each table states its population. Some documents
          lack reference labels; the denominator beside each estimate counts
          only evaluable observations.
        </p>
      </div>
      <section className="panel section-panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">01 / EXTRACTION</span>
            <h2>Two OCR columns. One honest comparison.</h2>
            <p>
              The difference between the columns exposes the cost of reading the
              page.
            </p>
          </div>
          <select
            className="plain-select"
            aria-label="Evaluation source"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            <option value="all">All sources</option>
            {sources.map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>SOURCE / BACKEND</th>
                <th>GOLD OCR · FIELD F1</th>
                <th>REAL OCR · FIELD F1</th>
                <th title="Total source documents. The denominator beside each metric identifies evaluable observations.">
                  GOLD / REAL n
                </th>
              </tr>
            </thead>
            <tbody>
              {paired.map((row) => (
                <tr key={`${row.source}-${row.backend}`}>
                  <td>
                    <strong>{label(row.backend)}</strong>
                    <small>
                      {label(row.source)} ·{" "}
                      {row.gold?.split || row.real?.split || "test"}
                    </small>
                  </td>
                  <td>{metric(row.gold?.field_f1)}</td>
                  <td>{metric(row.real?.field_f1)}</td>
                  <td className="mono">
                    {row.gold?.n ?? "N/A"} / {row.real?.n ?? "N/A"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="section-caption">
          Field F1 compares extracted fields with known labels. Confidence
          intervals are computed across documents. Gold OCR removes recognition
          error; real OCR uses the recorded engine.
        </div>
      </section>
      <div className="two-columns">
        <section className="panel section-panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">02 / OPERATING POINT</span>
              <h2>The cost of taking a second look</h2>
            </div>
          </div>
          {op ? (
            <>
              <p className="chart-population">
                Validation threshold sweep · n=
                {asText(
                  (op as unknown as Record<string, unknown>).validation_n,
                )}
              </p>
              <CurveChart points={op.curve || []} chosen={op.threshold} />
              <div className="chart-callout">
                <strong>
                  {op.threshold > 1
                    ? "Review all"
                    : `${pct(op.threshold)} confidence threshold`}
                </strong>
                <p>
                  Chosen on {op.chosen_on}; reported on {op.reported_on}. Review
                  cost: {op.review_cost}. Wrong auto-approval cost:{" "}
                  {op.error_cost}.
                </p>
              </div>
              <div className="mini-metrics">
                <div>
                  <span>Review rate</span>
                  {metric(op.review_rate)}
                </div>
                <div>
                  <span>Auto-approved error</span>
                  {metric(op.auto_approval_error)}
                </div>
              </div>
              <p className="section-caption">
                Test population n={op.n}; auto-approved n={op.auto_approved}. An
                empty approved set has no measured error rate. Review rate
                includes all documents; approval error uses only approved
                documents with evaluable reference labels.
                {op.unlabeled_test_documents != null && (
                  <>
                    {" "}
                    {op.unlabeled_test_documents} test documents lack required
                    reference labels.
                  </>
                )}
              </p>
              {!!op.unlabeled_auto_approved && (
                <p className="benchmark-warning">
                  {op.unlabeled_auto_approved} automatically approved documents
                  lack required reference labels and are excluded from the error
                  estimate. Their correctness is unknown.
                </p>
              )}
              <RoutingBreakdown rows={op.by_source || []} />
            </>
          ) : (
            <Unavailable />
          )}
        </section>
        <section className="panel section-panel" id="calibration">
          <div className="section-heading">
            <div>
              <span className="eyebrow">03 / CALIBRATION</span>
              <h2>Confidence, checked against outcomes</h2>
            </div>
          </div>
          {selectedCal ? (
            <>
              <select
                className="plain-select calibration-select"
                aria-label="Calibration field"
                value={`${selectedCal.backend}:${selectedCal.population || "all"}:${selectedCal.field}`}
                onChange={(e) => setCalField(e.target.value)}
              >
                {calibration.map((c) => (
                  <option
                    key={`${c.backend}:${c.population || "all"}:${c.field}`}
                    value={`${c.backend}:${c.population || "all"}:${c.field}`}
                  >
                    {label(c.field)} · {c.backend} ·{" "}
                    {label(c.population || "all")}
                  </option>
                ))}
              </select>
              <CalibrationChart cal={selectedCal} />
              <div className="chart-callout">
                <strong>
                  {label(selectedCal.field)} ·{" "}
                  {label(selectedCal.population || "all")} · held-out n=
                  {selectedCal.n} field observations
                </strong>
                <p>
                  {selectedCal.independent_documents != null && (
                    <>
                      {selectedCal.independent_documents} distinct parent pages;{" "}
                      {label(selectedCal.scope || "original")} population.{" "}
                    </>
                  )}
                  Expected calibration error: {pct(selectedCal.ece_before)}{" "}
                  before, {pct(selectedCal.ece_after)} after. Each bin compares
                  reported confidence with observed correctness. Interval bars
                  account for repeated variants of the same parent page.
                  Parent-page clustering does not remove dependence from
                  duplicate content or shared templates.
                </p>
              </div>
            </>
          ) : (
            <Unavailable />
          )}
        </section>
      </div>
      <section className="panel section-panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">04 / BEYOND SINGLE FIELDS</span>
            <h2>Rows and whole documents matter</h2>
          </div>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>SOURCE / BACKEND</th>
                <th>OCR ENGINE</th>
                <th>EXACT MATCH</th>
                <th>LINE ITEM F1</th>
                <th>DOCUMENT SUCCESS</th>
                <th>n</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => (
                <tr key={i}>
                  <td>
                    <strong>{label(r.backend)}</strong>
                    <small>{label(r.source)}</small>
                  </td>
                  <td>{r.ocr_engine}</td>
                  <td>{metric(r.exact_match)}</td>
                  <td>{metric(r.line_item_f1)}</td>
                  <td>{metric(r.document_success)}</td>
                  <td>{r.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <div className="two-columns">
        <section className="panel section-panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">05 / CLASSIFICATION</span>
              <h2>What kind of document is this?</h2>
            </div>
          </div>
          {classification?.labels ? (
            <>
              <div className="table-scroll">
                <table className="data-table confusion-table">
                  <caption>
                    Actual class in rows; predicted class in columns. n=
                    {classification.n}
                  </caption>
                  <thead>
                    <tr>
                      <th>ACTUAL / PREDICTED</th>
                      {classification.labels.map((l) => (
                        <th key={l}>{label(l)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {classification.confusion_matrix.map((row, i) => (
                      <tr key={i}>
                        <th>{label(classification.labels[i])}</th>
                        {row.map((value, j) => (
                          <td key={j} className={i === j ? "diagonal" : ""}>
                            {value}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <Unavailable />
          )}
        </section>
        <section className="panel section-panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">06 / CORRECTION LOOP</span>
              <h2>Did review help the model?</h2>
            </div>
          </div>
          {retrain ? <RetrainEvidence run={retrain} /> : <Unavailable />}
        </section>
      </div>
      <Pushback />
    </>
  );
}

function ChartToggle({
  table,
  onChange,
}: {
  table: boolean;
  onChange: () => void;
}) {
  return (
    <button className="chart-toggle button small-button" onClick={onChange}>
      {table ? <BarChart3 size={13} /> : <Table2 size={13} />}Show{" "}
      {table ? "chart" : "table"}
    </button>
  );
}
function CurveChart({
  points,
  chosen,
}: {
  points: RatePoint[];
  chosen: number;
}) {
  const [table, setTable] = useState(false);
  const valid = points.filter((p) => typeof p.error_rate === "number");
  const yMax = Math.max(0.05, ...valid.map((p) => p.error_rate || 0));
  const sorted = [...valid].sort((a, b) => a.review_rate - b.review_rate);
  return (
    <div className="chart-block">
      <ChartToggle table={table} onChange={() => setTable(!table)} />
      {table ? (
        <div className="table-scroll">
          <table className="data-table compact">
            <thead>
              <tr>
                <th>THRESHOLD</th>
                <th>REVIEW RATE</th>
                <th>ERROR RATE</th>
                <th>COST</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p, i) => (
                <tr key={i}>
                  <td>
                    {p.threshold > 1 ? "Review all" : pct(p.threshold)}
                    {p.threshold === chosen ? " · chosen" : ""}
                  </td>
                  <td>{pct(p.review_rate)}</td>
                  <td>
                    {p.error_rate == null ? "Not measured" : pct(p.error_rate)}
                  </td>
                  <td>{p.cost.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <svg
          className="chart-svg"
          viewBox="0 0 480 285"
          role="img"
          aria-label="Review rate against auto-approved error rate"
        >
          <defs>
            <pattern
              id="chart-dots"
              width="8"
              height="8"
              patternUnits="userSpaceOnUse"
            >
              <circle cx="1" cy="1" r=".6" fill="currentColor" opacity=".15" />
            </pattern>
          </defs>
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <g key={t}>
              <line
                className="grid-line"
                x1="56"
                x2="452"
                y1={225 - 180 * t}
                y2={225 - 180 * t}
              />
              <text x="46" y={229 - 180 * t} textAnchor="end">
                {pct(t * yMax)}
              </text>
              <text x={56 + 396 * t} y="247" textAnchor="middle">
                {Math.round(t * 100)}%
              </text>
            </g>
          ))}
          <text className="axis-title" x="250" y="275" textAnchor="middle">
            Documents sent for human review
          </text>
          <text className="axis-title" x="56" y="20">
            Error among auto-approved documents
          </text>
          <path
            className="curve-line"
            d={sorted
              .map(
                (p, i) =>
                  `${i ? "L" : "M"}${56 + 396 * p.review_rate},${225 - (180 * (p.error_rate || 0)) / yMax}`,
              )
              .join(" ")}
          />
          {sorted.map((p, i) => (
            <circle
              key={i}
              tabIndex={0}
              className={`curve-dot ${p.threshold === chosen ? "chosen" : ""}`}
              cx={56 + 396 * p.review_rate}
              cy={225 - (180 * (p.error_rate || 0)) / yMax}
              r={p.threshold === chosen ? 7 : 4}
            >
              <title>{`Threshold ${pct(p.threshold)}: ${pct(p.review_rate)} reviewed; ${pct(p.error_rate || 0)} error; cost ${p.cost.toFixed(2)}${p.threshold === chosen ? "; chosen operating point" : ""}`}</title>
            </circle>
          ))}
        </svg>
      )}
      <div className="chart-legend">
        <span>
          <i className="legend-line" />
          Threshold sweep
        </span>
        <span>
          <i className="legend-dot" />
          Chosen operating point
        </span>
      </div>
    </div>
  );
}
function CalibrationChart({ cal }: { cal: Cal }) {
  const [table, setTable] = useState(false);
  const bins = cal.bins
    .filter((b) => b.count > 0)
    .sort((a, b) => a.confidence - b.confidence);
  const maxCount = Math.max(1, ...bins.map((b) => b.count));
  return (
    <div className="chart-block">
      <ChartToggle table={table} onChange={() => setTable(!table)} />
      {table ? (
        <table className="data-table compact">
          <thead>
            <tr>
              <th>CONFIDENCE</th>
              <th>OBSERVED CORRECT</th>
              <th>FIELDS</th>
            </tr>
          </thead>
          <tbody>
            {bins.map((b, i) => (
              <tr key={i}>
                <td>{pct(b.confidence)}</td>
                <td>
                  {pct(b.accuracy)}
                  {b.ci && (
                    <small className="metric-interval">
                      95% CI {pct(b.ci[0])} to {pct(b.ci[1])}
                    </small>
                  )}
                  {b.interval_method && (
                    <small className="metric-interval">
                      {b.interval_method}
                    </small>
                  )}
                </td>
                <td>{b.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <svg
          className="chart-svg"
          viewBox="0 0 480 285"
          role="img"
          aria-label="Confidence reliability curve and bin counts"
        >
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <g key={t}>
              <line
                className="grid-line"
                x1="50"
                x2="450"
                y1={205 - 170 * t}
                y2={205 - 170 * t}
              />
              <text x="42" y={209 - 170 * t} textAnchor="end">
                {Math.round(t * 100)}%
              </text>
              <text x={50 + 400 * t} y="271" textAnchor="middle">
                {Math.round(t * 100)}%
              </text>
            </g>
          ))}
          <line x1="50" y1="205" x2="450" y2="35" className="ideal-line" />
          <path
            className="curve-line"
            d={bins
              .map(
                (b, i) =>
                  `${i ? "L" : "M"}${50 + b.confidence * 400},${205 - b.accuracy * 170}`,
              )
              .join(" ")}
          />
          {bins.map((b, i) => (
            <g key={i}>
              {b.ci && (
                <line
                  className="calibration-interval"
                  x1={50 + b.confidence * 400}
                  x2={50 + b.confidence * 400}
                  y1={205 - b.ci[0] * 170}
                  y2={205 - b.ci[1] * 170}
                />
              )}
              <circle
                className="curve-dot"
                tabIndex={0}
                cx={50 + b.confidence * 400}
                cy={205 - b.accuracy * 170}
                r="5"
              >
                <title>{`Of 100 fields in the ${pct(b.confidence)} confidence band, about ${Math.round(b.accuracy * 100)} were correct (n=${b.count} field observations).${b.ci ? ` 95% interval ${pct(b.ci[0])} to ${pct(b.ci[1])}.` : ""}`}</title>
              </circle>
              <rect
                className="hist-bar"
                x={42 + b.confidence * 400}
                y={251 - (b.count / maxCount) * 32}
                width="16"
                height={(b.count / maxCount) * 32}
              >
                <title>{`${b.count} fields in this bin`}</title>
              </rect>
            </g>
          ))}
          <text className="axis-title" x="50" y="19">
            Observed correctness
          </text>
        </svg>
      )}
      <div className="chart-legend">
        <span>
          <i className="legend-line" />
          Observed outcomes
        </span>
        <span>
          <i className="legend-line dashed" />
          Perfect calibration
        </span>
        <span>
          <i className="legend-bar" />
          Bin count
        </span>
      </div>
    </div>
  );
}

export function Rules({
  documents,
  evaluation,
}: {
  documents: DocumentItem[];
  evaluation: Manifest;
}) {
  const definitions = Array.from(
    new Map(documents.flatMap((d) => d.rules).map((r) => [r.id, r])).values(),
  );
  const [status, setStatus] = useState("all");
  const filtered = definitions.filter(
    (rule) =>
      status === "all" ||
      documents.some((d) =>
        d.rules.some((r) => r.id === rule.id && r.status === status),
      ),
  );
  return (
    <>
      <PageHeading
        eyebrow="VALIDATION / BUSINESS POLICY"
        title="Good numbers still need good checks"
        description="Arithmetic, identity, and purchasing policy are part of the decision."
      />
      <div className="policy-banner">
        <ShieldCheck size={24} />
        <div>
          <strong>Every required check must pass before auto-approval.</strong>
          <p>
            A high-confidence field cannot override a failed rule. The counts
            below are computed from the recorded queue. Detection quality is
            measured separately against known defects.
          </p>
        </div>
      </div>
      <RuleBenchmark rows={(evaluation.rules || []) as RuleScore[]} />
      <section className="panel section-panel">
        <div className="section-heading">
          <div>
            <h2>Current queue outcomes</h2>
            <p>
              {documents.length} demonstration documents in the current queue
            </p>
          </div>
          <select
            className="plain-select"
            aria-label="Filter rules"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">All rules</option>
            <option value="fail">Rules with failures</option>
            <option value="pass">Rules with passes</option>
          </select>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>RULE</th>
                <th>PASSED</th>
                <th>FLAGGED</th>
                <th>NOT APPLICABLE</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((rule) => {
                const outcomes = documents.flatMap((d) =>
                  d.rules.filter((r) => r.id === rule.id),
                );
                return (
                  <tr key={rule.id}>
                    <td>
                      <strong>{rule.name}</strong>
                      <small className="mono">{rule.id}</small>
                    </td>
                    <td>
                      <span className="rule-pass">
                        <Check size={13} />
                        {outcomes.filter((r) => r.status === "pass").length}
                      </span>
                    </td>
                    <td>
                      <span className="rule-pill">
                        {outcomes.filter((r) => r.status === "fail").length}
                      </span>
                    </td>
                    <td>
                      {
                        outcomes.filter((r) => r.status === "not_applicable")
                          .length
                      }
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <div className="rule-cards">
        {definitions.map((rule) => (
          <section className="panel rule-card" key={rule.id}>
            <ShieldCheck size={20} />
            <h3>{rule.name}</h3>
            <p>{rule.message}</p>
            <details>
              <summary>
                Inspect queue examples <ChevronRight size={14} />
              </summary>
              {documents
                .filter((d) => d.rules.some((r) => r.id === rule.id))
                .slice(0, 4)
                .map((d) => {
                  const result = d.rules.find((r) => r.id === rule.id)!;
                  return (
                    <Link
                      key={d.id}
                      className="rule-example"
                      href={`/review/?id=${encodeURIComponent(d.id)}`}
                    >
                      <span className="mono">{d.number}</span>
                      <Status status={result.status} />
                    </Link>
                  );
                })}
            </details>
          </section>
        ))}
      </div>
      <p className="data-caption">
        Recorded rule evaluation is available in the{" "}
        <button
          className="text-button"
          onClick={() =>
            download("docket-rule-scorecard.json", evaluation.rules || [])
          }
        >
          manifest download
        </button>
        . A correction in local practice does not rerun checks.
      </p>
    </>
  );
}

export function Models({ evaluation }: { evaluation: Manifest }) {
  const rows = (evaluation.extraction || []) as EvalRow[];
  const backends = Array.from(new Set(rows.map((r) => r.backend)));
  const descriptions: Record<string, string> = {
    rules:
      "Deterministic extraction using token text, layout, labels, and business document structure. Every value can expose a reproducible trace.",
    tokens:
      "A CPU token classifier learns the relationship between text shape, position, context, and field labels. Evaluated on the same committed splits.",
    vision:
      "Optional structured multimodal extraction. Availability and measured results depend on a configured provider.",
  };
  return (
    <>
      <PageHeading
        eyebrow="MODEL REGISTRY / TRANSPARENT BASELINES"
        title="Small models, visible evidence"
        description="Compare extractors against the same labels, with the reading stage kept separate."
      />
      <div className="model-grid">
        {backends.map((backend, index) => (
          <section className="panel model-card" key={backend}>
            <div className="model-top">
              <span className="model-number">0{index + 1}</span>
              <span className="backend-label">Recorded benchmark</span>
            </div>
            <h2>{label(backend)} extractor</h2>
            <p>
              {descriptions[backend] ||
                "Recorded extraction backend evaluated against labeled documents."}
            </p>
            <div className="model-facts">
              <div>
                <span>Interface</span>
                <code>extract(document)</code>
              </div>
              <div>
                <span>Evaluation rows</span>
                <strong>
                  {rows.filter((r) => r.backend === backend).length}
                </strong>
              </div>
              <div>
                <span>Production promotion</span>
                <strong>Not asserted</strong>
              </div>
            </div>
            <Link className="button full-width" href="/evaluation/">
              Inspect measured results <ArrowRight size={14} />
            </Link>
            {["rules", "tokens"].includes(backend) && (
              <a
                className="model-card-link"
                href={`https://github.com/mekala27-45/docket/blob/main/docs/model-cards/${backend}.md`}
                target="_blank"
                rel="noreferrer"
              >
                Read the model card <ArrowRight size={14} />
              </a>
            )}
          </section>
        ))}
      </div>
      <section className="panel section-panel">
        <div className="section-heading">
          <div>
            <h2>The deployment contract</h2>
            <p>A benchmark result alone does not approve a production model.</p>
          </div>
        </div>
        <div className="registry-checks">
          {[
            "Field quality is compared against known labels, not an LLM judge.",
            "The real OCR column includes recognition errors.",
            "A decision combines calibrated confidence and business rules.",
            "Production latency, data drift, and tenant-specific accuracy require separate checks.",
          ].map((text) => (
            <div key={text}>
              <ShieldCheck size={17} />
              <p>{text}</p>
            </div>
          ))}
        </div>
      </section>
      <Pushback />
    </>
  );
}

export function Lab({
  documents,
  evaluation,
}: {
  documents: DocumentItem[];
  evaluation: Manifest;
}) {
  const sweeps = (evaluation.degradation || []) as Degradation[];
  const floors = (evaluation.degradation_floors || []) as SweepFloor[];
  const policy = evaluation.degradation_policy as
    | {
        field_f1_floor?: number;
        parameters?: Record<string, DegradationParameter>;
      }
    | undefined;
  const floor = policy?.field_f1_floor ?? floors[0]?.floor;
  const recordedIds = new Set(
    sweeps.filter((s) => s.image && s.document_id).map((s) => s.document_id),
  );
  const allGenerated = documents.filter((d) => !d.source?.includes("cord"));
  const generated = allGenerated.filter((d) => recordedIds.has(d.id));
  const exampleDocuments = generated.length ? generated : allGenerated;
  const kinds = Array.from(new Set(sweeps.map((s) => s.kind)));
  const [docId, setDocId] = useState(sweeps[0]?.document_id || "");
  const [kind, setKind] = useState(kinds[0] || "blur");
  const [level, setLevel] = useState(0);
  const [table, setTable] = useState(false);
  const doc =
    exampleDocuments.find((d) => d.id === docId) || exampleDocuments[0];
  const data = sweeps.filter((s) => s.kind === kind);
  const levels = orderedLevels(data);
  const actualLevel = levels.includes(level) ? level : levels[0] || 0;
  const current = data.filter((d) => d.level === actualLevel);
  const example = current.find(
    (d) => d.image && (!d.document_id || d.document_id === doc?.id),
  );
  return (
    <>
      <PageHeading
        eyebrow="ROBUSTNESS / KNOWN-TRUTH DOCUMENTS"
        title="Put the page under pressure"
        description="Inspect how scan quality changes extraction against known fields."
      />
      <DegradationOverview
        rows={sweeps}
        floor={floor}
        floors={floors}
        parameters={policy?.parameters}
        active={kind}
        onSelect={(selected, selectedLevel) => {
          setKind(selected);
          setLevel(selectedLevel);
        }}
      />
      <div className="lab-controls panel">
        <label className="form-label">
          Document
          <select
            value={doc?.id || ""}
            onChange={(e) => setDocId(e.target.value)}
          >
            {exampleDocuments.map((d) => (
              <option value={d.id} key={d.id}>
                {d.number} · {d.vendor}
              </option>
            ))}
          </select>
        </label>
        <label className="form-label">
          Degradation
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setLevel(0);
            }}
          >
            {(kinds.length ? kinds : ["blur"]).map((k) => (
              <option key={k} value={k}>
                {label(k)}
              </option>
            ))}
          </select>
        </label>
        <label className="form-label">
          Recorded level
          <select
            value={actualLevel}
            onChange={(e) => setLevel(Number(e.target.value))}
          >
            {(levels.length ? levels : [0]).map((l) => (
              <option value={l} key={l}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <span className="recorded-label">
          <span className="live-dot" />
          Precomputed sweep
        </span>
      </div>
      <div className="two-columns lab-columns">
        <section className="panel lab-preview">
          <div className="section-heading">
            <h2>
              {example
                ? "Recorded degraded image"
                : "Original document reference"}
            </h2>
            <span className="backend-label">
              {label(kind)} {actualLevel}
            </span>
          </div>
          <div className="lab-paper">
            {doc?.image && (
              <img
                src={asset(example?.image || doc.image)}
                alt={`${label(kind)} document preview`}
              />
            )}
          </div>
          <p className="section-caption">
            {example
              ? "Image saved by the recorded degradation run."
              : "No saved degraded example is available for this selection. This is the original document; the chart still reports the measured population."}
          </p>
        </section>
        <section className="panel section-panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">RECORDED RESULTS</span>
              <h2>{label(kind)} tolerance</h2>
            </div>
            <ChartToggle table={table} onChange={() => setTable(!table)} />
          </div>
          {data.length ? (
            <>
              {table ? (
                <table className="data-table compact">
                  <thead>
                    <tr>
                      <th>LEVEL</th>
                      <th>BACKEND</th>
                      <th>FIELD F1</th>
                      <th>n</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.map((d, i) => (
                      <tr key={i}>
                        <td>{d.level}</td>
                        <td>{d.backend}</td>
                        <td>
                          {typeof d.field_f1 === "object"
                            ? metric(d.field_f1)
                            : pct(d.field_f1)}
                        </td>
                        <td>{d.n}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <DegradationChart
                  rows={data}
                  current={actualLevel}
                  kind={kind}
                  floor={floor}
                  onSelect={setLevel}
                />
              )}
              <div className="sweep-level-results">
                {current.map((d, i) => (
                  <div key={i}>
                    <span>{label(d.backend)}</span>
                    {typeof d.field_f1 === "object" ? (
                      metric(d.field_f1)
                    ) : (
                      <strong>{pct(d.field_f1)}</strong>
                    )}
                    <small>Field F1 · n={d.n}</small>
                  </div>
                ))}
              </div>
              <p className="section-caption">
                Each level aggregates the measured generated documents, not just
                the selected example. Intervals reflect this aggregate
                population. Degradation units are those recorded by the
                pipeline; field F1 is measured after OCR.
              </p>
            </>
          ) : (
            <Unavailable />
          )}
          <div className="lab-known">
            <h3>Current extracted fields</h3>
            {doc &&
              Object.entries(doc.extraction.fields)
                .slice(0, 7)
                .map(([name]) => (
                  <div key={name}>
                    <span>{label(name)}</span>
                    <strong>{asText(doc[name as keyof DocumentItem])}</strong>
                  </div>
                ))}
          </div>
        </section>
      </div>
    </>
  );
}

export function Explore({ documents }: { documents: DocumentItem[] }) {
  const initial =
    "SELECT currency, type, status, COUNT(*) AS documents,\n       ROUND(SUM(total), 2) AS total_amount\nFROM documents\nGROUP BY currency, type, status\nORDER BY documents DESC;";
  const [query, setQuery] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState<
    { columns: string[]; values: unknown[][] }[]
  >([]);
  const [db, setDb] = useState<import("sql.js").Database | null>(null);
  useEffect(() => {
    let active = true;
    let database: import("sql.js").Database | undefined;
    import("sql.js")
      .then((m) => m.default({ locateFile: () => `${BASE}/sql-wasm.wasm` }))
      .then((SQL) => {
        database = new SQL.Database();
        database.run(
          "CREATE TABLE documents (id TEXT, number TEXT, vendor TEXT, type TEXT, source TEXT, split TEXT, currency TEXT, total REAL, status TEXT, risk REAL, confidence REAL, rules_failed INTEGER)",
        );
        const statement = database.prepare(
          "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        );
        documents.forEach((d) =>
          statement.run([
            d.id,
            d.number,
            d.vendor,
            d.type,
            d.source,
            d.split,
            d.currency,
            d.extraction.fields.total?.value == null ? null : d.total,
            d.status,
            priorityAmount(d),
            displayedConfidence(d),
            d.rules.filter((r) => r.status === "fail").length,
          ]),
        );
        statement.free();
        if (active) {
          setDb(database);
          setResults(database.exec(initial));
        }
      })
      .catch((e) =>
        setError(
          e instanceof Error
            ? e.message
            : "Could not initialize the query engine.",
        ),
      );
    return () => {
      active = false;
      database?.close();
    };
  }, [documents]);
  const run = () => {
    if (!db) return;
    setBusy(true);
    setError("");
    try {
      if (
        !/^\s*(select|with)\b/i.test(query) ||
        /\b(insert|update|delete|drop|alter|create|attach|pragma)\b/i.test(
          query,
        )
      )
        throw new Error("Use a read-only SELECT query in this explorer.");
      setResults(db.exec(query));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Query failed.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageHeading
        eyebrow="EXPLORE / SQL IN YOUR BROWSER"
        title="Ask your own questions"
        description="Query the recorded queue locally. No server, credentials, or document upload."
      />
      <div className="explore-layout">
        <section className="panel sql-panel">
          <div className="section-heading">
            <div>
              <Code2 size={18} />
              <h2>Query editor</h2>
            </div>
            <span className="backend-label">SQLite · WebAssembly</span>
          </div>
          <label className="sr-only" htmlFor="sql-query">
            SQL query
          </label>
          <textarea
            id="sql-query"
            spellCheck={false}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                e.preventDefault();
                run();
              }
            }}
          />
          <div className="sql-actions">
            <span>Read-only queries · Ctrl + Enter to run</span>
            <button
              className="button primary"
              disabled={!db || busy}
              onClick={run}
            >
              <Play size={14} />
              Run query
            </button>
          </div>
        </section>
        <aside className="panel schema-panel">
          <span className="eyebrow">AVAILABLE TABLE</span>
          <h3>
            documents <span>{documents.length} rows</span>
          </h3>
          {[
            "id · text",
            "number · text",
            "vendor · text",
            "type · text",
            "source · text",
            "split · text",
            "currency · text",
            "total · real",
            "status · text",
            "risk · real",
            "confidence · real",
            "rules_failed · integer",
          ].map((f) => (
            <div className="schema-field" key={f}>
              {f}
            </div>
          ))}
        </aside>
      </div>
      {error && (
        <p className="form-error query-error" role="alert">
          {error}
        </p>
      )}
      <section className="panel section-panel">
        <div className="section-heading">
          <h2>Query results</h2>
          <button
            className="button small-button"
            onClick={() => download("docket-query-results.json", results)}
            disabled={!results.length}
          >
            <Download size={14} />
            Export JSON
          </button>
        </div>
        {results.map((result, i) => (
          <div className="table-scroll" key={i}>
            <table className="data-table">
              <thead>
                <tr>
                  {result.columns.map((c) => (
                    <th key={c}>{label(c)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.values.slice(0, 500).map((row, j) => (
                  <tr key={j}>
                    {row.map((v, k) => (
                      <td
                        key={k}
                        className={typeof v === "number" ? "mono" : ""}
                      >
                        {asText(v)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="section-caption">
              {result.values.length} rows returned
              {result.values.length > 500 ? "; showing the first 500" : ""}.
            </p>
          </div>
        ))}
        {!results.length && !error && (
          <p className="section-caption">
            {db
              ? "This query returned no rows."
              : "Loading the local query engine..."}
          </p>
        )}
      </section>
    </>
  );
}

export function Report({
  evaluation,
  documents,
}: {
  evaluation: Manifest;
  documents: DocumentItem[];
}) {
  const op = evaluation.operating_point as Operating | undefined;
  const scope = evaluation.scope as { limitations?: string[] } | undefined;
  const rows = (evaluation.extraction || []) as EvalRow[];
  return (
    <>
      <PageHeading
        eyebrow="EVALUATION REPORT / RECORDED RUN"
        title="A decision, with the evidence attached"
        description="A reproducible account of what this document pipeline can and cannot establish."
      >
        <button className="button" onClick={() => window.print()}>
          <Printer size={16} />
          Print report
        </button>
        <button
          className="button primary"
          onClick={() => download("docket-manifest.json", evaluation)}
        >
          <Download size={16} />
          Download manifest
        </button>
      </PageHeading>
      <article className="report-sheet">
        <div className="report-kicker">DOCKET / DOCUMENT INTELLIGENCE</div>
        <h2>
          How much can we approve,
          <br />
          and how often will we be wrong?
        </h2>
        <p className="report-lead">
          The useful unit is a business decision. This evaluation separates
          recognizing the words from extracting the fields, then applies
          confidence and business policy to decide which documents need human
          review.
        </p>
        {op && (
          <div className="report-metrics">
            <div>
              <span>Test review rate</span>
              {metric(op.review_rate)}
            </div>
            <div>
              <span>Error among auto-approvals</span>
              {metric(op.auto_approval_error)}
            </div>
          </div>
        )}
        <h3>Population and method</h3>
        <p>
          The displayed queue contains {documents.length} recorded demonstration
          documents. Extraction metrics below identify the source, engine, test
          population, and uncertainty. Gold OCR measures extraction with reading
          errors removed; real OCR retains those errors.
        </p>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>SOURCE</th>
                <th>BACKEND / OCR</th>
                <th>FIELD F1</th>
                <th>n</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td>{label(r.source)}</td>
                  <td>
                    {r.backend} / {r.ocr_engine}
                  </td>
                  <td>{metric(r.field_f1)}</td>
                  <td>{r.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h3>The operating policy</h3>
        <p>
          {op
            ? `A confidence threshold of ${pct(op.threshold)} was selected on ${op.chosen_on} with review cost ${op.review_cost} and wrong approval cost ${op.error_cost}. The reported ${op.reported_on} population has n=${op.n}.`
            : "No operating point was supplied in this recorded manifest."}{" "}
          Every required business rule must also pass. A threshold alone cannot
          repair an inconsistent invoice.
        </p>
        <h3>Limitations that affect the decision</h3>
        {scope?.limitations?.length ? (
          <ul>
            {scope.limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        ) : (
          <p>
            Generated invoices cover a small family of layouts. Public CORD
            receipts are not representative of every AP queue. These results are
            a baseline for further evaluation, not a production guarantee.
          </p>
        )}
        <h3>Human review and privacy</h3>
        <p>
          Corrections in this public workbench are explicitly browser-local
          practice. They do not change the published benchmark or retrain a
          server model. Uploads require an API selected by the user. The
          recorded queue uses generated invoices and licensed public receipt
          data.
        </p>
        <div className="report-end">
          <ShieldCheck size={18} />
          <span>Demonstration documents only. No customer transactions.</span>
        </div>
      </article>
      <Pushback />
    </>
  );
}
function Unavailable() {
  return (
    <div className="unavailable">
      <Info size={20} />
      <p>
        This observation is not available in the committed evaluation manifest.
      </p>
    </div>
  );
}
