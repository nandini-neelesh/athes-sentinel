import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  getErrorRateByEndpoint,
  getHourlyTraffic,
  getSlowestEndpoints,
  getStatusCodeDistribution,
  getTopEndpoints,
  getTopIps,
} from "../api/analytics.js";
import FileSelector from "../components/FileSelector.jsx";
import { useFileContext } from "../context/FileContext.jsx";

const GRID_COLOR = "#3b494c";
const TEXT_COLOR = "#849396";
const CYAN = "#00e5ff";
const BLUE = "#60a5fa";
const AMBER = "#f59e0b";
const ORANGE = "#f97316";
const RED = "#ef4444";

const EMPTY_ANALYTICS = {
  statusCodes: [],
  topIps: [],
  hourlyTraffic: [],
  topEndpoints: [],
  slowestEndpoints: [],
  errorRates: [],
};

function getErrorMessage(error) {
  const detail = error.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (detail) {
    return JSON.stringify(detail);
  }

  return "Could not load analytics data. Check that the backend is running.";
}

function formatPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function formatMilliseconds(value) {
  return `${Number(value || 0).toFixed(2)} ms`;
}

function getStatusCodeColor(statusCode) {
  const code = Number(statusCode);

  if (code >= 500) {
    return RED;
  }

  if (code >= 400) {
    return ORANGE;
  }

  if (code >= 300) {
    return BLUE;
  }

  return CYAN;
}

function getMaxValue(items, key) {
  return Math.max(...items.map((item) => Number(item[key] || 0)), 0);
}

function Panel({ children, className = "", isEmpty, isLoading, subtitle, title }) {
  return (
    <section
      className={[
        "rounded-md border border-[#3b494c] bg-[#192122]/90 shadow-lg shadow-black/20",
        className,
      ].join(" ")}
    >
      <div className="border-b border-[#3b494c] bg-[#242b2d]/60 px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-[#00e5ff]" />
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#dce4e5]">
            {title}
          </h2>
        </div>
        {subtitle ? <p className="mt-1 text-xs text-[#849396]">{subtitle}</p> : null}
      </div>

      {isLoading ? (
        <div className="flex min-h-[260px] items-center justify-center text-sm text-[#849396]">
          Loading analytics data...
        </div>
      ) : isEmpty ? (
        <div className="flex min-h-[260px] items-center justify-center text-sm text-[#849396]">
          No data available for this file.
        </div>
      ) : (
        children
      )}
    </section>
  );
}

function DarkTooltip({ active, label, payload }) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm shadow-xl">
      {label ? <p className="mb-1 font-semibold text-[#dce4e5]">{label}</p> : null}
      {payload.map((item) => (
        <p key={item.dataKey || item.name} style={{ color: item.color || CYAN }}>
          {item.name || item.dataKey}: {item.value}
        </p>
      ))}
    </div>
  );
}

function ErrorRateTooltip({ active, label, payload }) {
  if (!active || !payload?.length) {
    return null;
  }

  const item = payload[0];

  return (
    <div className="rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm shadow-xl">
      <p className="mb-1 font-semibold text-[#dce4e5]">{label}</p>
      <p className="text-red-300">Error rate: {formatPercent(item.value)}</p>
      <p className="text-[#849396]">
        Errors: {item.payload.error_count} / {item.payload.total_count}
      </p>
    </div>
  );
}

