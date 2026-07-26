import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Database,
  FileUp,
  ListChecks,
  Loader2,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getNetworkAnalytics } from "../../api/network.js";
import { useNetworkDataset } from "../../context/NetworkDatasetContext.jsx";

const SERVICE_LIMIT_OPTIONS = [5, 10, 20, 30, 50];
const COUNT_FORMATTER = new Intl.NumberFormat();

const GRID_COLOR = "#3b494c";
const TEXT_COLOR = "#849396";
const CYAN = "#00e5ff";
const BLUE = "#60a5fa";
const GREEN = "#4ade80";
const AMBER = "#f59e0b";
const ORANGE = "#f97316";
const RED = "#ef4444";
const SLATE = "#94a3b8";

const PREDICTION_COLORS = {
  normal: CYAN,
  attack: ORANGE,
};

const SEVERITY_COLORS = {
  critical: RED,
  high: ORANGE,
  medium: AMBER,
  low: BLUE,
};

const FAMILY_COLORS = {
  normal: CYAN,
  dos: RED,
  probe: AMBER,
  r2l: ORANGE,
  u2r: BLUE,
};

const STATUS_STYLES = {
  uploaded: "border-blue-400/40 bg-blue-500/10 text-blue-200",
  processing: "border-amber-400/40 bg-amber-500/10 text-amber-100",
  completed: "border-green-400/40 bg-green-500/10 text-green-200",
  failed: "border-red-400/40 bg-red-500/10 text-red-200",
};

function humanizeValue(value) {
  if (!value) {
    return "Unknown";
  }

  const normalizedValue = String(value).toLowerCase();
  const benchmarkAcronyms = {
    dos: "DoS",
    r2l: "R2L",
    u2r: "U2R",
  };

  if (benchmarkAcronyms[normalizedValue]) {
    return benchmarkAcronyms[normalizedValue];
  }

  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatCount(value) {
  if (value === null || value === undefined) {
    return "—";
  }

  return COUNT_FORMATTER.format(value);
}

function formatHumanPercentage(value) {
  if (value === null || value === undefined) {
    return "—";
  }

  return `${Number(value).toFixed(2)}%`;
}

function formatProbability(value) {
  if (value === null || value === undefined) {
    return "—";
  }

  return Number(value).toFixed(4);
}

function formatRateAsPercentage(value) {
  if (value === null || value === undefined) {
    return "—";
  }

  return `${(Number(value) * 100).toFixed(2)}%`;
}

function getRequestErrorMessage(error) {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        const message = item?.msg || item?.message;
        const location = Array.isArray(item?.loc)
          ? item.loc.filter((part) => part !== "body").join(".")
          : "";

        if (!message) {
          return null;
        }

        return location ? `${location}: ${message}` : message;
      })
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join("; ");
    }
  }

  if (error?.code === "ECONNABORTED") {
    return "The analytics request timed out. Retry when the backend is available.";
  }

  if (!error?.response && error?.message) {
    return `The backend could not be reached: ${error.message}`;
  }

  return "Could not load persisted network analytics.";
}

function Panel({ children, className = "" }) {
  return (
    <section
      className={[
        "rounded-md border border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20",
        className,
      ].join(" ")}
    >
      {children}
    </section>
  );
}

function PanelHeader({ action, description, icon: Icon, title }) {
  return (
    <div className="flex flex-col gap-3 border-b border-[#3b494c] bg-[#242b2d]/60 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div className="flex items-center gap-2">
          {Icon ? (
            <Icon className="h-4 w-4 text-[#00e5ff]" aria-hidden="true" />
          ) : (
            <span
              className="h-1.5 w-1.5 rounded-full bg-[#00e5ff]"
              aria-hidden="true"
            />
          )}
          <h2 className="text-sm font-semibold text-[#dce4e5]">{title}</h2>
        </div>
        {description ? (
          <p className="mt-1 max-w-3xl text-xs leading-5 text-[#849396]">
            {description}
          </p>
        ) : null}
      </div>
      {action}
    </div>
  );
}

function StatusBadge({ status }) {
  const normalizedStatus = String(status || "unknown").toLowerCase();

  return (
    <span
      className={[
        "inline-flex w-fit items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.1em]",
        STATUS_STYLES[normalizedStatus] ||
          "border-[#3b494c] bg-[#111a1b] text-[#bac9cc]",
      ].join(" ")}
    >
      {humanizeValue(normalizedStatus)}
    </span>
  );
}

function MetricCard({ helper, label, value }) {
  return (
    <div className="min-w-0 rounded border border-[#3b494c] border-l-2 border-l-[#00daf3] bg-[#111a1b]/85 p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.13em] text-[#849396]">
        {label}
      </p>
      <p className="mt-2 break-words text-2xl font-semibold tracking-tight text-[#dce4e5]">
        {value}
      </p>
      {helper ? (
        <p className="mt-1 text-xs leading-5 text-[#708083]">{helper}</p>
      ) : null}
    </div>
  );
}

function ErrorNotice({ children, onRetry }) {
  return (
    <div
      className="flex flex-col gap-3 rounded border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-100 sm:flex-row sm:items-center sm:justify-between"
      role="alert"
    >
      <div className="flex min-w-0 items-start gap-3">
        <AlertTriangle
          className="mt-0.5 h-4 w-4 shrink-0 text-red-300"
          aria-hidden="true"
        />
        <span className="leading-6">{children}</span>
      </div>
      {onRetry ? (
        <button
          className="shrink-0 rounded border border-red-300/40 px-3 py-1.5 text-xs font-semibold text-red-100 transition hover:border-red-200 focus:outline-none focus:ring-2 focus:ring-red-300/50"
          onClick={onRetry}
          type="button"
        >
          Retry analytics
        </button>
      ) : null}
    </div>
  );
}

function LoadingNotice({ children }) {
  return (
    <div
      className="flex items-center gap-3 rounded border border-[#00e5ff]/25 bg-[#00e5ff]/5 px-4 py-4 text-sm text-[#bac9cc]"
      role="status"
    >
      <Loader2
        className="h-4 w-4 shrink-0 animate-spin text-[#9cf0ff]"
        aria-hidden="true"
      />
      {children}
    </div>
  );
}

