"use client";

import { useState } from "react";
import { BarChart3, Table2 } from "lucide-react";
import { label, pct } from "@/lib/types";

export interface Measurement {
  value: number | null;
  ci?: (number | null)[];
  n?: number;
  reason?: string;
  method?: string;
}
export interface SweepRow {
  kind: string;
  level: number;
  level_index?: number;
  backend: string;
  n: number;
  field_f1: number | Measurement;
  cer?: number | Measurement;
  document_success?: Measurement;
  image?: string;
  document_id?: string;
}
export interface DegradationParameter {
  levels?: number[];
  unit?: string;
  severe_direction?: string;
}
export interface SweepFloor {
  kind: string;
  backend: string;
  floor: number;
  first_below: number | null;
  reason?: string | null;
}
export function orderedLevels(rows: SweepRow[]) {
  const levels = [...new Set(rows.map((r) => r.level))];
  return levels.sort((a, b) => {
    const ai = rows.find((r) => r.level === a)?.level_index,
      bi = rows.find((r) => r.level === b)?.level_index;
    if (typeof ai === "number" && typeof bi === "number") return ai - bi;
    return ["jpeg", "downscale"].includes(rows[0]?.kind) ? b - a : a - b;
  });
}
export interface RuleScore {
  id: string;
  name: string;
  n: number;
  source: string;
  split: string;
  precision: Measurement;
  recall: Measurement;
  fired: number;
  expected: number;
  tp?: number;
  fp?: number;
  fn?: number;
  tn?: number;
  definition?: string;
}

export interface RoutingPopulation {
  source: string;
  n: number;
  auto_approved: number;
  review_rate: Measurement;
  auto_approval_error: Measurement;
  unlabeled_documents?: number;
}