function RankedList({ accentColor = CYAN, items, labelKey, valueFormatter, valueKey }) {
  const maxValue = getMaxValue(items, valueKey);

  return (
    <div className="space-y-3 p-5">
      {items.map((item, index) => {
        const value = Number(item[valueKey] || 0);
        const width = maxValue > 0 ? `${Math.max((value / maxValue) * 100, 4)}%` : "4%";

        return (
          <div key={`${item[labelKey]}-${index}`} className="space-y-1.5">
            <div className="flex items-end justify-between gap-3 text-sm">
              <span className="min-w-0 truncate font-semibold text-[#dce4e5]">
                {item[labelKey] || "Unknown"}
              </span>
              <span className="shrink-0 text-xs font-semibold text-[#9cf0ff]">
                {valueFormatter(value, item)}
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[#0d1516]">
              <div
                className="h-full rounded-full"
                style={{ backgroundColor: accentColor, width }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function EndpointBars({ items }) {
  const maxValue = getMaxValue(items, "request_count");

  return (
    <div className="grid min-h-[260px] grid-cols-2 gap-3 p-5 sm:grid-cols-3 lg:grid-cols-5">
      {items.map((item, index) => {
        const value = Number(item.request_count || 0);
        const height = maxValue > 0 ? `${Math.max((value / maxValue) * 100, 8)}%` : "8%";

        return (
          <div
            className="flex min-h-[220px] flex-col justify-end gap-3"
            key={`${item.endpoint}-${index}`}
          >
            <div className="relative flex flex-1 items-end rounded border border-[#3b494c] bg-[#0d1516]/70">
              <div
                className="w-full rounded-t bg-[#00e5ff]/30 border-t-2 border-[#00e5ff]"
                style={{ height }}
              />
              <span className="absolute left-1/2 top-3 -translate-x-1/2 text-xs font-semibold text-[#dce4e5]">
                {value}
              </span>
            </div>
            <p className="truncate text-center text-xs font-semibold text-[#849396]">
              {item.endpoint || "Unknown"}
            </p>
          </div>
        );
      })}
    </div>
  );
}

function Header() {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,520px)] xl:items-end">
      <div>
        <p className="muted-label">Traffic intelligence</p>
        <h1 className="page-title mt-2">Log Analytics</h1>
        <p className="page-subtitle max-w-3xl">
          Explore traffic patterns, endpoint behavior, response performance, and
          suspicious activity.
        </p>
      </div>

      <FileSelector />
    </div>
  );
}

export default function Analytics() {
  const { selectedFileId } = useFileContext();
  const [analyticsData, setAnalyticsData] = useState(EMPTY_ANALYTICS);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!selectedFileId) {
      setAnalyticsData(EMPTY_ANALYTICS);
      setError("");
      return;
    }

    let shouldIgnoreResult = false;

    async function loadAnalytics() {
      setIsLoading(true);
      setError("");

      try {
        const [
          statusCodes,
          topIps,
          hourlyTraffic,
          topEndpoints,
          slowestEndpoints,
          errorRates,
        ] = await Promise.all([
          getStatusCodeDistribution(selectedFileId),
          getTopIps(selectedFileId),
          getHourlyTraffic(selectedFileId),
          getTopEndpoints(selectedFileId),
          getSlowestEndpoints(selectedFileId),
          getErrorRateByEndpoint(selectedFileId),
        ]);

        if (!shouldIgnoreResult) {
          setAnalyticsData({
            statusCodes,
            topIps,
            hourlyTraffic,
            topEndpoints,
            slowestEndpoints,
            errorRates,
          });
        }
      } catch (requestError) {
        if (!shouldIgnoreResult) {
          setError(getErrorMessage(requestError));
          setAnalyticsData(EMPTY_ANALYTICS);
        }
      } finally {
        if (!shouldIgnoreResult) {
          setIsLoading(false);
        }
      }
    }

    loadAnalytics();

    return () => {
      shouldIgnoreResult = true;
    };
  }, [selectedFileId]);

  const legendPayload = useMemo(
    () =>
      analyticsData.statusCodes.map((item) => ({
        color: getStatusCodeColor(item.status_code),
        id: item.status_code,
        type: "circle",
        value: String(item.status_code),
      })),
    [analyticsData.statusCodes]
  );

  return (
    <section className="space-y-5">
      <Header />

      {!selectedFileId ? (
        <div className="rounded border border-[#3b494c] bg-[#192122]/90 px-4 py-3 text-sm text-[#bac9cc]">
          Choose an uploaded file to load traffic and endpoint analytics.
        </div>
      ) : null}

      {error ? (
        <div className="rounded border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      {selectedFileId && !error ? (
        <div className="grid gap-5 xl:grid-cols-12">
          <Panel
            className="xl:col-span-8"
            isEmpty={analyticsData.hourlyTraffic.length === 0}
            isLoading={isLoading}
            subtitle="Hourly request volume from stored raw logs."
            title="Traffic Volume Over Time"
          >
            <div className="h-[360px] p-5">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={analyticsData.hourlyTraffic}>
                  <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                  <XAxis
                    dataKey="hour"
                    stroke={TEXT_COLOR}
                    tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                    tickFormatter={(value) => String(value).split(" ")[1] || value}
                  />
                  <YAxis stroke={TEXT_COLOR} tick={{ fill: TEXT_COLOR, fontSize: 11 }} />
                  <Tooltip content={<DarkTooltip />} />
                  <Line
                    dataKey="request_count"
                    dot={{ fill: CYAN, r: 3 }}
                    name="Requests"
                    stroke={CYAN}
                    strokeWidth={2}
                    type="monotone"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <Panel
            className="xl:col-span-4"
            isEmpty={analyticsData.statusCodes.length === 0}
            isLoading={isLoading}
            subtitle="Response codes grouped by count."
            title="Status Code Distribution"
          >
            <div className="h-[360px] p-5">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={analyticsData.statusCodes}
                    dataKey="count"
                    innerRadius={68}
                    nameKey="status_code"
                    outerRadius={108}
                    paddingAngle={3}
                  >
                    {analyticsData.statusCodes.map((entry) => (
                      <Cell
                        fill={getStatusCodeColor(entry.status_code)}
                        key={entry.status_code}
                      />
                    ))}
                  </Pie>
                  <Tooltip content={<DarkTooltip />} />
                  <Legend
                    payload={legendPayload}
                    wrapperStyle={{ color: "#bac9cc", fontSize: 12 }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <Panel
            className="xl:col-span-4"
            isEmpty={analyticsData.topIps.length === 0}
            isLoading={isLoading}
            subtitle="Ranked by request count."
            title="Top Source IPs"
          >
            <RankedList
              accentColor={CYAN}
              items={analyticsData.topIps}
              labelKey="ip_address"
              valueFormatter={(value) => `${value} requests`}
              valueKey="request_count"
            />
          </Panel>

          <Panel
            className="xl:col-span-8"
            isEmpty={analyticsData.topEndpoints.length === 0}
            isLoading={isLoading}
            subtitle="Most requested application paths."
            title="Most Accessed Endpoints"
          >
            <EndpointBars items={analyticsData.topEndpoints} />
          </Panel>

          <Panel
            className="xl:col-span-6"
            isEmpty={analyticsData.slowestEndpoints.length === 0}
            isLoading={isLoading}
            subtitle="Average response time by endpoint."
            title="Slowest Endpoints"
          >
            <RankedList
              accentColor={AMBER}
              items={analyticsData.slowestEndpoints}
              labelKey="endpoint"
              valueFormatter={(value, item) =>
                `${formatMilliseconds(value)} avg / ${formatMilliseconds(
                  item.max_response_time_ms
                )} max`
              }
              valueKey="avg_response_time_ms"
            />
          </Panel>

          <Panel
            className="xl:col-span-6"
            isEmpty={analyticsData.errorRates.length === 0}
            isLoading={isLoading}
            subtitle="Errors divided by total requests per endpoint."
            title="Error Rate by Endpoint"
          >
            <div className="h-[300px] p-5">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={analyticsData.errorRates}
                  layout="vertical"
                  margin={{ left: 24 }}
                >
                  <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                  <XAxis
                    type="number"
                    stroke={TEXT_COLOR}
                    tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                    tickFormatter={formatPercent}
                  />
                  <YAxis
                    dataKey="endpoint"
                    type="category"
                    stroke={TEXT_COLOR}
                    tick={{ fill: TEXT_COLOR, fontSize: 11 }}
                    width={120}
                  />
                  <Tooltip content={<ErrorRateTooltip />} />
                  <Bar
                    dataKey="error_rate"
                    fill={RED}
                    name="Error rate"
                    radius={[0, 4, 4, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Panel>
        </div>
      ) : null}
    </section>
  );
}