function EmptyChart({ children }) {
  return (
    <div className="flex min-h-[220px] items-center justify-center p-5 text-center text-sm text-[#849396]">
      {children}
    </div>
  );
}

function PredictionTooltip({ active, payload }) {
  if (!active || !payload?.length) {
    return null;
  }

  const item = payload[0]?.payload;

  if (!item) {
    return null;
  }

  return (
    <div className="rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm shadow-xl">
      <p className="font-semibold text-[#dce4e5]">
        Predicted {humanizeValue(item.predicted_class)}
      </p>
      <p className="mt-1 text-[#bac9cc]">
        Records: {formatCount(item.record_count)}
      </p>
      <p className="text-[#bac9cc]">
        Percentage: {formatHumanPercentage(item.percentage)}
      </p>
    </div>
  );
}

function GroupedTooltip({ active, kind, payload }) {
  if (!active || !payload?.length) {
    return null;
  }

  const item = payload[0]?.payload;

  if (!item) {
    return null;
  }

  const category = item[kind];

  return (
    <div className="max-w-xs rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm shadow-xl">
      <p className="break-all font-semibold text-[#dce4e5]">
        {humanizeValue(kind)}: {category}
      </p>
      <p className="mt-1 text-[#bac9cc]">
        Total records: {formatCount(item.total_records)}
      </p>
      <p className="text-orange-200">
        Predicted attacks: {formatCount(item.predicted_attacks)}
      </p>
      <p className="text-[#bac9cc]">
        Attack percentage: {formatHumanPercentage(item.attack_percentage)}
      </p>
      <p className="text-[#bac9cc]">
        Mean probability: {formatProbability(item.mean_attack_probability)}
      </p>
      {kind === "service" ? (
        <p className="text-[#bac9cc]">
          Maximum probability:{" "}
          {formatProbability(item.maximum_attack_probability)}
        </p>
      ) : null}
    </div>
  );
}

function HistogramTooltip({ active, payload }) {
  if (!active || !payload?.length) {
    return null;
  }

  const bucket = payload[0]?.payload;

  if (!bucket) {
    return null;
  }

  return (
    <div className="rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm shadow-xl">
      <p className="font-semibold text-[#dce4e5]">{bucket.label}</p>
      <p className="mt-1 text-[#bac9cc]">
        Records: {formatCount(bucket.record_count)}
      </p>
      <p className="text-[#bac9cc]">
        Percentage: {formatHumanPercentage(bucket.percentage)}
      </p>
      <p className="text-[#708083]">
        Bounds: {formatProbability(bucket.lower_bound_probability)} to{" "}
        {formatProbability(bucket.upper_bound_probability)}
      </p>
    </div>
  );
}

function NamedCountTooltip({ active, payload, prefix = "" }) {
  if (!active || !payload?.length) {
    return null;
  }

  const item = payload[0]?.payload;

  if (!item) {
    return null;
  }

  return (
    <div className="rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm shadow-xl">
      <p className="font-semibold text-[#dce4e5]">
        {prefix}
        {humanizeValue(item.value || item.severity)}
      </p>
      <p className="mt-1 text-[#bac9cc]">
        Records: {formatCount(item.record_count)}
      </p>
    </div>
  );
}