export function RoutingBreakdown({ rows }: { rows: RoutingPopulation[] }) {
  if (!rows.length) return null;
  return (
    <div className="routing-breakdown">
      <h3>Approval by population</h3>
      <p>
        Aggregate routing can hide which documents are actually approved. Empty
        approved sets have no measured error rate.
      </p>
      <div className="table-scroll">
        <table className="data-table compact">
          <thead>
            <tr>
              <th>TEST POPULATION</th>
              <th>n</th>
              <th>APPROVED</th>
              <th>UNLABELED</th>
              <th>REVIEW RATE</th>
              <th>APPROVAL ERROR</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.source}>
                <td>{label(row.source)}</td>
                <td>{row.n}</td>
                <td>{row.auto_approved}</td>
                <td>{row.unlabeled_documents ?? "Not supplied"}</td>
                <td>
                  <ObservedMetric measurement={row.review_rate} />
                </td>
                <td>
                  <ObservedMetric
                    measurement={row.auto_approval_error}
                    denominator
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface RetrainSlice {
  source: string;
  ocr_engine: string;
  split: string;
  n_test: number;
  before: Measurement;
  after: Measurement;
}
export interface RetrainRun {
  before?: Measurement;
  after?: Measurement;
  n_test?: number;
  corrections_used?: number;
  human_corrections_used?: number;
  simulated_corrections_used?: number;
  corrections_without_trainable_spans?: number;
  correction_source?: string;
  cord_test?: RetrainSlice;
  by_source?: RetrainSlice[];
}
export function RetrainEvidence({ run }: { run: RetrainRun }) {
  const focused = run.cord_test;
  return (
    <>
      <p className="retrain-population">
        {focused
          ? `CORD test · ${focused.ocr_engine} · n=${focused.n_test}`
          : `Mixed recorded test population${run.n_test != null ? ` · n=${run.n_test}` : ""}`}{" "}
        · field F1
      </p>
      <div className="retrain-flow">
        <div>
          <span>Before retraining</span>
          <ObservedMetric measurement={focused?.before || run.before} />
        </div>
        <span aria-hidden="true">→</span>
        <div>
          <span>After retraining</span>
          <ObservedMetric measurement={focused?.after || run.after} />
        </div>
      </div>
      <div className="retrain-provenance">
        {typeof run.human_corrections_used === "number" && (
          <div>
            <span>Client-declared human corrections</span>
            <strong>{run.human_corrections_used}</strong>
          </div>
        )}
        {typeof run.simulated_corrections_used === "number" && (
          <div>
            <span>Simulated corrections used</span>
            <strong>{run.simulated_corrections_used}</strong>
          </div>
        )}
        {typeof run.corrections_without_trainable_spans === "number" && (
          <div>
            <span>Excluded without trainable spans</span>
            <strong>{run.corrections_without_trainable_spans}</strong>
          </div>
        )}
      </div>
      <p className="section-caption">
        {run.correction_source ||
          "The browser practice queue is separate from this recorded experiment."}
        {run.human_corrections_used === 0
          ? " This run does not measure learning from human corrections."
          : ""}
      </p>
      {Boolean(run.by_source?.length) && (
        <details className="retrain-details">
          <summary>Compare source and OCR slices</summary>
          <div className="table-scroll">
            <table className="data-table compact">
              <thead>
                <tr>
                  <th>SOURCE / OCR</th>
                  <th>BEFORE F1</th>
                  <th>AFTER F1</th>
                  <th>n</th>
                </tr>
              </thead>
              <tbody>
                {run.by_source?.map((row) => (
                  <tr key={`${row.source}:${row.ocr_engine}`}>
                    <td>
                      {label(row.source)}
                      <small>
                        {row.ocr_engine} · {row.split}
                      </small>
                    </td>
                    <td>
                      <ObservedMetric measurement={row.before} />
                    </td>
                    <td>
                      <ObservedMetric measurement={row.after} />
                    </td>
                    <td>{row.n_test}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </>
  );
}

export function observedValue(value: number | Measurement | undefined) {
  return typeof value === "number" ? value : (value?.value ?? null);
}
export function ObservedMetric({
  measurement,
  denominator = false,
}: {
  measurement?: Measurement;
  denominator?: boolean;
}) {
  if (!measurement || measurement.value == null) {
    return (
      <span className="unmeasured-metric">
        <strong>Not measured</strong>
        <small>{measurement?.reason || "No eligible observations"}</small>
        {denominator && typeof measurement?.n === "number" && (
          <small>denominator n={measurement.n}</small>
        )}
      </span>
    );
  }
  const ci = measurement.ci;
  return (
    <span
      className="observed-metric"
      title={`${measurement.method || "Recorded estimate"}; evaluable denominator n=${measurement.n ?? "not supplied"}`}
    >
      <strong>{pct(measurement.value)}</strong>
      {ci?.length === 2 && ci.every((v) => typeof v === "number") && (
        <small>
          95% CI {pct(ci[0] as number)} to {pct(ci[1] as number)}
        </small>
      )}
      {denominator && typeof measurement.n === "number" && (
        <small>denominator n={measurement.n}</small>
      )}
    </span>
  );
}

export function RuleBenchmark({ rows }: { rows: RuleScore[] }) {
  return (
    <section
      className="panel section-panel"
      aria-label="Rule detection benchmark"
    >
      <div className="section-heading">
        <div>
          <span className="eyebrow">KNOWN DEFECTS / HELD-OUT SCORECARD</span>
          <h2>Did the rules catch the right defects?</h2>
          <p>
            Each prediction is scored against independently recorded expected
            rule outcomes. Queue counts below are a separate operational view.
          </p>
        </div>
      </div>
      <div className="table-scroll">
        <table className="data-table rule-benchmark-table">
          <thead>
            <tr>
              <th>RULE / POPULATION</th>
              <th>PRECISION</th>
              <th>RECALL</th>
              <th>FLAGGED / EXPECTED</th>
              <th>TP / FP / FN / TN</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.id}-${row.source}-${row.split}`}>
                <td>
                  <strong>{row.name}</strong>
                  <small>
                    {label(row.source)} · {row.split} · n={row.n}
                  </small>
                </td>
                <td>
                  <ObservedMetric measurement={row.precision} denominator />
                </td>
                <td>
                  <ObservedMetric measurement={row.recall} denominator />
                </td>
                <td>
                  <strong>
                    {row.fired} / {row.expected}
                  </strong>
                  <small>flagged / labeled positive</small>
                </td>
                <td>
                  {[row.tp, row.fp, row.fn, row.tn].every(
                    (v) => typeof v === "number",
                  ) ? (
                    <>
                      <strong>
                        {row.tp} / {row.fp} / {row.fn} / {row.tn}
                      </strong>
                      <small>
                        true / false positives, false / true negatives
                      </small>
                    </>
                  ) : (
                    <span className="muted">Counts not supplied</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="section-caption">
        Precision uses correctly flagged defects / all flagged documents. Recall
        uses correctly flagged defects / all labeled defects. A zero denominator
        is unmeasured, not perfect performance. Confidence intervals and
        denominators come from the recorded evaluation.
      </p>
    </section>
  );
}

function SummaryTable({ rows }: { rows: SweepRow[] }) {
  return (
    <div className="table-scroll">
      <table className="data-table compact sweep-data-table">
        <thead>
          <tr>
            <th>LEVEL</th>
            <th>BACKEND</th>
            <th>FIELD F1</th>
            <th>n</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.backend}:${row.level}`}>
              <td>{row.level}</td>
              <td>{label(row.backend)}</td>
              <td>
                {typeof row.field_f1 === "number" ? (
                  pct(row.field_f1)
                ) : (
                  <ObservedMetric measurement={row.field_f1} />
                )}
              </td>
              <td>{row.n}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DegradationChart({
  rows,
  floor,
  current,
  onSelect,
  kind,
  compact = false,
}: {
  rows: SweepRow[];
  floor?: number;
  current?: number;
  onSelect?: (level: number) => void;
  kind: string;
  compact?: boolean;
}) {
  const levels = orderedLevels(rows);
  const backends = [...new Set(rows.map((r) => r.backend))].sort();
  const x = (level: number) =>
    44 + (levels.indexOf(level) / Math.max(1, levels.length - 1)) * 286;
  const y = (value: number) => 186 - value * 148;
  return (
    <svg
      className={`chart-svg degradation-svg ${compact ? "compact-sweep" : ""}`}
      viewBox="0 0 360 240"
      role={onSelect ? "group" : "img"}
      aria-label={`${label(kind)} field F1 across recorded degradation levels`}
    >
      {[0, 0.25, 0.5, 0.75, 1].map((t) => (
        <g key={t}>
          <line className="grid-line" x1="44" x2="330" y1={y(t)} y2={y(t)} />
          <text x="36" y={y(t) + 4} textAnchor="end">
            {Math.round(t * 100)}%
          </text>
        </g>
      ))}
      {levels.map((l) => (
        <text key={l} x={x(l)} y="205" textAnchor="middle">
          {l}
        </text>
      ))}
      <text x="44" y="18" className="axis-title">
        Field F1
      </text>
      <text x="187" y="230" textAnchor="middle" className="axis-title">
        Recorded severity level
      </text>
      {typeof floor === "number" && (
        <g className="sweep-floor">
          <line
            x1="44"
            x2="330"
            y1={y(floor)}
            y2={y(floor)}
            strokeDasharray="3 4"
          />
          <text x="328" y={y(floor) - 6} textAnchor="end">
            {pct(floor)} floor
          </text>
        </g>
      )}
      {backends.map((backend, index) => {
        const series = rows
          .filter((r) => r.backend === backend)
          .sort((a, b) => levels.indexOf(a.level) - levels.indexOf(b.level));
        let previousKnown = false;
        const path = series
          .map((row) => {
            const value = observedValue(row.field_f1);
            if (value == null) {
              previousKnown = false;
              return "";
            }
            const command = previousKnown ? "L" : "M";
            previousKnown = true;
            return `${command}${x(row.level)},${y(value)}`;
          })
          .join(" ");
        return (
          <g key={backend} className={`sweep-series series-${index % 2}`}>
            <path
              d={path}
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeDasharray={index % 2 ? "6 4" : undefined}
            />
            {series.map((row) => {
              const value = observedValue(row.field_f1);
              if (value == null) return null;
              const measurement =
                typeof row.field_f1 === "number" ? null : row.field_f1;
              const ci = measurement?.ci;
              const description = `${label(kind)}, ${backend}, level ${row.level}: field F1 ${pct(value)}${ci?.every((v) => typeof v === "number") ? `, 95% interval ${pct(ci[0] as number)} to ${pct(ci[1] as number)}` : ""}, n=${row.n}`;
              return (
                <g key={row.level}>
                  {ci?.length === 2 &&
                    ci.every((v) => typeof v === "number") && (
                      <line
                        className="sweep-errorbar"
                        x1={x(row.level)}
                        x2={x(row.level)}
                        y1={y(ci[0] as number)}
                        y2={y(ci[1] as number)}
                      />
                    )}
                  <circle
                    className="sweep-mark"
                    cx={x(row.level)}
                    cy={y(value)}
                    r={current === row.level ? 5.5 : 3.5}
                    fill="currentColor"
                    tabIndex={0}
                    aria-label={description}
                    role={onSelect ? "button" : undefined}
                    onClick={() => onSelect?.(row.level)}
                    onKeyDown={(event) => {
                      if (
                        onSelect &&
                        (event.key === "Enter" || event.key === " ")
                      ) {
                        event.preventDefault();
                        onSelect(row.level);
                      }
                    }}
                  >
                    <title>{description}</title>
                  </circle>
                </g>
              );
            })}
          </g>
        );
      })}
    </svg>
  );
}

function SweepCard({
  kind,
  rows,
  floor,
  floors,
  unit,
  active,
  onSelect,
}: {
  kind: string;
  rows: SweepRow[];
  floor?: number;
  floors: SweepFloor[];
  unit?: string;
  active: boolean;
  onSelect: (kind: string, level: number) => void;
}) {
  const [table, setTable] = useState(false);
  const backends = [...new Set(rows.map((r) => r.backend))].sort();
  const levels = orderedLevels(rows);
  const populations = [...new Set(rows.map((r) => r.n))];
  return (
    <section
      className={`panel sweep-card ${active ? "selected-sweep" : ""}`}
      aria-label={`${label(kind)} degradation results`}
    >
      <div className="sweep-card-heading">
        <div>
          <button
            className="sweep-title"
            aria-pressed={active}
            onClick={() => onSelect(kind, levels[0] ?? 0)}
          >
            {label(kind)}
          </button>
          <p>
            {levels.length} levels ·{" "}
            {populations.length === 1
              ? `n=${populations[0]} documents per level`
              : `n=${Math.min(...populations)} to ${Math.max(...populations)} per level`}
          </p>
          {unit && <p className="sweep-unit">Unit: {unit}</p>}
        </div>
        <button
          className="button small-button"
          aria-label={`${label(kind)}: show ${table ? "chart" : "table"}`}
          onClick={() => setTable(!table)}
        >
          {table ? <BarChart3 size={13} /> : <Table2 size={13} />}
          <span>{table ? "Chart" : "Table"}</span>
        </button>
      </div>
      {table ? (
        <SummaryTable rows={rows} />
      ) : (
        <DegradationChart
          rows={rows}
          kind={kind}
          floor={floor}
          compact
          onSelect={(level) => onSelect(kind, level)}
        />
      )}
      <div className="sweep-crossings">
        {backends.map((backend, index) => {
          const known = rows
            .filter(
              (r) =>
                r.backend === backend && observedValue(r.field_f1) !== null,
            )
            .sort((a, b) => levels.indexOf(a.level) - levels.indexOf(b.level));
          const recorded = floors.find((f) => f.backend === backend);
          const crossing = recorded?.first_below;
          return (
            <div key={backend}>
              <span>
                <i
                  className={`legend-line ${index % 2 ? "dashed green-line" : ""}`}
                />
                {label(backend)}
              </span>
              <strong>
                {!recorded
                  ? "Floor not supplied"
                  : crossing != null
                    ? `Below floor at ${crossing}`
                    : known.length
                      ? "No crossing observed"
                      : "Unmeasured"}
              </strong>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function DegradationOverview({
  rows,
  floor,
  floors,
  parameters,
  active,
  onSelect,
}: {
  rows: SweepRow[];
  floor?: number;
  floors: SweepFloor[];
  parameters?: Record<string, DegradationParameter>;
  active: string;
  onSelect: (kind: string, level: number) => void;
}) {
  const kinds = [...new Set(rows.map((r) => r.kind))];
  if (!rows.length) return null;
  return (
    <section
      className="degradation-overview"
      aria-label="Degradation small multiples"
    >
      <div className="overview-heading">
        <div>
          <span className="eyebrow">SAME DOCUMENTS / SHARED F1 SCALE</span>
          <h2>Where does each extractor stop holding up?</h2>
          <p>
            Compare every recorded degradation side by side. Click a mark or
            title to inspect the saved example below.
          </p>
        </div>
        {floor != null && (
          <span className="floor-badge">Field F1 floor {pct(floor)}</span>
        )}
      </div>
      <div className="small-multiples-grid">
        {kinds.map((kind) => (
          <SweepCard
            key={kind}
            kind={kind}
            rows={rows.filter((row) => row.kind === kind)}
            floor={floor}
            floors={floors.filter((f) => f.kind === kind)}
            unit={parameters?.[kind]?.unit}
            active={active === kind}
            onSelect={onSelect}
          />
        ))}
      </div>
      <p className="data-caption">
        All charts share a 0 to 100% y-axis. Left to right means increasing
        degradation; JPEG quality and scale values decrease. Severity units
        differ across charts. Vertical bars show 95% intervals. A crossing is
        the first recorded mean below the stated floor, not an estimated failure
        point between levels. Missing observations are not drawn as zero.
      </p>
    </section>
  );
}