function DistributionTable({ items }) {
  return (
    <div className="overflow-x-auto border-t border-[#3b494c]">
      <table className="w-full min-w-[480px] text-left text-sm">
        <thead className="bg-[#111a1b]/80 text-[11px] uppercase tracking-[0.1em] text-[#849396]">
          <tr>
            <th className="px-4 py-3 font-semibold" scope="col">
              Binary prediction
            </th>
            <th className="px-4 py-3 text-right font-semibold" scope="col">
              Records
            </th>
            <th className="px-4 py-3 text-right font-semibold" scope="col">
              Percentage
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#3b494c] text-[#bac9cc]">
          {items.map((item) => (
            <tr key={item.predicted_class}>
              <th className="px-4 py-3 font-semibold text-[#dce4e5]" scope="row">
                Predicted {humanizeValue(item.predicted_class)}
              </th>
              <td className="px-4 py-3 text-right">
                {formatCount(item.record_count)}
              </td>
              <td className="px-4 py-3 text-right">
                {formatHumanPercentage(item.percentage)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GroupedAnalyticsTable({ items, kind }) {
  const isService = kind === "service";

  return (
    <div className="max-h-[520px] overflow-auto border-t border-[#3b494c]">
      <table className="w-full min-w-[800px] text-left text-sm">
        <thead className="sticky top-0 z-10 bg-[#111a1b] text-[11px] uppercase tracking-[0.1em] text-[#849396]">
          <tr>
            <th className="px-4 py-3 font-semibold" scope="col">
              {humanizeValue(kind)}
            </th>
            <th className="px-4 py-3 text-right font-semibold" scope="col">
              Total records
            </th>
            <th className="px-4 py-3 text-right font-semibold" scope="col">
              Predicted attacks
            </th>
            <th className="px-4 py-3 text-right font-semibold" scope="col">
              Attack percentage
            </th>
            <th className="px-4 py-3 text-right font-semibold" scope="col">
              Mean probability
            </th>
            {isService ? (
              <th className="px-4 py-3 text-right font-semibold" scope="col">
                Maximum probability
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody className="divide-y divide-[#3b494c] text-[#bac9cc]">
          {items.map((item) => (
            <tr key={item[kind]}>
              <th
                className="max-w-[240px] break-all px-4 py-3 font-semibold text-[#dce4e5]"
                scope="row"
              >
                {item[kind]}
              </th>
              <td className="px-4 py-3 text-right">
                {formatCount(item.total_records)}
              </td>
              <td className="px-4 py-3 text-right">
                {formatCount(item.predicted_attacks)}
              </td>
              <td className="px-4 py-3 text-right">
                {formatHumanPercentage(item.attack_percentage)}
              </td>
              <td className="px-4 py-3 text-right">
                {formatProbability(item.mean_attack_probability)}
              </td>
              {isService ? (
                <td className="px-4 py-3 text-right">
                  {formatProbability(item.maximum_attack_probability)}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PredictionDistribution({ items }) {
  return (
    <Panel>
      <PanelHeader
        icon={Activity}
        title="Binary prediction distribution"
        description="Normal and attack are the frozen detector's only prediction classes."
      />
      {items.length === 0 ? (
        <EmptyChart>No persisted prediction distribution is available.</EmptyChart>
      ) : (
        <>
          <div className="grid gap-4 p-5 lg:grid-cols-[minmax(0,1fr)_220px] lg:items-center">
            <div className="h-[300px]">
              <ResponsiveContainer height="100%" width="100%">
                <PieChart>
                  <Pie
                    data={items}
                    dataKey="record_count"
                    innerRadius={70}
                    nameKey="predicted_class"
                    outerRadius={108}
                    paddingAngle={2}
                    stroke="#192122"
                    strokeWidth={2}
                  >
                    {items.map((item) => (
                      <Cell
                        fill={
                          PREDICTION_COLORS[item.predicted_class] || SLATE
                        }
                        key={item.predicted_class}
                      />
                    ))}
                  </Pie>
                  <Tooltip content={<PredictionTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-3">
              {items.map((item) => (
                <div
                  className="rounded border border-[#3b494c] bg-[#111a1b]/80 p-3"
                  key={item.predicted_class}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 rounded-full"
                      style={{
                        backgroundColor:
                          PREDICTION_COLORS[item.predicted_class] || SLATE,
                      }}
                    />
                    <p className="text-sm font-semibold text-[#dce4e5]">
                      Predicted {humanizeValue(item.predicted_class)}
                    </p>
                  </div>
                  <p className="mt-2 text-xl font-semibold text-[#dce4e5]">
                    {formatCount(item.record_count)}
                  </p>
                  <p className="text-xs text-[#849396]">
                    {formatHumanPercentage(item.percentage)}
                  </p>
                </div>
              ))}
            </div>
          </div>
          <DistributionTable items={items} />
        </>
      )}
    </Panel>
  );
}

function ProtocolDistribution({ items }) {
  return (
    <Panel>
      <PanelHeader
        icon={BarChart3}
        title="Protocol distribution"
        description="Stored records and predicted attacks grouped by original protocol."
      />
      {items.length === 0 ? (
        <EmptyChart>No protocol analytics are available.</EmptyChart>
      ) : (
        <>
          <div className="h-[340px] p-5">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={items} margin={{ left: 4, right: 12, top: 8 }}>
                <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                <XAxis
                  dataKey="protocol"
                  stroke={TEXT_COLOR}
                  tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                />
                <YAxis
                  allowDecimals={false}
                  stroke={TEXT_COLOR}
                  tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                />
                <Tooltip
                  content={<GroupedTooltip kind="protocol" />}
                  cursor={{ fill: "#ffffff08" }}
                />
                <Bar
                  dataKey="total_records"
                  fill={CYAN}
                  name="Total records"
                  radius={[3, 3, 0, 0]}
                />
                <Bar
                  dataKey="predicted_attacks"
                  fill={ORANGE}
                  name="Predicted attacks"
                  radius={[3, 3, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-wrap gap-4 border-t border-[#3b494c] px-5 py-3 text-xs text-[#bac9cc]">
            <span className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-sm bg-[#00e5ff]" />
              Total records
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-sm bg-orange-500" />
              Predicted attacks
            </span>
          </div>
          <GroupedAnalyticsTable items={items} kind="protocol" />
        </>
      )}
    </Panel>
  );
}

function HorizontalGroupedDistribution({
  description,
  items,
  kind,
  title,
}) {
  const chartHeight = Math.max(300, items.length * 42);
  const isService = kind === "service";

  return (
    <Panel>
      <PanelHeader
        icon={BarChart3}
        title={title}
        description={description}
      />
      {items.length === 0 ? (
        <EmptyChart>No {kind} analytics are available.</EmptyChart>
      ) : (
        <>
          <div className="max-h-[620px] overflow-auto p-5">
            <div className="min-w-[680px]" style={{ height: chartHeight }}>
              <ResponsiveContainer height="100%" width="100%">
                <BarChart
                  data={items}
                  layout="vertical"
                  margin={{ bottom: 8, left: 18, right: 20, top: 8 }}
                >
                  <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                  <XAxis
                    allowDecimals={false}
                    stroke={TEXT_COLOR}
                    tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                    type="number"
                  />
                  <YAxis
                    dataKey={kind}
                    stroke={TEXT_COLOR}
                    tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                    tickFormatter={(value) => {
                      const label = String(value);
                      return label.length > 18
                        ? `${label.slice(0, 17)}…`
                        : label;
                    }}
                    type="category"
                    width={135}
                  />
                  <Tooltip
                    content={<GroupedTooltip kind={kind} />}
                    cursor={{ fill: "#ffffff08" }}
                  />
                  <Bar
                    dataKey="total_records"
                    fill={CYAN}
                    name="Total records"
                    radius={[0, 3, 3, 0]}
                  />
                  <Bar
                    dataKey="predicted_attacks"
                    fill={ORANGE}
                    name="Predicted attacks"
                    radius={[0, 3, 3, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="flex flex-wrap gap-4 border-t border-[#3b494c] px-5 py-3 text-xs text-[#bac9cc]">
            <span className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-sm bg-[#00e5ff]" />
              Total records
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-sm bg-orange-500" />
              Predicted attacks
            </span>
            {isService ? (
              <span className="text-[#708083]">
                Hover or use the table for mean and maximum probabilities.
              </span>
            ) : null}
          </div>
          <GroupedAnalyticsTable items={items} kind={kind} />
        </>
      )}
    </Panel>
  );
}

function SeverityDistribution({ items, totalIncidents }) {
  return (
    <Panel>
      <PanelHeader
        icon={AlertTriangle}
        title="Incident severity distribution"
        description="Severity is an analyst triage level derived from attack probability, not an ML attack-family prediction."
      />
      <div className="grid gap-4 p-5 lg:grid-cols-[minmax(0,1fr)_240px] lg:items-center">
        <div className="h-[300px]">
          <ResponsiveContainer height="100%" width="100%">
            <BarChart data={items} margin={{ left: 4, right: 12, top: 8 }}>
              <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
              <XAxis
                dataKey="severity"
                stroke={TEXT_COLOR}
                tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                tickFormatter={humanizeValue}
              />
              <YAxis
                allowDecimals={false}
                stroke={TEXT_COLOR}
                tick={{ fill: TEXT_COLOR, fontSize: 11 }}
              />
              <Tooltip
                content={<NamedCountTooltip prefix="Severity: " />}
                cursor={{ fill: "#ffffff08" }}
              />
              <Bar dataKey="record_count" name="Incidents" radius={[3, 3, 0, 0]}>
                {items.map((item) => (
                  <Cell
                    fill={SEVERITY_COLORS[item.severity] || SLATE}
                    key={item.severity}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="space-y-2">
          {items.map((item) => (
            <div
              className="flex items-center justify-between gap-3 rounded border border-[#3b494c] bg-[#111a1b]/80 px-3 py-2.5"
              key={item.severity}
            >
              <span className="inline-flex items-center gap-2 text-sm font-semibold text-[#dce4e5]">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{
                    backgroundColor:
                      SEVERITY_COLORS[item.severity] || SLATE,
                  }}
                />
                {humanizeValue(item.severity)}
              </span>
              <span className="text-sm text-[#bac9cc]">
                {formatCount(item.record_count)}
              </span>
            </div>
          ))}
          <div className="mt-3 rounded border border-[#00e5ff]/25 bg-[#00e5ff]/5 px-3 py-3">
            <p className="muted-label">Total persisted incidents</p>
            <p className="mt-1 text-xl font-semibold text-[#dce4e5]">
              {formatCount(totalIncidents)}
            </p>
            <p className="mt-1 text-xs text-[#849396]">
              Sum of all four returned severity counts.
            </p>
          </div>
        </div>
      </div>
    </Panel>
  );
}

function ProbabilityHistogram({ buckets, totalPredictions }) {
  const histogramTotal = buckets.reduce(
    (sum, bucket) => sum + Number(bucket.record_count || 0),
    0
  );
  const totalsMatch = histogramTotal === totalPredictions;

  return (
    <Panel>
      <PanelHeader
        icon={Activity}
        title="Attack-probability histogram"
        description="Buckets, labels, counts, and percentages are returned by the backend in fixed order; the browser does not re-bin predictions."
      />
      {buckets.length === 0 ? (
        <EmptyChart>No probability histogram is available.</EmptyChart>
      ) : (
        <>
          <div className="border-b border-[#3b494c] bg-[#00e5ff]/5 px-5 py-3 text-sm text-[#bac9cc]">
            <span className="font-semibold text-[#c3f5ff]">
              Decision threshold: 0.38.
            </span>{" "}
            Probabilities at or above 0.38 are classified as attack by the
            frozen binary detector. The returned buckets contain{" "}
            <span className="font-semibold text-[#dce4e5]">
              {formatCount(histogramTotal)}
            </span>{" "}
            records
            {totalsMatch
              ? ", matching the prediction distribution total."
              : `, which does not match the prediction distribution total of ${formatCount(
                  totalPredictions
                )}.`}
          </div>
          <div className="overflow-x-auto p-5">
            <div className="h-[360px] min-w-[820px]">
              <ResponsiveContainer height="100%" width="100%">
                <BarChart data={buckets} margin={{ left: 4, right: 12, top: 8 }}>
                  <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                  <XAxis
                    dataKey="label"
                    interval={0}
                    stroke={TEXT_COLOR}
                    tick={{ fill: TEXT_COLOR, fontSize: 10 }}
                  />
                  <YAxis
                    allowDecimals={false}
                    stroke={TEXT_COLOR}
                    tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                  />
                  <Tooltip
                    content={<HistogramTooltip />}
                    cursor={{ fill: "#ffffff08" }}
                  />
                  <Bar
                    dataKey="record_count"
                    name="Records"
                    radius={[3, 3, 0, 0]}
                  >
                    {buckets.map((bucket) => (
                      <Cell
                        fill={
                          Number(bucket.lower_bound_probability) >= 0.38
                            ? ORANGE
                            : CYAN
                        }
                        key={`${bucket.lower_bound_probability}-${bucket.upper_bound_probability}`}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="overflow-x-auto border-t border-[#3b494c]">
            <table className="w-full min-w-[660px] text-left text-sm">
              <thead className="bg-[#111a1b]/80 text-[11px] uppercase tracking-[0.1em] text-[#849396]">
                <tr>
                  <th className="px-4 py-3 font-semibold" scope="col">
                    Backend bucket
                  </th>
                  <th className="px-4 py-3 text-right font-semibold" scope="col">
                    Records
                  </th>
                  <th className="px-4 py-3 text-right font-semibold" scope="col">
                    Percentage
                  </th>
                  <th className="px-4 py-3 text-right font-semibold" scope="col">
                    Decision side
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#3b494c] text-[#bac9cc]">
                {buckets.map((bucket) => (
                  <tr
                    key={`${bucket.lower_bound_probability}-${bucket.upper_bound_probability}`}
                  >
                    <th
                      className="px-4 py-3 font-semibold text-[#dce4e5]"
                      scope="row"
                    >
                      {bucket.label}
                    </th>
                    <td className="px-4 py-3 text-right">
                      {formatCount(bucket.record_count)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {formatHumanPercentage(bucket.percentage)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {Number(bucket.lower_bound_probability) >= 0.38
                        ? "Attack side"
                        : "Normal side"}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="border-t border-[#3b494c] bg-[#111a1b]/60 text-[#dce4e5]">
                <tr>
                  <th className="px-4 py-3 font-semibold" scope="row">
                    All returned buckets
                  </th>
                  <td className="px-4 py-3 text-right font-semibold">
                    {formatCount(histogramTotal)}
                  </td>
                  <td className="px-4 py-3 text-right" colSpan={2}>
                    {totalsMatch
                      ? "Matches prediction total"
                      : `Prediction total: ${formatCount(totalPredictions)}`}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </>
      )}
    </Panel>
  );
}

function NamedCountList({ items, colors }) {
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div
          className="flex items-center justify-between gap-3 rounded border border-[#3b494c] bg-[#111a1b]/80 px-3 py-2.5"
          key={item.value}
        >
          <span className="inline-flex items-center gap-2 text-sm font-semibold text-[#dce4e5]">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: colors[item.value] || SLATE }}
            />
            {humanizeValue(item.value)}
          </span>
          <span className="text-sm text-[#bac9cc]">
            {formatCount(item.record_count)}
          </span>
        </div>
      ))}
    </div>
  );
}

function BenchmarkAnalytics({
  actualFamilies,
  benchmarkMetrics,
  correctness,
}) {
  const correctnessColors = {
    correct: GREEN,
    incorrect: RED,
  };

  return (
    <div className="space-y-5">
      <div>
        <p className="muted-label">Benchmark-only analytics</p>
        <h2 className="mt-2 text-xl font-semibold text-[#dce4e5]">
          Supplied ground-truth evaluation
        </h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-[#849396]">
          Actual families below come from supplied benchmark labels. They are
          not attack-family predictions from the binary model.
        </p>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel>
          <PanelHeader
            icon={Database}
            title="Actual family distribution"
            description="Normal, DoS, Probe, R2L, and U2R are supplied benchmark truth."
          />
          <div className="grid gap-4 p-5 md:grid-cols-[minmax(0,1fr)_210px] md:items-center">
            <div className="h-[300px]">
              <ResponsiveContainer height="100%" width="100%">
                <BarChart data={actualFamilies}>
                  <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                  <XAxis
                    dataKey="value"
                    stroke={TEXT_COLOR}
                    tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                    tickFormatter={(value) => String(value).toUpperCase()}
                  />
                  <YAxis
                    allowDecimals={false}
                    stroke={TEXT_COLOR}
                    tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                  />
                  <Tooltip
                    content={<NamedCountTooltip prefix="Actual: " />}
                    cursor={{ fill: "#ffffff08" }}
                  />
                  <Bar dataKey="record_count" radius={[3, 3, 0, 0]}>
                    {actualFamilies.map((item) => (
                      <Cell
                        fill={FAMILY_COLORS[item.value] || SLATE}
                        key={item.value}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <NamedCountList items={actualFamilies} colors={FAMILY_COLORS} />
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            icon={CheckCircle2}
            title="Prediction correctness"
            description="Correct and incorrect counts use persisted benchmark comparisons."
          />
          <div className="grid gap-4 p-5 md:grid-cols-[minmax(0,1fr)_210px] md:items-center">
            <div className="h-[300px]">
              <ResponsiveContainer height="100%" width="100%">
                <PieChart>
                  <Pie
                    data={correctness}
                    dataKey="record_count"
                    innerRadius={65}
                    nameKey="value"
                    outerRadius={105}
                    paddingAngle={2}
                    stroke="#192122"
                    strokeWidth={2}
                  >
                    {correctness.map((item) => (
                      <Cell
                        fill={correctnessColors[item.value] || SLATE}
                        key={item.value}
                      />
                    ))}
                  </Pie>
                  <Tooltip content={<NamedCountTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <NamedCountList items={correctness} colors={correctnessColors} />
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(320px,0.8fr)_minmax(0,1.2fr)]">
        <Panel>
          <PanelHeader
            icon={ListChecks}
            title="Binary confusion matrix"
            description="Rows are actual benchmark classes; columns are model predictions."
          />
          <div className="overflow-x-auto p-5">
            <div className="grid min-w-[420px] grid-cols-3 gap-2 text-center text-sm">
              <div />
              <div className="rounded bg-[#111a1b] px-3 py-2 font-semibold text-[#bac9cc]">
                Predicted normal
              </div>
              <div className="rounded bg-[#111a1b] px-3 py-2 font-semibold text-[#bac9cc]">
                Predicted attack
              </div>
              <div className="flex items-center justify-center rounded bg-[#111a1b] px-3 py-4 font-semibold text-[#bac9cc]">
                Actual normal
              </div>
              <div className="rounded border border-green-400/30 bg-green-500/10 px-3 py-4">
                <p className="muted-label">TN</p>
                <p className="mt-1 text-2xl font-semibold text-green-200">
                  {formatCount(benchmarkMetrics.true_negatives)}
                </p>
              </div>
              <div className="rounded border border-orange-400/30 bg-orange-500/10 px-3 py-4">
                <p className="muted-label">FP</p>
                <p className="mt-1 text-2xl font-semibold text-orange-200">
                  {formatCount(benchmarkMetrics.false_positives)}
                </p>
              </div>
              <div className="flex items-center justify-center rounded bg-[#111a1b] px-3 py-4 font-semibold text-[#bac9cc]">
                Actual attack
              </div>
              <div className="rounded border border-red-400/30 bg-red-500/10 px-3 py-4">
                <p className="muted-label">FN</p>
                <p className="mt-1 text-2xl font-semibold text-red-200">
                  {formatCount(benchmarkMetrics.false_negatives)}
                </p>
              </div>
              <div className="rounded border border-cyan-400/30 bg-cyan-500/10 px-3 py-4">
                <p className="muted-label">TP</p>
                <p className="mt-1 text-2xl font-semibold text-cyan-100">
                  {formatCount(benchmarkMetrics.true_positives)}
                </p>
              </div>
            </div>
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            icon={BarChart3}
            title="Benchmark metrics"
            description="Underlying values remain 0–1 and are formatted here as percentages."
          />
          <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-3">
            {[
              ["Accuracy", "accuracy"],
              ["Precision", "precision"],
              ["Recall", "recall"],
              ["F1 score", "f1"],
              ["F2 score", "f2"],
              ["False-positive rate", "false_positive_rate"],
              ["False-negative rate", "false_negative_rate"],
            ].map(([label, key]) => (
              <MetricCard
                helper="Benchmark rate"
                key={key}
                label={label}
                value={formatRateAsPercentage(benchmarkMetrics[key])}
              />
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

export default function NetworkAnalytics() {
  const {
    datasets,
    selectedDatasetId,
    selectedDataset,
    isLoadingDatasets,
    datasetsError,
    setSelectedDatasetId,
  } = useNetworkDataset();
  const [serviceLimit, setServiceLimit] = useState(10);
  const [analytics, setAnalytics] = useState(null);
  const [isLoadingAnalytics, setIsLoadingAnalytics] = useState(false);
  const [analyticsError, setAnalyticsError] = useState("");
  const isMountedRef = useRef(false);
  const requestSequenceRef = useRef(0);

  useEffect(() => {
    isMountedRef.current = true;

    return () => {
      isMountedRef.current = false;
      requestSequenceRef.current += 1;
    };
  }, []);

  const loadAnalytics = useCallback(async (datasetId, requestedServiceLimit) => {
    if (!datasetId) {
      requestSequenceRef.current += 1;
      setAnalytics(null);
      setAnalyticsError("");
      setIsLoadingAnalytics(false);
      return null;
    }

    const requestNumber = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestNumber;
    setAnalytics(null);
    setAnalyticsError("");
    setIsLoadingAnalytics(true);

    try {
      const response = await getNetworkAnalytics(datasetId, {
        serviceLimit: requestedServiceLimit,
      });

      if (
        isMountedRef.current &&
        requestSequenceRef.current === requestNumber
      ) {
        setAnalytics(response);
      }

      return response;
    } catch (error) {
      if (
        isMountedRef.current &&
        requestSequenceRef.current === requestNumber
      ) {
        setAnalyticsError(getRequestErrorMessage(error));
      }

      return null;
    } finally {
      if (
        isMountedRef.current &&
        requestSequenceRef.current === requestNumber
      ) {
        setIsLoadingAnalytics(false);
      }
    }
  }, []);

  useEffect(() => {
    setAnalytics(null);
    setAnalyticsError("");

    if (!selectedDatasetId) {
      requestSequenceRef.current += 1;
      setIsLoadingAnalytics(false);
      return undefined;
    }

    loadAnalytics(selectedDatasetId, serviceLimit);

    return () => {
      requestSequenceRef.current += 1;
    };
  }, [loadAnalytics, selectedDatasetId, serviceLimit]);

  const predictionDistribution = Array.isArray(
    analytics?.prediction_distribution
  )
    ? analytics.prediction_distribution
    : [];
  const protocolDistribution = Array.isArray(
    analytics?.protocol_distribution
  )
    ? analytics.protocol_distribution
    : [];
  const serviceDistribution = Array.isArray(analytics?.service_distribution)
    ? analytics.service_distribution
    : [];
  const flagDistribution = Array.isArray(analytics?.flag_distribution)
    ? analytics.flag_distribution
    : [];
  const probabilityHistogram = Array.isArray(
    analytics?.probability_histogram
  )
    ? analytics.probability_histogram
    : [];
  const actualFamilyDistribution = Array.isArray(
    analytics?.actual_family_distribution
  )
    ? analytics.actual_family_distribution
    : [];
  const correctnessDistribution = Array.isArray(
    analytics?.correctness_distribution
  )
    ? analytics.correctness_distribution
    : [];

  const derivedValues = useMemo(() => {
    const normal = predictionDistribution.find(
      (item) => item.predicted_class === "normal"
    );
    const attack = predictionDistribution.find(
      (item) => item.predicted_class === "attack"
    );
    const severity = analytics?.severity_distribution || {};
    const severityItems = ["critical", "high", "medium", "low"].map(
      (name) => ({
        severity: name,
        record_count: Number(severity[name] || 0),
      })
    );
    const highestSeverity =
      severityItems.find((item) => item.record_count > 0)?.severity || "none";
    const correct = correctnessDistribution.find(
      (item) => item.value === "correct"
    );
    const incorrect = correctnessDistribution.find(
      (item) => item.value === "incorrect"
    );

    return {
      normal,
      attack,
      severityItems,
      highestSeverity,
      correct,
      incorrect,
      totalPredictions: predictionDistribution.reduce(
        (sum, item) => sum + Number(item.record_count || 0),
        0
      ),
      totalIncidents: severityItems.reduce(
        (sum, item) => sum + item.record_count,
        0
      ),
      displayedServiceRecords: serviceDistribution.reduce(
        (sum, item) => sum + Number(item.total_records || 0),
        0
      ),
    };
  }, [
    analytics?.severity_distribution,
    correctnessDistribution,
    predictionDistribution,
    serviceDistribution,
  ]);

  const analysisStatus =
    analytics?.analysis_status ||
    selectedDataset?.analysis_status ||
    "uploaded";
  const isCompleted = analysisStatus === "completed";
  const hasPredictions =
    isCompleted && derivedValues.totalPredictions > 0;
  const hasBenchmarkAnalytics =
    Boolean(selectedDataset?.has_ground_truth) &&
    actualFamilyDistribution.length > 0 &&
    correctnessDistribution.length > 0 &&
    Boolean(analytics?.benchmark_metrics);

  if (!isLoadingDatasets && datasets.length === 0) {
    return (
      <section className="space-y-6">
        <div>
          <p className="muted-label">Persisted detector analytics</p>
          <h1 className="page-title mt-2">Network Analytics</h1>
          <p className="page-subtitle max-w-3xl">
            Explore stored binary prediction and incident distributions without
            rerunning the detector.
          </p>
        </div>

        {datasetsError ? <ErrorNotice>{datasetsError}</ErrorNotice> : null}

        <Panel className="p-8 text-center">
          <Database
            className="mx-auto h-10 w-10 text-[#00e5ff]"
            aria-hidden="true"
          />
          <h2 className="mt-4 text-xl font-semibold text-[#dce4e5]">
            No network datasets have been uploaded yet.
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[#849396]">
            Upload a supported NSL-KDD-compatible dataset before requesting
            persisted analytics.
          </p>
          <Link
            className="mt-5 inline-flex items-center gap-2 rounded border border-[#00e5ff]/50 bg-[#00e5ff]/10 px-4 py-2.5 text-sm font-semibold text-[#c3f5ff] transition hover:border-[#00e5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
            to="/network/upload"
          >
            <FileUp className="h-4 w-4" aria-hidden="true" />
            Upload Network Dataset
          </Link>
        </Panel>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <p className="muted-label">Persisted detector analytics</p>
          <h1 className="page-title mt-2">Network Analytics</h1>
          <p className="page-subtitle max-w-3xl">
            Explore persisted NSL-KDD binary predictions, network categories,
            incident severity, and optional benchmark truth.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            className="inline-flex items-center gap-2 rounded border border-[#3b494c] bg-[#192122] px-3 py-2 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
            to="/network"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Overview
          </Link>
          <Link
            className="inline-flex items-center gap-2 rounded border border-[#3b494c] bg-[#192122] px-3 py-2 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
            to="/network/upload"
          >
            <FileUp className="h-4 w-4" aria-hidden="true" />
            Upload
          </Link>
        </div>
      </div>

      <Panel>
        <PanelHeader
          icon={Database}
          title="Analytics controls"
          description="Choose a persisted dataset and how many highest-volume services the backend should return."
          action={
            <button
              className="inline-flex items-center justify-center gap-2 rounded border border-[#3b494c] px-3 py-2 text-xs font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!selectedDatasetId || isLoadingAnalytics}
              onClick={() =>
                loadAnalytics(selectedDatasetId, serviceLimit)
              }
              type="button"
            >
              <RefreshCw
                className={[
                  "h-4 w-4",
                  isLoadingAnalytics ? "animate-spin" : "",
                ].join(" ")}
                aria-hidden="true"
              />
              {isLoadingAnalytics ? "Refreshing…" : "Refresh analytics"}
            </button>
          }
        />
        <div className="grid gap-4 p-5 lg:grid-cols-[minmax(0,1fr)_220px]">
          <div>
            <label
              className="block text-xs font-semibold uppercase tracking-[0.12em] text-[#bac9cc]"
              htmlFor="network-analytics-dataset"
            >
              Network dataset
            </label>
            <select
              className="mt-2 w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-3 text-sm text-[#dce4e5] outline-none transition focus:border-[#00e5ff] focus:ring-2 focus:ring-[#00e5ff]/20 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={isLoadingDatasets}
              id="network-analytics-dataset"
              onChange={(event) => setSelectedDatasetId(event.target.value)}
              value={selectedDatasetId ?? ""}
            >
              <option value="" disabled>
                Select an uploaded dataset
              </option>
              {datasets.map((dataset) => (
                <option key={dataset.id} value={dataset.id}>
                  {dataset.filename} · ID {dataset.id} ·{" "}
                  {humanizeValue(dataset.analysis_status)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              className="block text-xs font-semibold uppercase tracking-[0.12em] text-[#bac9cc]"
              htmlFor="network-service-limit"
            >
              Top services displayed
            </label>
            <select
              className="mt-2 w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-3 text-sm text-[#dce4e5] outline-none transition focus:border-[#00e5ff] focus:ring-2 focus:ring-[#00e5ff]/20"
              id="network-service-limit"
              onChange={(event) => setServiceLimit(Number(event.target.value))}
              value={serviceLimit}
            >
              {SERVICE_LIMIT_OPTIONS.map((value) => (
                <option key={value} value={value}>
                  Top {value}
                </option>
              ))}
            </select>
          </div>

          <div className="min-w-0 lg:col-span-2">
            <div className="flex flex-wrap items-center gap-3 rounded border border-[#3b494c] bg-[#111a1b]/80 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p
                  className="truncate text-sm font-semibold text-[#dce4e5]"
                  title={selectedDataset?.filename}
                >
                  {selectedDataset?.filename || "No dataset selected"}
                </p>
                {selectedDatasetId ? (
                  <p className="mt-1 text-xs text-[#849396]">
                    Dataset ID {selectedDatasetId}
                  </p>
                ) : null}
              </div>
              {selectedDataset ? (
                <StatusBadge status={analysisStatus} />
              ) : null}
            </div>
            <p className="mt-2 text-xs leading-5 text-[#708083]">
              The service chart contains only the selected number of
              highest-volume services. Its displayed record total may be lower
              than the complete prediction total.
            </p>
          </div>
        </div>
      </Panel>

      {datasetsError ? <ErrorNotice>{datasetsError}</ErrorNotice> : null}

      {!selectedDatasetId ? (
        <Panel className="p-6">
          <p className="text-sm text-[#849396]">
            Select a network dataset to request persisted analytics. No
            detector analysis will start automatically.
          </p>
        </Panel>
      ) : null}

      {isLoadingAnalytics ? (
        <LoadingNotice>
          Loading persisted analytics for the selected dataset…
        </LoadingNotice>
      ) : null}

      {analyticsError ? (
        <ErrorNotice
          onRetry={() =>
            loadAnalytics(selectedDatasetId, serviceLimit)
          }
        >
          {analyticsError}
        </ErrorNotice>
      ) : null}

      {analytics && !isLoadingAnalytics && !analyticsError ? (
        <>
          {analysisStatus === "uploaded" ? (
            <Panel className="p-6">
              <div className="flex items-start gap-3">
                <Database
                  className="mt-0.5 h-5 w-5 shrink-0 text-blue-300"
                  aria-hidden="true"
                />
                <div>
                  <h2 className="font-semibold text-[#dce4e5]">
                    Dataset uploaded, analysis not started
                  </h2>
                  <p className="mt-1 text-sm leading-6 text-[#849396]">
                    The network flows are stored, but no persisted predictions
                    exist yet. Start the frozen-model analysis from Network
                    Overview before viewing charts.
                  </p>
                  <Link
                    className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-[#9cf0ff] transition hover:text-white focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
                    to="/network"
                  >
                    Open Network Overview
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </div>
              </div>
            </Panel>
          ) : null}

          {analysisStatus === "processing" ? (
            <Panel className="p-6">
              <div className="flex items-start gap-3">
                <Loader2
                  className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-amber-300"
                  aria-hidden="true"
                />
                <div>
                  <h2 className="font-semibold text-[#dce4e5]">
                    Analysis is in progress
                  </h2>
                  <p className="mt-1 text-sm leading-6 text-[#849396]">
                    Persisted results are not presented as complete yet. Use
                    Refresh analytics to read the latest backend state; this
                    page will not start or rerun analysis.
                  </p>
                </div>
              </div>
            </Panel>
          ) : null}

          {analysisStatus === "failed" ? (
            <Panel className="p-6">
              <div className="flex items-start gap-3">
                <AlertTriangle
                  className="mt-0.5 h-5 w-5 shrink-0 text-red-300"
                  aria-hidden="true"
                />
                <div>
                  <h2 className="font-semibold text-[#dce4e5]">
                    Analysis failed
                  </h2>
                  <p className="mt-1 text-sm leading-6 text-red-100">
                    {selectedDataset?.analysis_error ||
                      "The backend recorded a failed analysis without an additional safe error message."}
                  </p>
                  <Link
                    className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-[#9cf0ff] transition hover:text-white focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
                    to="/network"
                  >
                    Open Network Overview to retry
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </div>
              </div>
            </Panel>
          ) : null}

          {isCompleted && derivedValues.totalPredictions === 0 ? (
            <Panel className="p-8 text-center">
              <Activity
                className="mx-auto h-9 w-9 text-[#849396]"
                aria-hidden="true"
              />
              <h2 className="mt-3 text-lg font-semibold text-[#dce4e5]">
                Completed analysis has no persisted predictions
              </h2>
              <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[#849396]">
                The backend returned a completed lifecycle state with zero
                prediction records. Charts are withheld rather than presenting
                deceptive zero-result visualizations.
              </p>
            </Panel>
          ) : null}
        </>
      ) : null}

      {analytics && hasPredictions && !analyticsError ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            <MetricCard
              label="Predicted normal"
              value={formatCount(derivedValues.normal?.record_count)}
            />
            <MetricCard
              label="Predicted attack"
              value={formatCount(derivedValues.attack?.record_count)}
            />
            <MetricCard
              helper="Human-facing 0–100 percentage"
              label="Predicted attack share"
              value={formatHumanPercentage(
                derivedValues.attack?.percentage
              )}
            />
            <MetricCard
              helper="Sum of returned severity counts"
              label="Total incidents"
              value={formatCount(derivedValues.totalIncidents)}
            />
            <MetricCard
              helper="Highest non-zero triage band"
              label="Highest active severity"
              value={humanizeValue(derivedValues.highestSeverity)}
            />
            {hasBenchmarkAnalytics ? (
              <MetricCard
                helper={`${formatCount(
                  derivedValues.incorrect?.record_count || 0
                )} incorrect`}
                label="Correct benchmark predictions"
                value={formatCount(
                  derivedValues.correct?.record_count || 0
                )}
              />
            ) : (
              <MetricCard
                helper="Returned incident severity total"
                label="Critical incidents"
                value={formatCount(
                  analytics.severity_distribution?.critical || 0
                )}
              />
            )}
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            <PredictionDistribution items={predictionDistribution} />
            <ProtocolDistribution items={protocolDistribution} />
          </div>

          <HorizontalGroupedDistribution
            description={`The backend returned the top ${serviceLimit} highest-volume services. These rows contain ${formatCount(
              derivedValues.displayedServiceRecords
            )} records and may not cover every service in the dataset.`}
            items={serviceDistribution}
            kind="service"
            title={`Top ${serviceLimit} service distribution`}
          />

          <HorizontalGroupedDistribution
            description="Stored records and predicted attacks grouped by original NSL-KDD connection flag codes."
            items={flagDistribution}
            kind="flag"
            title="Connection-flag distribution"
          />

          <div className="grid gap-5 xl:grid-cols-2">
            <SeverityDistribution
              items={derivedValues.severityItems}
              totalIncidents={derivedValues.totalIncidents}
            />
            <ProbabilityHistogram
              buckets={probabilityHistogram}
              totalPredictions={derivedValues.totalPredictions}
            />
          </div>

          {hasBenchmarkAnalytics ? (
            <BenchmarkAnalytics
              actualFamilies={actualFamilyDistribution}
              benchmarkMetrics={analytics.benchmark_metrics}
              correctness={correctnessDistribution}
            />
          ) : selectedDataset?.has_ground_truth ? (
            <Panel className="p-5">
              <p className="text-sm text-[#849396]">
                This labelled dataset does not currently have complete
                persisted benchmark analytics to display.
              </p>
            </Panel>
          ) : (
            <Panel className="p-5">
              <p className="text-sm text-[#849396]">
                Ground-truth labels were not supplied with this inference-only
                dataset, so benchmark families, correctness, confusion counts,
                and evaluation metrics are omitted.
              </p>
            </Panel>
          )}

          <Panel>
            <PanelHeader
              icon={ArrowRight}
              title="Continue in Network IDS"
              description="Navigate to persisted results and analyst workflow without rerunning inference."
            />
            <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-4">
              {[
                {
                  description: "Review lifecycle, model, and headline KPIs.",
                  icon: ShieldCheck,
                  label: "Overview",
                  to: "/network",
                },
                {
                  description: "Open the complete persisted incident queue.",
                  icon: AlertTriangle,
                  label: "Incidents",
                  to: "/network/incidents",
                },
                {
                  description: "Continue analyst incident triage.",
                  icon: ListChecks,
                  label: "Workflow",
                  to: "/network/workflow",
                },
                {
                  description: "Add another supported network dataset.",
                  icon: FileUp,
                  label: "Upload",
                  to: "/network/upload",
                },
              ].map((item) => {
                const Icon = item.icon;

                return (
                  <Link
                    className="group rounded border border-[#3b494c] bg-[#111a1b]/80 p-4 transition hover:border-[#00daf3] focus:outline-none focus:ring-2 focus:ring-[#00e5ff]/60"
                    key={item.to}
                    to={item.to}
                  >
                    <div className="flex items-center justify-between">
                      <Icon
                        className="h-5 w-5 text-[#9cf0ff]"
                        aria-hidden="true"
                      />
                      <ArrowRight
                        className="h-4 w-4 text-[#708083] transition group-hover:translate-x-0.5 group-hover:text-[#9cf0ff]"
                        aria-hidden="true"
                      />
                    </div>
                    <p className="mt-3 text-sm font-semibold text-[#dce4e5]">
                      {item.label}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-[#849396]">
                      {item.description}
                    </p>
                  </Link>
                );
              })}
            </div>
          </Panel>
        </>
      ) : null}
    </section>
  );
}
